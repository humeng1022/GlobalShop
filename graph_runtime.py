"""
图运行时：按 APP_MODE 提供编译好的图实例。

- embedded：Flask 进程内直接跑图，使用官方开源 checkpointer（SqliteSaver / PostgresSaver），
  不需要 LangGraph 授权，重启不丢历史。
- server：返回 None，交给独立 LangGraph 服务（需 LangGraph Cloud 许可证，本项目默认不用）。

注意：Neon 等云数据库会主动断开长时间空闲的连接（"server closed the connection"），
所以每次使用前检查连接状态，失效则重建图并重试一次。
"""

import os
import sqlite3
import threading
from typing import Any

from config import APP_MODE, DATABASE_URL
from db import is_postgres, sqlite_path

_lock = threading.Lock()
_graph = None
_conn: Any = None


def _conn_alive() -> bool:
    if _conn is None:
        return False
    if getattr(_conn, "closed", False):
        return False
    if getattr(_conn, "broken", False):
        return False
    return True


def _close_conn() -> None:
    global _conn
    try:
        if _conn is not None:
            _conn.close()
    except Exception:
        pass
    _conn = None


def _build_checkpointer():
    """按 DATABASE_URL 选择 SQLite 或 Postgres checkpointer。"""
    global _conn
    if is_postgres(DATABASE_URL):
        import psycopg
        from langgraph.checkpoint.postgres import PostgresSaver

        _conn = psycopg.connect(
            DATABASE_URL,
            autocommit=True,
            connect_timeout=15,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=3,
        )
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
    """单例获取编译后的图；连接断开时自动重建。"""
    global _graph
    if _graph is not None and (APP_MODE != "embedded" or _conn_alive()):
        return _graph

    with _lock:
        if _graph is None or (APP_MODE == "embedded" and not _conn_alive()):
            _close_conn()
            _graph = None
            from multi_agent_customer_service import make_graph

            checkpointer = _build_checkpointer() if APP_MODE == "embedded" else None
            _graph = make_graph(checkpointer=checkpointer)
    return _graph


def reset_graph() -> None:
    """丢弃当前图与数据库连接（测试/热重载/连接失效时用）。"""
    global _graph
    with _lock:
        _graph = None
        _close_conn()


def _run_with_reconnect(op):
    """执行一次操作；连接失效时重建连接并重试一次。"""
    try:
        return op(get_graph())
    except Exception as e:
        print(f"⚠️ checkpointer 连接异常，重建后重试: {e}")
        reset_graph()
        return op(get_graph())


def run_sync(graph_input: dict, config: dict):
    """线程安全地执行一次图（同一 worker 内串行，避免共享连接并发冲突）。"""
    return _run_with_reconnect(
        lambda graph: _invoke_locked(graph, graph_input, config)
    )


def _invoke_locked(graph, graph_input, config):
    with _run_lock:
        return graph.invoke(graph_input, config=config)


def get_state_sync(config: dict):
    """线程安全地读取线程状态；连接失效时自动重连重试。"""
    return _run_with_reconnect(
        lambda graph: _get_state_locked(graph, config)
    )


def _get_state_locked(graph, config):
    with _run_lock:
        return graph.get_state(config)


_run_lock = threading.Lock()
