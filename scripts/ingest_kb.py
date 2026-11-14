"""
知识库入库脚本。

用法（在项目根目录执行）：
    python scripts/ingest_kb.py            # 增量：只向量化新增/变更的 chunk
    python scripts/ingest_kb.py --force    # 全量重建
    python scripts/ingest_kb.py --stats    # 只看索引状态

数据来源：knowledge/products.csv、knowledge/policies.md、knowledge/faq.json
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


def main() -> int:
    args = set(sys.argv[1:])

    from db import ping
    from knowledge_loader import load_chunks
    from vector_store import build_index, stats

    if "--stats" in args:
        print(stats())
        return 0

    chunks = load_chunks()
    db_info = ping()
    print(f"📚 知识库来源: {os.path.join(BASE_DIR, 'knowledge')}")
    print(f"🧩 切分结果: {len(chunks)} 个 chunk")
    for c in chunks[:5]:
        print(f"   - [{c['category']}] {c['title']}")
    if len(chunks) > 5:
        print(f"   ... 其余 {len(chunks) - 5} 个")
    print(f"🗄️ 数据库: {db_info}")

    result = build_index(force="--force" in args)
    print(f"✅ 入库完成: {result}")
    print(f"📊 当前索引: {stats()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
