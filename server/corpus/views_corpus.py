"""语料接口：把库里沉睡的三块资产露出来。

  /api/corpus/authors            作者列表（3,895 位，带作品数）
  /api/corpus/authors/<name>     某作者的诗（分页）
  /api/corpus/poems/<id>         单首
  /api/texts                     书目（含卷数）
  /api/texts/<book_id>           某书的卷列表
  /api/texts/juan/<unit_id>      某卷全文（分段落）
"""
from functools import lru_cache
import unicodedata

from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import db


def _unavailable():
    return Response({"detail": "语料库未连接"}, status=503)


@api_view(["GET"])
def work_link_candidates(request, key):
    if not db.available():
        return _unavailable()
    from .literary_links import work_candidates
    return Response({'items':work_candidates(key), 'scope':'候选关联·未经人工审校'})


@api_view(["GET"])
def poem_link_candidates(request, poem_id):
    if not db.available():
        return _unavailable()
    from .literary_links import poem_candidates
    return Response({'items':poem_candidates(poem_id), 'scope':'候选关联·未经人工审校'})


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
    from .corpus_origins import attach_poem
    attach_poem(row)
    return Response(row)


@api_view(["GET"])
def texts(request):
    if not db.available():
        return _unavailable()
    rows = db.query(
        """WITH units AS (
            SELECT book_id,count(*) AS juan,sum(length(body)) AS chars,max(edition) AS edition,
                count(*) FILTER (WHERE punctuated) AS punctuated_juan FROM text_unit GROUP BY book_id
        ), poems AS (
            SELECT book_id,count(*) AS poems,sum(length(body)) AS chars,
                count(*) FILTER(WHERE body ~ '[，。！？；：]') AS punctuated_poems FROM corpus_poem GROUP BY book_id
        ) SELECT b.id,b.title,coalesce(u.juan,0) AS juan,coalesce(p.poems,0) AS poems,
            coalesce(u.chars,0)+coalesce(p.chars,0) AS chars,coalesce(u.edition,b.edition) AS edition,
            coalesce(u.punctuated_juan,0) AS punctuated_juan,coalesce(p.punctuated_poems,0) AS punctuated_poems
        FROM book b LEFT JOIN units u ON u.book_id=b.id LEFT JOIN poems p ON p.book_id=b.id
        WHERE u.juan>0 OR p.poems>0 ORDER BY chars DESC"""
    )
    from .reading import converter
    cc, _ = converter()
    for book in rows:
        book['title_simplified'] = cc.convert(book['title']) if cc else book['title']
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
    from .corpus_origins import attach_book
    attach_book(book, rows)
    result = {"book": book, "total": len(rows), "juan": rows}
    if not rows:
        try:
            limit = max(1, min(int(request.query_params.get('limit', 50)), 200))
            offset = max(0, int(request.query_params.get('offset', 0)))
        except (ValueError, TypeError):
            return Response({'detail': '分页参数必须是整数'}, status=400)
        q = (request.query_params.get('q') or '').strip()
        from .reading import query_forms
        condition = '''book_id=%s AND (%s='' OR EXISTS(SELECT 1 FROM unnest(%s::text[]) f(form)
            WHERE strpos(lower(coalesce(author,'') || E'\n' || coalesce(title,'') || E'\n' || coalesce(body,'')),lower(form))>0))'''
        params = (book_id, q, query_forms(q))
        total = db.one('SELECT count(*) AS c FROM corpus_poem WHERE ' + condition, params)
        result.update({'poemTotal': total['c'], 'poemOffset': offset, 'poemLimit': limit,
            'poemQuery': q, 'poems': db.query('''SELECT id,title,author,left(coalesce(body_simplified,body),80) AS head
                FROM corpus_poem WHERE ''' + condition + ' ORDER BY id LIMIT %s OFFSET %s', params + (limit, offset))})
    return Response(result)


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
    paras = db.query("SELECT id, seq, body FROM paragraph WHERE unit_id = %s ORDER BY seq", (unit_id,))
    from .corpus_origins import attach_unit
    attach_unit(unit, paras)
    from .paragraph_explanations import attach_explanations
    attach_explanations(unit, paras)
    unit["paragraphs"] = paras
    from .reading import attach_reading
    attach_reading(unit, paras)
    return Response(unit)


