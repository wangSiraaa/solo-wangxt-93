"""数据模型：选举、候选人、匿名合成选票、轮次与发布锁定。"""
from django.db import models

from .engine import RULES_VERSION


class Election(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿（可重算）"
        PUBLISHED = "published", "已发布（输入与轮次锁定）"

    slug = models.SlugField("短标识", max_length=80, unique=True)
    name = models.CharField("选举名称", max_length=200)
    rules_version = models.CharField("规则版本", max_length=60, default=RULES_VERSION)
    rules_snapshot = models.JSONField("规则快照", default=dict)
    status = models.CharField("状态", max_length=16, choices=Status.choices,
                              default=Status.DRAFT)
    # 计票时固化的输入摘要与指纹；发布后 Publication 再存一份锁定值
    input_digest = models.CharField("输入指纹 SHA256", max_length=64, blank=True, default="")
    input_summary = models.JSONField("输入摘要", default=dict, blank=True)
    computed_at = models.DateTimeField("最近计票时间", null=True, blank=True)
    winner_code = models.CharField("当选人代号", max_length=32, blank=True, default="")
    # 每张匿名票的逐轮转移链（计票结果的一部分，便于按票追踪）
    result_chains = models.JSONField("选票转移链", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "选举"
        verbose_name_plural = "选举"

    def __str__(self):
        return f"{self.name} [{self.slug}]"


class Candidate(models.Model):
    election = models.ForeignKey(Election, on_delete=models.CASCADE,
                                 related_name="candidates")
    code = models.CharField("代号", max_length=32)
    name = models.CharField("姓名", max_length=100)
    sort_order = models.PositiveIntegerField("排序", default=0)

    class Meta:
        verbose_name = "候选人"
        verbose_name_plural = "候选人"
        unique_together = ("election", "code")
        ordering = ["sort_order", "code"]

    def __str__(self):
        return f"{self.code} {self.name}"


class Ballot(models.Model):
    """匿名合成选票：只有合成代号（如 B001），不含任何真实选民信息。"""
    class Status(models.TextChoices):
        VALID = "valid", "有效"
        EXHAUSTED = "exhausted", "穷尽"
        BLANK = "blank", "空白"
        INVALID = "invalid", "无效"

    election = models.ForeignKey(Election, on_delete=models.CASCADE,
                                 related_name="ballots")
    code = models.CharField("合成选票代号", max_length=40)
    raw_ranking = models.JSONField("原始排名", default=dict)
    status = models.CharField("去脏状态", max_length=16,
                              choices=Status.choices, blank=True, default="")
    normalized_ranking = models.JSONField("规范化后排名", default=list, blank=True)
    reason = models.CharField("判定说明", max_length=255, blank=True, default="")
    dropped = models.JSONField("被剔除条目", default=list, blank=True)

    class Meta:
        verbose_name = "匿名合成选票"
        verbose_name_plural = "匿名合成选票"
        unique_together = ("election", "code")
        ordering = ["code"]


class Round(models.Model):
    """一轮计票结果。frozen=True 表示随发布锁定，重算绝不覆盖。"""
    election = models.ForeignKey(Election, on_delete=models.CASCADE,
                                 related_name="rounds")
    round_no = models.PositiveIntegerField("轮次")
    data = models.JSONField("轮次完整数据", default=dict)
    frozen = models.BooleanField("已随发布锁定", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "计票轮次"
        verbose_name_plural = "计票轮次"
        unique_together = ("election", "round_no")
        ordering = ["round_no"]


class Publication(models.Model):
    """发布记录：锁定输入摘要/指纹与轮次数量，作为重算保护的依据。"""
    election = models.OneToOneField(Election, on_delete=models.PROTECT,
                                    related_name="publication")
    input_digest = models.CharField("发布时输入指纹", max_length=64)
    input_summary = models.JSONField("发布时输入摘要", default=dict)
    rules_snapshot = models.JSONField("发布时规则快照", default=dict)
    winner_code = models.CharField("发布的当选人代号", max_length=32)
    rounds_count = models.PositiveIntegerField("发布轮次数")
    published_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "结果发布"
        verbose_name_plural = "结果发布"
