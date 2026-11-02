"""导入殆知阁纯文本（按节标题切卷）。

殆知阁的史部文件有两种结构：
  A. 目录 + 连续正文，正文节标题形如「　　本纪第二 太宗上」（行首为全角空格）
  B. 以「卷X 本纪第Y」直接分卷（如清史稿）

本命令用**行首字符**判断，不依赖正则里的全角空格（易被编辑器/终端改写）：
  行首为 U+3000，且去掉空白后以 本纪/志/表/列传/卷 开头 → 视为新的一卷。

用法：
  manage.py import_daizhige --file <txt> --book 舊唐書 --dry-run

旧写入器已移除；本命令仅预览候选切分，不能证明全文或卷界完整。
"""
import re
from pathlib import Path

from django.core.management.base import BaseCommand

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
    help = "只读预览殆知阁TXT候选卷界，不写数据库"

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
        self.stdout.write("仅预览，未写入数据库。TXT卷界须核实；不得直接用候选切分覆盖现存正文。")
