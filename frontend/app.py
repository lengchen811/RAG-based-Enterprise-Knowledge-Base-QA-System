"""企业知识库问答系统 - Streamlit 前端。

功能：登录/注册、文档上传、流式问答、引用来源、历史会话管理。
与后端 FastAPI 通过 REST + SSE 通信。
"""
import json
import os

import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://localhost:8000")

# ---------------------------------------------------------------------------
# 页面配置
# ---------------------------------------------------------------------------
st.set_page_config(page_title="企业知识库问答", page_icon="📚", layout="wide")

# 初始化状态
if "token" not in st.session_state:
    st.session_state.token = None
if "user" not in st.session_state:
    st.session_state.user = None
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []


def _headers() -> dict:
    return {"Authorization": f"Bearer {st.session_state.token}"}


def _api(method: str, path: str, **kwargs):
    """调用后端 API，返回统一 JSON（data 字段）。"""
    url = f"{API_BASE}{path}"
    resp = requests.request(method, url, headers=_headers(), timeout=60, **kwargs)
    if resp.status_code == 401:
        st.session_state.token = None
        raise PermissionError("登录已过期，请重新登录")
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(body.get("message", "请求失败"))
    return body.get("data")


# ---------------------------------------------------------------------------
# 登录 / 注册
# ---------------------------------------------------------------------------
def show_auth():
    st.title("📚 企业知识库问答系统")
    st.caption("基于 RAG 的检索增强生成 —— 文档解析 · 混合检索 · 重排序 · 流式问答")
    tab_login, tab_register = st.tabs(["登录", "注册"])

    with tab_login:
        with st.form("login"):
            u = st.text_input("用户名")
            p = st.text_input("密码", type="password")
            if st.form_submit_button("登录", use_container_width=True):
                try:
                    r = requests.post(f"{API_BASE}/api/auth/login", json={"username": u, "password": p}, timeout=30)
                    body = r.json()
                    if body.get("code") != 0:
                        st.error(body.get("message", "登录失败"))
                    else:
                        st.session_state.token = body["data"]["access_token"]
                        st.session_state.user = body["data"]["user"]
                        st.rerun()
                except Exception as e:
                    st.error(f"登录失败：{e}")

    with tab_register:
        with st.form("register"):
            u = st.text_input("用户名", key="reg_u")
            p = st.text_input("密码", key="reg_p", type="password")
            if st.form_submit_button("注册", use_container_width=True):
                try:
                    r = requests.post(f"{API_BASE}/api/auth/register", json={"username": u, "password": p}, timeout=30)
                    body = r.json()
                    if body.get("code") != 0:
                        st.error(body.get("message", "注册失败"))
                    else:
                        st.success("注册成功，请登录")
                except Exception as e:
                    st.error(f"注册失败：{e}")


