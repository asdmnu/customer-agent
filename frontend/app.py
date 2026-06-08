"""Customer Agent 3 Streamlit demo page."""

from __future__ import annotations

import json
import os
import uuid

import requests
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_URL = f"{API_BASE_URL.rstrip('/')}/chat"
THREADS_URL = f"{API_BASE_URL.rstrip('/')}/threads"


def init_session_state() -> None:
    """Initialize frontend session state."""
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = f"demo-{uuid.uuid4().hex[:8]}"
    if "customer_id" not in st.session_state:
        st.session_state.customer_id = ""
    if "login_customer_id" not in st.session_state:
        st.session_state.login_customer_id = ""
    if "is_logged_in" not in st.session_state:
        st.session_state.is_logged_in = False
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "pending_thread_id" not in st.session_state:
        st.session_state.pending_thread_id = ""
    if "pending_reset_chat" not in st.session_state:
        st.session_state.pending_reset_chat = False


def login() -> None:
    """Mock login with customer id only."""
    customer_id = st.session_state.get("login_customer_id", "").strip()
    if not customer_id:
        st.warning("请输入用户 ID 后再登录。")
        return

    st.session_state.customer_id = customer_id
    st.session_state.is_logged_in = True
    st.session_state.thread_id = f"{customer_id}-{uuid.uuid4().hex[:8]}"
    st.session_state.chat_history = []
    st.session_state.pending_thread_id = ""


def logout() -> None:
    """Clear current login state."""
    st.session_state.customer_id = ""
    st.session_state.login_customer_id = ""
    st.session_state.is_logged_in = False
    st.session_state.thread_id = f"demo-{uuid.uuid4().hex[:8]}"
    st.session_state.chat_history = []
    st.session_state.pending_thread_id = ""
    st.session_state.pending_reset_chat = False


