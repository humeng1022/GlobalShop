"""
向量检索：bge-m3 向量 + 余弦相似度。

向量和知识库原文都放在应用库（SQLite / Postgres）里，不依赖额外向量服务。
数据量在几万 chunk 以内时，Python + numpy 暴力检索完全够用（毫秒级）。
"""

from typing import Any, Dict, List, Optional

import numpy as np

from config import EMBEDDING_MODEL
from db import delete_stale, fetch_chunks, fetch_vectors, upsert_chunks, upsert_vectors
from embedding_client import embed_query, embed_texts
from knowledge_loader import load_chunks


def _to_blob(vec: List[float]) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def _from_blob(blob: Any) -> np.ndarray:
    return np.frombuffer(bytes(blob), dtype=np.float32)


def build_index(force: bool = False, verbose: bool = True) -> Dict[str, Any]:
    """把 knowledge/ 下的内容 + 后台新增条目切块、向量化并写入数据库。"""
    file_chunks = load_chunks()

    # 后台在管理页新增的条目（source=admin）只存在 DB 里，重建时不能丢
    admin_chunks = [row for row in fetch_chunks() if row.get("source") == "admin"]
    chunks = file_chunks + admin_chunks

    if not chunks:
        return {"chunks": 0, "embedded": 0, "removed": 0, "model": EMBEDDING_MODEL}

    upsert_chunks(file_chunks)

    existing = {row["chunk_id"] for row in fetch_vectors() if row["model"] == EMBEDDING_MODEL}
    todo = [c for c in chunks if force or c["chunk_id"] not in existing]

    embedded = 0
    batch_size = 16
    for start in range(0, len(todo), batch_size):
        batch = todo[start:start + batch_size]
        vectors = embed_texts([c["content"] for c in batch])
        rows = [
            {
                "chunk_id": c["chunk_id"],
                "model": EMBEDDING_MODEL,
                "dim": len(v),
                "vector": _to_blob(v),
            }
            for c, v in zip(batch, vectors)
        ]
        upsert_vectors(rows)
        embedded += len(batch)
        if verbose:
            print(f"  向量化 {embedded}/{len(todo)}")

    removed = delete_stale([c["chunk_id"] for c in chunks])

    return {
        "chunks": len(chunks),
        "embedded": embedded,
        "removed": removed,
        "model": EMBEDDING_MODEL,
        "dim": len(vectors[0]) if todo else 0,
    }


def has_index() -> bool:
    try:
        return len(fetch_vectors()) > 0
    except Exception:
        return False


def search(query: str, top_k: int = 4, category: Optional[str] = None,
           min_score: float = 0.30) -> List[Dict[str, Any]]:
    """按余弦相似度召回知识片段。"""
    if not query or not query.strip():
        return []

    rows = [r for r in fetch_vectors() if r["model"] == EMBEDDING_MODEL]
    if not rows:
        return []

    chunks = {c["chunk_id"]: c for c in fetch_chunks()}
    rows = [r for r in rows if r["chunk_id"] in chunks]
    if category:
        rows = [r for r in rows if (chunks[r["chunk_id"]].get("category") or "") == category]
    if not rows:
        return []

    q = np.asarray(embed_query(query), dtype=np.float32)
    q_norm = q / (np.linalg.norm(q) + 1e-8)

    matrix = np.vstack([_from_blob(r["vector"]) for r in rows])
    matrix = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8)
    scores = matrix @ q_norm

    order = np.argsort(scores)[::-1][:top_k]
    results: List[Dict[str, Any]] = []
    for idx in order:
        score = float(scores[idx])
        if score < min_score:
            continue
        row = rows[int(idx)]
        chunk = chunks[row["chunk_id"]]
        results.append({
            "chunk_id": row["chunk_id"],
            "score": round(score, 4),
            "title": chunk.get("title") or "",
            "content": chunk.get("content") or "",
            "source": chunk.get("source") or "",
            "category": chunk.get("category") or "",
        })
    return results


def stats() -> Dict[str, Any]:
    try:
        chunk_count = len(fetch_chunks())
        vector_count = len(fetch_vectors())
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "chunks": chunk_count,
        "vectors": vector_count,
        "model": EMBEDDING_MODEL,
        "indexed": vector_count > 0,
    }


def upsert_admin_entry(chunk_id: str, title: str, content: str, category: str = "admin") -> Dict[str, Any]:
    """后台新增/编辑知识条目：写原文 + 立即向量化。"""
    from db import upsert_admin_chunk

    upsert_admin_chunk(chunk_id, title, content, category)
    vector = embed_texts([content])[0]
    upsert_vectors([{
        "chunk_id": chunk_id,
        "model": EMBEDDING_MODEL,
        "dim": len(vector),
        "vector": _to_blob(vector),
    }])
    return {"chunk_id": chunk_id, "dim": len(vector)}
