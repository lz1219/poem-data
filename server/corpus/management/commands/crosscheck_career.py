"""行迹 <-> CBDB 仕历 交叉校验。

两套独立数据互证：
  行迹：我们自己编排的站位（年 + 古地名 + 事由）
  CBDB：592,350 条任职记录（年区间 + 官职 + 地点）

判定（保守，不猜）：
  ok              年份落在某段任职区间内，且地名相符
  place-mismatch  年份对上，但地名不同（可能是异写/不同任所）
  no-record       该年无任何任职记录（可能是史料补充，也可能是错年）
  skip            人物未映射 CBDB

只输出报告，不改数据。

用法：
  python manage.py crosscheck_career
  python manage.py crosscheck_career --json out.json
"""
import json
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from corpus import db
from corpus.models import Journey, Person

SQL = """
SELECT p.c_firstyear AS y1, p.c_lastyear AS y2, o.c_office_chn AS office,
       (SELECT string_agg(coalesce(a.c_name_simp, a.c_name_chn), '、')
          FROM cbdb."POSTED_TO_ADDR_DATA" pa
          JOIN cbdb."ADDR_CODES" a ON a.c_addr_id = pa.c_addr_id
         WHERE pa.c_posting_id = p.c_posting_id) AS places
  FROM cbdb."POSTED_TO_OFFICE_DATA" p
  LEFT JOIN cbdb."OFFICE_CODES" o ON o.c_office_id = p.c_office_id
 WHERE p.c_personid = %s
"""


class Command(BaseCommand):
    help = "校验行迹站点与 CBDB 任职记录是否互相印证"

    def add_arguments(self, parser):
        parser.add_argument("--json", default=None, help="把完整结果写到文件")

    def handle(self, *args, **opts):
        if not db.available():
            self.stderr.write("语料库未连接（需要 CORPUS_DSN 或 PGHOST 等变量）")
            return

        rows = []
        for j in Journey.objects.prefetch_related("stops").all():
            p = j.person
            cbdb = (p.cbdb_id or "").strip() if p else ""
            if not cbdb.isdigit():
                rows.append({"journey": j.key, "status": "skip", "note": "人物未映射 CBDB"})
                continue

            career = db.query(SQL, (int(cbdb),))
            for s in j.stops.all():
                if not s.year:
                    continue
                place = (s.place_ancient or "").replace("（", "").replace("）", "")
                covering = [
                    r for r in career
                    if r["y1"] is not None and s.year >= r["y1"] and s.year <= (r["y2"] if r["y2"] is not None else r["y1"]) + 1
                ]
                with_place = [r for r in covering if r["places"] and place and place in r["places"]]
                # 生、卒、应举、游历这类站点本来就不该有任职记录
                non_office = any(k in (s.title_zh or "") for k in ("生于", "卒于", "登第", "遇", "望岳", "避乱", "陷贼", "读书", "隐居", "辞亲", "漫游", "卜居",
                           "求仕", "应试", "应举", "游", "访", "会", "别", "归", "赴", "宴", "题"))
                if with_place:
                    status = "ok"
                elif covering:
                    # 有任职记录，但 CBDB 未记任职地 → 只能算「年份对上、地点无载」
                    has_place = any(r["places"] for r in covering)
                    status = "place-mismatch" if has_place else "year-only"
                elif non_office:
                    status = "non-office"
                else:
                    status = "no-record"
                rows.append(
                    {
                        "journey": j.key,
                        "person": p.zh if p else "",
                        "year": s.year,
                        "place": place,
                        "title": s.title_zh,
                        "status": status,
                        "career": [
                            f"{r['y1'] or '?'}-{r['y2'] or '?'} {r['office'] or ''}"
                            + (f"@{r['places']}" if r["places"] else "")
                            for r in covering
                        ][:3],
                    }
                )

        def by(s):
            return [r for r in rows if r["status"] == s]

        ok, mismatch, none, skip, nonoff = by("ok"), by("place-mismatch"), by("no-record"), by("skip"), by("non-office")
        year_only = by("year-only")
        self.stdout.write(f"\n站点校验：共 {len(rows)} 条")
        self.stdout.write(f"  OK 年份与地名都对上   {len(ok)}")
        self.stdout.write(f"  ~ 年份对上、地名不同 {len(mismatch)}")
        self.stdout.write(f"  ? 该年无任职记录     {len(none)}")
        self.stdout.write(f"  - 年份对上、CBDB 未记地点 {len(year_only)}")
        self.stdout.write(f"  - 生卒游历（无需任职） {len(nonoff)}")
        self.stdout.write(f"  - 跳过（未映射）     {len(skip)}")

        if year_only:
            self.stdout.write("\n年份对上但 CBDB 未记任职地（不算矛盾）：")
            for r in year_only[:8]:
                self.stdout.write(f"  {r['person']} {r['year']} 本站「{r['place']}」↔ {' / '.join(r['career'])}")
        if mismatch:
            self.stdout.write("\n地名不同（需人工看）：")
            for r in mismatch[:15]:
                self.stdout.write(f"  {r['person']} {r['year']} 本站「{r['place']}」<-> CBDB {' / '.join(r['career'])}")
        if none:
            self.stdout.write("\n该年无任职记录：")
            for r in none[:15]:
                self.stdout.write(f"  {r['person']} {r['year']} {r['place']} — {r['title']}")

        if opts["json"]:
            Path(opts["json"]).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(f"\n完整结果：{opts['json']}")
