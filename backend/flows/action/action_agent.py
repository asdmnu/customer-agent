"""基于 LangChain create_agent 的受限执行 Agent。"""

from __future__ import annotations

from functools import lru_cache

from langchain.agents import create_agent

from backend.core.config import load_action_system_prompt
from backend.models.factory import get_chat_model
from backend.tools.tool_registry import get_tools_by_category


def _extract_text(content: object) -> str:
    """把 LangChain 消息内容统一转换成纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return str(content or "")


@lru_cache(maxsize=8)
def build_action_agent(category: str):
    """按子场景构建可复用的执行类 Agent 实例。"""
    return create_agent(
        model=get_chat_model(),
        tools=get_tools_by_category(category),
        system_prompt=load_action_system_prompt(),
    )


def run_action_agent(
    user_query: str,
    category: str,
    history_messages: list[dict[str, str]] | None = None,
) -> str:
    """运行执行类 Agent，并返回最终文本回答。"""
    agent = build_action_agent(category)
    request_messages = list(history_messages or [])
    request_messages.append({"role": "user", "content": user_query})
    result = agent.invoke(
        {
            "messages": request_messages
        }
    )
    messages = result.get("messages", [])
    if not messages:
        return "执行类 Agent 没有返回消息。"
    final_message = messages[-1]
    return _extract_text(getattr(final_message, "content", final_message)).strip()
