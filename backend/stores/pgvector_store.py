"""基于 PostgreSQL + pgvector 的向量存储。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

import psycopg
from langchain_core.documents import Document

from backend.core.config import load_postgres_config
from backend.models.factory import get_embedding_model


DISTANCE_OPERATORS = {
    "cosine": "<=>",
    "l2": "<->",
    "inner_product": "<#>",
}


@dataclass(slots=True)
class PostgresConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    table_name: str
    embedding_dimension: int
    distance_strategy: str = "cosine"
    fts_regconfig: str = "simple"
    vector_search_k: int = 8
    keyword_search_k: int = 8
    hybrid_top_k: int = 3
    rrf_k: int = 60


@dataclass(slots=True)
class SearchHit:
    content: str
    metadata: dict[str, Any]
    vector_rank: int | None = None
    keyword_rank: int | None = None
    vector_score: float | None = None
    keyword_score: float | None = None
    fusion_score: float = 0.0


class PGVectorStore:
    """封装 pgvector 检索与写入逻辑。"""

    FILE_REGISTRY_TABLE = "ingested_files"

    def __init__(self):
        raw_config = load_postgres_config()
        self.config = PostgresConfig(
            host=raw_config["host"],
            port=int(raw_config["port"]),
            database=raw_config["database"],
            user=raw_config["user"],
            password=raw_config["password"],
            table_name=raw_config["table_name"],
            embedding_dimension=int(raw_config["embedding_dimension"]),
            distance_strategy=raw_config.get("distance_strategy", "cosine"),
            fts_regconfig=raw_config.get("fts_regconfig", "simple"),
            vector_search_k=int(raw_config.get("vector_search_k", 8)),
            keyword_search_k=int(raw_config.get("keyword_search_k", 8)),
            hybrid_top_k=int(raw_config.get("hybrid_top_k", 3)),
            rrf_k=int(raw_config.get("rrf_k", 60)),
        )
        self.embedding_model = get_embedding_model()
        self.distance_operator = DISTANCE_OPERATORS.get(
            self.config.distance_strategy,
            DISTANCE_OPERATORS["cosine"],
        )
        self._ensure_schema()

    @property
    def dsn(self) -> str:
        return (
            f"host={self.config.host} "
            f"port={self.config.port} "
            f"dbname={self.config.database} "
            f"user={self.config.user} "
            f"password={self.config.password}"
        )

    @property
    def fts_regconfig(self) -> str:
        regconfig = self.config.fts_regconfig.strip()
        if not re.fullmatch(r"[A-Za-z0-9_]+", regconfig):
            return "simple"
        return regconfig or "simple"

    def _connect(self):
        return psycopg.connect(self.dsn)

    def _ensure_schema(self) -> None:
        table_name = self.config.table_name
        file_registry_table = self.FILE_REGISTRY_TABLE
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute(
                    """
                    SELECT to_regclass(%s), to_regclass(%s)
                    """,
                    (table_name, f"{table_name}_id_seq"),
                )
                table_regclass, sequence_regclass = cursor.fetchone()
                if table_regclass is None and sequence_regclass is not None:
                    cursor.execute(f"DROP SEQUENCE IF EXISTS {table_name}_id_seq CASCADE")
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table_name} (
                        id BIGSERIAL PRIMARY KEY,
                        content TEXT NOT NULL,
                        source TEXT NOT NULL,
                        path TEXT NOT NULL,
                        category TEXT NOT NULL,
                        chunk_index INTEGER NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        file_hash TEXT NOT NULL DEFAULT '',
                        chunk_uuid TEXT NOT NULL DEFAULT '',
                        embedding VECTOR({self.config.embedding_dimension}) NOT NULL,
                        search_vector TSVECTOR
                    )
                    """
                )
                cursor.execute(
                    f"""
                    ALTER TABLE {table_name}
                    ADD COLUMN IF NOT EXISTS file_hash TEXT NOT NULL DEFAULT ''
                    """
                )
                cursor.execute(
                    f"""
                    ALTER TABLE {table_name}
                    ADD COLUMN IF NOT EXISTS chunk_uuid TEXT NOT NULL DEFAULT ''
                    """
                )
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {file_registry_table} (
                        id BIGSERIAL PRIMARY KEY,
                        file_hash TEXT NOT NULL UNIQUE,
                        source TEXT NOT NULL,
                        path TEXT NOT NULL,
                        category TEXT NOT NULL,
                        byte_size BIGINT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {table_name}_search_vector_idx
                    ON {table_name} USING GIN (search_vector)
                    """
                )
                cursor.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {table_name}_file_hash_idx
                    ON {table_name} (file_hash)
                    """
                )
                cursor.execute(
                    f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS {table_name}_chunk_uuid_uidx
                    ON {table_name} (chunk_uuid)
                    """
                )
                cursor.execute(
                    f"""
                    UPDATE {table_name}
                    SET search_vector = to_tsvector('{self.fts_regconfig}', content)
                    WHERE search_vector IS NULL
                    """
                )
            connection.commit()

    def reset_collection(self) -> None:
        table_name = self.config.table_name
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
                cursor.execute(f"DROP SEQUENCE IF EXISTS {table_name}_id_seq CASCADE")
            connection.commit()
        self._ensure_schema()

    def has_documents(self) -> bool:
        table_name = self.config.table_name
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT EXISTS (SELECT 1 FROM {table_name} LIMIT 1)")
                row = cursor.fetchone()
        return bool(row and row[0])

    def filter_uningested_documents(self, documents: list[Document]) -> list[Document]:
        """基于文件哈希过滤掉已入库过的原始文档。"""
        if not documents:
            return []

        file_hashes = sorted(
            {
                str(document.metadata.get("file_hash", "")).strip()
                for document in documents
                if str(document.metadata.get("file_hash", "")).strip()
            }
        )
        if not file_hashes:
            return documents

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT file_hash FROM {self.FILE_REGISTRY_TABLE} WHERE file_hash = ANY(%s)",
                    (file_hashes,),
                )
                existing_hashes = {str(row[0]) for row in cursor.fetchall()}

        return [
            document
            for document in documents
            if str(document.metadata.get("file_hash", "")).strip() not in existing_hashes
        ]

    def add_documents(self, chunks: list[Document]) -> None:
        if not chunks:
            return

        table_name = self.config.table_name
        texts = [chunk.page_content for chunk in chunks]
        embeddings = self.embedding_model.embed_documents(texts)

        rows: list[tuple[Any, ...]] = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            metadata = dict(chunk.metadata)
            file_hash = str(metadata.get("file_hash", "")).strip()
            chunk_uuid = self._build_chunk_uuid(metadata, chunk.page_content)
            rows.append(
                (
                    chunk.page_content,
                    str(metadata.get("source", "unknown")),
                    str(metadata.get("path", "")),
                    str(metadata.get("category", "default")),
                    int(metadata.get("chunk_index", 0)),
                    json.dumps(metadata, ensure_ascii=False),
                    file_hash,
                    chunk_uuid,
                    self._vector_literal(embedding),
                    chunk.page_content,
                )
            )

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    f"""
                    INSERT INTO {table_name} (
                        content,
                        source,
                        path,
                        category,
                        chunk_index,
                        metadata,
                        file_hash,
                        chunk_uuid,
                        embedding,
                        search_vector
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s::jsonb,
                        %s,
                        %s,
                        %s::vector,
                        to_tsvector('{self.fts_regconfig}', %s)
                    )
                    ON CONFLICT (chunk_uuid) DO NOTHING
                    """,
                    rows,
                )
                file_rows = self._collect_file_rows(chunks)
                if file_rows:
                    cursor.executemany(
                        f"""
                        INSERT INTO {self.FILE_REGISTRY_TABLE} (
                            file_hash,
                            source,
                            path,
                            category,
                            byte_size
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (file_hash) DO UPDATE
                        SET
                            source = EXCLUDED.source,
                            path = EXCLUDED.path,
                            category = EXCLUDED.category,
                            byte_size = EXCLUDED.byte_size,
                            updated_at = NOW()
                        """,
                        file_rows,
                    )
            connection.commit()

    def vector_search(self, query: str, k: int | None = None) -> list[SearchHit]:
        normalized_query = query.strip()
        if not normalized_query:
            return []

        query_embedding = self.embedding_model.embed_query(normalized_query)
        table_name = self.config.table_name
        vector_literal = self._vector_literal(query_embedding)
        top_k = k or self.config.vector_search_k

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT
                        content,
                        source,
                        path,
                        category,
                        chunk_index,
                        metadata,
                        embedding {self.distance_operator} %s::vector AS vector_distance
                    FROM {table_name}
                    ORDER BY vector_distance
                    LIMIT %s
                    """,
                    (vector_literal, top_k),
                )
                rows = cursor.fetchall()

        hits: list[SearchHit] = []
        for rank, row in enumerate(rows, start=1):
            content, source, path, category, chunk_index, metadata, vector_distance = row
            hits.append(
                SearchHit(
                    content=content,
                    metadata=self._merge_metadata(source, path, category, chunk_index, metadata),
                    vector_rank=rank,
                    vector_score=float(vector_distance),
                )
            )
        return hits

    def keyword_search(self, query: str, k: int | None = None) -> list[SearchHit]:
        normalized_query = query.strip()
        if not normalized_query:
            return []

        table_name = self.config.table_name
        top_k = k or self.config.keyword_search_k

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT
                        content,
                        source,
                        path,
                        category,
                        chunk_index,
                        metadata,
                        ts_rank_cd(
                            search_vector,
                            plainto_tsquery('{self.fts_regconfig}', %s)
                        ) AS keyword_score
                    FROM {table_name}
                    WHERE search_vector @@ plainto_tsquery('{self.fts_regconfig}', %s)
                    ORDER BY keyword_score DESC
                    LIMIT %s
                    """,
                    (normalized_query, normalized_query, top_k),
                )
                rows = cursor.fetchall()

        if not rows:
            return self._fallback_keyword_search(normalized_query, top_k)

        hits: list[SearchHit] = []
        for rank, row in enumerate(rows, start=1):
            content, source, path, category, chunk_index, metadata, keyword_score = row
            hits.append(
                SearchHit(
                    content=content,
                    metadata=self._merge_metadata(source, path, category, chunk_index, metadata),
                    keyword_rank=rank,
                    keyword_score=float(keyword_score),
                )
            )
        return hits

    def hybrid_search(self, query: str, k: int | None = None) -> list[Document]:
        normalized_query = query.strip()
        if not normalized_query:
            return []

        top_k = k or self.config.hybrid_top_k
        vector_hits = self.vector_search(normalized_query, k=self.config.vector_search_k)
        keyword_hits = self.keyword_search(normalized_query, k=self.config.keyword_search_k)

        if not keyword_hits:
            return self._hits_to_documents(vector_hits[:top_k])

        merged_hits: dict[tuple[str, str, str], SearchHit] = {}
        for hit in vector_hits:
            merged_hits[self._hit_key(hit)] = hit

        for hit in keyword_hits:
            key = self._hit_key(hit)
            existing = merged_hits.get(key)
            if existing is None:
                merged_hits[key] = hit
                continue
            existing.keyword_rank = hit.keyword_rank
            existing.keyword_score = hit.keyword_score

        ranked_hits = list(merged_hits.values())
        for hit in ranked_hits:
            hit.fusion_score = self._rrf_score(hit)
        ranked_hits.sort(
            key=lambda item: (
                item.fusion_score,
                -(item.keyword_score or 0.0),
                -((1.0 / (1.0 + item.vector_score)) if item.vector_score is not None else 0.0),
            ),
            reverse=True,
        )
        return self._hits_to_documents(ranked_hits[:top_k])

    @staticmethod
    def _vector_literal(embedding: list[float]) -> str:
        return "[" + ",".join(str(value) for value in embedding) + "]"

    @staticmethod
    def _build_chunk_uuid(metadata: dict[str, Any], content: str) -> str:
        file_hash = str(metadata.get("file_hash", "")).strip()
        path = str(metadata.get("path", "")).strip()
        chunk_index = int(metadata.get("chunk_index", 0))
        raw = f"{file_hash}:{path}:{chunk_index}:{content}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _collect_file_rows(chunks: list[Document]) -> list[tuple[str, str, str, str, int]]:
        unique_rows: dict[str, tuple[str, str, str, str, int]] = {}
        for chunk in chunks:
            metadata = dict(chunk.metadata)
            file_hash = str(metadata.get("file_hash", "")).strip()
            if not file_hash:
                continue
            if file_hash in unique_rows:
                continue
            unique_rows[file_hash] = (
                file_hash,
                str(metadata.get("source", "unknown")),
                str(metadata.get("path", "")),
                str(metadata.get("category", "default")),
                int(metadata.get("byte_size", 0)),
            )
        return list(unique_rows.values())

    @staticmethod
    def _merge_metadata(
        source: str,
        path: str,
        category: str,
        chunk_index: int,
        metadata: dict[str, Any] | Any,
    ) -> dict[str, Any]:
        combined_metadata = {
            "source": source,
            "path": path,
            "category": category,
            "chunk_index": chunk_index,
        }
        if isinstance(metadata, dict):
            combined_metadata.update(metadata)
        return combined_metadata

    @staticmethod
    def _hit_key(hit: SearchHit) -> tuple[str, str, str]:
        return (
            str(hit.metadata.get("path", "")),
            str(hit.metadata.get("chunk_index", "")),
            hit.content,
        )

    def _rrf_score(self, hit: SearchHit) -> float:
        score = 0.0
        if hit.vector_rank is not None:
            score += 1.0 / (self.config.rrf_k + hit.vector_rank)
        if hit.keyword_rank is not None:
            score += 1.0 / (self.config.rrf_k + hit.keyword_rank)
        return score

    def _fallback_keyword_search(self, query: str, k: int) -> list[SearchHit]:
        keywords = [item for item in re.split(r"\s+", query.strip()) if item]
        if not keywords:
            return []

        conditions = " OR ".join(["content ILIKE %s" for _ in keywords])
        score_terms = " + ".join([f"(CASE WHEN content ILIKE %s THEN 1 ELSE 0 END)" for _ in keywords])
        params: list[Any] = [f"%{keyword}%" for keyword in keywords]
        score_params: list[Any] = [f"%{keyword}%" for keyword in keywords]
        table_name = self.config.table_name

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT
                        content,
                        source,
                        path,
                        category,
                        chunk_index,
                        metadata,
                        ({score_terms}) AS keyword_score
                    FROM {table_name}
                    WHERE {conditions}
                    ORDER BY keyword_score DESC, chunk_index ASC
                    LIMIT %s
                    """,
                    tuple(score_params + params + [k]),
                )
                rows = cursor.fetchall()

        hits: list[SearchHit] = []
        for rank, row in enumerate(rows, start=1):
            content, source, path, category, chunk_index, metadata, keyword_score = row
            hits.append(
                SearchHit(
                    content=content,
                    metadata=self._merge_metadata(source, path, category, chunk_index, metadata),
                    keyword_rank=rank,
                    keyword_score=float(keyword_score),
                )
            )
        return hits

    @staticmethod
    def _hits_to_documents(hits: list[SearchHit]) -> list[Document]:
        return [Document(page_content=hit.content, metadata=hit.metadata) for hit in hits]
