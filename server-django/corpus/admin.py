"""后台：录入校记 / 评点 / 系年，全部带校验。"""
from django.contrib import admin
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

from .models import Apparatus, Commentary, Dating, Edition, Journey, JourneyLink, Person, Stop, Work

admin.site.site_header = "江山行止 · 文献"
admin.site.site_title = "文献管理"
admin.site.index_title = "作品、人物与行迹"


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
class WorkAdmin(admin.ModelAdmin):
    list_display = ("title_zh", "author", "genre", "year", "level", "apparatus_count", "commentary_count")
    list_filter = ("genre", "level", "certainty", "traditional_derived")
    search_fields = ("title_zh", "key", "meaning", "appreciation")
    autocomplete_fields = ("author",)
    readonly_fields = ("preview_paragraphs",)
    fieldsets = (
        ("基本信息", {"fields": ("key", "title_zh", "title_en", "aliases", "author", "genre", "level", "certainty")}),
        ("系年与作地", {"fields": ("year", "year_kind", "place_zh")}),
        ("文本", {"fields": ("source_edition", "paragraphs", "paragraphs_simplified", "simplified_by", "traditional_derived", "preview_paragraphs")}),
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
class PersonAdmin(admin.ModelAdmin):
    list_display = ("zh", "courtesy_zh", "born", "died", "has_journey")
    search_fields = ("zh", "key", "courtesy_zh")
    list_filter = ("dynasty_key",)

    @admin.display(description="行迹")
    def has_journey(self, obj):
        return "有" if obj.journey_key else "—"


@admin.register(Journey)
class JourneyAdmin(admin.ModelAdmin):
    list_display = ("title_zh", "person", "origin", "stop_count")
    search_fields = ("title_zh", "key")
    list_filter = ("origin",)

    @admin.display(description="站数")
    def stop_count(self, obj):
        return obj.stops.count()


class StopInline(admin.TabularInline):
    model = Stop
    extra = 0
    fields = ("seq", "year", "era_zh", "place_ancient", "place_modern", "title_zh", "source")


class LinkInline(admin.TabularInline):
    model = JourneyLink
    extra = 0
    fields = ("position", "text", "source")


admin.site.register(Edition)
admin.site.register(Stop)
admin.site.register(JourneyLink)

# Journey 的后台加上站点与承接语内联
JourneyAdmin.inlines = (StopInline, LinkInline)
