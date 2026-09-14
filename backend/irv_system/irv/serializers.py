from rest_framework import serializers

from .engine import MAX_RANKS, RULES_SNAPSHOT


class CandidateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32)
    name = serializers.CharField(max_length=100)
    sort_order = serializers.IntegerField(required=False, default=0)

    def validate_code(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("代号不能为空")
        if value in ("EXHAUSTED", "BLANK", "INVALID"):
            raise serializers.ValidationError("该代号为系统保留值")
        return value


class BallotSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=40)
    ranking = serializers.DictField(required=False, default=dict)

    def validate_ranking(self, value):
        for k, v in value.items():
            try:
                rank = int(k)
            except (TypeError, ValueError):
                raise serializers.ValidationError(f"名次键必须是整数：{k!r}")
            if not (1 <= rank <= MAX_RANKS):
                raise serializers.ValidationError(
                    f"名次 {rank} 超出允许范围 1..{MAX_RANKS}")
            if isinstance(v, (list, tuple)):
                if len(v) < 2:
                    raise serializers.ValidationError(
                        f"名次 {rank} 的列表至少需要 2 个候选（overvote 演示）")
                if not all(isinstance(x, str) for x in v):
                    raise serializers.ValidationError(f"名次 {rank} 含有非字符串代号")
            elif not isinstance(v, str):
                raise serializers.ValidationError(f"名次 {rank} 的值必须是字符串或列表")
        return value


class ElectionCreateSerializer(serializers.Serializer):
    slug = serializers.SlugField(max_length=80)
    name = serializers.CharField(max_length=200)
    candidates = CandidateSerializer(many=True)
    ballots = BallotSerializer(many=True, default=list)

    def validate(self, attrs):
        codes = [c["code"] for c in attrs["candidates"]]
        if len(codes) != len(set(codes)):
            raise serializers.ValidationError({"candidates": "候选人代号不能重复"})
        if len(codes) < 2:
            raise serializers.ValidationError({"candidates": "至少需要 2 名候选人"})
        ballot_codes = [b["code"] for b in attrs["ballots"]]
        if len(ballot_codes) != len(set(ballot_codes)):
            raise serializers.ValidationError({"ballots": "选票代号不能重复"})
        return attrs

    def to_representation(self, instance):  # 仅为消除 IDE 警告
        return instance


def rules_snapshot():
    return dict(RULES_SNAPSHOT)
