"""
清空所有会话（仅本地演示用）。

用法：
    docker compose run --rm web python scripts/clear_sessions.py
    python scripts/clear_sessions.py          # 本地 SQLite/Postgres
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


def main() -> int:
    from chat_service_embedded import delete_remote_thread
    from db import list_threads

    rows = list_threads(limit=1000)
    print(f"待删除会话: {len(rows)} 条")
    for row in rows:
        tid = row["thread_id"]
        ok, status = delete_remote_thread(tid)
        print(f"  {'OK ' if ok else 'FAIL'} {tid} {row.get('title') or ''}")
    print("完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
