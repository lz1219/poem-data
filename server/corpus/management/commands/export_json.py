"""
把数据库导出回 data/*.json（import_json 的逆操作）。

用法：
  python manage.py export_json                  # 写回 settings.DATA_DIR
  python manage.py export_json --out ../data-export
  python manage.py export_json --check          # 只比对不写，有差异则退出码 1

规则：
  1. 形状与 import_json 读取的完全一致，保证往返无损。
  2. 一作品一文件，原子写入（先写临时文件再 rename）。
  3. 导完自动重算 data/index.json。
"""
import json
import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from corpus.models import Commentary, Edition, Journey, Person, Work


def _num(v):
    """经纬度等浮点：整数值还原成 int，避免 30.0 与 30 的假差异。"""
    if v is None:
        return None
    f = float(v)
    return int(f) if f.is_integer() else f


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class Command(BaseCommand):
    help = "把数据库导出为 data/*.json"

    def add_arguments(self, parser):
        parser.add_argument("--out", default=None, help="输出目录（默认 settings.DATA_DIR）")
        parser.add_argument("--check", action="store_true", help="只比对，不写入")

    def handle(self, *args, **opts):
        out = Path(opts["out"] or settings.DATA_DIR)
        check = opts["check"]
        diffs: list[str] = []

        files: dict[Path, str] = {}

        # ── 版本 ──
        editions = {}
        for e in Edition.objects.all():
            editions[e.key] = {
                "book": e.book or None,
                "name": e.name,
                "kind": e.kind or None,
                "year": e.year,
                "yearText": e.year_text or None,
                "publisher": e.publisher or None,
                "parent": e.parent.key if e.parent_id else None,
                "note": e.note or None,
            }
        files[(out.parent if out.name == "data" else out) / "shared" / "editions.json"] = _dump(editions)

        # ── 人物 ──
        for p in Person.objects.all():
            files[out / "persons" / f"{p.key}.json"] = _dump({
                "schemaVersion": "1.0",
                "key": p.key,
                "zh": p.zh,
                "en": p.en or None,
                "courtesyZh": p.courtesy_zh or None,
                "dynastyKey": p.dynasty_key or None,
                "span": [p.born, p.died],
                "spanNote": p.span_note or None,
                "aliases": p.aliases or [],
                "externalIds": {"cbdb": p.cbdb_id or None, "wikidata": p.wikidata_id or None},
                "journeyKey": p.journey_key or None,
            })

        # ── 作品 ──
        for w in Work.objects.select_related("author", "source_edition").prefetch_related("apparatus", "dating").all():
            comments = list(w.commentaries.all())
            commentary_file = None
            if comments:
                commentary_file = f"comments/{w.key}.json"
                files[out / commentary_file] = _dump({
                    "schemaVersion": "1.0",
                    "workKey": w.key,
                    "items": [
                        {
                            "id": f"c{i:03d}",
                            "critic": c.critic,
                            "dynasty": c.dynasty,
                            "text": c.text,
                            "source": c.source,
                            "topic": c.topic or None,
                            "alsoIn": c.also_in or None,
                            "status": c.status,
                        }
                        for i, c in enumerate(comments, start=1)
                    ],
                })

            doc = {
                "schemaVersion": "1.0",
                "key": w.key,
                "titleZh": w.title_zh,
                "titleEn": w.title_en or None,
                "aliases": w.aliases or [],
                "authorKey": w.author.key if w.author_id else "anonymous",
                "genre": w.genre,
                "level": w.level,
                "certainty": w.certainty,
                **({"excerpt": True} if w.excerpt else {}),
                "composed": {
                    "year": w.year,
                    "yearKind": w.year_kind,
                    "placeZh": w.place_zh or None,
                    "placeKey": None,
                },
                "text": {
                    "sourceEdition": w.source_edition.key if w.source_edition_id else None,
                    "paragraphs": w.paragraphs or [],
                    "paragraphsSimplified": w.paragraphs_simplified or [],
                    "simplifiedBy": w.simplified_by or None,
                    "traditionalDerived": w.traditional_derived,
                },
                "meaning": w.meaning or None,
                "notes": w.notes or [],
                "background": w.background or None,
                "appreciation": {
                    "text": w.appreciation,
                    "inference": (
                        {"text": w.inference, "basis": w.inference_basis} if w.inference else None
                    ),
                    "by": w.appreciation_by,
                    "license": w.appreciation_license,
                },
                "apparatus": [
                    {
                        "id": f"a{i:03d}",
                        "locator": a.locator or {},
                        "baseEdition": a.base_edition or None,
                        "baseText": a.base_text,
                        "variantEdition": a.variant_edition or None,
                        "variantText": a.variant_text,
                        "judgement": a.judgement,
                        "basis": a.basis,
                    }
                    for i, a in enumerate(w.apparatus.all(), start=1)
                ],
                "commentaryFile": commentary_file,
                "dating": [
                    {
                        "claim": d.claim,
                        "stance": d.stance,
                        "note": d.note or None,
                        "evidence": d.evidence or [],
                    }
                    for d in w.dating.all()
                ],
                "citation": w.citation or None,
            }
            files[out / "works" / f"{w.key}.json"] = _dump(doc)

        # ── 行迹 ──
        for j in Journey.objects.select_related("person").prefetch_related("stops", "links").all():
            doc = {
                "schemaVersion": "1.0",
                "key": j.key,
                "personKey": j.person.key if j.person_id else "",
                "titleZh": j.title_zh,
                "titleEn": j.title_en or None,
                "spanZh": j.span_zh or None,
                "origin": j.origin,
                "intro": {"text": j.intro, "source": j.intro_source} if j.intro else None,
                "stops": [
                    {
                        "seq": s.seq,
                        "year": s.year,
                        "eraZh": s.era_zh or None,
                        "place": {
                            "ancient": s.place_ancient,
                            "modern": s.place_modern or None,
                            "coord": [_num(s.lng), _num(s.lat)] if s.lng is not None else None,
                        },
                        "titleZh": s.title_zh,
                        "descZh": s.desc_zh,
                        "quote": s.quote_zh or None,
                        "source": s.source,
                    }
                    for s in j.stops.all()
                ],
                "links": {
                    str(l.position): {"text": l.text, "source": l.source} for l in j.links.all()
                },
            }
            files[out / "journeys" / f"{j.key}.json"] = _dump(doc)

        # ── index.json（静态前端用）──
        from django.db.models import Count
        from django.utils import timezone

        works = list(
            Work.objects.select_related("author")
            .annotate(_apparatus=Count("apparatus", distinct=True), _comments=Count("commentaries", distinct=True))
        )
        # 用 Python 排序（码位序），与前端 build-index.mjs 的 JS sort 一致
        works.sort(key=lambda w: w.key)
        persons = sorted(Person.objects.all(), key=lambda p: p.key)
        journeys = sorted(Journey.objects.all(), key=lambda j: j.key)
        index = {
            "generatedAt": timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "works": [
                {
                    "key": w.key,
                    "titleZh": w.title_zh,
                    "authorKey": w.author.key if w.author_id else "anonymous",
                    "genre": w.genre,
                    "level": w.level,
                    "year": w.year,
                    "traditionalDerived": w.traditional_derived,
                    "apparatus": w._apparatus,
                    "hasComments": bool(w._comments),
                    "file": f"data/works/{w.key}.json",
                }
                for w in works
            ],
            "persons": [
                {"key": p.key, "zh": p.zh, "span": [p.born, p.died],
                 "hasJourney": bool(p.journey_key), "file": f"data/persons/{p.key}.json"}
                for p in persons
            ],
            "journeys": [
                {"key": j.key, "titleZh": j.title_zh, "stops": len(j.stops.all()),
                 "origin": j.origin, "file": f"data/journeys/{j.key}.json"}
                for j in journeys
            ],
        }
        files[out / "index.json"] = _dump(index)

        # ── 写入或比对 ──
        if check:

            def _norm(path: Path, text: str) -> str:
                # index.json 的 generatedAt 每次不同，比对时忽略
                if path.name == "index.json":
                    d = json.loads(text)
                    d.pop("generatedAt", None)
                    return json.dumps(d, ensure_ascii=False, sort_keys=True)
                return text

            for path, text in files.items():
                if not path.exists():
                    diffs.append(f"缺失 {path}")
                    continue
                old = path.read_text("utf-8").replace("\r\n", "\n")
                if _norm(path, old) != _norm(path, text):
                    diffs.append(f"不同 {path}")
            if diffs:
                self.stdout.write(f"差异 {len(diffs)} 处：")
                for d in diffs[:20]:
                    self.stdout.write("  " + d)
                raise SystemExit(1)
            self.stdout.write(self.style.SUCCESS(f"无差异（{len(files)} 个文件）"))
            return

        for path, text in files.items():
            _atomic_write(path, text)
        self.stdout.write(self.style.SUCCESS(
            f"导出完成：{len(files)} 个文件 → {out}"
            f"（作品 {len(works)} / 人物 {len(persons)} / 行迹 {len(journeys)}）"
        ))
