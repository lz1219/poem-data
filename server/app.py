"""
江山行止 · 文献 API（Python / FastAPI）

数据分工
  策展内容（作品/人物/行迹/评点） → 启动时从 data/*.json 读入内存，<1ms 响应
  大规模检索（诗/原文卷）        → PostgreSQL，带 TTL 缓存

环境变量
  PORT            监听端口（默认 8081）
  DATA_DIR        数据目录（默认 <repo>/data）
  PUBLIC_DIR      前端目录（默认 <repo>/public）
  PGDATABASE_URL  PostgreSQL 连接串；不设则检索类端点降级
  ADMIN_TOKEN     预留；不设则后台关闭
  CACHE_TTL       检索缓存秒数（默认 60）
"""
import os
import json
import time
import threading
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

BASE = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR") or (BASE / "data"))
PUBLIC_DIR = Path(os.getenv("PUBLIC_DIR") or (BASE.parent / "public"))
PGDSN = os.getenv("PGDATABASE_URL") or ""
CACHE_TTL = int(os.getenv("CACHE_TTL", "60"))
PORT = int(os.getenv("PORT", "8081"))

READ_ONLY_HINT = "该接口只读；数据修改请走 data/*.json"


# ────────────────────────────── 策展内容 ──────────────────────────────
class Store:
    def __init__(self) -> None:
        self.works: dict[str, dict] = {}
        self.persons: dict[str, dict] = {}
        self.journeys: dict[str, dict] = {}
        self.loaded_at: float = 0.0
        self._lock = threading.Lock()

    def load(self) -> None:
        works, persons, journeys = {}, {}, {}
        for f in sorted((DATA_DIR / "works").glob("*.json")):
            w = json.loads(f.read_text("utf-8"))
            works[w["key"]] = w
        for f in sorted((DATA_DIR / "persons").glob("*.json")):
            p = json.loads(f.read_text("utf-8"))
            persons[p["key"]] = p
        for f in sorted((DATA_DIR / "journeys").glob("*.json")):
            j = json.loads(f.read_text("utf-8"))
            journeys[j["key"]] = j
        with self._lock:
            self.works, self.persons, self.journeys = works, persons, journeys
            self.loaded_at = time.time()

    def index(self) -> dict:
        """与前端 data/index.json 完全同形，便于无缝切换。"""
        return {
            "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.loaded_at)),
            "works": [
                {
                    "key": w["key"],
                    "titleZh": w.get("titleZh"),
                    "authorKey": w.get("authorKey"),
                    "genre": w.get("genre"),
                    "level": w.get("level"),
                    "year": (w.get("composed") or {}).get("year"),
                    "traditionalDerived": bool((w.get("text") or {}).get("traditionalDerived")),
                    "apparatus": len(w.get("apparatus") or []),
                    "hasComments": bool(w.get("commentaryFile")),
                    "file": f"/api/works/{w['key']}",
                }
                for w in self.works.values()
            ],
            "persons": [
                {
                    "key": p["key"],
                    "zh": p.get("zh"),
                    "span": p.get("span"),
                    "hasJourney": bool(p.get("journeyKey")),
                    "file": f"/api/persons/{p['key']}",
                }
                for p in self.persons.values()
            ],
            "journeys": [
                {
                    "key": j["key"],
                    "titleZh": j.get("titleZh"),
                    "stops": len(j.get("stops") or []),
                    "origin": j.get("origin"),
                    "file": f"/api/journeys/{j['key']}",
                }
                for j in self.journeys.values()
            ],
        }

    def works_by_author(self, author_key: str) -> list[dict]:
        return [w for w in self.works.values() if w.get("authorKey") == author_key]


store = Store()


# ────────────────────────────── PG 与缓存 ──────────────────────────────
class Cache:
    def __init__(self, ttl: int) -> None:
        self.ttl = ttl
        self._d: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, k: str):
        with self._lock:
            hit = self._d.get(k)
        if hit and time.time() - hit[0] < self.ttl:
            return hit[1]
        return None

    def put(self, k: str, v: Any) -> Any:
        with self._lock:
            self._d[k] = (time.time(), v)
        return v


cache = Cache(CACHE_TTL)
_pool = None


