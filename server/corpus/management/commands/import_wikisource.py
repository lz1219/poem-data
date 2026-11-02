"""Retired lossy importer; legacy parsing remains only for migration comparisons.

The old writer dropped headings/references and recreated paragraph IDs.
Use scripts/wikisource_source.py preview with a fixed reading selection.
"""
import re
from django.core.management.base import BaseCommand, CommandError

COMMENT = re.compile(r"<!--.*?-->", re.S)
TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
REF = re.compile(r"<ref[^>]*>.*?</ref>", re.S)
TAG = re.compile(r"<[^>]+>")
LINK_PIPE = re.compile(r"\[\[[^\]|]*\|([^\]]*)\]\]")
LINK = re.compile(r"\[\[([^\]]*)\]\]")
BOLD = re.compile(r"'{2,}")


def clean(text: str) -> str:
    t = COMMENT.sub("", text)
    t = REF.sub("", t)
    t = TEMPLATE.sub("", t)
    t = TAG.sub("", t)
    t = LINK_PIPE.sub(r"\1", t)
    t = LINK.sub(r"\1", t)
    t = BOLD.sub("", t)
    return t


def to_paragraphs(text: str):
    out = []
    for line in clean(text).split("\n"):
        s = line.strip("\u3000 \t\r")
        if not s or s.startswith("==") or s.startswith("|") or s.startswith("{{"):
            continue
        s = re.sub(r"^[\*#:]+", "", s).strip()
        if s:
            out.append(s)
    return out


class Command(BaseCommand):
    help = "旧维基导入器已停用：会丢失标题/校记并重建段落ID"

    def add_arguments(self, parser):
        parser.add_argument('--page')
        parser.add_argument('--book')
        parser.add_argument('--edition')
        parser.add_argument('--limit', type=int, default=0)
        parser.add_argument('--delay', type=float, default=0.4)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        raise CommandError('旧维基导入器已停用。请使用 scripts/wikisource_source.py --reading-selection <固定选择文件> --operation preview；现存正文修复须先核段落ID和引用。')
