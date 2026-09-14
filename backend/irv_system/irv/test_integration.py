"""发布锁定、指纹一致性、API 行为的集成测试（默认 SQLite 也可跑）。"""
from django.test import TestCase

from irv.models import Election
from irv.services import (PublishedLockedError, create_election, publish,
                          run_tally)


def _payload(slug="lock-test"):
    return {
        "slug": slug,
        "name": "锁定流程测试",
        "candidates": [
            {"code": "A", "name": "甲"},
            {"code": "B", "name": "乙"},
            {"code": "C", "name": "丙"},
        ],
        "ballots": [
            {"code": f"B{i:03d}", "ranking": r}
            for i, r in enumerate(
                [{"1": "A", "2": "B"}] * 6
                + [{"1": "B", "2": "A"}] * 4
                + [{"1": "C"}] * 3
                + [{"1": "Z"}] * 5,
                start=1)
        ],
    }


class PublishLockTests(TestCase):
    def setUp(self):
        self.election = create_election(_payload())
        run_tally(self.election)

    def test_draft_rounds_are_not_frozen_and_recompute_replaces_them(self):
        rounds_before = list(self.election.rounds.values_list("round_no", flat=True))
        self.assertTrue(rounds_before)
        self.assertFalse(self.election.rounds.filter(frozen=True).exists())

        run_tally(self.election)  # 草稿态重算
        self.election.refresh_from_db()
        self.assertEqual(
            list(self.election.rounds.values_list("round_no", flat=True)),
            rounds_before)
        # 重算后仍非冻结
        self.assertFalse(self.election.rounds.filter(frozen=True).exists())

    def test_publish_freezes_rounds_and_sets_summary(self):
        pub = publish(self.election)
        self.election.refresh_from_db()
        self.assertEqual(self.election.status, Election.Status.PUBLISHED)
        self.assertTrue(self.election.rounds.count() > 0)
        self.assertEqual(
            self.election.rounds.filter(frozen=True).count(),
            self.election.rounds.count())
        self.assertEqual(pub.rounds_count, self.election.rounds.count())
        self.assertEqual(pub.input_digest, self.election.input_digest)
        # 输入摘要关键字段
        self.assertEqual(pub.input_summary["ballots_cast"], 18)

    def test_recompute_after_publish_raises_and_data_untouched(self):
        publish(self.election)
        digest_before = self.election.input_digest
        frozen_snapshot = list(self.election.rounds.order_by("round_no")
                               .values_list("round_no", "frozen"))
        with self.assertRaises(PublishedLockedError):
            run_tally(self.election)
        self.election.refresh_from_db()
        # 数据原封不动
        self.assertEqual(self.election.input_digest, digest_before)
        self.assertEqual(
            list(self.election.rounds.order_by("round_no")
                 .values_list("round_no", "frozen")),
            frozen_snapshot)

    def test_double_publish_raises(self):
        publish(self.election)
        with self.assertRaises(PublishedLockedError):
            publish(self.election)


class ApiLockTests(TestCase):
    def setUp(self):
        self.election = create_election(_payload("api-test"))
        run_tally(self.election)

    def test_compute_publish_compute_flow_returns_409_after_lock(self):
        from rest_framework.test import APIClient
        client = APIClient()

        r = client.post("/api/elections/api-test/compute/", format="json")
        self.assertEqual(r.status_code, 200, r.content)

        r = client.post("/api/elections/api-test/publish/", format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["election"]["rounds"][0]["frozen"])

        r = client.post("/api/elections/api-test/compute/", format="json")
        self.assertEqual(r.status_code, 409)
        self.assertIn("锁定", r.data["detail"])
        self.assertTrue(r.data["input_matches_published"])

        r = client.post("/api/elections/api-test/publish/", format="json")
        self.assertEqual(r.status_code, 409)

    def test_digest_stable_across_recompute(self):
        from rest_framework.test import APIClient
        client = APIClient()
        d1 = client.get("/api/elections/api-test/").data["input_digest"]
        client.post("/api/elections/api-test/compute/", format="json")
        d2 = client.get("/api/elections/api-test/").data["input_digest"]
        self.assertEqual(d1, d2)
        self.assertEqual(len(d1), 64)  # sha256 hex

    def test_validation_rejects_bad_payload(self):
        from rest_framework.test import APIClient
        client = APIClient()
        # 候选人不足
        r = client.post("/api/elections/", data={
            "slug": "x1", "name": "x",
            "candidates": [{"code": "A", "name": "甲"}],
            "ballots": [],
        }, format="json")
        self.assertEqual(r.status_code, 400)
        # 名次越界
        r = client.post("/api/elections/", data={
            "slug": "x2", "name": "x",
            "candidates": [{"code": "A", "name": "甲"},
                           {"code": "B", "name": "乙"}],
            "ballots": [{"code": "T1", "ranking": {"9": "A"}}],
        }, format="json")
        self.assertEqual(r.status_code, 400)
