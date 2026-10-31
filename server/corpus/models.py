"""
数据模型：与 poem-data 的 JSON Schema 一一对应。

设计原则
  1. 能存「不确定」：校记有 judgement、系年有多说、出处是必填。
  2. 不丢字段：notes / aliases / dating 在 JSON 里有的，这里都有列。
  3. 关系显式：Work → Person、Work → Apparatus/Commentary/Dating、Journey → Stop。
"""
from django.db import models


class Edition(models.Model):
    """版本：一部书的某一版本，可成谱系。"""

    key = models.SlugField(max_length=80, unique=True)
    book = models.CharField(max_length=120, blank=True)
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=40, blank=True)
    year = models.IntegerField(null=True, blank=True)
    year_text = models.CharField(max_length=80, blank=True)
    publisher = models.CharField(max_length=120, blank=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = "版本"
        verbose_name_plural = "版本"
        ordering = ["key"]

    def __str__(self) -> str:
        return f"{self.name}"


class Person(models.Model):
    key = models.SlugField(max_length=80, unique=True)
    zh = models.CharField("姓名", max_length=80)
    en = models.CharField("英文名", max_length=120, blank=True)
    courtesy_zh = models.CharField("字号", max_length=160, blank=True)
    dynasty_key = models.CharField(max_length=40, blank=True)
    born = models.IntegerField(null=True, blank=True)
    died = models.IntegerField(null=True, blank=True)
    span_note = models.CharField("生卒异说", max_length=200, blank=True)
    aliases = models.JSONField("别名", default=list, blank=True)
    cbdb_id = models.CharField(max_length=40, blank=True)
    wikidata_id = models.CharField(max_length=40, blank=True)
    journey_key = models.CharField(max_length=80, blank=True)

    class Meta:
        verbose_name = "人物"
        verbose_name_plural = "人物"
        ordering = ["born"]

    def __str__(self) -> str:
        return self.zh


class Work(models.Model):
    GENRE = [("shi", "诗"), ("ci", "词"), ("fu", "赋"), ("wen", "文"), ("history", "史传"), ("qu", "曲")]
    LEVEL = [("academic", "学术级"), ("popular", "通俗级")]
    CERTAINTY = [("confirmed", "确考"), ("probable", "近是"), ("disputed", "有争议"), ("unknown", "未详")]

    key = models.CharField("键", max_length=120, unique=True)
    title_zh = models.CharField("题名", max_length=200)
    title_en = models.CharField("英文题名", max_length=200, blank=True)
    aliases = models.JSONField("别名", default=list, blank=True)
    author = models.ForeignKey(Person, null=True, blank=True, on_delete=models.SET_NULL, related_name="works", verbose_name="作者")

    genre = models.CharField("文体", max_length=20, choices=GENRE, default="shi")
    level = models.CharField("级别", max_length=20, choices=LEVEL, default="popular")
    certainty = models.CharField("系年可信度", max_length=20, choices=CERTAINTY, default="unknown")

    year = models.IntegerField("系年", null=True, blank=True)
    year_kind = models.CharField("系年类型", max_length=20, default="composition")
    place_zh = models.CharField("作地", max_length=80, blank=True)

    source_edition = models.ForeignKey(Edition, null=True, blank=True, on_delete=models.SET_NULL, related_name="works", verbose_name="正文所据版本")
    paragraphs = models.JSONField("正文（繁体，按句）", default=list)
    paragraphs_simplified = models.JSONField("正文（简体）", default=list, blank=True)
    simplified_by = models.CharField("简繁转换器", max_length=60, blank=True)
    traditional_derived = models.BooleanField("繁体为反推", default=False)

    meaning = models.TextField("大意", blank=True)
    notes = models.JSONField("注释", default=list, blank=True)
    background = models.TextField("写作背景", blank=True)

    appreciation = models.TextField("赏析", blank=True)
    inference = models.TextField("推测", blank=True)
    inference_basis = models.TextField("推测依据", blank=True)
    appreciation_by = models.CharField(max_length=40, default="本站自撰")
    appreciation_license = models.CharField(max_length=40, default="CC BY-SA 4.0")

    citation = models.CharField("出处", max_length=300, blank=True)

    class Meta:
        verbose_name = "作品"
        verbose_name_plural = "作品"
        ordering = ["year", "key"]

    def __str__(self) -> str:
        return f"{self.title_zh}（{self.author or '佚名'}）"


class Apparatus(models.Model):
    """校记：底本与异文，判定可为待裁。"""

    JUDGE = [("pending", "待裁"), ("base-right", "底本是"), ("var-right", "异文是"), ("both", "两通")]
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="apparatus")
    locator = models.JSONField("定位", default=dict, blank=True)
    base_edition = models.CharField(max_length=80, blank=True)
    base_text = models.CharField("底本作", max_length=200)
    variant_edition = models.CharField(max_length=80, blank=True)
    variant_text = models.CharField("异文作", max_length=200)
    judgement = models.CharField(max_length=20, choices=JUDGE, default="pending")
    basis = models.TextField("判定依据")

    class Meta:
        verbose_name = "校记"
        verbose_name_plural = "校记"
        ordering = ["work_id", "id"]

    def __str__(self) -> str:
        return f"{self.base_text}/{self.variant_text}（{self.get_judgement_display()}）"

    def save(self, *args, **kwargs):
        if not (self.basis or "").strip():
            raise ValueError("校记必须有判定依据（basis）")
        super().save(*args, **kwargs)


