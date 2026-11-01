"""导入殆知阁纯文本（按节标题切卷）。

殆知阁的史部文件有两种结构：
  A. 目录 + 连续正文，正文节标题形如「　　本纪第二 太宗上」（行首为全角空格）
  B. 以「卷X 本纪第Y」直接分卷（如清史稿）

本命令用**行首字符**判断，不依赖正则里的全角空格（易被编辑器/终端改写）：
  行首为 U+3000，且去掉空白后以 本纪/志/表/列传/卷 开头 → 视为新的一卷。

用法：
  manage.py import_daizhige --file <txt> --book 舊唐書 --edition "殆知阁 史藏·正史（简体标点本）"
"""
import hashlib
import re
from pathlib import Path

from django.core.management.base import BaseCommand

from corpus import db

HEAD_PREFIX = ("本纪", "本紀", "志", "表", "列传", "列傳", "卷")
PUNCT = re.compile(r"[，。！？；：]")


def split_sections(raw: str):
    """按行首 U+3000 + 节标题关键字切分。返回 [(卷名, [段落...])]."""
    units = []
    cur = None
    for line in raw.split("\n"):
        s = line.rstrip("\r")
        if not s.strip():
            continue
        body = s.lstrip("\u3000 \t")
        is_head = s.startswith("\u3000") and body.startswith(HEAD_PREFIX)
        # A 型文件：正文节标题行很短（通常 < 40 字），且不以句号逗号结尾
        if is_head and len(body) <= 40 and not PUNCT.search(body):
            if cur and cur[1]:
                units.append(cur)
            cur = (body.strip(), [])
            continue
        if cur is None:
            continue
        t = body.strip()
        if t:
            cur[1].append(t)
    if cur and cur[1]:
        units.append(cur)
    return units


class Command(BaseCommand):
    help = "导入殆知阁纯文本，按节标题切卷"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--book", required=True)
        parser.add_argument("--edition", default="殆知阁")
        parser.add_argument("--url", default="https://github.com/garychowcmu/daizhigev20")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        raw = Path(opts["file"]).read_text(encoding="utf-8")
        units = split_sections(raw)
        total = sum(len("".join(p)) for _, p in units)
        self.stdout.write(f"切出 {len(units)} 卷，共 {total} 字")
        for juan, paras in units[:3]:
            self.stdout.write(f"  {juan}（{len(paras)} 段）")
        if opts["dry_run"]:
            return
        if not units:
            self.stderr.write("没有切出任何卷，放弃导入")
            return

        db.execute(
            """INSERT INTO book (title, edition, source_url) VALUES (%s,%s,%s)
               ON CONFLICT (title) DO UPDATE SET edition=EXCLUDED.edition, source_url=EXCLUDED.source_url""",
            (opts["book"], opts["edition"], opts["url"]),
        )
        book_id = db.one("SELECT id FROM book WHERE title=%s", (opts["book"],))["id"]

        done = 0
        for juan, paras in units:
            body = "\n".join(paras)
            row = db.one(
                """INSERT INTO text_unit (book_id, juan, title, body, body_simplified, sha256, edition, source_url, punctuated)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (book_id, juan, edition) DO UPDATE SET
                     body=EXCLUDED.body, body_simplified=EXCLUDED.body_simplified,
                     sha256=EXCLUDED.sha256, punctuated=EXCLUDED.punctuated
                   RETURNING id""",
                (book_id, juan, opts["book"], body, body,
                 hashlib.sha256(body.encode()).hexdigest(), opts["edition"], opts["url"],
                 bool(PUNCT.search(body))),
            )
            unit_id = row["id"]
            db.execute("DELETE FROM paragraph WHERE unit_id=%s", (unit_id,))
            for i, p in enumerate(paras, start=1):
                db.execute("INSERT INTO paragraph (unit_id, seq, body) VALUES (%s,%s,%s)", (unit_id, i, p))
            done += 1
            if done % 20 == 0:
                self.stdout.write(f"  …已入库 {done}")

        self.stdout.write(f"入库 {done} 卷")