def matching_text(q, limit, book_id=None):
    """Literal original/available simplified text search; snippets retain their source form."""
    if not db.available():
        return None
    from .reading import query_forms
    return db.query("""WITH matches AS (
        SELECT t.id,t.book_id,b.title AS book,t.title,t.juan,t.edition,t.source_url,
            needle.form AS matched_query,
            CASE WHEN strpos(lower(t.body),lower(needle.form))>0 THEN t.body ELSE t.body_simplified END AS matched_body,
            CASE WHEN strpos(lower(t.body),lower(needle.form))>0 THEN 'original' ELSE 'simplified' END AS matched_field
        FROM public.text_unit t JOIN public.book b ON b.id=t.book_id
        CROSS JOIN LATERAL (
            SELECT form FROM unnest(%s::text[]) WITH ORDINALITY AS f(form,n)
            WHERE strpos(lower(t.body),lower(form))>0 OR strpos(lower(t.body_simplified),lower(form))>0
            ORDER BY n LIMIT 1
        ) needle
        WHERE (%s::integer IS NULL OR t.book_id=%s)
        ORDER BY t.id LIMIT %s
    ) SELECT id,book_id,book,title,juan,edition,source_url,matched_field,matched_query,
        substring(matched_body FROM greatest(1,strpos(lower(matched_body),lower(matched_query))-24) FOR 100) AS snippet
      FROM matches ORDER BY id""", (query_forms(q), book_id, book_id, limit))

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

@api_view(["GET"])
def work_corpus_text(request, key):
    """返回同作者、同题且首句对应的候选文本，仍需审校。"""
    from .models import Work

    if not db.available():
        return _unavailable()
    w = Work.objects.select_related("author").filter(key=key).first()
    if not w:
        return Response({"detail": f"未找到作品：{key}"}, status=404)

    author = (w.author.zh if w.author else "") or ""
    title = (w.title_zh or "").replace(" ", "")
    # 题名与别名都转成简体后比对（语料题名是繁体，如「出師表」对「出师表」）
    cands = {title}
    for a in (w.aliases or []):
        if a:
            cands.add(str(a).replace(" ", ""))
    rows = db.query(
        """SELECT id, coalesce(nullif(title_display, ''), title) AS title,
                  title AS title_raw, author, body, coalesce(body_simplified, body) AS body_simplified
             FROM corpus_poem
            WHERE coalesce(author_simplified, author) = %s
              AND (
                replace(replace(coalesce(title_simp, title), ' ', ''), '　', '') = ANY(%s)
                OR EXISTS (
                  SELECT 1 FROM unnest(string_to_array(
                    translate(replace(replace(coalesce(title_simp, title), ' ', ''), '　', ''),
                              '・·', '··'), '·')) AS title_part
                  WHERE title_part = ANY(%s)
                )
              )
            ORDER BY id""",
        (author, list(cands), list(cands)),
    )
    matches = _matching_corpus_texts(w.paragraphs_simplified or w.paragraphs or [], rows)
    # 组诗、异体字或词牌别名可能使题名检索漏掉同一篇；仍须作者及正文锚点对应。
    if not matches:
        paragraphs = w.paragraphs_simplified or w.paragraphs or []
        prefix = _corpus_search_prefix(paragraphs)
        if prefix:
            fallback = db.query(
                """SELECT id, coalesce(nullif(title_display, ''), title) AS title,
                          title AS title_raw, author, body, coalesce(body_simplified, body) AS body_simplified
                     FROM corpus_poem
                    WHERE coalesce(author_simplified, author) = %s
                      AND strpos(coalesce(body_simplified, body), %s) > 0
                    ORDER BY id LIMIT 100""",
                (author, prefix),
            )
            matches = _matching_corpus_texts(paragraphs, fallback)
    return Response({"work": key, "author": author, "title": w.title_zh, "matches": matches,
                     "scope": "候选对照·未经人工审校"})


def _corpus_search_prefix(paragraphs):
    for paragraph in paragraphs:
        run = ''
        for char in paragraph:
            if char.isspace() or unicodedata.category(char).startswith(('P', 'Z')):
                if len(run) >= 4:
                    return run[:4]
                run = ''
            else:
                run += char
        if len(run) >= 4:
            return run[:4]
    return ''


