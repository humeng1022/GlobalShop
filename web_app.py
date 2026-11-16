#!/usr/bin/env python3
"""
GlobalShop AI 客服中心 - Web 入口（跨境电商智能客服）
基于 LangGraph API 接口，路由与 Flask 会话；业务逻辑见 chat_web_service.py
"""

import os
import time
from typing import Dict, Any, List

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, render_template, request, jsonify, session, Response

# 导入配置（需先于会话服务导入，用来决定 APP_MODE）
from config import *  # noqa: E402,F401,F403

if APP_MODE == "embedded":
    # 单进程模式：图直接跑在 Flask 里，checkpointer 持久化（本地默认）
    from chat_service_embedded import (
        run_chat_sync,
        stream_chat_events,
        fetch_sessions_list,
        fetch_session_detail,
        delete_remote_thread,
        clear_thread_and_create_new,
        langgraph_connectivity_test,
        get_current_thread_id,
        get_last_reasoning,
        get_last_elapsed,
        get_last_agent,
    )
else:
    # 双服务模式：通过 HTTP 调用独立 LangGraph 服务
    from chat_web_service import (
        run_chat_sync,
        stream_chat_events,
        fetch_sessions_list,
        fetch_session_detail,
        delete_remote_thread,
        clear_thread_and_create_new,
        langgraph_connectivity_test,
        get_current_thread_id,
        get_last_reasoning,
        get_last_elapsed,
        get_last_agent,
    )

app = Flask(__name__)

# 后台管理（/admin）
from admin import admin_bp  # noqa: E402

app.register_blueprint(admin_bp)


# 启动预热：提前建立 checkpointer 连接并建表，避免第一个用户等 Neon 冷启动
def _warmup_graph():
    try:
        if APP_MODE != "embedded":
            return
        import time
        import graph_runtime

        started = time.time()
        graph_runtime.get_graph()
        print(f"✅ 图预热完成，用时 {time.time() - started:.1f}s")
    except Exception as e:
        print(f"⚠️ 图预热失败（不影响 /api/health）: {e}")


if APP_MODE == "embedded":
    import threading

    threading.Thread(target=_warmup_graph, daemon=True).start()

# Flask 配置
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your-secret-key-here")
app.config['SESSION_TYPE'] = 'filesystem'


# --- Flask session 内的本地对话占位（主页模板可能使用）---

def get_conversation_history(session_id: str) -> List[Dict[str, Any]]:
    if 'conversations' not in session:
        session['conversations'] = {}
    return session['conversations'].get(session_id, [])


def add_conversation_message(session_id: str, role: str, content: str) -> None:
    history = get_conversation_history(session_id)
    history.append({
        'role': role,
        'content': content,
    })
    session['conversations'][session_id] = history


@app.route('/')
def index():
    """主页"""
    current_session_id = session.get('current_session_id', 'default')
    conversation_history = get_conversation_history(current_session_id)
    return render_template('index.html', conversation_history=conversation_history)


