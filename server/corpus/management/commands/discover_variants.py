"""用语料库自动发现异文候选。

只比对「繁体取自底本」的作品（traditionalDerived=false）：
    这些正文来自语料本身，与语料逐字比对才有意义。
    繁体是反推的作品与语料必然不同（简繁差异），跳过。

比对前统一：
    去标点空白 → 应用 variant_char 异体字归一 → 逐字比较

输出：差异片段（前后各 8 字上下文）+ 是否与已有校记重复。
--write 才写入 apparatus（judgement=pending，basis 写明依据来源）。
"""
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from corpus import db
from corpus.models import Apparatus, Work

PUNCT = re.compile(r"[\s，。！？；：、,.!?;:\"'“”‘’（）()《》「」『』·—…]")


class Command(BaseCommand):
    help = "用语料库发现异文候选（默认只报告，加 --write 才写入校记）"

    def add_arguments(self, parser):
        parser.add_argument("--write", action="store_true", help="把候选写入 apparatus（judgement=pending）")
        parser.add_argument("--json", default=None)

    def handle(self, *args, **opts):
        if not db.available():
            self.stderr.write("语料库未连接")
            return

        variants = {r["from_char"]: r["to_char"] for r in db.query("SELECT from_char, to_char FROM variant_char")}

        def norm(s: str) -> str:
            s = PUNCT.sub("", s or "")
            return "".join(variants.get(ch, ch) for ch in s)

        found = []
        for w in Work.objects.prefetch_related("apparatus").filter(traditional_derived=False):
            mine = norm("".join(w.paragraphs or []))
            if not mine:
                continue
            author = w.author.zh if w.author else ""
            rows = db.query(
                """SELECT body, title
                     FROM corpus_poem
                    WHERE coalesce(author_simplified, author) = %s
                      AND replace(replace(title, ' ', ''), '　', '') = %s
                    LIMIT 1""",
                (author, (w.title_zh or "").replace(" ", "")),
            )
            if not rows:
                continue
            theirs = norm(rows[0]["body"])

            # 逐字比较，取第一处不一致
            n = min(len(mine), len(theirs))
            i = 0
            while i < n and mine[i] == theirs[i]:
                i += 1
            if i >= n:
                continue  # 完全一致

            # 差异片段：从 i 起，各自取到重新同步为止（最多 6 字）
            j = i
            while j < n and j - i < 6 and mine[j] != theirs[j]:
                j += 1
            a, b = mine[i:j], theirs[i:j]
            if not a or not b:
                continue

            ctx = mine[max(0, i - 8) : i]
            known = {(x.base_text, x.variant_text) for x in w.apparatus.all()}
            dup = (a, b) in known or (b, a) in known

            found.append(
                {
                    "work": w.key,
                    "ours": a,
                    "corpus": b,
                    "context": ctx,
                    "dup": dup,
                }
            )

        self.stdout.write(f"\n可比对作品（繁体取自底本）：{Work.objects.filter(traditional_derived=False).count()} 条")
        self.stdout.write(f"发现异文候选：{len(found)} 处（其中已记录 {sum(1 for f in found if f['dup'])} 处）\n")
        for f in found[:20]:
            mark = "（已有）" if f["dup"] else ""
            self.stdout.write(f"  {f['work']}  …{f['context']}【{f['ours']}】↔【{f['corpus']}】 {mark}")

        if not opts["write"]:
            self.stdout.write("\n（只报告，未写入；加 --write 落库）")
            if opts["json"]:
                Path(opts["json"]).write_text(json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")
            return

        written = 0
        with transaction.atomic():
            for f in found:
                if f["dup"]:
                    continue
                w = Work.objects.get(key=f["work"])
                Apparatus.objects.create(
                    work=w,
                    locator={},
                    base_edition=(w.source_edition.key if w.source_edition else ""),
                    base_text=f["ours"],
                    variant_text=f["corpus"],
                    judgement="pending",
                    basis=f"本站正文作「{f['ours']}」，全唐诗语料作「{f['corpus']}」（上下文：{f['context']}…）；尚未比对原始版本，待裁。",
                )
                written += 1
        self.stdout.write(f"\n已写入 {written} 条校记（judgement=pending）")