def _matching_corpus_texts(paragraphs, rows):
    def plain(text):
        return ''.join(c for c in text if not c.isspace() and not unicodedata.category(c).startswith(('P', 'Z')))

    original = plain(''.join(paragraphs))
    # 短于八字的摘录不足以区分同词牌作品，宁可不显示。
    if len(original) < 8:
        return []
    anchor = original[:min(12, len(original))]
    return [row for row in rows if anchor in plain(row.get('body_simplified') or row.get('body') or '')][:3]

@api_view(["GET"])
def person_timeline(request, key):
    """作者年表：生卒 + 行迹站点 + 作品系年，合并成一条时间轴。"""
    from .models import Journey, Person, Work

    p = Person.objects.filter(key=key).first()
    if not p:
        return Response({"detail": f"未找到人物：{key}"}, status=404)

    events = []
    if p.born:
        events.append({"year": p.born, "kind": "life", "title": "生", "place": "", "source": ""})
    if p.died:
        events.append({"year": p.died, "kind": "life", "title": "卒", "place": "", "source": ""})

    j = Journey.objects.prefetch_related("stops").filter(person=p).first()
    if not j and p.journey_key:
        j = Journey.objects.prefetch_related("stops").filter(key=p.journey_key).first()
    if j:
        for s in j.stops.all():
            if s.year:
                events.append({
                    "year": s.year,
                    "kind": "office",
                    "title": s.title_zh,
                    "place": s.place_ancient,
                    "modern": s.place_modern,
                    "source": s.source,
                })

    works = Work.objects.filter(author=p).order_by("year")
    for w in works:
        if w.year:
            events.append({
                "year": w.year,
                "kind": "work",
                "title": w.title_zh,
                "place": w.place_zh or "",
                "key": w.key,
                "source": w.source_edition.key if w.source_edition else "",
            })

    events.sort(key=lambda e: (e["year"] or 0, {"life": 0, "office": 1, "work": 2}[e["kind"]]))
    return Response({
        "person": {"key": p.key, "zh": p.zh, "span": [p.born, p.died]},
        "journey": j.title_zh if j else None,
        "total": len(events),
        "events": events,
    })

@api_view(["GET"])
def person_relations(request, key):
    """人物关系：CBDB 亲属（KIN_DATA 56 万）与交游（ASSOC_DATA 19 万）。"""
    from .models import Person

    p = Person.objects.filter(key=key).first()
    if not p:
        return Response({"detail": f"未找到人物：{key}"}, status=404)
    if not db.available():
        return _unavailable()
    if not (p.cbdb_id or "").isdigit():
        return Response({"cbdb": None, "kinship": [], "assoc": [], "note": "未映射 CBDB，无关系数据"})

    pid = int(p.cbdb_id)
    kin = db.query(
        """SELECT b.c_name_chn AS name, b.c_personid AS pid, kc.c_kinrel_chn AS relation
             FROM cbdb."KIN_DATA" k
             JOIN cbdb."BIOG_MAIN" b ON b.c_personid = k.c_kin_id
             LEFT JOIN cbdb."KINSHIP_CODES" kc ON kc.c_kincode = k.c_kin_code
            WHERE k.c_personid = %s
            ORDER BY kc.c_pick_sorting NULLS LAST, b.c_name_chn
            LIMIT 40""",
        (pid,),
    )
    assoc = db.query(
        """SELECT b.c_name_chn AS name, b.c_personid AS pid, count(*) AS times,
                  min(CASE WHEN a.c_assoc_first_year > 0 THEN a.c_assoc_first_year END) AS first_year
             FROM cbdb."ASSOC_DATA" a
             JOIN cbdb."BIOG_MAIN" b ON b.c_personid = a.c_assoc_id
            WHERE a.c_personid = %s AND a.c_assoc_id > 0
            GROUP BY 1, 2
            ORDER BY times DESC, first_year NULLS LAST
            LIMIT 30""",
        (pid,),
    )
    # 关系里的人若也在本站人物表（按 CBDB id 对），给出可点击的 key
    from .models import Person as _P

    ids = {str(r["pid"]) for r in (kin + assoc) if r.get("pid")}
    mapping = {x.cbdb_id: x.key for x in _P.objects.filter(cbdb_id__in=ids).only("key", "cbdb_id")}
    for r in kin + assoc:
        r["key"] = mapping.get(str(r.get("pid") or ""), "")

    return Response({
        "cbdb": p.cbdb_id,
        "kinship": kin,
        "assoc": assoc,
        "total": {"kinship": len(kin), "assoc": len(assoc)},
    })
