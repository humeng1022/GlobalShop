"""
数据库访问层：本地 SQLite / 云端 Postgres 自动切换。

- DATABASE_URL 为空或以 sqlite:/// 开头 → SQLite 文件（默认 ./data/app.db）
- postgres:// 或 postgresql://            → psycopg2 连接

当前存两张表：
- kb_chunks   知识库原文（切分后的 chunk）
- kb_vectors  对应的向量（float32 BLOB/BYTEA）
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from config import DATABASE_URL

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_SQLITE = os.path.join(_BASE_DIR, "data", "app.db")

_lock = threading.Lock()
_initialized = False


def is_postgres(url: str) -> bool:
    return url.startswith("postgres://") or url.startswith("postgresql://")


def database_url() -> str:
    return (DATABASE_URL or "").strip()


def is_configured() -> bool:
    return bool(database_url())


def sqlite_path() -> str:
    """当前配置对应的 SQLite 文件路径（Postgres 模式无意义）。"""
    return _sqlite_path(database_url())


def _sqlite_path(url: str) -> str:
    if not url:
        return _DEFAULT_SQLITE
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
    elif url.startswith("sqlite://"):
        path = url[len("sqlite://"):]
    else:
        path = url
    if not os.path.isabs(path):
        path = os.path.join(_BASE_DIR, path)
    return os.path.normpath(path)


def _connect():
    url = database_url()
    if is_postgres(url):
        import psycopg2  # 延迟导入，本地 SQLite 环境不需要
        from psycopg2.extras import RealDictCursor

        conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
        conn.autocommit = True
        return conn
    path = _sqlite_path(url)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _ph() -> str:
    """占位符：SQLite 用 ?，Postgres 用 %s。"""
    return "%s" if is_postgres(database_url()) else "?"


def _exec(conn, sql: str, params: Iterable[Any] = ()):
    sql = sql.replace("?", _ph()) if _ph() == "%s" else sql
    cur = conn.cursor()
    cur.execute(sql, tuple(params))
    return cur


def init_db() -> None:
    """建表（幂等）。"""
    global _initialized
    if _initialized:
        return
    with _lock:
        if _initialized:
            return
        blob_type = "BYTEA" if is_postgres(database_url()) else "BLOB"
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kb_chunks (
                    chunk_id   TEXT PRIMARY KEY,
                    source     TEXT NOT NULL,
                    category   TEXT,
                    title      TEXT,
                    content    TEXT NOT NULL,
                    lang       TEXT,
                    updated_at TEXT
                )
            """)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS kb_vectors (
                    chunk_id TEXT PRIMARY KEY,
                    model    TEXT NOT NULL,
                    dim      INTEGER NOT NULL,
                    vector   {blob_type} NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_threads (
                    thread_id  TEXT PRIMARY KEY,
                    title      TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tracking_numbers (
                    number     TEXT PRIMARY KEY,
                    status_zh  TEXT,
                    status_en  TEXT,
                    location   TEXT,
                    eta        TEXT,
                    note       TEXT,
                    updated_at TEXT
                )
            """)
            conn.commit()
        _initialized = True


def upsert_thread(thread_id: str, title: str = "", touch: bool = True) -> None:
    """记录/更新会话元数据（用于侧栏列表）。"""
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        _exec(conn,
              "INSERT INTO chat_threads (thread_id, title, created_at, updated_at) "
              "VALUES (?,?,?,?) "
              "ON CONFLICT (thread_id) DO UPDATE SET "
              "title = CASE WHEN excluded.title <> '' THEN excluded.title ELSE chat_threads.title END, "
              "updated_at = excluded.updated_at",
              (thread_id, title or "", now, now))
        conn.commit()


def list_threads(limit: int = 100) -> List[Dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        cur = _exec(conn,
                    "SELECT thread_id, title, created_at, updated_at FROM chat_threads "
                    "ORDER BY updated_at DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def get_thread(thread_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        cur = _exec(conn,
                    "SELECT thread_id, title, created_at, updated_at FROM chat_threads WHERE thread_id=?",
                    (thread_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def delete_thread(thread_id: str) -> None:
    init_db()
    with get_conn() as conn:
        _exec(conn, "DELETE FROM chat_threads WHERE thread_id=?", (thread_id,))
        conn.commit()


def rename_thread(thread_id: str, title: str) -> None:
    """重命名会话（侧栏双击/菜单）。"""
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        _exec(conn, "UPDATE chat_threads SET title=?, updated_at=? WHERE thread_id=?",
              ((title or "").strip()[:60], now, thread_id))
        conn.commit()


# ---------------- 知识库（后台新增条目，source=admin）----------------

def list_admin_chunks() -> List[Dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        cur = _exec(conn,
                    "SELECT chunk_id, source, category, title, content, lang, updated_at "
                    "FROM kb_chunks WHERE source='admin' ORDER BY updated_at DESC")
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def upsert_admin_chunk(chunk_id: str, title: str, content: str, category: str = "admin") -> None:
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        _exec(conn,
              "INSERT INTO kb_chunks (chunk_id, source, category, title, content, lang, updated_at) "
              "VALUES (?,?,?,?,?,?,?) "
              "ON CONFLICT (chunk_id) DO UPDATE SET "
              "source='admin', category=excluded.category, title=excluded.title, "
              "content=excluded.content, updated_at=excluded.updated_at",
              (chunk_id, "admin", category, title, content, "bi", now))
        conn.commit()


def delete_chunk(chunk_id: str) -> None:
    init_db()
    with get_conn() as conn:
        _exec(conn, "DELETE FROM kb_vectors WHERE chunk_id=?", (chunk_id,))
        _exec(conn, "DELETE FROM kb_chunks WHERE chunk_id=?", (chunk_id,))
        conn.commit()


# ---------------- 模拟运单 ----------------

def tracking_list() -> List[Dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        cur = _exec(conn,
                    "SELECT number, status_zh, status_en, location, eta, note, updated_at "
                    "FROM tracking_numbers ORDER BY updated_at DESC")
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def tracking_get(number: str) -> Optional[Dict[str, Any]]:
    init_db()
    if not number:
        return None
    with get_conn() as conn:
        cur = _exec(conn,
                    "SELECT number, status_zh, status_en, location, eta, note, updated_at "
                    "FROM tracking_numbers WHERE number=?", (number.strip().upper(),))
        row = cur.fetchone()
    return dict(row) if row else None


def tracking_upsert(number: str, status_zh: str, status_en: str,
                    location: str = "", eta: str = "", note: str = "") -> None:
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        _exec(conn,
              "INSERT INTO tracking_numbers (number, status_zh, status_en, location, eta, note, updated_at) "
              "VALUES (?,?,?,?,?,?,?) "
              "ON CONFLICT (number) DO UPDATE SET "
              "status_zh=excluded.status_zh, status_en=excluded.status_en, location=excluded.location, "
              "eta=excluded.eta, note=excluded.note, updated_at=excluded.updated_at",
              (number.strip().upper(), status_zh, status_en, location, eta, note, now))
        conn.commit()


def tracking_delete(number: str) -> None:
    init_db()
    with get_conn() as conn:
        _exec(conn, "DELETE FROM tracking_numbers WHERE number=?", (number.strip().upper(),))
        conn.commit()


# ---------------- 概览指标 ----------------

def admin_counts() -> Dict[str, int]:
    init_db()
    out: Dict[str, int] = {}
    with get_conn() as conn:
        for key, sql in (
            ("threads", "SELECT COUNT(*) AS c FROM chat_threads"),
            ("kb_chunks", "SELECT COUNT(*) AS c FROM kb_chunks"),
            ("kb_vectors", "SELECT COUNT(*) AS c FROM kb_vectors"),
            ("tracking", "SELECT COUNT(*) AS c FROM tracking_numbers"),
        ):
            cur = _exec(conn, sql)
            row = cur.fetchone()
            out[key] = int(row["c"]) if row else 0
    return out


def upsert_chunks(chunks: List[Dict[str, Any]]) -> None:
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        for c in chunks:
            _exec(conn,
                  "INSERT INTO kb_chunks (chunk_id, source, category, title, content, lang, updated_at) "
                  "VALUES (?,?,?,?,?,?,?) "
                  "ON CONFLICT (chunk_id) DO UPDATE SET "
                  "source=excluded.source, category=excluded.category, title=excluded.title, "
                  "content=excluded.content, lang=excluded.lang, updated_at=excluded.updated_at",
                  (c["chunk_id"], c["source"], c.get("category"), c.get("title"),
                   c["content"], c.get("lang"), now))
        conn.commit()


def upsert_vectors(rows: List[Dict[str, Any]]) -> None:
    init_db()
    with get_conn() as conn:
        for r in rows:
            _exec(conn,
                  "INSERT INTO kb_vectors (chunk_id, model, dim, vector) VALUES (?,?,?,?) "
                  "ON CONFLICT (chunk_id) DO UPDATE SET "
                  "model=excluded.model, dim=excluded.dim, vector=excluded.vector",
                  (r["chunk_id"], r["model"], r["dim"], r["vector"]))
        conn.commit()


def fetch_chunks() -> List[Dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT chunk_id, source, category, title, content, lang FROM kb_chunks")
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def fetch_vectors() -> List[Dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT chunk_id, model, dim, vector FROM kb_vectors")
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def delete_stale(valid_ids: Iterable[str]) -> int:
    """删除知识库里已经不存在的 chunk 及其向量。"""
    valid = list(valid_ids)
    if not valid:
        return 0
    init_db()
    removed = 0
    valid_set = set(valid)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT chunk_id FROM kb_chunks")
        existing = [row["chunk_id"] for row in cur.fetchall()]
        for chunk_id in existing:
            if chunk_id in valid_set:
                continue
            _exec(conn, "DELETE FROM kb_vectors WHERE chunk_id=?", (chunk_id,))
            _exec(conn, "DELETE FROM kb_chunks WHERE chunk_id=?", (chunk_id,))
            removed += 1
        conn.commit()
    return removed


def ping() -> Dict[str, Any]:
    """连通性检查，给管理后台/启动自检用。"""
    url = database_url()
    kind = "postgres" if is_postgres(url) else "sqlite"
    try:
        init_db()
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"ok": True, "kind": kind, "target": "postgres" if kind == "postgres" else _sqlite_path(url)}
    except Exception as e:
        return {"ok": False, "kind": kind, "error": str(e)}