# ---------------------------------------------------------------------------
# 主界面
# ---------------------------------------------------------------------------
def show_main():
    u = st.session_state.user
    st.sidebar.title("📚 知识库")
    st.sidebar.caption(f"当前用户：{u['username']}")

    # 会话列表
    st.sidebar.subheader("💬 历史会话")
    try:
        sessions = _api("GET", "/api/chat/sessions")["items"]
    except Exception:
        sessions = []
    session_options = {f"{s['id']} - {s['title']}": s["id"] for s in sessions}
    if session_options:
        sel = st.sidebar.selectbox("选择会话", list(session_options.keys()), label_visibility="collapsed")
        if st.sidebar.button("加载该会话", use_container_width=True):
            load_session(session_options[sel])
    else:
        st.sidebar.info("暂无会话")
    if st.sidebar.button("➕ 新对话", use_container_width=True):
        st.session_state.current_session_id = None
        st.session_state.messages = []
        st.rerun()
    if st.sidebar.button("🚪 退出登录", use_container_width=True):
        st.session_state.token = None
        st.session_state.user = None
        st.session_state.current_session_id = None
        st.session_state.messages = []
        st.rerun()

    # 文档上传
    st.sidebar.divider()
    st.sidebar.subheader("📄 上传文档")
    uploaded = st.sidebar.file_uploader("PDF / Markdown / TXT", type=["pdf", "md", "txt"])
    if uploaded is not None and st.sidebar.button("上传并解析", use_container_width=True):
        upload_document(uploaded)

    # 文档列表
    st.sidebar.subheader("🗂 已上传文档")
    if st.sidebar.button("🔄 刷新状态", use_container_width=True):
        st.rerun()
    try:
        docs = _api("GET", "/api/documents")["items"]
        if docs:
            status_icon = {"COMPLETED": "✅", "PROCESSING": "⏳", "PENDING": "⏳", "FAILED": "❌"}
            for d in docs:
                st.sidebar.markdown(
                    f"{status_icon.get(d['status'], '❓')} {d['filename']} "
                    f"`{d['status']}` {d['chunk_count']}块"
                )
        else:
            st.sidebar.info("暂无文档")
    except Exception:
        pass

    # 主问答区
    st.subheader("💬 智能问答")
    st.caption("基于企业知识库回答，支持多轮对话与引用溯源")

    # 渲染历史消息
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m.get("sources"):
                with st.expander("📎 引用来源"):
                    for s in m["sources"]:
                        st.markdown(f"- **{s['filename']}** （块 {s.get('chunk_index', '-')}）")
                        if s.get("content_excerpt"):
                            st.caption(s["content_excerpt"][:120])

    # 输入框
    if question := st.chat_input("输入你的问题…"):
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            try:
                full, sources = stream_answer(question)
            except Exception as e:
                st.error(f"回答失败：{e}")
                full, sources = "", []
            # 引用来源：独立折叠框，直接写在 chat_message 容器内
            if sources:
                with st.expander("📎 引用来源"):
                    for s in sources:
                        st.markdown(f"- **{s['filename']}** （块 {s.get('chunk_index', '-')}）")
                        if s.get("content_excerpt"):
                            st.caption(s["content_excerpt"][:120])


def load_session(session_id: int):
    """加载历史会话到界面。"""
    try:
        data = _api("GET", f"/api/chat/sessions/{session_id}/messages")
        msgs = []
        for m in data["messages"]:
            msgs.append({"role": m["role"], "content": m["content"], "sources": m.get("sources")})
        st.session_state.current_session_id = session_id
        st.session_state.messages = msgs
        st.rerun()
    except Exception as e:
        st.error(f"加载会话失败：{e}")


def upload_document(file):
    """上传文档并异步处理。"""
    try:
        files = {"file": (file.name, file.getvalue(), "application/octet-stream")}
        resp = requests.post(f"{API_BASE}/api/documents/upload", headers=_headers(), files=files, timeout=60)
        body = resp.json()
        if body.get("code") != 0:
            st.sidebar.error(body.get("message", "上传失败"))
            return
        d = body["data"]
        st.sidebar.success(f"已上传 {d['filename']}，后台解析中…")
    except Exception as e:
        st.sidebar.error(f"上传失败：{e}")


def stream_answer(question: str) -> tuple:
    """通过 SSE 流式调用后端，逐 token 渲染。

    不使用 st.write_stream（该 API 在多次重渲染时触发 Streamlit 的
    removeChild DOM bug），改为手动逐 token 更新占位符。
    返回 (完整答案, 引用来源)。
    """
    sources = []
    full = ""
    placeholder = st.empty()

    payload = {
        "question": question,
        "session_id": st.session_state.current_session_id,
        "top_k": 5,
    }
    with requests.post(
        f"{API_BASE}/api/chat/stream", headers=_headers(), json=payload, stream=True, timeout=180
    ) as resp:
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            evt = json.loads(line[6:])
            t = evt.get("type")
            if t == "token":
                full += evt["content"]
                placeholder.markdown(full)
            elif t == "sources":
                sources.extend(evt.get("sources", []))
            elif t == "start":
                st.session_state.current_session_id = evt["session_id"]

    # 保存回答到会话历史
    st.session_state.messages.append({"role": "assistant", "content": full, "sources": sources})
    return full, sources


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
if st.session_state.token is None:
    show_auth()
else:
    show_main()