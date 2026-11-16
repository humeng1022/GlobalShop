"""
后台管理路由：概览 / 会话 / 知识库 / 模拟运单。

鉴权：ADMIN_PASSWORD + Flask session。
知识库：后台新增条目存 DB（source=admin），与文件数据一起参与向量检索；
        文件数据只读展示，避免在页面上改乱 CSV/Markdown。
"""

import uuid
from functools import wraps

from flask import Blueprint, jsonify, redirect, render_template, request, session

from config import ADMIN_PASSWORD

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return jsonify({"error": "未登录或登录已过期"}), 401
        return fn(*args, **kwargs)
    return wrapper


# ---------------- 页面 ----------------

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password") or ""
        if ADMIN_PASSWORD and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect("/admin")
        return render_template("admin_login.html", error="密码错误", configured=bool(ADMIN_PASSWORD)), 401
    if not ADMIN_PASSWORD:
        return render_template("admin_login.html", error="未配置 ADMIN_PASSWORD，请先在 .env 中设置", configured=False)
    return render_template("admin_login.html", configured=True)


@admin_bp.route("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect("/admin/login")


@admin_bp.route("/")
def index():
    if not session.get("is_admin"):
        return redirect("/admin/login")
    return render_template("admin.html")


# ---------------- API ----------------

@admin_bp.route("/api/overview")
@admin_required
def api_overview():
    from db import admin_counts, list_threads
    from vector_store import stats

    try:
        return jsonify({
            "counts": admin_counts(),
            "vector": stats(),
            "sessions": list_threads(10),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/api/sessions")
@admin_required
def api_sessions():
    from db import list_threads
    try:
        return jsonify({"sessions": list_threads(200)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/api/sessions/<session_id>")
@admin_required
def api_session_detail(session_id):
    try:
        from config import APP_MODE
        if APP_MODE == "embedded":
            from chat_service_embedded import fetch_session_detail
        else:
            from chat_web_service import fetch_session_detail
        detail, err = fetch_session_detail(session_id)
        if err:
            return jsonify({"error": err}), 500
        return jsonify({"session": detail})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/api/kb")
@admin_required
def api_kb_list():
    from db import list_admin_chunks
    from vector_store import stats
    try:
        chunks = list_admin_chunks()
        return jsonify({"entries": chunks, "stats": stats(), "files": _file_sources()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _file_sources():
    """文件来源的条目数量（只读展示）。"""
    from db import fetch_chunks
    counts = {}
    for row in fetch_chunks():
        if row.get("source") == "admin":
            continue
        counts[row.get("source") or "unknown"] = counts.get(row.get("source") or "unknown", 0) + 1
    return counts


@admin_bp.route("/api/kb", methods=["POST"])
@admin_required
def api_kb_create():
    from db import list_admin_chunks
    from vector_store import upsert_admin_entry

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    category = (data.get("category") or "admin").strip() or "admin"
    if not title or not content:
        return jsonify({"error": "标题和内容不能为空"}), 400

    try:
        chunk_id = "admin-" + uuid.uuid4().hex[:12]
        result = upsert_admin_entry(chunk_id, title, content, category)
        return jsonify({"ok": True, "entry": result, "total": len(list_admin_chunks())})
    except Exception as e:
        return jsonify({"error": f"保存失败: {e}"}), 500


@admin_bp.route("/api/kb/<chunk_id>", methods=["PUT"])
@admin_required
def api_kb_update(chunk_id):
    from vector_store import upsert_admin_entry

    if not chunk_id.startswith("admin-"):
        return jsonify({"error": "文件来源的条目为只读，请在后台新建条目"}), 400

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    category = (data.get("category") or "admin").strip() or "admin"
    if not title or not content:
        return jsonify({"error": "标题和内容不能为空"}), 400

    try:
        result = upsert_admin_entry(chunk_id, title, content, category)
        return jsonify({"ok": True, "entry": result})
    except Exception as e:
        return jsonify({"error": f"更新失败: {e}"}), 500


@admin_bp.route("/api/kb/<chunk_id>", methods=["DELETE"])
@admin_required
def api_kb_delete(chunk_id):
    from db import delete_chunk

    if not chunk_id.startswith("admin-"):
        return jsonify({"error": "文件来源的条目为只读"}), 400
    try:
        delete_chunk(chunk_id)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": f"删除失败: {e}"}), 500


@admin_bp.route("/api/kb/<chunk_id>/delete", methods=["POST"])
@admin_required
def api_kb_delete_post(chunk_id):
    """POST 别名：魔搭网关会拦截 DELETE。"""
    return api_kb_delete(chunk_id)


@admin_bp.route("/api/kb/reindex", methods=["POST"])
@admin_required
def api_kb_reindex():
    from vector_store import build_index, stats

    try:
        force = bool((request.get_json(silent=True) or {}).get("force"))
        result = build_index(force=force, verbose=False)
        return jsonify({"ok": True, "result": result, "stats": stats()})
    except Exception as e:
        return jsonify({"error": f"重建失败: {e}"}), 500


@admin_bp.route("/api/tracking", methods=["GET", "POST"])
@admin_required
def api_tracking():
    from db import tracking_list, tracking_upsert

    if request.method == "GET":
        try:
            return jsonify({"items": tracking_list()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    data = request.get_json(silent=True) or {}
    number = (data.get("number") or "").strip().upper()
    if not number:
        return jsonify({"error": "运单号不能为空"}), 400
    try:
        tracking_upsert(
            number,
            (data.get("status_zh") or "").strip(),
            (data.get("status_en") or "").strip(),
            (data.get("location") or "").strip(),
            (data.get("eta") or "").strip(),
            (data.get("note") or "").strip(),
        )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": f"保存失败: {e}"}), 500


@admin_bp.route("/api/tracking/<number>", methods=["DELETE"])
@admin_required
def api_tracking_delete(number):
    from db import tracking_delete
    try:
        tracking_delete(number)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": f"删除失败: {e}"}), 500


@admin_bp.route("/api/tracking/<number>/delete", methods=["POST"])
@admin_required
def api_tracking_delete_post(number):
    """POST 别名：魔搭网关会拦截 DELETE。"""
    return api_tracking_delete(number)
