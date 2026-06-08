"""知识库检索访问层。"""

from __future__ import annotations

from langchain_core.documents import Document

from backend.core.config import load_rag_config
from backend.stores.pgvector_store import PGVectorStore


RAG_CONFIG = load_rag_config()


class RetrievalStore:
    """封装 PostgreSQL 向量库的检索逻辑。"""

    def __init__(self):
        self.top_k = int(RAG_CONFIG["top_k"])
        self.vector_store = PGVectorStore()

    def search(self, query: str, top_k: int | None = None) -> list[dict[str, str]]:
        """执行混合检索并返回统一字典结构。"""
        documents = self.vector_store.hybrid_search(query, k=top_k or self.top_k)
        return [self._document_to_dict(document) for document in documents]

    @staticmethod
    def _document_to_dict(document: Document) -> dict[str, str]:
        """把检索结果转换成统一字典结构。"""
        return {
            "source": str(document.metadata.get("source", "unknown")),
            "content": document.page_content,
            "path": str(document.metadata.get("path", "")),
            "chunk_index": str(document.metadata.get("chunk_index", "")),
        }


retrieval_store = RetrievalStore()
