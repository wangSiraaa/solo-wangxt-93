"""计票与发布服务：引擎结果落库、守恒校验、发布锁定。"""
from dataclasses import asdict
from datetime import datetime, timezone

from django.db import transaction
from rest_framework.exceptions import ValidationError

from .digest import digest_input, summarize_input
from .engine import RULES_SNAPSHOT, RULES_VERSION, tally
from .models import Ballot, Candidate, Election, Publication, Round


class InputChangedError(Exception):
    """当前输入指纹与发布时锁定值不一致。"""


class PublishedLockedError(Exception):
    """已发布选举不允许再次计票/覆盖。"""


@transaction.atomic
def create_election(payload: dict) -> Election:
    election = Election.objects.create(
        slug=payload["slug"],
        name=payload["name"],
        rules_version=RULES_VERSION,
        rules_snapshot=dict(RULES_SNAPSHOT),
    )
    for i, c in enumerate(payload["candidates"]):
        Candidate.objects.create(
            election=election, code=c["code"], name=c["name"],
            sort_order=c.get("sort_order", i))
    for b in payload["ballots"]:
        Ballot.objects.create(election=election, code=b["code"],
                              raw_ranking=b.get("ranking", {}))
    return election


def _load_input(election: Election):
    candidates = [{"code": c.code, "name": c.name}
                  for c in election.candidates.order_by("sort_order", "code")]
    ballots = [{"code": b.code, "ranking": b.raw_ranking}
               for b in election.ballots.order_by("code")]
    return candidates, ballots


def current_digest(election: Election) -> str:
    candidates, ballots = _load_input(election)
    return digest_input(election.rules_version, candidates, ballots)


@transaction.atomic
def run_tally(election: Election) -> dict:
    """对选举执行计票。草稿态可反复重算（只覆盖非冻结轮次）；发布态拒绝。"""
    if election.status == Election.Status.PUBLISHED:
        raise PublishedLockedError(
            f"选举 {election.slug} 已发布：轮次已锁定，重算不会覆盖已公布结果")

    candidates, ballots = _load_input(election)
    digest = digest_input(election.rules_version, candidates, ballots)

    result = tally(candidates, ballots)

    # 落库去脏结果到选票
    norm_by_code = {n["code"]: n for n in result.normalized}
    for ballot in election.ballots.all():
        n = norm_by_code[ballot.code]
        ballot.status = n["status"]
        ballot.normalized_ranking = n["ranking"]
        ballot.reason = n["reason"]
        ballot.dropped = n["dropped"]
        ballot.save(update_fields=["status", "normalized_ranking",
                                   "reason", "dropped"])

    # 旧的非冻结轮次删除后重建；冻结轮次（正常情况下发布态根本进不来）绝不删除
    Round.objects.filter(election=election, frozen=False).delete()
    for rr in result.rounds:
        Round.objects.create(election=election, round_no=rr.round_no,
                             data=asdict(rr), frozen=False)

    election.input_digest = digest
    election.input_summary = summarize_input(
        candidates, ballots, result.normalized, digest, election.rules_version)
    election.winner_code = result.winner or ""
    election.result_chains = result.chains
    election.computed_at = datetime.now(timezone.utc)
    election.save(update_fields=["input_digest", "input_summary",
                                 "winner_code", "result_chains", "computed_at"])
    return {"digest": digest, "rounds": len(result.rounds),
            "winner": result.winner}


@transaction.atomic
def publish(election: Election) -> Publication:
    if election.status == Election.Status.PUBLISHED:
        raise PublishedLockedError(f"选举 {election.slug} 已发布，不能重复发布")

    # 发布前强制计票（若从未计算或草稿轮次缺失则在此生成）
    run_tally(election)
    election.refresh_from_db()
    digest = current_digest(election)
    if digest != election.input_digest:
        # 正常不会发生（run_tally 刚算完）；发生说明输入在事务中被改动
        raise InputChangedError("输入在计票后发生变化，拒绝发布")

    rounds = list(election.rounds.order_by("round_no"))
    publication = Publication.objects.create(
        election=election,
        input_digest=digest,
        input_summary=election.input_summary,
        rules_snapshot=election.rules_snapshot,
        winner_code=election.winner_code,
        rounds_count=len(rounds),
    )
    # 锁定：状态切换 + 每一轮标记冻结
    election.status = Election.Status.PUBLISHED
    election.save(update_fields=["status"])
    Round.objects.filter(election=election).update(frozen=True)
    return publication
