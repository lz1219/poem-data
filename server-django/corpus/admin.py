"""后台：录入校记 / 评点 / 系年，全部带校验。"""
from django.contrib import admin
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

from .forms import WorkAdminForm
from .models import Apparatus, Commentary, Dating, Edition, Journey, JourneyLink, Person, Stop, Work


class BaseAdmin(admin.ModelAdmin):
    """统一注入后台微调样式。"""

    class Media:
        css = {"all": ("corpus/admin_extra.css",)}


class ApparatusInline(admin.TabularInline):
    model = Apparatus
    extra = 0
    fields = ("locator", "base_text", "variant_text", "judgement", "basis")


class CommentaryInline(admin.TabularInline):
    model = Commentary
    extra = 0
    fields = ("critic", "dynasty", "text", "source", "topic", "status")


class DatingInline(admin.TabularInline):
    model = Dating
    extra = 0
    fields = ("claim", "stance", "note", "evidence")


@admin.register(Work)
class WorkAdmin(BaseAdmin):
    form = WorkAdminForm
    list_display = ("title_zh", "author", "genre", "year", "level", "apparatus_count", "commentary_count")
    list_filter = ("genre", "level", "certainty", "traditional_derived")
    search_fields = ("title_zh", "key", "meaning", "appreciation")
    autocomplete_fields = ("author",)
    readonly_fields = ("preview_paragraphs",)
    fieldsets = (
        ("基本信息", {"fields": ("key", "title_zh", "title_en", "aliases", "author", "genre", "level", "certainty")}),
        ("系年与作地", {"fields": ("year", "year_kind", "place_zh")}),
        (
            "文本",
            {
                "fields": (
                    "source_edition",
                    "paragraphs",
                    "paragraphs_simplified",
                    "simplified_by",
                    "traditional_derived",
                    "preview_paragraphs",
                )
            },
        ),
        ("释义", {"fields": ("meaning", "notes", "background")}),
        ("赏析", {"fields": ("appreciation", "inference", "inference_basis", "appreciation_by", "appreciation_license")}),
        ("出处", {"fields": ("citation",)}),
    )
    inlines = (ApparatusInline, CommentaryInline, DatingInline)

    @admin.display(description="校记")
    def apparatus_count(self, obj):
        return obj.apparatus.count()

    @admin.display(description="评点")
    def commentary_count(self, obj):
        return obj.commentaries.count()

    @admin.display(description="正文预览")
    def preview_paragraphs(self, obj):
        lines = (obj.paragraphs or [])[:4]
        if not lines:
            return "（空）"
        return format_html("{}", mark_safe("<br>".join(escape(x) for x in lines)))


@admin.register(Person)
class PersonAdmin(BaseAdmin):
    list_display = ("zh", "courtesy_zh", "born", "died", "has_journey")
    search_fields = ("zh", "key", "courtesy_zh")
    list_filter = ("dynasty_key",)

    @admin.display(description="行迹")
    def has_journey(self, obj):
        return "有" if obj.journey_key else "—"


class StopInline(admin.TabularInline):
    model = Stop
    extra = 0
    fields = ("seq", "year", "era_zh", "place_ancient", "place_modern", "title_zh", "source")


class LinkInline(admin.TabularInline):
    model = JourneyLink
    extra = 0
    fields = ("position", "text", "source")


@admin.register(Journey)
class JourneyAdmin(BaseAdmin):
    list_display = ("title_zh", "person", "origin", "stop_count")
    search_fields = ("title_zh", "key")
    list_filter = ("origin",)
    inlines = (StopInline, LinkInline)

    @admin.display(description="站数")
    def stop_count(self, obj):
        return obj.stops.count()


@admin.register(Apparatus)
class ApparatusAdmin(BaseAdmin):
    list_display = ("work", "base_text", "variant_text", "judgement", "basis_short")
    list_filter = ("judgement",)
    search_fields = ("base_text", "variant_text", "basis", "work__title_zh")
    autocomplete_fields = ("work",)

    @admin.display(description="依据")
    def basis_short(self, obj):
        return (obj.basis or "")[:40]


@admin.register(Commentary)
class CommentaryAdmin(BaseAdmin):
    list_display = ("work", "critic", "dynasty", "text_short", "status")
    list_filter = ("status", "dynasty", "topic")
    search_fields = ("critic", "text", "source", "work__title_zh")
    autocomplete_fields = ("work",)

    @admin.display(description="评语")
    def text_short(self, obj):
        return (obj.text or "")[:36]


@admin.register(Dating)
class DatingAdmin(BaseAdmin):
    list_display = ("work", "claim", "stance")
    list_filter = ("stance",)
    search_fields = ("claim", "note", "work__title_zh")
    autocomplete_fields = ("work",)


@admin.register(Edition)
class EditionAdmin(BaseAdmin):
    list_display = ("name", "book", "kind", "year", "publisher")
    search_fields = ("name", "book")


@admin.register(Stop)
class StopAdmin(BaseAdmin):
    list_display = ("journey", "seq", "year", "place_ancient", "title_zh")
    search_fields = ("place_ancient", "title_zh", "journey__title_zh")
    list_filter = ("journey",)


@admin.register(JourneyLink)
class JourneyLinkAdmin(BaseAdmin):
    list_display = ("journey", "position", "text_short")
    search_fields = ("text", "journey__title_zh")

    @admin.display(description="承接语")
    def text_short(self, obj):
        return (obj.text or "")[:40]
