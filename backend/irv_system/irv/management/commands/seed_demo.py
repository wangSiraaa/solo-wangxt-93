"""
灌入两场匿名合成演示选举（全部选票为合成数据，不接真实选举）：

1) sf-union-2026（社团联合会单席位，172 张合成票）
   - 第一轮无人过半（最高 42，门槛 70）
   - 第一轮 D/E/F 三方 12 平票 -> 按代号字典序决胜淘汰 D；
     第二轮 E/F 平票（首轮得票相同）-> 再按代号淘汰 E
   - 连续多轮转移：D->C、E->A、F->C、B->C，可逐票追踪
   - 终轮穷尽票 44 张（28 张首轮即穷尽 + 16 张 B-only 在 B 出局后中途穷尽）
   - 含重复排名、overvote、跳号、无效候选条目被忽略、空白等判定
2) tie-final-demo（100 张）
   - 最终两人 42:42 平票均未过半，首轮得票相同 -> 代号字典序决胜，Q 当选
"""
from django.core.management.base import BaseCommand

from irv.models import Election, Publication
from irv.serializers import rules_snapshot
from irv.services import create_election, publish, run_tally

# (排名 dict, 张数)；展开时按顺序赋合成代号 B001..
MAIN_BLOCKS = [
    # —— 正式候选票（A 林岚 / B 陈岳 / C 周禾 / D 高远 / E 唐宁 / F 许安）——
    ({"1": "A", "2": "F", "3": "C", "4": "B"}, 18),
    ({"1": "A", "2": "C", "3": "F"}, 22),
    ({"1": "B", "2": "C", "3": "A"}, 24),    # B 中途出局后转移给 C
    ({"1": "C", "3": "F", "5": "A"}, 20),    # 跳号 2、4：合法，按 1,3,5 读
    ({"1": "D", "2": "C", "3": "F"}, 12),    # F 出局后无后续候选 -> 末端穷尽
    ({"1": "E", "2": "A"}, 12),
    ({"1": "F", "2": "C", "3": "A"}, 12),
    ({"1": "B"}, 16),                         # B 出局后无后续候选 -> 中途穷尽

    # —— 第一轮即穷尽：有效名次全部指向无效候选（条目被忽略后无合法排名）——
    ({"1": "Z", "2": "Y"}, 26),
    ({"1": "9"}, 2),

    # —— 无效票 / 空白票（不计入任何候选人）——
    ({"1": "A", "2": "A"}, 3),               # 同一候选重复出现 -> invalid
    ({"1": ["D", "A"]}, 2),                  # 同一位次两候选（overvote）-> invalid
    ({}, 1),                                  # 空白票 -> blank

    # —— 带"瑕疵"但仍有效的票：无效候选条目被忽略，其余排名照常 ——
    ({"1": "Z", "2": "A", "3": "F", "4": "C"}, 2),
]
# 引擎核对（172 张）：
# R1 A=42 B=40 C=20 D=12 E=12 F=12 valid=138 exh=28 blank=1 inv=5 门槛70
#    D/E/F 三方 12 平票，首轮决胜按代号字典序淘汰 D
# R2 D 的 12 票转 C：C=32；E/F 仍 12 平票（首轮相同）-> 按代号淘汰 E
# R3 E 的 12 票转 A：A=54；F=12 最低出局，其 12 票转 C
# R4 A=54 B=40 C=44；B 最低出局：24 票转 C、16 张 B-only 穷尽
# R5 A=54 C=68 valid=122 exh=44 门槛62 -> C 过半胜出（穷尽票占 25.6%）

MAIN_CANDIDATES = [
    {"code": "A", "name": "林岚", "sort_order": 1},
    {"code": "B", "name": "陈岳", "sort_order": 2},
    {"code": "C", "name": "周禾", "sort_order": 3},
    {"code": "D", "name": "高远", "sort_order": 4},
    {"code": "E", "name": "唐宁", "sort_order": 5},
    {"code": "F", "name": "许安", "sort_order": 6},
]

