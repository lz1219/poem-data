"""语料层数据访问：56,968 首诗、1,301 卷原文、3,895 位作者都在 PostgreSQL 里。

这些表不是 Django 模型（体量大、只读），所以直接用 SQL 访问。
连接走 psycopg 连接池；DSN 支持 DATABASE_URL 或 PGHOST 等分段变量。
"""
import os

_pool = None


def dsn() -> str:
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("postgres"):
        return url
    host = os.getenv("PGHOST")
    if not host:
        return ""
    user = os.getenv("PGUSER", "")
    pwd = os.getenv("PGPASSWORD", "")
    port = os.getenv("PGPORT", "5432")
    db = os.getenv("PGDATABASE", "jiangshan")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def init_pool() -> None:
    global _pool
    d = dsn()
    if not d:
        print("[warn] 未配置语料库连接，语料相关接口将返回 503")
        return
    try:
        from psycopg_pool import ConnectionPool

        _pool = ConnectionPool(d, min_size=1, max_size=4, timeout=5, open=True)
        print("[ok] 语料库连接池已建立")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 语料库连接池失败：{e}")


def available() -> bool:
    return _pool is not None


def query(sql: str, params: tuple = ()) -> list[dict]:
    if _pool is None:
        raise RuntimeError("语料库未连接")
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


def one(sql: str, params: tuple = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None