@app.route('/api/chat', methods=['POST'])
def chat():
    """处理聊天请求"""
    try:
        data = request.get_json()
        user_message = (data.get('message') or '').strip()
        client_session_id = data.get('session_id', 'default')
        use_kb = bool(data.get('use_kb', True))

        ai_text, err_msg, http_code = run_chat_sync(user_message, client_session_id, use_kb=use_kb)
        if err_msg:
            return jsonify({'error': err_msg}), http_code or 500

        tid = get_current_thread_id()
        return jsonify({
            'response': ai_text,
            'session_id': tid,
            'thread_id': tid,
            'reasoning': get_last_reasoning(),
            'elapsed': get_last_elapsed(),
            'agent': get_last_agent(),
        })
    except Exception as e:
        print(f"❌ 聊天处理错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'内部错误: {str(e)}'}), 500


@app.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    """处理流式聊天请求"""
    try:
        data = request.get_json()
        user_message = (data.get('message') or '').strip()
        client_session_id = data.get('session_id', 'default')

        return Response(
            stream_chat_events(user_message, client_session_id),
            mimetype='text/event-stream'
        )

    except Exception as e:
        print(f"❌ 流式聊天处理错误: {e}")
        return jsonify({'error': f'内部错误: {str(e)}'}), 500


@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    """获取会话列表"""
    sessions, err = fetch_sessions_list()
    if err:
        return jsonify({'error': err}), 500
    return jsonify({'sessions': sessions or []})


@app.route('/api/sessions/<session_id>', methods=['GET'])
def get_session(session_id):
    """获取特定会话详情"""
    session_data, err = fetch_session_detail(session_id)
    if err:
        return jsonify({'error': err}), 500
    return jsonify({'session': session_data})


@app.route('/api/sessions/<session_id>', methods=['PATCH'])
def rename_session(session_id):
    """重命名会话（侧栏操作）。"""
    try:
        data = request.get_json(silent=True) or {}
        title = (data.get('title') or '').strip()
        if not title:
            return jsonify({'error': '标题不能为空'}), 400
        from db import rename_thread
        rename_thread(session_id, title)
        return jsonify({'message': '重命名成功', 'title': title})
    except Exception as e:
        return jsonify({'error': f'重命名失败: {e}'}), 500


@app.route('/api/sessions/<session_id>/rename', methods=['POST'])
def rename_session_post(session_id):
    """POST 别名：魔搭 ms.show 网关会拦截 PATCH/DELETE，改用 POST。"""
    return rename_session(session_id)


@app.route('/api/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    """删除会话"""
    try:
        ok, status = delete_remote_thread(session_id)
        if ok:
            if 'conversations' in session and session_id in session['conversations']:
                del session['conversations'][session_id]
            return jsonify({'message': '会话删除成功'})
        return jsonify({'error': f'删除会话失败: {status}'}), 500
    except Exception as e:
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500


@app.route('/api/sessions/<session_id>/delete', methods=['POST'])
def delete_session_post(session_id):
    """POST 别名：魔搭 ms.show 网关会拦截 DELETE。"""
    return delete_session(session_id)


@app.route('/api/sessions/<session_id>/clear', methods=['POST'])
def clear_session(session_id):
    """清空会话"""
    try:
        new_thread_id, err = clear_thread_and_create_new(session_id)
        if err:
            return jsonify({'error': err}), 500

        if 'conversations' in session and session_id in session['conversations']:
            session['conversations'][session_id] = []

        return jsonify({
            'message': '会话清空成功',
            'new_thread_id': new_thread_id
        })
    except Exception as e:
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500


@app.route('/api/new_session', methods=['POST'])
def create_new_session():
    """创建新会话（Flask session 侧）"""
    try:
        import uuid
        new_session_id = str(uuid.uuid4())
        session['current_session_id'] = new_session_id
        if 'conversations' not in session:
            session['conversations'] = {}
        session['conversations'][new_session_id] = []
        return jsonify({
            'session_id': new_session_id,
            'message': '新会话创建成功'
        })
    except Exception as e:
        return jsonify({'error': f'创建会话失败: {str(e)}'}), 500


@app.route('/api/health')
def health_check():
    """健康检查"""
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time()
    })


@app.route('/api/test')
def test_langgraph():
    """测试 LangGraph API 调用"""
    result, err = langgraph_connectivity_test()
    if err:
        return jsonify({'error': err}), 500
    return jsonify(result)


def main():
    """主函数"""
    print("🚀 GlobalShop AI 客服中心 Web 应用")
    print("=" * 60)
    print("🌐 启动 Web 服务...")
    print(f"📱 访问地址: http://localhost:{PORT}")
    print("💡 按 Ctrl+C 停止服务")
    print()
    # debug 交给 gunicorn / 环境变量控制，避免生产环境暴露调试器
    app.run(host='0.0.0.0', port=PORT, debug=FLASK_DEBUG)


if __name__ == "__main__":
    main()
