"""回填 text_unit.punctuated（分批，避免大表整表 UPDATE 触发语句超时）。

只记录「原文有没有标点」这个事实，不改动任何文本。
分批按 id 段进行，每批独立提交，可重复运行（幂等）。
"""
from django.core.management.base import BaseCommand

from corpus import db

BATCH = 100


class Command(BaseCommand):
    help = "回填原文卷的标点状态（punctuated），分批提交"

    def add_arguments(self, parser):
        parser.add_argument("--batch", type=int, default=BATCH)
        parser.add_argument("--force", action="store_true", help="重算全部（包括已有值的）")

    def handle(self, *args, **opts):
        if not db.available():
            self.stderr.write("语料库未连接（需要 CORPUS_DSN 或 PGHOST 等变量）")
            return

        batch = opts["batch"]
        where = "" if opts["force"] else "AND punctuated IS NULL"

        row = db.one("SELECT min(id) AS lo, max(id) AS hi FROM text_unit")
        lo, hi = row["lo"], row["hi"]
        if lo is None:
            self.stdout.write("text_unit 为空")
            return
        self.stdout.write(f"id 范围 {lo}..{hi}，每批 {batch}")

        done = 0
        start = lo
        while start <= hi:
            done += db.execute(
                f"""UPDATE text_unit
                       SET punctuated = (body ~ '[，。！？；：]')
                     WHERE id >= %s AND id < %s {where}""",
                (start, start + batch),
            )
            start += batch
            if (start - lo) % (batch * 20) == 0:
                self.stdout.write(f"  …已到 id {start}，累计 {done}")

        for r in db.query("SELECT punctuated, count(*) AS c FROM text_unit GROUP BY 1 ORDER BY 1 DESC NULLS LAST"):
            v = r["punctuated"]
            label = "有标点" if v else ("无标点" if v is False else "未判定")
            self.stdout.write(f"  {label}: {r['c']}")
        self.stdout.write(f"本次更新 {done} 行")
