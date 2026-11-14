"""
知识库加载器：把 knowledge/ 下的 CSV / Markdown / JSON 统一切成可检索的 chunk。

三种来源：
- products.csv  → 每个 SKU 一个 chunk
- policies.md   → 每个 `## 章节` 一个 chunk
- faq.json      → 每条问答一个 chunk

chunk 结构（同时供关键词检索和向量检索使用）：
{chunk_id, source, category, title, content, lang}
"""

import csv
import hashlib
import json
import os
import re
from typing import Any, Dict, List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")

PRODUCTS_CSV = os.path.join(KNOWLEDGE_DIR, "products.csv")
POLICIES_MD = os.path.join(KNOWLEDGE_DIR, "policies.md")
FAQ_JSON = os.path.join(KNOWLEDGE_DIR, "faq.json")

_SECTION_RE = re.compile(r"^##(?!#)\s*(.+)$", re.MULTILINE)


def _chunk_id(source: str, key: str) -> str:
    return hashlib.sha1(f"{source}:{key}".encode("utf-8")).hexdigest()[:16]


def load_products(path: str = PRODUCTS_CSV) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return chunks
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            sku = (row.get("sku") or "").strip()
            if not sku:
                continue
            title = f"{row.get('title_en','').strip()} / {row.get('title_zh','').strip()}".strip(" /")
            lines = [
                f"SKU: {sku}",
                f"Title: {row.get('title_en','').strip()} / {row.get('title_zh','').strip()}",
                f"Category: {row.get('category','').strip()}",
                f"Price: USD {row.get('price_usd','').strip()}",
                f"Weight: {row.get('weight_g','').strip()} g",
                f"Stock: {row.get('stock','').strip()}",
                f"Variants: {row.get('variants','').strip()}",
                f"Warranty region: {row.get('warranty_region','').strip()}",
                f"Description: {row.get('description','').strip()}",
            ]
            chunks.append({
                "chunk_id": _chunk_id("products", sku),
                "source": "products.csv",
                "category": "products",
                "title": f"{sku} · {title}",
                "content": "\n".join(lines),
                "lang": "bi",
            })
    return chunks


def load_policies(path: str = POLICIES_MD) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return chunks
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    matches = list(_SECTION_RE.finditer(raw))
    for idx, match in enumerate(matches):
        header = match.group(1).strip()
        body_start = match.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw)
        body = raw[body_start:body_end].strip()
        if not body:
            continue

        parts = [p.strip() for p in header.split("|")]
        section_id = parts[0] if parts else ""
        title = parts[1] if len(parts) > 1 else section_id

        chunks.append({
            "chunk_id": _chunk_id("policies", section_id or title),
            "source": "policies.md",
            "category": section_id or "policy",
            "title": title,
            "content": body,
            "lang": "bi",
        })
    return chunks


def load_faq(path: str = FAQ_JSON) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return chunks
    with open(path, "r", encoding="utf-8") as f:
        items = json.load(f)

    for item in items:
        q_en = (item.get("question_en") or "").strip()
        q_zh = (item.get("question_zh") or "").strip()
        a_en = (item.get("answer_en") or "").strip()
        a_zh = (item.get("answer_zh") or "").strip()
        if not (q_en or q_zh):
            continue
        content = (
            f"Q (EN): {q_en}\nQ (中文): {q_zh}\n"
            f"A (EN): {a_en}\nA (中文): {a_zh}"
        )
        chunks.append({
            "chunk_id": _chunk_id("faq", item.get("id") or q_en),
            "source": "faq.json",
            "category": (item.get("category") or "faq").strip().lower(),
            "title": f"FAQ · {q_en or q_zh}",
            "content": content,
            "lang": "bi",
        })
    return chunks


def load_chunks(knowledge_dir: str = KNOWLEDGE_DIR) -> List[Dict[str, Any]]:
    """加载全部知识 chunk（顺序：商品 → 政策 → FAQ）。"""
    policies = os.path.join(knowledge_dir, "policies.md")
    products = os.path.join(knowledge_dir, "products.csv")
    faq = os.path.join(knowledge_dir, "faq.json")
    chunks = load_products(products) + load_policies(policies) + load_faq(faq)

    # 去重（同一文件被误改出重复 id 时以先出现的为准）
    seen = set()
    unique = []
    for chunk in chunks:
        if chunk["chunk_id"] in seen:
            continue
        seen.add(chunk["chunk_id"])
        unique.append(chunk)
    return unique
