"""回答生成链。"""

from langchain_core.prompts import PromptTemplate

from backend.core.config import load_answer_prompt
from backend.models.factory import get_chat_model


def build_answer_prompt(
    query: str,
    extra_context: str,
    retrieval_context: str,
    conversation_history: str,
) -> str:
    """渲染最终回答提示词。"""
    prompt = PromptTemplate.from_template(load_answer_prompt())
    return prompt.format(
        query=query,
        extra_context=extra_context or "无",
        conversation_history=conversation_history or "无",
        retrieval_context=retrieval_context or "没有检索到相关上下文。",
    )


def _chunk_to_text(chunk: object) -> str:
    """把流式分片统一转换成纯文本。"""
    content = getattr(chunk, "content", chunk)
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


def stream_answer_chunks(
    query: str,
    extra_context: str,
    retrieval_context: str,
    conversation_history: str = "",
):
    """通过聊天模型流式生成回答文本。"""
    final_prompt = build_answer_prompt(
        query=query,
        extra_context=extra_context,
        retrieval_context=retrieval_context,
        conversation_history=conversation_history,
    )
    model = get_chat_model()
    for chunk in model.stream(final_prompt):
        text = _chunk_to_text(chunk)
        if text:
            yield text


def split_text_chunks(text: str, chunk_size: int = 18) -> list[str]:
    """把固定文本切成适合前端渐进刷新的小片段。"""
    if not text:
        return [""]
    return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)]
