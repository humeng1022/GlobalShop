"""
Embedding 客户端：调用 OpenAI 兼容的 /embeddings 接口（默认硅基流动 bge-m3）。
"""

import time
from typing import List

import requests

from config import (
    EMBEDDING_BASE_URL,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MODEL,
    HTTP_MAX_RETRIES,
    OPENAI_API_KEY,
)

# bge-m3 固定 1024 维；换模型时可通过环境变量覆盖
EMBEDDING_DIM = 1024


def _endpoint() -> str:
    return EMBEDDING_BASE_URL.rstrip("/") + "/embeddings"


def embed_texts(texts: List[str], batch_size: int = None, timeout: int = 60) -> List[List[float]]:
    """批量向量化，返回与输入等长的向量列表。"""
    if not texts:
        return []
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY 未配置，无法调用 embedding 接口")

    batch_size = batch_size or EMBEDDING_BATCH_SIZE
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    vectors: List[List[float]] = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        payload = {"model": EMBEDDING_MODEL, "input": batch}

        last_error = None
        for attempt in range(HTTP_MAX_RETRIES):
            try:
                resp = requests.post(_endpoint(), json=payload, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    # 部分服务不保证返回顺序，按 index 排序
                    data = sorted(data, key=lambda d: d.get("index", 0))
                    vectors.extend(item["embedding"] for item in data)
                    last_error = None
                    break
                if resp.status_code == 429:
                    wait = 10 * (attempt + 1)
                    print(f"⚠️ embedding 限流，{wait}s 后重试…")
                    time.sleep(wait)
                    last_error = RuntimeError(f"429: {resp.text[:200]}")
                    continue
                raise RuntimeError(f"embedding 失败 {resp.status_code}: {resp.text[:300]}")
            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt == HTTP_MAX_RETRIES - 1:
                    break
                time.sleep(3 * (attempt + 1))
        if last_error:
            raise last_error

    if len(vectors) != len(texts):
        raise RuntimeError(f"embedding 返回数量不匹配: {len(vectors)} != {len(texts)}")
    return vectors


def embed_query(text: str) -> List[float]:
    return embed_texts([text])[0]
