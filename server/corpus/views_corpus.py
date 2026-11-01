"""语料接口：把库里沉睡的三块资产露出来。

  /api/corpus/authors            作者列表（3,895 位，带作品数）
  /api/corpus/authors/<name>     某作者的诗（分页）
  /api/corpus/poems/<id>         单首
  /api/texts                     书目（含卷数）
  /api/texts/<book_id>           某书的卷列表
  /api/texts/juan/<unit_id>      某卷全文（分段落）
"""
from functools import lru_cache

from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import db


def _unavailable():
    return Response({"detail": "语料库未连接"}, status=503)


def _clip(text: str, n: int = 60) -> str:
    t = (text or "").replace("\n", " ").strip()
    return t if len(t) <= n else t[:n] + "…"


@lru_cache(maxsize=1)
def _has_simplified() -> bool:
    """author_simplified 列是否存在（存在才按简体匹配）。"""
    try:
        row = db.one(
            "SELECT 1 AS ok FROM information_schema.columns "
            "WHERE table_name='corpus_poem' AND column_name='author_simplified'"
        )
        return bool(row)
    except Exception:  # noqa: BLE001
        return False


@api_view(["GET"])
def authors(request):
    if not db.available():
        return _unavailable()
    q = (request.query_params.get("q") or "").strip()
    limit = min(int(request.query_params.get("limit", 100)), 300)
    offset = max(int(request.query_params.get("offset", 0)), 0)
    col = "coalesce(author_simplified, author)" if _has_simplified() else "author"
    where = f"WHERE {col} LIKE %s" if q else ""
    params: list = [f"%{q}%"] if q else []

    rows = db.query(
        f"""SELECT {col} AS name, count(*) AS poems,
                   count(DISTINCT genre) AS genres
            FROM corpus_poem
            {where}
            GROUP BY 1
            ORDER BY poems DESC
            LIMIT %s OFFSET %s""",
        tuple(params + [limit, offset]),
    )
    total = db.one(f"SELECT count(DISTINCT {col}) AS c FROM corpus_poem {where}", tuple(params))
    return Response({"total": total["c"] if total else 0, "limit": limit, "offset": offset, "items": rows})


@api_view(["GET"])
def author_detail(request, name):
    if not db.available():
        return _unavailable()
    limit = min(int(request.query_params.get("limit", 50)), 200)
    offset = max(int(request.query_params.get("offset", 0)), 0)
    col = "coalesce(author_simplified, author)" if _has_simplified() else "author"

    total = db.one(f"SELECT count(*) AS c FROM corpus_poem WHERE {col} = %s", (name,))
    if not total or total["c"] == 0:
        return Response({"detail": f"语料库中未找到作者：{name}"}, status=404)

    rows = db.query(
        f"""SELECT id, coalesce(nullif(title_display, ''), title) AS title, author, left(coalesce(body_simplified, body), 80) AS head,
                   length(coalesce(body_simplified, body)) AS chars
            FROM corpus_poem
            WHERE {col} = %s
            ORDER BY id
            LIMIT %s OFFSET %s""",
        (name, limit, offset),
    )
    return Response({"name": name, "total": total["c"], "limit": limit, "offset": offset, "items": rows})


@api_view(["GET"])
def poem_detail(request, poem_id: int):
    if not db.available():
        return _unavailable()
    row = db.one(
        """SELECT p.id, coalesce(nullif(p.title_display, ''), p.title) AS title, p.title AS title_raw, p.author, coalesce(p.author_simplified, p.author) AS author_simplified,
                  p.genre, p.body, p.body_simplified, p.book_id, b.title AS book
           FROM corpus_poem p LEFT JOIN book b ON b.id = p.book_id
           WHERE p.id = %s""",
        (poem_id,),
    )
    if not row:
        return Response({"detail": "未找到该诗"}, status=404)
    return Response(row)