class Commentary(models.Model):
    """历代评点：评者·朝代·原文·出处 四要素齐全才允许保存。"""

    STATUS = [("pending", "待核原文"), ("verified", "已核")]

    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="commentaries")
    critic = models.CharField("评者", max_length=80)
    dynasty = models.CharField("朝代", max_length=20, blank=True)
    text = models.TextField("评语原文")
    source = models.CharField("出处（书名+卷页）", max_length=200)
    topic = models.CharField(max_length=20, blank=True)
    also_in = models.CharField("亦见", max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="pending")

    class Meta:
        verbose_name = "历代评点"
        verbose_name_plural = "历代评点"
        ordering = ["work_id", "id"]

    def __str__(self) -> str:
        return f"{self.dynasty}{self.critic}：{self.text[:20]}"

    def save(self, *args, **kwargs):
        missing = [n for n in ("critic", "text", "source") if not (getattr(self, n) or "").strip()]
        if missing:
            raise ValueError("评点缺要素：" + "、".join(missing))
        super().save(*args, **kwargs)


class Dating(models.Model):
    """系年考辨：并列各说，只有一条可 adopted。"""

    STANCE = [("adopted", "采信"), ("rejected", "不采"), ("pending", "待定")]

    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="dating")
    claim = models.CharField("说法", max_length=120)
    stance = models.CharField(max_length=20, choices=STANCE, default="pending")
    note = models.CharField(max_length=300, blank=True)
    evidence = models.JSONField("依据", default=list, blank=True)

    class Meta:
        verbose_name = "系年考辨"
        verbose_name_plural = "系年考辨"
        ordering = ["work_id", "id"]

    def __str__(self) -> str:
        return f"{self.claim}（{self.get_stance_display()}）"


class Journey(models.Model):
    ORIGIN = [("upstream", "上游数据"), ("overlay", "本仓库补录")]

    key = models.SlugField(max_length=80, unique=True)
    person = models.ForeignKey(Person, null=True, blank=True, on_delete=models.SET_NULL, related_name="journeys")
    title_zh = models.CharField(max_length=200)
    title_en = models.CharField("英文题名", max_length=200, blank=True)
    span_zh = models.CharField(max_length=80, blank=True)
    origin = models.CharField(max_length=20, choices=ORIGIN, default="overlay")
    intro = models.TextField("导语", blank=True)
    intro_source = models.CharField("导语出处", max_length=300, blank=True)

    class Meta:
        verbose_name = "行迹"
        verbose_name_plural = "行迹"
        ordering = ["key"]

    def __str__(self) -> str:
        return self.title_zh


class Stop(models.Model):
    journey = models.ForeignKey(Journey, on_delete=models.CASCADE, related_name="stops")
    seq = models.IntegerField("站序")
    year = models.IntegerField(null=True, blank=True)
    era_zh = models.CharField("年号", max_length=40, blank=True)
    place_ancient = models.CharField("古地名", max_length=80)
    place_modern = models.CharField("今地名", max_length=120, blank=True)
    lng = models.FloatField(null=True, blank=True)
    lat = models.FloatField(null=True, blank=True)
    title_zh = models.CharField("事由", max_length=200)
    desc_zh = models.TextField("叙述")
    quote_zh = models.TextField("引文", blank=True)
    source = models.CharField("出处", max_length=300)

    class Meta:
        verbose_name = "站点"
        verbose_name_plural = "站点"
        ordering = ["journey_id", "seq"]
        unique_together = [("journey", "seq")]

    def __str__(self) -> str:
        return f"{self.seq}. {self.year or '?'} {self.place_ancient}"

    def save(self, *args, **kwargs):
        if not (self.source or "").strip():
            raise ValueError("站点必须有出处（source）")
        super().save(*args, **kwargs)


class JourneyLink(models.Model):
    """站间承接语：挂在第 position 站之前。"""

    journey = models.ForeignKey(Journey, on_delete=models.CASCADE, related_name="links")
    position = models.IntegerField("插在第几站之前")
    text = models.TextField("承接语")
    source = models.CharField("出处", max_length=300)

    class Meta:
        verbose_name = "承接语"
        verbose_name_plural = "承接语"
        ordering = ["journey_id", "position"]
        unique_together = [("journey", "position")]

    def __str__(self) -> str:
        return f"{self.position}：{self.text[:20]}"
