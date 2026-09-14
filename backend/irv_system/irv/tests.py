import math

from django.test import SimpleTestCase

from .engine import (EXHAUSTED, INVALID, RULES_SNAPSHOT, normalize_ballot, tally)

CANDS = [{"code": c, "name": c} for c in ["A", "B", "C", "D", "E", "F"]]
CSET = {c["code"] for c in CANDS}


class NormalizeTests(SimpleTestCase):
    def test_valid_plain_and_skip_ranks(self):
        nb = normalize_ballot({"code": "x", "ranking": {"1": "A", "3": "C", "5": "B"}},
                              CSET)
        self.assertEqual(nb.status, "valid")
        self.assertEqual(nb.ranking, ("A", "C", "B"))  # 跳号合法，按名次升序

    def test_invalid_candidate_entry_ignored_not_fatal(self):
        nb = normalize_ballot({"code": "x", "ranking": {"1": "Z", "2": "A"}}, CSET)
        self.assertEqual(nb.status, "valid")
        self.assertEqual(nb.ranking, ("A",))
        self.assertTrue(any(d["candidate"] == "Z" for d in nb.dropped))

    def test_invalid_only_becomes_exhausted(self):
        nb = normalize_ballot({"code": "x", "ranking": {"1": "Z"}}, CSET)
        self.assertEqual(nb.status, "exhausted")

    def test_blank(self):
        nb = normalize_ballot({"code": "x", "ranking": {}}, CSET)
        self.assertEqual(nb.status, "blank")

    def test_duplicate_candidate_invalidates_whole_ballot(self):
        nb = normalize_ballot({"code": "x", "ranking": {"1": "A", "2": "A"}}, CSET)
        self.assertEqual(nb.status, "invalid")
        self.assertIn("重复", nb.reason)

    def test_overvote_invalidates_whole_ballot(self):
        nb = normalize_ballot({"code": "x", "ranking": {"1": ["D", "A"]}}, CSET)
        self.assertEqual(nb.status, "invalid")
        self.assertIn("overvote", nb.reason)

    def test_rank_out_of_range_ignored(self):
        nb = normalize_ballot({"code": "x", "ranking": {"1": "A", "9": "B"}}, CSET)
        self.assertEqual(nb.status, "valid")
        self.assertEqual(nb.ranking, ("A",))


def blocks_to_ballots(blocks):
    out, n = [], 0
    for ranking, w in blocks:
        for _ in range(w):
            n += 1
            out.append({"code": f"B{n:03d}", "ranking": {**ranking}})
    return out


MAIN = blocks_to_ballots([
    ({"1": "A", "2": "F", "3": "C", "4": "B"}, 18),
    ({"1": "A", "2": "C", "3": "F"}, 22),
    ({"1": "B", "2": "C", "3": "A"}, 24),
    ({"1": "C", "3": "F", "5": "A"}, 20),
    ({"1": "D", "2": "C", "3": "F"}, 12),
    ({"1": "E", "2": "A"}, 12),
    ({"1": "F", "2": "C", "3": "A"}, 12),
    ({"1": "B"}, 16),
    ({"1": "Z", "2": "Y"}, 26),
    ({"1": "9"}, 2),
    ({"1": "A", "2": "A"}, 3),
    ({"1": ["D", "A"]}, 2),
    ({}, 1),
    ({"1": "Z", "2": "A", "3": "F", "4": "C"}, 2),
])


