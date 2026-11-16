"""
Embedded 会话服务：不依赖独立 LangGraph 服务，直接在 Flask 进程内跑图。

对外暴露与 chat_web_service 相同的函数名，web_app 按 APP_MODE 选择导入。
会话历史由 checkpointer 持久化（SQLite / Postgres），重启不丢。
"""

import json
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage

import graph_runtime
from db import delete_thread as db_delete_thread
from db import get_thread, list_threads, upsert_thread

# 每个请求线程独立保存本次运行的元信息，避免并发时互相覆盖
_local = threading.local()


def get_current_thread_id() -> str:
    return getattr(_local, "thread_id", "") or ""


def get_last_reasoning() -> str:
    """最近一次回答的推理过程（「深度思考」折叠区）。"""
    return getattr(_local, "reasoning", "") or ""


def get_last_elapsed() -> float:
    """最近一次回答耗时（秒）。"""
    return getattr(_local, "elapsed", 0.0) or 0.0


def get_last_agent() -> str:
    """最近一次回答由哪个智能体处理。"""
    return getattr(_local, "agent", "") or ""


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _checkpoint_thread_id(raw: str) -> str:
    """把任意会话 ID 稳定映射成 UUID。

    Postgres checkpointer 的 thread_id 列是 UUID 类型，必须是合法 UUID；
    前端的 web_<时间戳> 这类 ID 需要确定性转换（同一 ID 永远得到同一 UUID）。
    """
    if _is_uuid(raw):
        return str(uuid.UUID(raw))
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"globalshop:{raw}"))


def get_current_thread_id() -> str:
    return getattr(_local, "thread_id", "") or ""


def _resolve_thread(client_session_id: Optional[str]) -> str:
    """复用前端传来的会话 ID（web_<ts> 或 UUID 都行）；没有才新建。

    关键点：thread_id 不要求是 UUID，LangGraph checkpoint 支持任意字符串。
    之前只认 UUID，导致前端每条消息都被当成新会话。
    """
    sid = (client_session_id or "").strip()

    if sid and sid != "default":
        tid = _checkpoint_thread_id(sid)
        if not get_thread(tid):
            upsert_thread(tid)
        _local.thread_id = tid
        return tid

    current = getattr(_local, "thread_id", None)
    if current:
        return current

    tid = str(uuid.uuid4())
    upsert_thread(tid)
    _local.thread_id = tid
    return tid


def _graph():
    return graph_runtime.get_graph()


def run_chat_sync(user_message: str, client_session_id: Optional[str] = None,
                  use_kb: bool = True
                  ) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    message = (user_message or "").strip()
    if not message:
        return None, "消息不能为空", 400

    tid = _resolve_thread(client_session_id)
    config = {"configurable": {"thread_id": tid}}

    started = time.time()
    try:
        result = graph_runtime.run_sync(
            {
                "customer_query": message,
                "messages": [HumanMessage(content=message)],
                "session_id": tid,
                "use_kb": bool(use_kb),
            },
            config=config,
        )
    except Exception as e:
        print(f"❌ embedded 图执行失败: {e}")
        return None, f"处理失败: {e}", 500

    _local.elapsed = round(time.time() - started, 1)
    _local.reasoning = ((result or {}).get("reasoning") or "").strip()
    _local.agent = (result or {}).get("agent_name") or (result or {}).get("current_agent") or ""

    # 标题只取第一条用户消息，后续消息不覆盖（侧栏显示更稳定）
    existing = get_thread(tid) or {}
    if not (existing.get("title") or "").strip():
        upsert_thread(tid, title=message[:30])
    else:
        upsert_thread(tid)
    _local.thread_id = tid
    response = (result or {}).get("response") or ""
    return response, None, None


def stream_chat_events(user_message: str, client_session_id: Optional[str] = None):
    """SSE 兼容接口：embedded 模式一次性返回完整回复（当前前端走 /api/chat）。"""
    text, err, _ = run_chat_sync(user_message, client_session_id)
    if err:
        yield f"data: {json.dumps({'error': err}, ensure_ascii=False)}\n\n"
    else:
        yield f"data: {json.dumps({'response': text}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


