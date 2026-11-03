"""Retired lossy writer. Legacy comparisons live in wikisource_source.legacy_projection."""
from django.core.management.base import BaseCommand, CommandError


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
