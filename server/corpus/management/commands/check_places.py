"""地名标准化核对：行迹站点 ↔ place 地名库（38,489 条，18,811 有坐标）。

检查：
  1. 站点的古地名能否在地名库中找到
  2. 找到的，今地名与坐标是否与站点记录一致
  3. 找不到的，列出来（可能是生僻地名，也可能写错）

只报告，不改数据。
"""
from django.core.management.base import BaseCommand

from corpus import db
from corpus.models import Stop

SQL = """
SELECT ancient, modern, lng, lat, admin, is_capital
  FROM place
 WHERE ancient = %s
 ORDER BY (lng IS NULL), id
 LIMIT 3
"""


class Command(BaseCommand):
    help = "核对行迹站点与地名库"

    def handle(self, *args, **opts):
        if not db.available():
            self.stderr.write("语料库未连接")
            return

        total = hit = agree = mismatch = 0
        missing = []
        differ = []

        for s in Stop.objects.select_related("journey").all():
            total += 1
            place = (s.place_ancient or "").strip()
            if not place:
                continue
            rows = db.query(SQL, (place,))
            if not rows:
                missing.append((s.journey.key, s.seq, place, s.place_modern))
                continue
            hit += 1
            r = rows[0]
            same_modern = (r["modern"] or "") == (s.place_modern or "")
            near = (
                r["lng"] is not None
                and s.lng is not None
                and abs(float(r["lng"]) - float(s.lng)) < 0.05
                and abs(float(r["lat"]) - float(s.lat)) < 0.05
            )
            if same_modern or near:
                agree += 1
            else:
                mismatch += 1
                differ.append((s.journey.key, s.seq, place, s.place_modern, r["modern"], (s.lng, s.lat), (r["lng"], r["lat"])))

        self.stdout.write(f"\n站点 {total} 个：地名库命中 {hit}，其中今地名/坐标一致 {agree}，有出入 {mismatch}")
        if missing:
            self.stdout.write(f"\n地名库未收录 {len(missing)} 个：")
            for m in missing[:15]:
                self.stdout.write(f"  {m[0]} 第{m[1]}站  {m[2]}（今 {m[3]}）")
        if differ:
            self.stdout.write(f"\n今地名或坐标有出入 {len(differ)} 个：")
            for d in differ[:15]:
                self.stdout.write(f"  {d[0]} 第{d[1]}站  {d[2]}：本站今地「{d[3]}」↔ 库「{d[4]}」；坐标 {d[5]} ↔ {d[6]}")