def fetch_threads(customer_id: str, limit: int = 20) -> list[dict]:
    """Fetch recent threads for the current customer."""
    normalized_customer_id = customer_id.strip()
    if not normalized_customer_id:
        return []

    try:
        response = requests.get(
            THREADS_URL,
            params={"customer_id": normalized_customer_id, "limit": limit},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return []


def fetch_thread_messages(thread_id: str, customer_id: str) -> list[dict]:
    """Fetch messages for one thread after customer filtering."""
    normalized_thread_id = thread_id.strip()
    normalized_customer_id = customer_id.strip()
    if not normalized_thread_id or not normalized_customer_id:
        return []

    try:
        response = requests.get(
            f"{THREADS_URL}/{normalized_thread_id}/messages",
            params={"customer_id": normalized_customer_id},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return []


def apply_pending_thread_selection() -> None:
    """Apply deferred thread selection before rendering the input widgets."""
    pending_thread_id = st.session_state.get("pending_thread_id", "").strip()
    customer_id = st.session_state.get("customer_id", "").strip()
    if not pending_thread_id or not customer_id:
        return

    st.session_state.thread_id = pending_thread_id
    st.session_state.chat_history = fetch_thread_messages(pending_thread_id, customer_id)
    st.session_state.pending_thread_id = ""


def apply_pending_reset_chat() -> None:
    """Apply deferred chat reset before rendering the input widgets."""
    if not st.session_state.get("pending_reset_chat", False):
        return

    customer_id = st.session_state.get("customer_id", "").strip() or "customer"
    st.session_state.chat_history = []
    st.session_state.thread_id = f"{customer_id}-{uuid.uuid4().hex[:8]}"
    st.session_state.pending_thread_id = ""
    st.session_state.pending_reset_chat = False


def reset_chat() -> None:
    """Reset the current chat window and create a new thread id."""
    st.session_state.pending_reset_chat = True


def render_history() -> None:
    """Render current chat history."""
    for item in st.session_state.chat_history:
        role = item.get("role", "assistant")
        with st.chat_message("user" if role == "user" else "assistant"):
            st.markdown(item.get("content", ""))


def stream_chat(query: str, extra_context: str, thread_id: str, customer_id: str) -> str:
    """Send a streaming request to the backend and return the full answer."""
    answer_parts: list[str] = []

    with st.chat_message("assistant"):
        response_area = st.empty()
        meta_area = st.empty()

        try:
            with requests.post(
                API_URL,
                json={
                    "query": query,
                    "extra_context": extra_context,
                    "thread_id": thread_id,
                    "customer_id": customer_id,
                },
                stream=True,
                timeout=120,
            ) as response:
                response.raise_for_status()

                for raw_line in response.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue
                    if not raw_line.startswith("data:"):
                        continue

                    payload = json.loads(raw_line[5:].strip())
                    content = payload.get("content", "")
                    if content:
                        answer_parts.append(content)
                        response_area.markdown("".join(answer_parts))

                    if payload.get("type") == "done":
                        route = payload.get("route", "")
                        reason = payload.get("reason", "")
                        action_category = payload.get("action_category", "")
                        if route or reason or action_category:
                            lines = [
                                f"`thread_id`: `{thread_id}`",
                                f"`customer_id`: `{customer_id}`",
                            ]
                            if route:
                                lines.append(f"`route`: `{route}`")
                            if action_category:
                                lines.append(f"`action_category`: `{action_category}`")
                            if reason:
                                lines.append(f"`reason`: {reason}")
                            meta_area.caption(" | ".join(lines))

        except requests.exceptions.RequestException as exc:
            error_message = f"请求后端失败：{exc}"
            response_area.error(error_message)
            return error_message

    return "".join(answer_parts).strip()


def render_login_view() -> None:
    """Render the mock login page."""
    st.title("Customer Agent 3")
    st.caption("请先输入用户 ID 登录，登录后才能查看并继续该用户的历史会话。")

    with st.container(border=True):
        st.subheader("模拟登录")
        st.text_input("用户 ID", key="login_customer_id", placeholder="例如：customer-1001")
        if st.button("登录", use_container_width=True):
            login()
            if st.session_state.get("is_logged_in"):
                st.rerun()


def render_chat_view() -> None:
    """Render the chat page for the logged-in customer."""
    st.title("Customer Agent 3")
    st.caption("用于验证登录隔离、历史会话过滤、短期记忆与长期记忆。")

    with st.sidebar:
        st.subheader("当前登录")
        st.caption(f"用户 ID：`{st.session_state.customer_id}`")
        if st.button("退出登录", use_container_width=True):
            logout()
            st.rerun()

        st.subheader("会话设置")
        st.text_input("当前 thread_id", key="thread_id", disabled=True)
        if st.button("新建对话", use_container_width=True):
            reset_chat()
            st.rerun()

        st.markdown("**历史会话**")
        threads = fetch_threads(st.session_state.customer_id, limit=20)
        if not threads:
            st.caption("当前用户暂无历史会话。")
        else:
            for item in threads:
                thread_id = item.get("thread_id", "")
                label = str(item.get("title", thread_id))
                if st.button(label, key=f"load-{thread_id}", use_container_width=True):
                    st.session_state.pending_thread_id = thread_id
                    st.rerun()

    render_history()

    with st.form("chat-form", clear_on_submit=True):
        query = st.text_input("用户问题", placeholder="例如：请问怎么退套餐")
        extra_context = st.text_area("附加上下文", placeholder="可选，补充业务背景或约束")
        submitted = st.form_submit_button("发送", use_container_width=True)

    if submitted and query.strip():
        user_query = query.strip()
        st.session_state.chat_history.append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)

        answer = stream_chat(
            query=user_query,
            extra_context=extra_context.strip(),
            thread_id=st.session_state.thread_id,
            customer_id=st.session_state.customer_id,
        )
        st.session_state.chat_history.append({"role": "assistant", "content": answer})


def main() -> None:
    """Render the demo page."""
    st.set_page_config(page_title="Customer Agent 3", page_icon="💬", layout="wide")
    init_session_state()

    if not st.session_state.get("is_logged_in", False):
        render_login_view()
        return

    apply_pending_reset_chat()
    apply_pending_thread_selection()
    render_chat_view()


if __name__ == "__main__":
    main()