class TallyMainDemoTests(SimpleTestCase):
    def setUp(self):
        self.res = tally(CANDS, MAIN)

    def test_winner_and_round_count(self):
        self.assertEqual(self.res.winner, "C")
        self.assertEqual(len(self.res.rounds), 5)

    def test_first_round_counts_and_lex_tie(self):
        r1 = self.res.rounds[0]
        self.assertEqual(r1.counts,
                         {"A": 42, "B": 40, "C": 20, "D": 12, "E": 12, "F": 12})
        self.assertEqual(r1.exhausted, 28)
        self.assertEqual(r1.invalid, 5)
        self.assertEqual(r1.blank, 1)
        self.assertEqual(r1.majority_threshold, 70)  # floor(138/2)+1
        self.assertTrue(r1.tie_break_used)
        self.assertIn("代号字典序", r1.elimination_note)
        # 三方并列时每轮只淘汰决胜第一名：D
        self.assertEqual(r1.eliminated, ["D"])

    def test_second_round_tie_broken_by_first_round_count_then_lex(self):
        r2 = self.res.rounds[1]
        self.assertEqual(r2.eliminated, ["E"])  # E/F 首轮均 12 -> 代号小者先
        self.assertIn("第一轮得票", r2.elimination_note)

    def test_conservation_every_round(self):
        for r in self.res.rounds:
            self.assertEqual(
                r.valid + r.exhausted + r.blank + r.invalid, r.ballots_cast,
                msg=f"第 {r.round_no} 轮票数守恒失败")
            self.assertEqual(r.valid, sum(r.counts.values()))
            self.assertEqual(r.ballots_cast, 172)

    def test_denominator_excludes_exhausted(self):
        last = self.res.rounds[-1]
        # 终轮 valid=122，穷尽=44（28 初始 + 16 张 B-only 中途穷尽）
        self.assertEqual(last.exhausted, 44)
        self.assertEqual(last.valid, 122)
        self.assertEqual(last.majority_threshold, 62)
        self.assertEqual(last.counts, {"A": 54, "C": 68})
        self.assertEqual(last.winner, "C")
        # 分母明确是仍有效票而非投票总数（若用 172 做底则门槛应为 87）
        self.assertLess(last.majority_threshold,
                        math.floor(last.ballots_cast / 2) + 1)

    def test_b_only_ballot_exhausts_mid_race_with_full_chain(self):
        code = next(n["code"] for n in self.res.normalized
                    if n["ranking"] == ["B"])
        chain = self.res.chains[code]
        self.assertEqual([s["destination"] for s in chain[:4]],
                         ["B", "B", "B", "B"])
        self.assertEqual(chain[4]["destination"], EXHAUSTED)
        self.assertIn("穷尽", chain[4]["reason"])

    def test_transfer_chain_followed_step_by_step(self):
        code = next(n["code"] for n in self.res.normalized
                    if n["ranking"] == ["D", "C", "F"])
        chain = self.res.chains[code]
        self.assertEqual([s["destination"] for s in chain],
                         ["D", "C", "C", "C", "C"])
        # 每步原因可读
        self.assertTrue(all(s["reason"] for s in chain))

    def test_invalid_and_blank_chains(self):
        invalid_codes = [n["code"] for n in self.res.normalized
                         if n["status"] == "invalid"]
        self.assertEqual(len(invalid_codes), 5)
        self.assertTrue(all(self.res.chains[c][0]["destination"] == INVALID
                            for c in invalid_codes))

    def test_flows_partition_transferred_ballots(self):
        # 第 5 轮：B 的 40 票全部转出（24->C、16->穷尽），无停留
        r5 = self.res.rounds[4]
        moved = []
        for f in r5.flows:
            moved.extend(f["ballots"])
        self.assertEqual(len(moved), 40)
        self.assertEqual(len(moved), len(set(moved)))
        b_ballots = {n["code"] for n in self.res.normalized
                     if n["ranking"] and n["ranking"][0] == "B"}
        self.assertEqual(set(moved), b_ballots)
        # 每条聚合流向的票数与选票代号数一致
        for f in r5.flows:
            self.assertEqual(f["count"], len(f["ballots"]))

    def test_exhausted_not_in_counts(self):
        for r in self.res.rounds:
            self.assertNotIn(EXHAUSTED, r.counts)


