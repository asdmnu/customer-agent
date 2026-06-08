"""QA 路径的检索辅助逻辑。"""

from backend.stores.retrieval_store import retrieval_store


def _build_retrieval_query(query: str, conversation_history: str = "") -> str:
    """把当前问题和历史对话合并成检索语句。"""
    if not conversation_history.strip():
        return query
    return f"历史对话：\n{conversation_history}\n\n当前问题：\n{query}"


def retrieve_context(query: str, conversation_history: str = "") -> str:
    """检索知识库并格式化命中的片段。"""
    docs = retrieval_store.search(_build_retrieval_query(query, conversation_history))
    if not docs:
        return "没有找到匹配的知识库片段。"

    lines: list[str] = []
    for index, doc in enumerate(docs, start=1):
        lines.append(
            f"[参考资料 {index}]\n"
            f"来源：{doc['source']}\n"
            f"路径：{doc.get('path', '')}\n"
            f"切片：{doc.get('chunk_index', '')}\n"
            f"内容：{doc['content']}"
        )
    return "\n\n".join(lines)