def init_pool() -> None:
    global _pool
    if not PGDSN:
        print("[warn] 未配置 PGDATABASE_URL，检索类端点将返回 503")
        return
    try:
        from psycopg_pool import ConnectionPool

        _pool = ConnectionPool(PGDSN, min_size=1, max_size=4, timeout=5, open=True)
        print("[ok] PostgreSQL 连接池已建立")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 连接池建立失败：{e}")


def pg_query(sql: str, params: tuple = ()) -> list[dict]:
    if _pool is None:
        raise HTTPException(status_code=503, detail="检索服务未就绪（未配置数据库）")
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


def snippet(text: str, q: str, width: int = 36) -> str:
    i = text.find(q)
    if i < 0:
        return text[: width * 2]
    a, b = max(0, i - width), min(len(text), i + len(q) + width)
    return ("…" if a else "") + text[a:b] + ("…" if b < len(text) else "")


# ────────────────────────────── 应用 ──────────────────────────────
app = FastAPI(
    title="江山行止 · 文献 API",
    version="0.1.0",
    description="只读文献数据。策展内容来自 data/*.json，检索来自 PostgreSQL。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    store.load()
    init_pool()
    print(f"[ok] 已载入 作品 {len(store.works)} / 人物 {len(store.persons)} / 行迹 {len(store.journeys)}")


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    db_ok = False
    if _pool is not None:
        try:
            with _pool.connection() as c:
                with c.cursor() as cur:
                    cur.execute("SELECT 1")
                    db_ok = cur.fetchone()[0] == 1
        except Exception:  # noqa: BLE001
            db_ok = False
    return {"ok": True, "db": db_ok, "works": len(store.works), "readOnly": READ_ONLY_HINT}


@app.get("/api/meta", tags=["meta"])
def meta() -> dict:
    return {
        "works": len(store.works),
        "persons": len(store.persons),
        "journeys": len(store.journeys),
        "loadedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(store.loaded_at)),
        "schemaVersion": "1.0",
    }


@app.get("/api/index", tags=["meta"])
def index() -> dict:
    return store.index()


@app.get("/api/works", tags=["works"])
def list_works(
    genre: Optional[str] = None,
    level: Optional[str] = None,
    author: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    rows = list(store.works.values())
    if genre:
        rows = [w for w in rows if w.get("genre") == genre]
    if level:
        rows = [w for w in rows if w.get("level") == level]
    if author:
        rows = [w for w in rows if w.get("authorKey") == author]
    if q:
        ql = q.lower()
        rows = [
            w
            for w in rows
            if ql in (w.get("titleZh") or "").lower()
            or any(ql in str(a).lower() for a in (w.get("aliases") or []))
        ]
    rows.sort(key=lambda w: ((w.get("composed") or {}).get("year") or 0))
    total = len(rows)
    page = rows[offset : offset + limit]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "key": w["key"],
                "titleZh": w.get("titleZh"),
                "titleEn": w.get("titleEn"),
                "authorKey": w.get("authorKey"),
                "genre": w.get("genre"),
                "level": w.get("level"),
                "year": (w.get("composed") or {}).get("year"),
            }
            for w in page
        ],
    }


@app.get("/api/works/{key}", tags=["works"])
def get_work(key: str) -> dict:
    w = store.works.get(key)
    if not w:
        raise HTTPException(status_code=404, detail=f"未找到作品：{key}")
    return w


@app.get("/api/persons", tags=["persons"])
def list_persons(has_journey: Optional[bool] = None) -> dict:
    rows = list(store.persons.values())
    if has_journey is not None:
        rows = [p for p in rows if bool(p.get("journeyKey")) == has_journey]
    rows.sort(key=lambda p: ((p.get("span") or [0, 0])[0] or 0))
    return {"total": len(rows), "items": rows}


@app.get("/api/persons/{key}", tags=["persons"])
def get_person(key: str) -> dict:
    p = store.persons.get(key)
    if not p:
        raise HTTPException(status_code=404, detail=f"未找到人物：{key}")
    out = dict(p)
    out["works"] = [
        {"key": w["key"], "titleZh": w.get("titleZh"), "year": (w.get("composed") or {}).get("year")}
        for w in store.works_by_author(key)
    ]
    if p.get("journeyKey"):
        j = store.journeys.get(p["journeyKey"])
        if j:
            out["journey"] = {"key": j["key"], "titleZh": j.get("titleZh"), "stops": len(j.get("stops") or [])}
    return out


