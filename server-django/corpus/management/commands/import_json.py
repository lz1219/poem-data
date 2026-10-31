"""
把 data/*.json 导入数据库。

用法：
  python manage.py import_json            # 全量导入（先清空再写）
  python manage.py import_json --keep     # 不清空，按 key upsert

设计：JSON 是发布物，数据库是编辑态。导入是单向的（JSON → DB）。
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from corpus.models import (
    Apparatus, Commentary, Dating, Edition, Journey, JourneyLink, Person, Stop, Work,
)


class Command(BaseCommand):
    help = "从 data/*.json 导入作品、人物、行迹"

    def add_arguments(self, parser):
        parser.add_argument("--keep", action="store_true", help="不清空已有数据")
        parser.add_argument("--data-dir", default=None, help="数据目录")

    def handle(self, *args, **opts):
        data_dir = Path(opts["data_dir"] or settings.DATA_DIR)
        if not data_dir.exists():
            self.stderr.write(f"数据目录不存在：{data_dir}")
            return

        with transaction.atomic():
            if not opts["keep"]:
                for m in (Apparatus, Commentary, Dating, Stop, JourneyLink, Work, Journey, Person, Edition):
                    m.objects.all().delete()
                self.stdout.write("已清空旧数据")

            editions = self._load_editions(data_dir)
            persons = self._load_persons(data_dir)
            n_works = self._load_works(data_dir, persons, editions)
            n_j = self._load_journeys(data_dir, persons)

        self.stdout.write(self.style.SUCCESS(
            f"导入完成：版本 {Edition.objects.count()} / 人物 {Person.objects.count()} / "
            f"作品 {n_works} / 行迹 {n_j}"
        ))

    # ── 版本 ──
    def _load_editions(self, data_dir: Path) -> dict:
        f = data_dir.parent / "shared" / "editions.json"
        out = {}
        if not f.exists():
            return out
        blob = json.loads(f.read_text("utf-8"))
        for key, e in blob.items():
            obj, _ = Edition.objects.update_or_create(
                key=key[:80],
                defaults={
                    "book": e.get("book") or "",
                    "name": e.get("name") or key,
                    "kind": e.get("kind") or "",
                    "year": e.get("year"),
                    "year_text": e.get("yearText") or "",
                    "publisher": e.get("publisher") or "",
                    "note": e.get("note") or "",
                },
            )
            out[key] = obj
        self.stdout.write(f"版本 {len(out)}")
        return out

    # ── 人物 ──
    def _load_persons(self, data_dir: Path) -> dict:
        out = {}
        for f in sorted((data_dir / "persons").glob("*.json")):
            p = json.loads(f.read_text("utf-8"))
            span = p.get("span") or [None, None]
            # 有些来源把生卒存成字符串（如 CBDB 导入的 "803"），统一转整数
            span = [int(x) if isinstance(x, str) and x.lstrip("-").isdigit() else x for x in span]
            obj, _ = Person.objects.update_or_create(
                key=p["key"][:80],
                defaults={
                    "zh": p.get("zh") or p["key"],
                    "en": p.get("en") or "",
                    "courtesy_zh": p.get("courtesyZh") or "",
                    "dynasty_key": p.get("dynastyKey") or "",
                    "born": span[0] if span else None,
                    "died": span[1] if span else None,
                    "span_note": p.get("spanNote") or "",
                    "aliases": p.get("aliases") or [],
                    "cbdb_id": (p.get("externalIds") or {}).get("cbdb") or "",
                    "wikidata_id": (p.get("externalIds") or {}).get("wikidata") or "",
                    "journey_key": p.get("journeyKey") or "",
                },
            )
            out[p["key"]] = obj
        self.stdout.write(f"人物 {len(out)}")
        return out

    # ── 作品 ──
    def _load_works(self, data_dir: Path, persons: dict, editions: dict) -> int:
        n = 0
        for f in sorted((data_dir / "works").glob("*.json")):
            w = json.loads(f.read_text("utf-8"))
            text = w.get("text") or {}
            app = w.get("appreciation") or {}
            comp = w.get("composed") or {}
            edition = editions.get(text.get("sourceEdition") or "")

            obj, _ = Work.objects.update_or_create(
                key=w["key"],
                defaults={
                    "title_zh": w.get("titleZh") or w["key"],
                    "title_en": w.get("titleEn") or "",
                    "aliases": w.get("aliases") or [],
                    "author": persons.get(w.get("authorKey") or ""),
                    "genre": w.get("genre") or "shi",
                    "level": w.get("level") or "popular",
                    "certainty": w.get("certainty") or "unknown",
                    "year": comp.get("year"),
                    "year_kind": comp.get("yearKind") or "composition",
                    "place_zh": comp.get("placeZh") or "",
                    "source_edition": edition,
                    "paragraphs": text.get("paragraphs") or [],
                    "paragraphs_simplified": text.get("paragraphsSimplified") or [],
                    "simplified_by": text.get("simplifiedBy") or "",
                    "traditional_derived": bool(text.get("traditionalDerived")),
                    "meaning": w.get("meaning") or "",
                    "notes": w.get("notes") or [],
                    "background": w.get("background") or "",
                    "appreciation": app.get("text") or "",
                    "inference": (app.get("inference") or {}).get("text") or "",
                    "inference_basis": (app.get("inference") or {}).get("basis") or "",
                    "appreciation_by": app.get("by") or "本站自撰",
                    "appreciation_license": app.get("license") or "CC BY-SA 4.0",
                    "citation": w.get("citation") or "",
                },
            )
            obj.apparatus.all().delete()
            for a in w.get("apparatus") or []:
                Apparatus.objects.create(
                    work=obj,
                    locator=a.get("locator") or {},
                    base_edition=a.get("baseEdition") or "",
                    base_text=a.get("baseText") or "",
                    variant_edition=a.get("variantEdition") or "",
                    variant_text=a.get("variantText") or "",
                    judgement=a.get("judgement") or "pending",
                    basis=a.get("basis") or "（待补）",
                )
            obj.dating.all().delete()
            for d in w.get("dating") or []:
                Dating.objects.create(
                    work=obj,
                    claim=str(d.get("claim") or ""),
                    stance=d.get("stance") or "pending",
                    note=d.get("note") or "",
                    evidence=d.get("evidence") or [],
                )
            # 评点
            rel = w.get("commentaryFile")
            obj.commentaries.all().delete()
            if rel:
                cf = data_dir / rel
                if cf.exists():
                    blob = json.loads(cf.read_text("utf-8"))
                    for c in blob.get("items") or []:
                        Commentary.objects.create(
                            work=obj,
                            critic=c.get("critic") or "",
                            dynasty=c.get("dynasty") or "",
                            text=c.get("text") or "",
                            source=c.get("source") or "",
                            topic=c.get("topic") or "",
                            also_in=c.get("alsoIn") or "",
                            status=c.get("status") or "pending",
                        )
            n += 1
        self.stdout.write(f"作品 {n}")
        return n

    # ── 行迹 ──
    def _load_journeys(self, data_dir: Path, persons: dict) -> int:
        n = 0
        for f in sorted((data_dir / "journeys").glob("*.json")):
            j = json.loads(f.read_text("utf-8"))
            intro = j.get("intro") or {}
            obj, _ = Journey.objects.update_or_create(
                key=j["key"][:80],
                defaults={
                    "person": persons.get(j.get("personKey") or ""),
                    "title_zh": j.get("titleZh") or j["key"],
                    "title_en": j.get("titleEn") or "",
                    "span_zh": j.get("spanZh") or "",
                    "origin": j.get("origin") or "overlay",
                    "intro": intro.get("text") or "",
                    "intro_source": intro.get("source") or "",
                },
            )
            obj.stops.all().delete()
            for i, s in enumerate(j.get("stops") or [], start=1):
                place = s.get("place") or {}
                coord = place.get("coord") or [None, None]
                Stop.objects.create(
                    journey=obj,
                    seq=s.get("seq") or i,
                    year=s.get("year"),
                    era_zh=s.get("eraZh") or "",
                    place_ancient=place.get("ancient") or "",
                    place_modern=place.get("modern") or "",
                    lng=coord[0] if coord else None,
                    lat=coord[1] if coord and len(coord) > 1 else None,
                    title_zh=s.get("titleZh") or "",
                    desc_zh=s.get("descZh") or "",
                    quote_zh=s.get("quote") or "",
                    source=s.get("source") or "",
                )
            obj.links.all().delete()
            for pos, l in (j.get("links") or {}).items():
                JourneyLink.objects.create(
                    journey=obj,
                    position=int(pos),
                    text=l.get("text") or "",
                    source=l.get("source") or "",
                )
            n += 1
        self.stdout.write(f"行迹 {n}")
        return n
