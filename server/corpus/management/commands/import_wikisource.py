"""从维基文库导入标点本古籍（按卷）。

为什么用它：
  四庫本（Kanripo / 维基的四庫版）**无标点**；维基文库另有一套**标点本**，
  如「舊唐書/卷1」带完整句读，且为 CC BY-SA / 公有领域。

用法：
  manage.py import_wikisource --page 舊唐書 --book 舊唐書 --limit 5 --dry-run
  manage.py import_wikisource --page 舊唐書 --book 舊唐書
"""
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request

from django.core.management.base import BaseCommand

from corpus import db

API = "https://zh.wikisource.org/w/api.php"
UA = "jiangshan-xingzhi/0.1 (https://github.com/lz1219/poem-data)"

COMMENT = re.compile(r"<!--.*?-->", re.S)
TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
REF = re.compile(r"<ref[^>]*>.*?</ref>", re.S)
TAG = re.compile(r"<[^>]+>")
LINK_PIPE = re.compile(r"\[\[[^\]|]*\|([^\]]*)\]\]")
LINK = re.compile(r"\[\[([^\]]*)\]\]")
BOLD = re.compile(r"'{2,}")


def _get(url: str, timeout: int = 30, retries: int = 4) -> str:
    """用 curl 取数据：Python 的 urllib 在本机走 SSL 会偶发 EOF，curl 稳定。"""
    import subprocess
    import time as _t

    for i in range(retries):
        out = subprocess.run(
            ["curl", "-s", "-m", str(timeout), "--noproxy", "*", "-H", f"User-Agent: {UA}", url],
            capture_output=True,
        )
        txt = out.stdout.decode("utf-8", "replace")
        if txt.strip().startswith("{"):
            return txt
        _t.sleep(1.5 * (i + 1))
    return ""


def api(params: dict) -> dict:
    return json.loads(_get(API + "?" + urllib.parse.urlencode(params)))


def pages_wikitext(titles):
    """一次取多个页面（titles=A|B|C，最多 20 个），返回 {title: text}。"""
    out = {}
    for i in range(0, len(titles), 20):
        chunk = titles[i : i + 20]
        d = api({
            "action": "query", "prop": "revisions", "rvprop": "content",
            "rvslots": "main", "format": "json", "titles": "|".join(chunk),
        })
        for _, p in d.get("query", {}).get("pages", {}).items():
            t = p.get("title")
            rev = p.get("revisions")
            if t and rev:
                out[t] = rev[0]["slots"]["main"].get("*", "")
    return out


def page_wikitext(title: str) -> str:
    d = api({
        "action": "query", "prop": "revisions", "rvprop": "content",
        "rvslots": "main", "format": "json", "titles": title,
    })
    pages = d.get("query", {}).get("pages", {})
    for _, p in pages.items():
        rev = p.get("revisions")
        if rev:
            return rev[0]["slots"]["main"].get("*", "")
    return ""


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


PUNCT = re.compile(r"[，。！？；：]")


class Command(BaseCommand):
    help = "从维基文库导入标点本"

    def add_arguments(self, parser):
        parser.add_argument("--page", required=True, help="目录页，如 舊唐書")
        parser.add_argument("--book", required=True, help="入库书名")
        parser.add_argument("--edition", default="維基文庫 標點本")
        parser.add_argument("--limit", type=int, default=0, help="只导前 N 卷（调试用）")
        parser.add_argument("--delay", type=float, default=0.4, help="每卷间隔秒数")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **o):
        if not db.available():
            self.stderr.write("语料库未连接")
            return

        idx = api({"action": "parse", "page": o["page"], "prop": "links", "format": "json"})
        links = [l["*"] for l in idx.get("parse", {}).get("links", []) if l.get("*", "").startswith(o["page"] + "/")]
        links.sort(key=lambda s: int(re.sub(r"\D", "", s) or 0))
        self.stdout.write(f"目录页 {o['page']}：找到 {len(links)} 卷")
        if o["limit"]:
            links = links[: o["limit"]]
        if not links:
            self.stderr.write("没有子页面，检查 --page")
            return

        if not o["dry_run"]:
            db.execute(
                """INSERT INTO book (title, edition, source_url) VALUES (%s,%s,%s)
                   ON CONFLICT (title) DO UPDATE SET edition=EXCLUDED.edition, source_url=EXCLUDED.source_url""",
                (o["book"], o["edition"], "https://zh.wikisource.org/wiki/" + urllib.parse.quote(o["page"])),
            )
            book_id = db.one("SELECT id FROM book WHERE title=%s", (o["book"],))["id"]

        done = punct = chars = 0
        fetched = {}
        for i in range(0, len(links), 20):
            chunk = links[i : i + 20]
            try:
                fetched.update(pages_wikitext(chunk))
            except Exception as e:  # noqa: BLE001
                self.stderr.write(f"  批量取失败（{i}–{i+len(chunk)}）：{e}")
            time.sleep(o["delay"])
            self.stdout.write(f"  已抓取 {len(fetched)}/{len(links)} 卷")

        for title in links:
            text = fetched.get(title, "")
            if not text:
                continue
            paras = to_paragraphs(text)
            if not paras:
                continue
            body = "\n".join(paras)
            juan = title.split("/")[-1]
            chars += len(body)
            has_p = bool(PUNCT.search(body))
            punct += 1 if has_p else 0
            done += 1

            if o["dry_run"]:
                if done <= 2:
                    self.stdout.write(f"  {title}：{len(paras)} 段，{len(body)} 字，标点={has_p}")
            else:
                row = db.one(
                    """INSERT INTO text_unit (book_id, juan, title, body, body_simplified, sha256, edition, source_url, punctuated)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (book_id, juan, edition) DO UPDATE SET
                         body=EXCLUDED.body, body_simplified=EXCLUDED.body_simplified,
                         sha256=EXCLUDED.sha256, punctuated=EXCLUDED.punctuated
                       RETURNING id""",
                    (book_id, juan, f"{o['book']}{juan}", body, body,
                     hashlib.sha256(body.encode()).hexdigest(), o["edition"],
                     "https://zh.wikisource.org/wiki/" + urllib.parse.quote(title), has_p),
                )
                uid = row["id"]
                db.execute("DELETE FROM paragraph WHERE unit_id=%s", (uid,))
                for i, p in enumerate(paras, start=1):
                    db.execute("INSERT INTO paragraph (unit_id, seq, body) VALUES (%s,%s,%s)", (uid, i, p))
                if done % 20 == 0:
                    self.stdout.write(f"  …已入库 {done}/{len(links)}")

            time.sleep(o["delay"])

        self.stdout.write(f"完成：{done} 卷，有标点 {punct} 卷，共 {chars} 字")