@app.get("/api/journeys", tags=["journeys"])
def list_journeys() -> dict:
    rows = list(store.journeys.values())
    return {
        "total": len(rows),
        "items": [
            {
                "key": j["key"],
                "titleZh": j.get("titleZh"),
                "personKey": j.get("personKey"),
                "stops": len(j.get("stops") or []),
                "origin": j.get("origin"),
            }
            for j in rows
        ],
    }


@app.get("/api/journeys/{key}", tags=["journeys"])
def get_journey(key: str) -> dict:
    j = store.journeys.get(key)
    if not j:
        raise HTTPException(status_code=404, detail=f"未找到行迹：{key}")
    return j


@app.get("/api/comments/{work_key}", tags=["works"])
def get_comments(work_key: str) -> dict:
    w = store.works.get(work_key)
    if not w:
        raise HTTPException(status_code=404, detail=f"未找到作品：{work_key}")
    rel = w.get("commentaryFile")
    if not rel:
        return {"workKey": work_key, "items": [], "note": "未找到可核原文的评点，不编造。"}
    f = DATA_DIR / rel
    if not f.exists():
        return {"workKey": work_key, "items": [], "note": "评点文件缺失"}
    return json.loads(f.read_text("utf-8"))


@app.get("/api/search", tags=["search"])
def search(
    q: str = Query(..., min_length=1),
    scope: str = Query("works", pattern="^(works|corpus|text|all)$"),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """works=策展内容（内存）；corpus=66,968 首诗；text=38,219 段原文；all=合并"""
    q = q.strip()
    out: dict[str, list] = {"works": [], "corpus": [], "text": []}

    if scope in ("works", "all"):
        ql = q.lower()
        for w in store.works.values():
            body = "".join((w.get("text") or {}).get("paragraphsSimplified") or (w.get("text") or {}).get("paragraphs") or [])
            title = (w.get("titleZh") or "").lower()
            if ql in title or q in body:
                out["works"].append(
                    {
                        "key": w["key"],
                        "titleZh": w.get("titleZh"),
                        "authorKey": w.get("authorKey"),
                        "year": (w.get("composed") or {}).get("year"),
                        "snippet": snippet(body, q) if q in body else "",
                    }
                )

    if scope in ("corpus", "all"):
        ck = f"corpus:{q}:{limit}"
        hit = cache.get(ck)
        if hit is None:
            rows = pg_query(
                """
                SELECT title, author, left(coalesce(body_simplified, body), 120) AS head,
                       coalesce(body_simplified, body) AS body
                FROM corpus_poem
                WHERE coalesce(body_simplified, body) LIKE %s
                ORDER BY length(coalesce(body_simplified, body))
                LIMIT %s
                """,
                (f"%{q}%", limit),
            )
            hit = cache.put(
                ck,
                [
                    {
                        "title": r["title"],
                        "author": r["author"],
                        "snippet": snippet(r["body"] or "", q),
                    }
                    for r in rows
                ],
            )
        out["corpus"] = hit

    if scope in ("text", "all"):
        ck = f"text:{q}:{limit}"
        hit = cache.get(ck)
        if hit is None:
            rows = pg_query(
                """
                SELECT p.body, tu.title AS work_title, tu.juan
                FROM paragraph p
                JOIN text_unit tu ON tu.id = p.unit_id
                WHERE p.body LIKE %s
                LIMIT %s
                """,
                (f"%{q}%", limit),
            )
            hit = cache.put(
                ck,
                [
                    {
                        "workTitle": r["work_title"],
                        "juan": r["juan"],
                        "snippet": snippet(r["body"] or "", q),
                    }
                    for r in rows
                ],
            )
        out["text"] = hit

    return {"q": q, "scope": scope, **out}


# ── 静态前端 ──
if PUBLIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(PUBLIC_DIR), html=True), name="public")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
