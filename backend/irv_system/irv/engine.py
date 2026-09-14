"""
IRV (Instant-Runoff Voting / 单席位排序选择投票) 纯逻辑引擎。

本模块不依赖 Django ORM，便于独立单元测试。规则以 ``RULES_SNAPSHOT`` 为固定快照
（版本 2026.irv-sfu.v1），候选人同票淘汰使用预先固定、可复现的决胜规则，
绝不使用随机数。

规则要点
--------
1. 每张选票为一个“名次 -> 候选人代号”的映射（每一名次至多一个代号）。
2. 去脏（normalize）顺序固定：
   a. 名次必须是 1..max_ranks 的整数，否则忽略该条目；
   b. 代号不在候选人名单内 -> 仅忽略该条目（无效候选不影响其他合法排名）；
   c. 同一代号重复出现 -> 整张票判 invalid（重复排名，整张作废）；
   d. 同一名次写入多个候选（overvote）-> 整张票判 invalid；
   e. 允许名次跳号（如 {1,3}），按名次升序读取，空缺按不存在处理；
   f. 去脏后无合法条目：原始也为空 -> blank；否则 -> exhausted（第一轮即穷尽）。
3. 有效票按当前最高且未被淘汰的候选计票；榜上候选全部出局后转为 exhausted。
4. 过半分母明确：分母 = 仍有效票数（不含 exhausted/blank/invalid），
   门槛 = floor(valid/2) + 1（严格过半）。
5. 同票淘汰决胜（预先固定、确定性、可复现，禁止随机）：
   第一轮僵局按候选人代号字典序（小者先淘汰）；其后轮次先比“第一轮得票”
   （少者淘汰），再比代号字典序（小者淘汰）。最低票并列者一并淘汰。
6. 终止：严格过半即胜；只剩 1 人时即使未过半也由其当选（穷尽票可导致无人过半）；
   最终 2 人平票均未过半时，按“首轮得票高者胜、相同则代号字典序靠后者胜”
   选出胜者。
7. 每轮校验票数守恒：
   valid(仍有效票) + exhausted(穷尽票) + blank(空白票) + invalid(无效票)
   == ballots_cast（投票总数，全程不变）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

RULES_VERSION = "2026.irv-sfu.v1"
MAX_RANKS = 5

RULES_SNAPSHOT: dict[str, Any] = {
    "version": RULES_VERSION,
    "seat_count": 1,
    "max_ranks": MAX_RANKS,
    "allow_skip_ranks": True,
    "duplicate_rank_handling": "同一候选人代号在一张票中重复出现，整张选票判定为 invalid（作废）",
    "overvote_handling": "同一位次写入多个候选人（overvote），整张选票判定为 invalid（作废）",
    "invalid_candidate_handling": "名次指向不在候选人名单中的代号时仅忽略该条目，其余合法排名照常生效",
    "skipped_rank_handling": "允许名次跳号，按名次升序读取；中间空缺按不存在处理，不判废",
    "exhausted_definition": "选票合法但榜上所有候选均已被淘汰（或去脏后仅剩无效条目）时计为 exhausted（穷尽票）",
    "blank_definition": "选票未填写任何名次计为 blank（空白票），不投给任何人",
    "invalid_definition": "重复排名或同一位次多候选使整张票作废，计为 invalid（无效票）",
    "valid_denominator": "过半分母 = 仍有效票数（未穷尽、非 blank、非 invalid）；门槛 = floor(valid/2) + 1",
    "tie_break": "确定性决胜，禁止随机：第一轮僵局按代号字典序（小者先淘汰）；其后先比第一轮得票（少者先淘汰），再按代号字典序（小者先淘汰）；最低票并列时每轮只淘汰决胜排序第一名，其余进入下一轮；最终两人平票则首轮得票高者胜，相同则代号靠后者胜",
    "termination": "严格过半即胜；仅剩一名候选时即便未过半也胜出；最终两人平票按决胜规则定胜负",
    "conservation": "每轮校验 valid + exhausted + blank + invalid == ballots_cast",
}


class BallotConservationError(RuntimeError):
    """票数守恒校验失败：发生即说明引擎存在缺陷。"""


@dataclass(frozen=True)
class NormalizedBallot:
    code: str
    ranking: tuple[str, ...]               # 名次升序的合法代号
    status: str                            # valid | exhausted | blank | invalid
    reason: str
    dropped: tuple[dict[str, Any], ...] = ()


@dataclass
class RoundResult:
    round_no: int
    counts: dict[str, int]
    continuing: list[str]
    valid: int
    exhausted: int
    blank: int
    invalid: int
    ballots_cast: int
    majority_threshold: int | None
    winner: str | None
    eliminated: list[str]
    elimination_note: str
    tie_break_used: bool
    flows: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TallyResult:
    rounds: list[RoundResult]
    winner: str | None
    ballots_cast: int
    chains: dict[str, list[dict[str, Any]]]
    normalized: list[dict[str, Any]]
    candidate_codes: list[str]


EXHAUSTED = "EXHAUSTED"
BLANK = "BLANK"
INVALID = "INVALID"

_REASON = {
    "overvote": "同一位次填写了多个候选人（overvote），整张选票作废",
    "duplicate": "同一候选人重复出现在多个名次，整张选票作废",
    "invalid_only": "所有已填名次都指向不在名单中的候选人，选票自第一轮即穷尽",
    "empty": "空白选票，不计入任何候选人",
}


def normalize_ballot(raw: dict[str, Any], valid_codes: set[str],
                     max_ranks: int = MAX_RANKS) -> NormalizedBallot:
    """按固定顺序对单张原始选票去脏。

    ranking 原始格式：{名次: 代号}，其中代号可为字符串（正常）或字符串列表
    （同一位次并列多个候选 = overvote，整张判废）。
    例：{"1": "A", "2": "X"} 或 {"1": ["D", "A"]}。
    """
    code = str(raw.get("code", ""))
    ranking_raw = raw.get("ranking") or {}
    dropped: list[dict[str, Any]] = []
    entries: list[tuple[int, str]] = []

    for rank_key, cand in ranking_raw.items():
        try:
            rank = int(rank_key)
        except (TypeError, ValueError):
            dropped.append({"rank": str(rank_key), "candidate": cand,
                            "reason": "名次不是整数，忽略该条目"})
            continue
        if not (1 <= rank <= max_ranks):
            dropped.append({"rank": rank, "candidate": cand,
                            "reason": f"名次超出 1..{max_ranks}，忽略该条目"})
            continue
        # 同一位次给了多个候选（overvote）：整张票作废，不做静默选取
        if isinstance(cand, (list, tuple)):
            return NormalizedBallot(code, (), "invalid",
                                    _REASON["overvote"], tuple(dropped))
        cand_str = str(cand).strip()
        if cand_str not in valid_codes:
            dropped.append({"rank": rank, "candidate": cand_str,
                            "reason": "候选人不在名单中，忽略该条目"})
            continue
        entries.append((rank, cand_str))

    if not entries:
        if not ranking_raw:
            return NormalizedBallot(code, (), "blank", _REASON["empty"], tuple(dropped))
        return NormalizedBallot(code, (), "exhausted", _REASON["invalid_only"], tuple(dropped))

    seen_ranks: set[int] = set()
    for rank, _c in entries:
        if rank in seen_ranks:
            return NormalizedBallot(code, tuple(c for _, c in sorted(entries)),
                                    "invalid", _REASON["overvote"], tuple(dropped))
        seen_ranks.add(rank)

    entries.sort(key=lambda e: e[0])
    ordered = tuple(c for _, c in entries)
    if len(set(ordered)) != len(ordered):
        return NormalizedBallot(code, ordered, "invalid",
                                _REASON["duplicate"], tuple(dropped))

    return NormalizedBallot(code, ordered, "valid", "有效", tuple(dropped))


def _destination(nb: NormalizedBallot, eliminated: set[str]) -> str | None:
    for cand in nb.ranking:
        if cand not in eliminated:
            return cand
    return None


def _eliminate_losers(counts: dict[str, int], continuing: list[str],
                      round_no: int, first_round_counts: dict[str, int]
                      ) -> tuple[list[str], bool, str]:
    """返回 (本轮淘汰代号列表（恰好 1 人）, 是否触发并列决胜, 说明)。

    最低票并列时，一轮只淘汰决胜排序后的第一名；其余并列者留到下一轮，
    其选票在新的格局下重新比较——这样每一轮的转移都可单独解释。
    """
    tally = {c: counts.get(c, 0) for c in continuing}
    minimum = min(tally.values())
    lowest = sorted(c for c, v in tally.items() if v == minimum)
    if len(lowest) == 1:
        return lowest, False, f"最低得票 {minimum} 票唯一，淘汰 {lowest[0]}"

    if round_no == 1:
        ordered = sorted(lowest)
        first = ordered[0]
        note = (f"最低得票 {minimum} 票出现 {len(lowest)} 人并列（{'、'.join(lowest)}）；"
                f"第一轮决胜按代号字典序（小者先淘汰），本轮淘汰 {first}，"
                f"其余并列者进入下一轮重新比较")
    else:
        ordered = sorted(lowest, key=lambda c: (first_round_counts.get(c, 0), c))
        first = ordered[0]
        detail = "，".join(f"{c}(首轮 {first_round_counts.get(c, 0)} 票)" for c in ordered)
        note = (f"最低得票 {minimum} 票出现 {len(lowest)} 人并列（{'、'.join(lowest)}）；"
                f"按决胜规则 [第一轮得票少者先淘汰 → 代号字典序小者先淘汰] 排序："
                f"{detail}，本轮淘汰 {first}，其余并列者进入下一轮重新比较")
    return [first], True, note


def _choose_final_winner(a: str, b: str,
                         first_round_counts: dict[str, int]) -> tuple[str, str]:
    """最终两人平票均未过半时的固定决胜：首轮得票高者胜，相同则代号靠后者胜。"""
    key_a = (first_round_counts.get(a, 0), a)
    key_b = (first_round_counts.get(b, 0), b)
    winner, loser = (a, b) if key_a > key_b else (b, a)
    note = (
        f"仅剩 {a}、{b} 两人且平票、均未过半；启用预先固定决胜："
        f"第一轮得票 {a}={first_round_counts.get(a, 0)}、{b}={first_round_counts.get(b, 0)}；"
        f"首轮得票高者胜（相同则代号字典序靠后者胜）→ {winner} 当选，{loser} 出局")
    return winner, note


def tally(candidates: list[dict[str, str]],
          raw_ballots: list[dict[str, Any]],
          max_ranks: int = MAX_RANKS) -> TallyResult:
    """执行完整 IRV 逐轮计票。"""
    candidate_codes = [c["code"] for c in candidates]
    valid_codes = set(candidate_codes)

    normalized = [normalize_ballot(b, valid_codes, max_ranks) for b in raw_ballots]
    by_code = {n.code: n for n in normalized}
    ballots_cast = len(normalized)
    blank = sum(1 for n in normalized if n.status == "blank")
    invalid = sum(1 for n in normalized if n.status == "invalid")
    initially_exhausted = {n.code for n in normalized if n.status == "exhausted"}
    active = [n for n in normalized if n.status == "valid"]

    eliminated: set[str] = set()
    exhausted_so_far = set(initially_exhausted)
    first_round_counts: dict[str, int] = {}
    rounds: list[RoundResult] = []
    # code -> 每轮一步 {round, destination, candidate, reason}
    chains: dict[str, list[dict[str, Any]]] = {n.code: [] for n in normalized}

    winner: str | None = None
    round_no = 0
    while True:
        round_no += 1
        continuing = [c for c in candidate_codes if c not in eliminated]

        counts = {c: 0 for c in continuing}
        step_dest: dict[str, str] = {}
        for n in active:
            dest = _destination(n, eliminated)
            if dest is None:
                exhausted_so_far.add(n.code)
                step_dest[n.code] = EXHAUSTED
            else:
                counts[dest] += 1
                step_dest[n.code] = dest

        # 票链：active 票每轮一步
        for n in active:
            dest = step_dest[n.code]
            if dest == EXHAUSTED:
                reason = "榜上候选均已淘汰，选票穷尽"
            elif round_no == 1:
                reason = "按第一选择计票"
            else:
                reason = "按当前最高有效名次计票"
            chains[n.code].append({"round": round_no, "destination": dest,
                                   "candidate": dest if dest in valid_codes else None,
                                   "reason": reason})
        # 票链：第一轮即穷尽的票，每轮固定 EXHAUSTED
        for code in initially_exhausted:
            chains[code].append({
                "round": round_no, "destination": EXHAUSTED, "candidate": None,
                "reason": "去脏后无有效候选（如只填了无效代号），自第一轮起穷尽"})
        # blank / invalid：仅记录一次（第一轮），前端按全轮次固定展示
        if round_no == 1:
            for n in normalized:
                if n.status == "blank":
                    chains[n.code] = [{"round": 1, "destination": BLANK,
                                       "candidate": None, "reason": n.reason}]
                elif n.status == "invalid":
                    chains[n.code] = [{"round": 1, "destination": INVALID,
                                       "candidate": None, "reason": n.reason}]

        valid_count = sum(counts.values())
        exhausted_count = len(exhausted_so_far)

        conserved = valid_count + exhausted_count + blank + invalid
        if conserved != ballots_cast:
            raise BallotConservationError(
                f"第 {round_no} 轮守恒失败：valid={valid_count} + exhausted={exhausted_count} "
                f"+ blank={blank} + invalid={invalid} = {conserved} != {ballots_cast}")

        threshold = math.floor(valid_count / 2) + 1 if valid_count > 0 else None

        round_winner: str | None = None
        eliminated_now: list[str] = []
        note = ""
        tie_used = False

        if round_no == 1:
            first_round_counts.update(counts)

        leaders = [c for c in continuing if threshold is not None and counts[c] >= threshold]
        if leaders:
            round_winner = sorted(leaders, key=lambda c: (-counts[c], c))[0]
            winner = round_winner
            note = (f"{round_winner} 得 {counts[round_winner]} 票，"
                    f"达到过半门槛 {threshold}（分母＝仍有效票 {valid_count}），胜出")
        elif len(continuing) == 1:
            round_winner = continuing[0]
            winner = round_winner
            note = (f"仅剩 {round_winner} 一名候选（得 {counts[round_winner]} 票，未过半门槛 "
                    f"{threshold}）；穷尽票 {exhausted_count} 张，仍由其当选")
        elif len(continuing) == 2 and counts[continuing[0]] == counts[continuing[1]]:
            # 最终两人平票且均未过半：按预先固定决胜立即定胜负，
            # 绝不把两人同时淘汰（该决定与得票相同，不依赖任何随机因素）
            win, note = _choose_final_winner(
                continuing[0], continuing[1], first_round_counts)
            round_winner = win
            winner = win
            eliminated_now = [c for c in continuing if c != win]
        else:
            lowest, tie_used, elim_note = _eliminate_losers(
                counts, continuing, round_no, first_round_counts)
            remaining = [c for c in continuing if c not in lowest]
            eliminated_now = lowest
            note = elim_note

        rounds.append(RoundResult(
            round_no=round_no,
            counts={c: counts[c] for c in continuing},
            continuing=list(continuing),
            valid=valid_count,
            exhausted=exhausted_count,
            blank=blank,
            invalid=invalid,
            ballots_cast=ballots_cast,
            majority_threshold=threshold,
            winner=round_winner,
            eliminated=eliminated_now,
            elimination_note=note,
            tie_break_used=tie_used,
        ))

        if round_winner is not None:
            break
        eliminated.update(eliminated_now)
        if not [c for c in candidate_codes if c not in eliminated]:
            raise BallotConservationError("所有候选被淘汰却没有胜者")

    _attach_flows(rounds, chains)

    return TallyResult(
        rounds=rounds,
        winner=winner,
        ballots_cast=ballots_cast,
        chains=chains,
        normalized=[
            {"code": n.code, "ranking": list(n.ranking), "status": n.status,
             "reason": n.reason, "dropped": [dict(d) for d in n.dropped]}
            for n in normalized
        ],
        candidate_codes=candidate_codes,
    )


def _attach_flows(rounds: list[RoundResult],
                  chains: dict[str, list[dict[str, Any]]]) -> None:
    """聚合相邻轮次间的票去向（只含发生转移的票），并细化票链转移原因。"""
    for i in range(1, len(rounds)):
        prev_no, cur_no = rounds[i - 1].round_no, rounds[i].round_no
        buckets: dict[tuple[str, str], list[str]] = {}
        for code, chain in chains.items():
            prev = next((s for s in chain if s["round"] == prev_no), None)
            cur = next((s for s in chain if s["round"] == cur_no), None)
            if prev is None or cur is None:
                continue
            src, dst = prev["destination"], cur["destination"]
            if src == dst:
                continue
            buckets.setdefault((src, dst), []).append(code)
            if dst == EXHAUSTED:
                cur["reason"] = f"原落点 {src} 出局后，该票榜上无其他候选，转移后穷尽"
            else:
                cur["reason"] = f"原落点 {src} 出局，转移到下一有效名次 {dst}"
        flows = []
        for (src, dst), codes in sorted(buckets.items()):
            flows.append({
                "from": src,
                "to": dst,
                "count": len(codes),
                "ballots": sorted(codes),
                "reason": ("转移后穷尽：选票上无未淘汰候选" if dst == EXHAUSTED
                           else f"从 {src} 转移至下一有效名次 {dst}"),
            })
        rounds[i].flows = flows
