"""
关键词检索：向量索引不可用时的兜底方案。

数据来源与向量检索一致（knowledge/ 下的 CSV / Markdown / JSON），
保证两种检索召回的是同一批内容，不会出现"两套知识库"。
"""

import os
import re
from typing import Dict, List, Optional, Tuple

from knowledge_loader import FAQ_JSON, POLICIES_MD, PRODUCTS_CSV, load_chunks

_CJK = re.compile(r"[\u4e00-\u9fff]")


def _tokens(text: str) -> List[str]:
    """英文按词切，中文按二元组切，兼顾两种语言。"""
    lower = (text or "").lower()
    latin = re.findall(r"[a-z0-9]{3,}", lower)
    bigrams = [
        lower[i:i + 2]
        for i in range(len(lower) - 1)
        if _CJK.match(lower[i]) and _CJK.match(lower[i + 1])
    ]
    return latin + bigrams


class KnowledgeBase:
    def __init__(self):
        self.chunks: List[Dict] = []
        self._stamp = None
        self.reload_if_changed()

    def _files_stamp(self):
        stamp = []
        for path in (PRODUCTS_CSV, POLICIES_MD, FAQ_JSON):
            try:
                stamp.append(os.path.getmtime(path))
            except OSError:
                stamp.append(0)
        return tuple(stamp)

    def reload_if_changed(self) -> None:
        stamp = self._files_stamp()
        if stamp == self._stamp:
            return
        try:
            self.chunks = load_chunks()
            self._stamp = stamp
        except Exception as e:
            print(f"⚠️ 知识库加载失败: {e}")

    def search(self, query: str, limit: int = 2,
               categories: Optional[List[str]] = None) -> List[Tuple[str, str]]:
        self.reload_if_changed()
        if not query:
            return []

        tokens = _tokens(query)
        q_lower = query.lower()
        scored: List[Tuple[int, Dict]] = []

        for chunk in self.chunks:
            if categories and chunk.get("category") not in categories:
                continue
            text = f"{chunk.get('title','')}\n{chunk.get('content','')}".lower()
            score = sum(1 for t in tokens if t in text)
            if chunk.get("category") and chunk["category"] in q_lower:
                score += 3
            if score:
                scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [(c.get("title", ""), c.get("content", "")) for _, c in scored[:limit]]

    def as_prompt_block(self, query: str, limit: int = 2,
                        categories: Optional[List[str]] = None) -> str:
        hits = self.search(query, limit=limit, categories=categories)
        if not hits:
            return ""
        return "\n\n".join(f"### {title}\n{body}" for title, body in hits)


default_knowledge_base = KnowledgeBase()