def fetch_sessions_list() -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    try:
        rows = list_threads(limit=200)
    except Exception as e:
        return None, f"读取会话失败: {e}"

    sessions = []
    for row in rows:
        preview = (row.get("title") or "").strip()
        sessions.append({
            "session_id": row["thread_id"],
            "thread_id": row["thread_id"],
            "title": preview or "新对话",
            "last_user_question": preview,
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        })
    return sessions, None


def _load_state(session_id: str):
    """兼容旧数据：先按原 ID 读，失败再按 UUID 映射读（Postgres 的 thread_id 是 UUID）。"""
    candidates = [session_id]
    converted = _checkpoint_thread_id(session_id)
    if converted != session_id:
        candidates.append(converted)

    last_error = None
    for tid in candidates:
        try:
            return graph_runtime.get_state_sync({"configurable": {"thread_id": tid}})
        except Exception as e:  # 连接失效 / UUID 不合法等
            last_error = e
    raise last_error


def fetch_session_detail(session_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not session_id:
        return None, "缺少会话 ID"

    values: Dict[str, Any] = {}
    warning = None
    try:
        state = _load_state(session_id)
        values = state.values if hasattr(state, "values") else {}
    except Exception as e:
        # 不让 UI 因为状态读取失败而整体 500；返回空历史并附带 warning
        print(f"⚠️ 读取会话状态失败（返回空历史）: {e}")
        warning = str(e)

    dialogue = values.get("persisted_dialogue") or []
    history = [
        {
            "is_user": bool(item.get("is_user", True)),
            "content": item.get("content", ""),
            "timestamp": item.get("timestamp", ""),
        }
        for item in dialogue
    ]
    meta = get_thread(session_id) or {}
    result = {
        "session_id": session_id,
        "title": meta.get("title") or "",
        "conversation_history": history,
        "current_agent": values.get("current_agent", ""),
    }
    if warning:
        result["warning"] = warning
    return result, None


def delete_remote_thread(session_id: str) -> Tuple[bool, int]:
    if not session_id:
        return False, 400
    try:
        db_delete_thread(session_id)
    except Exception as e:
        print(f"删除会话元数据失败: {e}")
        return False, 500

    # 尽力删除 checkpoint（兼容旧 ID 与 UUID 映射）
    candidates = {session_id, _checkpoint_thread_id(session_id)}
    try:
        saver = getattr(graph_runtime.get_graph(), "checkpointer", None)
        if saver is not None and hasattr(saver, "delete_thread"):
            for tid in candidates:
                try:
                    saver.delete_thread(tid)
                except Exception as e:
                    print(f"删除 checkpoint {tid} 失败（忽略）: {e}")
    except Exception as e:
        print(f"删除 checkpoint 失败（忽略）: {e}")

    return True, 200


def clear_thread_and_create_new(session_id: str) -> Tuple[Optional[str], Optional[str]]:
    """清空当前会话 = 删除旧线程并新建一个空线程。"""
    if session_id:
        delete_remote_thread(session_id)
    new_id = str(uuid.uuid4())
    try:
        upsert_thread(new_id)
    except Exception as e:
        return None, f"创建会话失败: {e}"
    return new_id, None


def langgraph_connectivity_test() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        from db import ping

        db_info = ping()
        _graph()  # 触发一次构建，验证图可加载
        healthy = 200 if db_info.get("ok") else 500
        return ({
            "status": "test_completed",
            "mode": "embedded",
            "health_check": healthy,
            "threads_search": healthy,
            "assistants_search": healthy,
            "details": {
                "ok_response": "OK" if healthy == 200 else "FAILED",
                "db": db_info,
            },
        }, None)
    except Exception as e:
        print(f"❌ embedded 自检失败: {e}")
        return None, f"自检失败: {e}"