# 小型最终平票演示（100 张）：
# 第一轮 P=42/Q=42/R=16，门槛 51 无人过半，淘汰 R；
# R 的 16 张选票只选了 R，无后续候选 -> 全部穷尽；
# 第二轮 P=42/Q=42（门槛 43），最终两人平票且均未过半，
# 启用预先固定决胜：首轮得票相同（42=42）-> 代号字典序靠后者 Q 当选。
# （二轮平票蕴含首轮 P、Q 相等，故本例决胜走到代号规则。）
TIE_BLOCKS = [
    ({"1": "P", "2": "Q"}, 30),
    ({"1": "P"}, 12),
    ({"1": "Q", "2": "P"}, 34),
    ({"1": "Q"}, 8),
    ({"1": "R"}, 16),  # 只选 R：R 出局后无后续候选 -> 穷尽
]

TIE_CANDIDATES = [
    {"code": "P", "name": "演示候选-潘", "sort_order": 1},
    {"code": "Q", "name": "演示候选-齐", "sort_order": 2},
    {"code": "R", "name": "演示候选-任", "sort_order": 3},
]


def expand(blocks):
    ballots, n = [], 0
    for ranking, weight in blocks:
        for _ in range(weight):
            n += 1
            ballots.append({"code": f"B{n:03d}", "ranking": {**ranking}})
    return ballots


class Command(BaseCommand):
    help = "创建/重建两场匿名合成演示选举，计票并发布。"

    def add_arguments(self, parser):
        parser.add_argument("--no-publish", action="store_true",
                            help="两场都保持草稿态（界面均可发布）")
        parser.add_argument("--main-draft", action="store_true",
                            help="主演示保留草稿（可点发布），决胜局正常发布锁定")

    def handle(self, *args, **opts):
        existing = Election.objects.filter(
            slug__in=["sf-union-2026", "tie-final-demo"])
        # Publication 以 PROTECT 保护发布结果；这是显式的"重建演示"命令，
        # 先删发布记录再删选举（生产环境下没有任何代码路径会静默删除发布数据）。
        Publication.objects.filter(election__in=existing).delete()
        existing.delete()

        # 第一场：创建 -> 计票
        main = create_election({
            "slug": "sf-union-2026",
            "name": "2026 社团联合会单席位排序选择投票（合成数据演示）",
            "candidates": MAIN_CANDIDATES,
            "ballots": expand(MAIN_BLOCKS),
        })
        main.rules_snapshot = rules_snapshot()
        main.save(update_fields=["rules_snapshot"])
        info = run_tally(main)
        self.stdout.write(self.style.SUCCESS(
            f"[sf-union-2026] 选票 {main.ballots.count()} 张，"
            f"共 {info['rounds']} 轮，胜者代号 {info['winner']}，"
            f"输入指纹 {info['digest'][:16]}…"))

        # 第二场：小型最终平票决胜局
        tie = create_election({
            "slug": "tie-final-demo",
            "name": "决胜规则演示：最终两人平票（合成数据）",
            "candidates": TIE_CANDIDATES,
            "ballots": expand(TIE_BLOCKS),
        })
        tie.rules_snapshot = rules_snapshot()
        tie.save(update_fields=["rules_snapshot"])
        info2 = run_tally(tie)
        self.stdout.write(self.style.SUCCESS(
            f"[tie-final-demo] 选票 {tie.ballots.count()} 张，"
            f"共 {info2['rounds']} 轮，最终平票决胜胜者 {info2['winner']}"))

        if opts["no_publish"]:
            self.stdout.write(self.style.WARNING(
                "--no-publish：两场选举均保持草稿态，可在界面点击发布以演示锁定"))
            return

        if opts["main_draft"]:
            publish(tie)
            self.stdout.write(self.style.WARNING(
                "tie-final-demo 已发布锁定；sf-union-2026 保持草稿态供界面发布演示"))
            return

        publish(main)
        publish(tie)
        self.stdout.write(self.style.SUCCESS("两场选举均已发布，输入摘要与轮次锁定"))
