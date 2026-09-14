"""输入摘要与确定性指纹：发布锁定 / 重算比对的依据。"""
import hashlib
import json
from typing import Any


def canonical_ranking(ranking: Any) -> dict[str, Any]:
    """把原始排名规范成 {名次字符串: 代号或[代号...]}，名次按数字升序。"""
    out: dict[str, Any] = {}
    if not isinstance(ranking, dict):
        return out
    items = []
    for k, v in ranking.items():
        try:
            items.append((int(k), v))
        except (TypeError, ValueError):
            items.append((k, v))
    int_items = sorted((i for i in items if isinstance(i[0], int)),
                       key=lambda i: i[0])
    for rank, value in int_items:
        if isinstance(value, (list, tuple)):
            out[str(rank)] = [str(x).strip() for x in value]
        else:
            out[str(rank)] = str(value).strip()
    # 非整数名次键无法进入 IRV，指纹中保留以保证"输入改一字面量指纹即变"
    for k, value in sorted((i for i in items if not isinstance(i[0], int)),
                           key=lambda i: str(i[0])):
        out[str(k)] = [str(x).strip() for x in value] \
            if isinstance(value, (list, tuple)) else str(value).strip()
    return out


def build_canonical_input(rules_version: str,
                          candidates: list[dict[str, Any]],
                          ballots: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "rules_version": rules_version,
        "candidates": sorted(
            ({"code": str(c["code"]), "name": str(c["name"])} for c in candidates),
            key=lambda c: c["code"]),
        "ballots": sorted(
            ({"code": str(b["code"]),
              "ranking": canonical_ranking(b.get("ranking") or {})}
             for b in ballots),
            key=lambda b: b["code"]),
    }


def digest_input(rules_version: str,
                 candidates: list[dict[str, Any]],
                 ballots: list[dict[str, Any]]) -> str:
    payload = build_canonical_input(rules_version, candidates, ballots)
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def summarize_input(candidates: list[dict[str, Any]],
                    ballots: list[dict[str, Any]],
                    normalized: list[dict[str, Any]],
                    digest: str, rules_version: str) -> dict[str, Any]:
    """输入摘要：票数、去脏分类、第一选择分布。用于发布页面展示与核对。"""
    status_count = {"valid": 0, "exhausted": 0, "blank": 0, "invalid": 0}
    first_choice: dict[str, int] = {}
    for n in normalized:
        status_count[n["status"]] = status_count.get(n["status"], 0) + 1
        if n["ranking"]:
            first_choice[n["ranking"][0]] = first_choice.get(n["ranking"][0], 0) + 1
    return {
        "rules_version": rules_version,
        "candidate_count": len(candidates),
        "candidate_codes": [c["code"] for c in
                            sorted(candidates, key=lambda c: c["code"])],
        "ballots_cast": len(ballots),
        "status_count": status_count,
        "first_choice": dict(sorted(first_choice.items())),
        "input_digest_sha256": digest,
        "digest_algorithm": "sha256 over canonical JSON "
                            "(sorted codes/ranks, no whitespace)",
    }
