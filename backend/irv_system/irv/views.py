from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .digest import digest_input
from .models import Ballot, Candidate, Election
from .serializers import ElectionCreateSerializer
from .services import (InputChangedError, PublishedLockedError, create_election,
                       publish, run_tally)
from .engine import RULES_SNAPSHOT, RULES_VERSION


class RuleSnapshotView(APIView):
    """固定规则快照：去脏、穷尽、决胜、分母等全部规则的唯一权威说明。"""

    def get(self, request):
        return Response({"version": RULES_VERSION, "snapshot": RULES_SNAPSHOT})


class ElectionListCreateView(APIView):
    def get(self, request):
        data = [
            {
                "slug": e.slug,
                "name": e.name,
                "status": e.status,
                "winner_code": e.winner_code,
                "rounds_count": e.rounds.count(),
                "rules_version": e.rules_version,
                "input_digest": e.input_digest,
            }
            for e in Election.objects.prefetch_related("rounds").order_by("created_at")
        ]
        return Response(data)

    def post(self, request):
        ser = ElectionCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if Election.objects.filter(slug=ser.validated_data["slug"]).exists():
            return Response({"detail": f"slug {ser.validated_data['slug']} 已存在"},
                            status=status.HTTP_409_CONFLICT)
        election = create_election(ser.validated_data)
        return Response(_election_payload(election, include_chains=False),
                        status=status.HTTP_201_CREATED)


class ElectionDetailView(APIView):
    def get(self, request, slug):
        election = _get_election(slug)
        return Response(_election_payload(election, include_chains=True))


class ElectionComputeView(APIView):
    """草稿态重算；已发布 -> 409，绝不覆盖已公布轮次。"""

    def post(self, request, slug):
        election = _get_election(slug)
        if election.status == Election.Status.PUBLISHED:
            return Response(_locked_payload(election),
                            status=status.HTTP_409_CONFLICT)
        try:
            info = run_tally(election)
        except PublishedLockedError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        election.refresh_from_db()
        return Response({"detail": "计票完成", **info,
                         "election": _election_payload(election, True)})


class ElectionPublishView(APIView):
    def post(self, request, slug):
        election = _get_election(slug)
        try:
            pub = publish(election)
        except PublishedLockedError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except InputChangedError as exc:
            return Response({"detail": str(exc)},
                            status=status.HTTP_409_CONFLICT)
        election.refresh_from_db()
        return Response({
            "detail": "结果已发布，输入摘要与全部轮次已锁定；此后重算将被拒绝",
            "publication": {
                "published_at": pub.published_at.isoformat(),
                "input_digest": pub.input_digest,
                "rounds_count": pub.rounds_count,
                "winner_code": pub.winner_code,
                "input_summary": pub.input_summary,
            },
            "election": _election_payload(election, True),
        })


class BallotChainView(APIView):
    """按匿名选票代号查询完整转移链（含被剔除条目与判定原因）。"""

    def get(self, request, slug, code):
        election = _get_election(slug)
        try:
            ballot = election.ballots.get(code=code)
        except Ballot.DoesNotExist:
            return Response({"detail": f"选票 {code} 不存在"},
                            status=status.HTTP_404_NOT_FOUND)
        chain = election.result_chains.get(code, [])
        return Response({
            "code": ballot.code,
            "raw_ranking": ballot.raw_ranking,
            "normalized_ranking": ballot.normalized_ranking,
            "status": ballot.status,
            "reason": ballot.reason,
            "dropped": ballot.dropped,
            "chain": chain,
        })


def _get_election(slug: str) -> Election:
    from django.shortcuts import get_object_or_404
    return get_object_or_404(
        Election.objects.prefetch_related("candidates", "rounds",
                                          "ballots", "publication"),
        slug=slug)


def _locked_payload(election: Election) -> dict:
    candidates = list(election.candidates.all())
    ballots = list(election.ballots.all())
    live_digest = digest_input(
        election.rules_version,
        [{"code": c.code, "name": c.name} for c in candidates],
        [{"code": b.code, "ranking": b.raw_ranking} for b in ballots])
    same = live_digest == election.input_digest
    return {
        "detail": "该选举结果已发布并锁定：重算不会覆盖已公布轮次。",
        "published_digest": election.input_digest,
        "current_input_digest": live_digest,
        "input_matches_published": same,
        "winner_code": election.winner_code,
    }


def _election_payload(election: Election, include_chains: bool) -> dict:
    candidates = list(election.candidates.all())
    ballots = list(election.ballots.all())
    rounds = list(election.rounds.order_by("round_no"))
    payload = {
        "slug": election.slug,
        "name": election.name,
        "status": election.status,
        "rules_version": election.rules_version,
        "rules_snapshot": election.rules_snapshot,
        "winner_code": election.winner_code,
        "input_digest": election.input_digest,
        "input_summary": election.input_summary,
        "computed_at": election.computed_at.isoformat() if election.computed_at else None,
        "candidates": [{"code": c.code, "name": c.name,
                        "sort_order": c.sort_order} for c in candidates],
        "rounds": [{"round_no": r.round_no, "frozen": r.frozen, **r.data}
                   for r in rounds],
        "ballots": [
            {
                "code": b.code,
                "raw_ranking": b.raw_ranking,
                "normalized_ranking": b.normalized_ranking,
                "status": b.status,
                "reason": b.reason,
                "dropped": b.dropped,
            }
            for b in ballots
        ],
    }
    if include_chains:
        payload["chains"] = election.result_chains
    pub = getattr(election, "publication", None)
    if pub is not None:
        payload["publication"] = {
            "published_at": pub.published_at.isoformat(),
            "input_digest": pub.input_digest,
            "rounds_count": pub.rounds_count,
            "winner_code": pub.winner_code,
            "input_summary": pub.input_summary,
        }
    return payload