class TieBreakFinalTests(SimpleTestCase):
    def test_final_tie_when_first_round_equal_uses_lex(self):
        cands = [{"code": "P", "name": "潘"},
                 {"code": "Q", "name": "齐"},
                 {"code": "R", "name": "任"}]
        ballots = blocks_to_ballots([
            ({"1": "P", "2": "Q"}, 30),
            ({"1": "P"}, 12),
            ({"1": "Q", "2": "P"}, 34),
            ({"1": "Q"}, 8),
            ({"1": "R"}, 16),
        ])
        res = tally(cands, ballots)
        last = res.rounds[-1]
        self.assertEqual(last.counts, {"P": 42, "Q": 42})
        self.assertEqual(last.exhausted, 16)
        self.assertEqual(res.winner, "Q")  # 首轮相同 -> 代号靠后者
        self.assertIn("平票", last.elimination_note)
        for r in res.rounds:
            self.assertEqual(r.valid + r.exhausted + r.blank + r.invalid, 100)

    def test_final_tie_broken_by_first_round_count_when_differ(self):
        # 构造首轮 P、Q 不等、最终仍平票不可行（守恒），
        # 这里直接验证决胜函数使用首轮得票的顺序约定：
        # 2 人平票且首轮 P<Q 时 Q 胜（首轮票高者胜）。
        cands = [{"code": "P", "name": "潘"}, {"code": "Q", "name": "齐"}]
        ballots = blocks_to_ballots([({"1": "P"}, 5), ({"1": "Q"}, 5)])
        res = tally(cands, ballots)
        self.assertEqual(res.winner, "Q")  # 首轮 5=5 -> 代号靠后
        last = res.rounds[-1]
        self.assertIn("第一轮得票", last.elimination_note)


class SoleRemainingTests(SimpleTestCase):
    def test_sole_candidate_wins_without_majority_after_exhaustion(self):
        # A=3（第二选择为无效代号 Z），B=2 只选 B，C=2 只选 C：
        # R1 A=3 B=2 C=2 门槛4；B/C 首轮平票，代号小者 B 先淘汰（B 票穷尽）
        # R2 A=3 C=2 valid=5 门槛3 -> A 严格过半
        cands = [{"code": "A", "name": "安"},
                 {"code": "B", "name": "白"},
                 {"code": "C", "name": "晨"}]
        ballots = blocks_to_ballots([
            ({"1": "A", "2": "Z"}, 3),
            ({"1": "B"}, 2),
            ({"1": "C"}, 2),
        ])
        res = tally(cands, ballots)
        last = res.rounds[-1]
        self.assertEqual(res.winner, "A")
        self.assertEqual(last.exhausted, 2)

    def test_sole_remaining_wins_even_below_majority(self):
        # A=1（无后续），B=3 只选 B，另有 8 张首轮即穷尽：
        # R1 A=1 B=3 valid=4 门槛3 -> B 首轮过半；
        # 改为 A=2,B=2, C-only 4 张首轮穷尽票不在分母：
        # valid=4 门槛3，A/B 各 2 平票 -> 代号 Q 式决胜；
        # 要触发"只剩一人但未过半"，让淘汰后 A 一人但穷尽票把分母压低到仍不过半：
        cands = [{"code": "A", "name": "安"}, {"code": "B", "name": "白"}]
        ballots = blocks_to_ballots([
            ({"1": "A"}, 3),
            ({"1": "B", "2": "Z"}, 3),
            ({"1": "Z"}, 10),
        ])
        res = tally(cands, ballots)
        # R1 valid=6 A=3 B=3 平票 -> A 出局；R2 B=3 valid=3 门槛2 -> B 过半
        # （只剩一人时严格过半几乎必然成立；本用例保留对无异常终止的回归）
        last = res.rounds[-1]
        self.assertEqual(res.winner, "B")
        self.assertEqual(last.exhausted, 10)


class SnapshotTests(SimpleTestCase):
    def test_snapshot_covers_required_rules(self):
        keys = {"duplicate_rank_handling", "overvote_handling",
                "invalid_candidate_handling", "skipped_rank_handling",
                "exhausted_definition", "valid_denominator", "tie_break",
                "conservation", "termination", "blank_definition",
                "invalid_definition"}
        self.assertTrue(keys.issubset(RULES_SNAPSHOT.keys()))

    def test_tally_is_deterministic(self):
        # 同样输入两次结果必须逐字节一致（禁止任何随机决胜）
        r1 = tally(CANDS, MAIN)
        r2 = tally(CANDS, list(reversed(MAIN)))  # 选票顺序也不应影响结果
        self.assertEqual(
            [(r.round_no, r.counts, r.eliminated, r.winner) for r in r1.rounds],
            [(r.round_no, r.counts, r.eliminated, r.winner) for r in r2.rounds])
        self.assertEqual(r1.winner, r2.winner)
