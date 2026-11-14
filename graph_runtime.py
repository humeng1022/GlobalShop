"""
图运行时：按 APP_MODE 提供编译好的图实例。

- embedded：Flask 进程内直接跑图，使用官方开源 checkpointer（SqliteSaver / PostgresSaver），
  不需要 LangGraph 授权，重启不丢历史。
- server：返回 None，交给独立 LangGraph 服务（需 LangGraph Cloud 许可证，本项目默认不用）。
"""

import os
import sqlite3
import threading
from typing import Any, Optional

from config import APP_MODE, DATABASE_URL
from db import is_postgres, sqlite_path

_lock = threading.Lock()
_run_lock = threading.Lock()
_graph = None
_conn: Any = None


def _build_checkpointer():
    """按 DATABASE_URL 选择 SQLite 或 Postgres checkpointer。"""
    global _conn
    if is_postgres(DATABASE_URL):
        import psycopg
        from langgraph.checkpoint.postgres import PostgresSaver

        _conn = psycopg.connect(DATABASE_URL, autocommit=True)
        saver = PostgresSaver(_conn)
    else:
        from langgraph.checkpoint.sqlite import SqliteSaver

        path = sqlite_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False)
        saver = SqliteSaver(_conn)

    saver.setup()  # 幂等建表
    return saver


def get_graph():
    """单例获取编译后的图（embedded 模式带持久化）。"""
    global _graph
    if _graph is None:
        with _lock:
            if _graph is None:
                from multi_agent_customer_service import make_graph

                checkpointer = _build_checkpointer() if APP_MODE == "embedded" else None
                _graph = make_graph(checkpointer=checkpointer)
    return _graph


def reset_graph() -> None:
    """测试/热重载用：丢弃当前图实例。"""
    global _graph
    with _lock:
        _graph = None


def run_sync(graph_input: dict, config: dict):
    """线程安全地执行一次图。

    checkpointer（尤其 PostgresSaver）复用一个连接，不是线程安全的；
    同一 worker 内串行执行，多 worker 之间仍然并行。
    """
    graph = get_graph()
    with _run_lock:
        return graph.invoke(graph_input, config=config)


def get_state_sync(config: dict):
    """线程安全地读取线程状态。"""
    graph = get_graph()
    with _run_lock:
        return graph.get_state(config)