@api_view(["GET"])
def texts(request):
    if not db.available():
        return _unavailable()
    rows = db.query(
        """SELECT b.id, b.title, count(t.id) AS juan,
                  sum(length(t.body)) AS chars,
                  max(t.edition) AS edition,
                  count(*) FILTER (WHERE t.punctuated) AS punctuated_juan
           FROM book b JOIN text_unit t ON t.book_id = b.id
           GROUP BY b.id, b.title
           HAVING count(t.id) > 0
           ORDER BY sum(length(t.body)) DESC"""
    )
    return Response({"total": len(rows), "items": rows})


@api_view(["GET"])
def book_detail(request, book_id: int):
    if not db.available():
        return _unavailable()
    book = db.one("SELECT id, title, edition, source_url FROM book WHERE id = %s", (book_id,))
    if not book:
        return Response({"detail": "未找到该书"}, status=404)
    rows = db.query(
        """SELECT id, juan, title, length(body) AS chars, coalesce(punctuated, false) AS punctuated
           FROM text_unit WHERE book_id = %s ORDER BY id""",
        (book_id,),
    )
    return Response({"book": book, "total": len(rows), "juan": rows})


@api_view(["GET"])
def juan_detail(request, unit_id: int):
    if not db.available():
        return _unavailable()
    unit = db.one(
        """SELECT t.id, t.juan, t.title, t.body, t.body_simplified, b.title AS book, b.id AS book_id,
                  coalesce(t.punctuated, false) AS punctuated, t.edition, t.source_url
           FROM text_unit t JOIN book b ON b.id = t.book_id WHERE t.id = %s""",
        (unit_id,),
    )
    if not unit:
        return Response({"detail": "未找到该卷"}, status=404)
    paras = db.query("SELECT seq, body FROM paragraph WHERE unit_id = %s ORDER BY seq", (unit_id,))
    unit["paragraphs"] = paras
    return Response(unit)

CAREER_SQL = """
SELECT p.c_firstyear AS first_year,
       p.c_lastyear  AS last_year,
       p.c_sequence  AS seq,
       o.c_office_chn AS office,
       (SELECT string_agg(a.c_name_chn, '、')
          FROM cbdb."POSTED_TO_ADDR_DATA" pa
          JOIN cbdb."ADDR_CODES" a ON a.c_addr_id = pa.c_addr_id
         WHERE pa.c_posting_id = p.c_posting_id) AS places
FROM cbdb."POSTED_TO_OFFICE_DATA" p
LEFT JOIN cbdb."OFFICE_CODES" o ON o.c_office_id = p.c_office_id
WHERE p.c_personid = %s
ORDER BY p.c_firstyear NULLS LAST, p.c_sequence
"""


@api_view(["GET"])
def person_career(request, key):
    """人物仕历：来自 CBDB 的 59 万条任职记录。"""
    from .models import Person

    if not db.available():
        return _unavailable()
    try:
        p = Person.objects.get(key=key)
    except Person.DoesNotExist:
        return Response({"detail": f"未找到人物：{key}"}, status=404)

    cbdb_id = (p.cbdb_id or "").strip()
    if not cbdb_id.isdigit():
        return Response(
            {
                "person": key,
                "cbdbId": None,
                "items": [],
                "note": "该人物尚未与 CBDB 建立可靠映射（生卒无法互相印证），故不展示仕历。",
            }
        )

    rows = db.query(CAREER_SQL, (int(cbdb_id),))
    bio = db.one(
        'SELECT c_name_chn, c_birthyear, c_deathyear FROM cbdb."BIOG_MAIN" WHERE c_personid = %s',
        (int(cbdb_id),),
    )
    return Response(
        {
            "person": key,
            "cbdbId": cbdb_id,
            "cbdbName": (bio or {}).get("c_name_chn"),
            "span": [(bio or {}).get("c_birthyear"), (bio or {}).get("c_deathyear")],
            "total": len(rows),
            "items": rows,
        }
    )
