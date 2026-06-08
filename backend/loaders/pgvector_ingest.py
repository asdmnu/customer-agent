"""把 data 目录中的文本切片并写入 PostgreSQL + pgvector。"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.core.config import load_rag_config
from backend.core.paths import get_abs_path
from backend.stores.pgvector_store import PGVectorStore


RAG_CONFIG = load_rag_config()
DATA_DIR = Path(get_abs_path("data"))


def should_reset_vector_store() -> bool:
    """返回本次导入是否需要先清空向量表。"""
    return os.getenv("RESET_VECTOR_STORE_ON_INGEST", "true").lower() == "true"


def load_source_documents() -> list[Document]:
    """读取 data 目录下的知识库文本文件。"""
    documents: list[Document] = []
    allow_types = {item.lower().lstrip(".") for item in RAG_CONFIG["allow_knowledge_file_type"]}

    for file_path in sorted(DATA_DIR.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower().lstrip(".") not in allow_types:
            continue

        relative_path = file_path.relative_to(DATA_DIR)
        category = relative_path.parts[0] if len(relative_path.parts) > 1 else "default"
        raw_bytes = file_path.read_bytes()
        file_hash = hashlib.sha256(raw_bytes).hexdigest()
        content = raw_bytes.decode("utf-8").strip()
        if not content:
            continue
        documents.append(
            Document(
                page_content=content,
                metadata={
                    "source": file_path.name,
                    "path": str(relative_path).replace("\\", "/"),
                    "category": category,
                    "file_hash": file_hash,
                    "byte_size": len(raw_bytes),
                },
            )
        )
    return documents


def split_documents(documents: list[Document]) -> list[Document]:
    """按配置切分文档。"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=int(RAG_CONFIG["chunk_size"]),
        chunk_overlap=int(RAG_CONFIG["chunk_overlap"]),
        separators=RAG_CONFIG["separators"],
    )

    chunks: list[Document] = []
    for document in documents:
        split_docs = splitter.split_documents([document])
        for chunk_index, chunk in enumerate(split_docs):
            chunk.metadata["chunk_index"] = chunk_index
            chunks.append(chunk)
    return chunks


def ingest_documents(chunks: list[Document], vector_store: PGVectorStore) -> None:
    """写入 PostgreSQL 向量表。"""
    if not chunks:
        print("没有可写入的知识片段。")
        return

    should_reset = should_reset_vector_store()
    if should_reset:
        vector_store.reset_collection()
    vector_store.add_documents(chunks)


def main() -> None:
    vector_store = PGVectorStore()
    documents = load_source_documents()
    if not should_reset_vector_store():
        documents = vector_store.filter_uningested_documents(documents)
    chunks = split_documents(documents)
    ingest_documents(chunks, vector_store)

    print(f"扫描知识文件数：{len(documents)}")
    print(f"生成切片数：{len(chunks)}")
    print(f"PostgreSQL 表：{vector_store.config.table_name}")


if __name__ == "__main__":
    main()
