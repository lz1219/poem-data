"""序列化：输出形状与 FastAPI 版完全一致，前端无需改动。"""
from rest_framework import serializers

from .models import Apparatus, Commentary, Dating, Journey, JourneyLink, Person, Stop, Work


class ApparatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Apparatus
        fields = ("id", "locator", "base_edition", "base_text", "variant_edition", "variant_text", "judgement", "basis")


class CommentarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Commentary
        fields = ("id", "critic", "dynasty", "text", "source", "topic", "also_in", "status")


class DatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dating
        fields = ("id", "claim", "stance", "note", "evidence")


class WorkSerializer(serializers.ModelSerializer):
    apparatus = ApparatusSerializer(many=True, read_only=True)
    dating = DatingSerializer(many=True, read_only=True)
    authorKey = serializers.CharField(source="author.key", default=None)
    titleZh = serializers.CharField(source="title_zh")
    titleEn = serializers.CharField(source="title_en")
    composed = serializers.SerializerMethodField()
    text = serializers.SerializerMethodField()
    appreciation_field = serializers.SerializerMethodField()

    class Meta:
        model = Work
        fields = (
            "key", "titleZh", "titleEn", "aliases", "authorKey", "genre", "level", "certainty", "excerpt",
            "composed", "text", "meaning", "notes", "background", "appreciation_field",
            "apparatus", "dating", "citation",
        )

    def get_composed(self, obj):
        return {"year": obj.year, "yearKind": obj.year_kind, "placeZh": obj.place_zh or None}

    def get_text(self, obj):
        return {
            "sourceEdition": obj.source_edition.key if obj.source_edition else None,
            "paragraphs": obj.paragraphs or [],
            "paragraphsSimplified": obj.paragraphs_simplified or [],
            "simplifiedBy": obj.simplified_by or None,
            "traditionalDerived": obj.traditional_derived,
        }

    def get_appreciation_field(self, obj):
        return {
            "text": obj.appreciation,
            "inference": {"text": obj.inference, "basis": obj.inference_basis} if obj.inference else None,
            "by": obj.appreciation_by,
            "license": obj.appreciation_license,
        }


class WorkListItemSerializer(serializers.ModelSerializer):
    titleZh = serializers.CharField(source="title_zh")
    authorKey = serializers.CharField(source="author.key", default=None)
    year = serializers.IntegerField()

    class Meta:
        model = Work
        fields = ("key", "titleZh", "authorKey", "genre", "level", "year")


class PersonSerializer(serializers.ModelSerializer):
    span = serializers.SerializerMethodField()

    class Meta:
        model = Person
        fields = ("key", "zh", "en", "courtesy_zh", "dynasty_key", "span", "span_note", "aliases",
                  "cbdb_id", "wikidata_id", "journey_key")

    def get_span(self, obj):
        return [obj.born, obj.died]


class StopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stop
        fields = ("seq", "year", "era_zh", "place_ancient", "place_modern", "lng", "lat",
                  "title_zh", "desc_zh", "quote_zh", "source")


class LinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = JourneyLink
        fields = ("position", "text", "source")


class JourneySerializer(serializers.ModelSerializer):
    personKey = serializers.CharField(source="person.key", default=None)
    stops = StopSerializer(many=True, read_only=True)
    links = LinkSerializer(many=True, read_only=True)

    class Meta:
        model = Journey
        fields = ("key", "title_zh", "title_en", "span_zh", "origin", "personKey",
                  "intro", "intro_source", "stops", "links")
