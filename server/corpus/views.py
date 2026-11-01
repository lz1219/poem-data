"""API 视图：路径与 FastAPI 版保持一致。

/api/health  /api/meta  /api/index
/api/works  /api/works/<key>
/api/persons /api/persons/<key>
/api/journeys /api/journeys/<key>
/api/comments/<workKey>
/api/search?q=&scope=works|corpus|text|all
"""
import os
import time

from django.db.models import Count
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Journey, Person, Work
from .serializers import JourneySerializer, PersonSerializer, WorkListItemSerializer, WorkSerializer

PGDSN = os.getenv("DATABASE_URL", "")
CACHE_TTL = int(os.getenv("CACHE_TTL", "60"))
_cache: dict[str, tuple[float, object]] = {}


def _cache_get(key: str):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    return None


def _cache_put(key: str, value):
    _cache[key] = (time.time(), value)
    return value


def _corpus_dsn() -> str:
    """语料检索用的连接串：统一走 corpus.db.dsn()（优先 CORPUS_DSN）。

    以前这里自己拼 PGHOST，在"业务库与语料库分离"的部署下会连错库。
    """
    from . import db as _db

    return _db.dsn()


def _matching_corpus(q: str, limit: int = 20):
    """检索 66,968 首诗：直连 PostgreSQL，带 60 秒缓存。"""
    ck = f"corpus:{q}:{limit}"
    hit = _cache_get(ck)
    if hit is not None:
        return hit
    dsn = _corpus_dsn()
    if not dsn:
        return None
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT coalesce(nullif(title_display, ''), title) AS title, author, coalesce(body_simplified, body)
                       FROM corpus_poem
                       WHERE coalesce(body_simplified, body) LIKE %s
                       LIMIT %s""",
                    (f"%{q}%", limit),
                )
                rows = cur.fetchall()
        out = []
        for title, author, body in rows:
            i = body.find(q)
            a = max(0, i - 30) if i >= 0 else 0
            out.append({"title": title, "author": author, "snippet": body[a : a + len(q) + 60]})
        return _cache_put(ck, out)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 语料检索失败：{e}")
        return None


@api_view(["GET"])
def health(request):
    db_ok = True
    try:
        Work.objects.exists()
    except Exception:  # noqa: BLE001
        db_ok = False
    return Response({"ok": True, "db": db_ok, "works": Work.objects.count(),
                     "readOnly": "该接口只读；数据修改请在 /admin 或 data/*.json"})


@api_view(["GET"])
def meta(request):
    return Response({
        "works": Work.objects.count(),
        "persons": Person.objects.count(),
        "journeys": Journey.objects.count(),
        "schemaVersion": "1.0",
    })


@api_view(["GET"])
def index(request):
    """首屏索引：一次查询取完所有计数，结果缓存 60 秒。"""
    hit = _cache_get("api:index")
    if hit is not None:
        resp = Response(hit)
        resp["X-Cache"] = "HIT"
        return resp

    works = (
        Work.objects.select_related("author")
        .annotate(_apparatus=Count("apparatus", distinct=True), _comments=Count("commentaries", distinct=True))
        .order_by("key")
    )
    journeys = Journey.objects.annotate(_stops=Count("stops", distinct=True)).select_related("person").order_by("key")

    payload = {
        "generatedAt": None,
        "works": [
            {
                "key": w.key, "titleZh": w.title_zh,
                "authorKey": w.author.key if w.author_id else None,
                "genre": w.genre, "level": w.level, "year": w.year,
                "traditionalDerived": w.traditional_derived,
                "apparatus": w._apparatus,
                "hasComments": w._comments > 0,
                "file": f"/api/works/{w.key}",
            }
            for w in works
        ],
        "persons": [
            {"key": p.key, "zh": p.zh, "span": [p.born, p.died],
             "hasJourney": bool(p.journey_key), "file": f"/api/persons/{p.key}"}
            for p in Person.objects.order_by("key")
        ],
        "journeys": [
            {"key": j.key, "titleZh": j.title_zh, "stops": j._stops,
             "origin": j.origin, "file": f"/api/journeys/{j.key}"}
            for j in journeys
        ],
    }
    _cache_put("api:index", payload)
    resp = Response(payload)
    resp["X-Cache"] = "MISS"
    resp["Cache-Control"] = f"public, max-age={CACHE_TTL}"
    return resp


@api_view(["GET"])
def works(request):
    qs = Work.objects.select_related("author")
    genre = request.query_params.get("genre")
    level = request.query_params.get("level")
    author = request.query_params.get("author")
    q = request.query_params.get("q")
    if genre:
        qs = qs.filter(genre=genre)
    if level:
        qs = qs.filter(level=level)
    if author:
        qs = qs.filter(author__key=author)
    if q:
        qs = qs.filter(title_zh__icontains=q)
    limit = min(int(request.query_params.get("limit", 50)), 200)
    offset = int(request.query_params.get("offset", 0))
    total = qs.count()
    items = qs.order_by("year")[offset : offset + limit]
    return Response({"total": total, "limit": limit, "offset": offset,
                     "items": WorkListItemSerializer(items, many=True).data})


@api_view(["GET"])
def work_detail(request, key):
    try:
        w = Work.objects.select_related("author", "source_edition").prefetch_related("apparatus", "dating").get(key=key)
    except Work.DoesNotExist:
        return Response({"detail": f"未找到作品：{key}"}, status=404)
    return Response(WorkSerializer(w).data)


@api_view(["GET"])
def persons(request):
    qs = Person.objects.all()
    hj = request.query_params.get("has_journey")
    if hj in ("true", "1"):
        qs = qs.exclude(journey_key="")
    elif hj in ("false", "0"):
        qs = qs.filter(journey_key="")
    return Response({"total": qs.count(), "items": PersonSerializer(qs, many=True).data})


@api_view(["GET"])
def person_detail(request, key):
    try:
        p = Person.objects.get(key=key)
    except Person.DoesNotExist:
        return Response({"detail": f"未找到人物：{key}"}, status=404)
    data = PersonSerializer(p).data
    data["works"] = [
        {"key": w.key, "titleZh": w.title_zh, "year": w.year}
        for w in p.works.all()
    ]
    return Response(data)


@api_view(["GET"])
def journeys(request):
    qs = Journey.objects.all()
    return Response({
        "total": qs.count(),
        "items": [{"key": j.key, "titleZh": j.title_zh, "personKey": j.person.key if j.person_id else None,
                   "stops": j.stops.count(), "origin": j.origin} for j in qs],
    })


@api_view(["GET"])
def journey_detail(request, key):
    try:
        j = Journey.objects.prefetch_related("stops", "links").get(key=key)
    except Journey.DoesNotExist:
        return Response({"detail": f"未找到行迹：{key}"}, status=404)
    return Response(JourneySerializer(j).data)


@api_view(["GET"])
def comments(request, work_key):
    try:
        w = Work.objects.get(key=work_key)
    except Work.DoesNotExist:
        return Response({"detail": f"未找到作品：{work_key}"}, status=404)
    items = [{"id": c.id, "critic": c.critic, "dynasty": c.dynasty, "text": c.text,
              "source": c.source, "topic": c.topic, "alsoIn": c.also_in, "status": c.status}
             for c in w.commentaries.filter(status='verified')]
    return Response({"workKey": work_key, "items": items,
                     "note": None if items else "未找到可核原文的评点，不编造。"})


@api_view(["GET"])
def search(request):
    q = (request.query_params.get("q") or "").strip()
    scope = request.query_params.get("scope", "works")
    try:
        limit = max(1, min(int(request.query_params.get("limit", 20)), 100))
        book_id = request.query_params.get('book_id')
        book_id = int(book_id) if book_id is not None else None
    except (ValueError, TypeError):
        return Response({'detail': 'limit和book_id须为整数'}, status=400)
    if not q:
        return Response({"detail": "缺少 q"}, status=400)

    out = {"q": q, "scope": scope, "works": [], "corpus": [], "text": []}

    if scope in ("works", "all"):
        # 作品只有 69 条，直接内存匹配：标题 / 别名 / 正文 / 注释 / 大意 / 背景
        # 之前只查 title_zh，搜「莫听」命中不了《定风波》
        ql = q.lower()
        hits = []
        for w in Work.objects.all().only(
            "key", "title_zh", "aliases", "paragraphs", "paragraphs_simplified", "notes", "meaning", "background", "year"
        ):
            fields = [
                ("标题", w.title_zh or ""),
                ("别名", "、".join(w.aliases or [])),
                ("大意", w.meaning or ""),
                ("背景", w.background or ""),
            ]
            fields += [("正文", p) for p in (w.paragraphs or [])]
            fields += [("正文", p) for p in (w.paragraphs_simplified or [])]
            for n in (w.notes or []):
                if isinstance(n, dict):
                    fields.append(("注释", f"{n.get('term', '')} {n.get('explain', '')}"))
            for label, text in fields:
                i = (text or "").lower().find(ql)
                if i < 0:
                    continue
                a = max(0, i - 24)
                snippet = text[a : a + 80].replace("\n", " ")
                hits.append(
                    {
                        "key": w.key,
                        "titleZh": w.title_zh,
                        "year": w.year,
                        "field": label,
                        "snippet": ("…" if a > 0 else "") + snippet,
                    }
                )
                break
        out["works"] = hits[:limit]

    if scope in ("corpus", "all"):
        out["corpus"] = _matching_corpus(q, limit) or []

    if scope in ('text', 'all'):
        from .views_corpus import matching_text
        hits = matching_text(q, limit, book_id)
        if hits is None and scope == 'text':
            return Response({'detail': '语料库暂未连接'}, status=503)
        out['text'] = hits or []

    return Response(out)
