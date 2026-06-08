"""Short-term session memory service."""

from __future__ import annotations

import psycopg

from backend.core.config import load_postgres_config
from backend.models.factory import get_chat_model


class SessionMemoryService:
    """Persist conversation messages by thread."""

    TABLE_NAME = "session_messages"
    SUMMARY_TABLE_NAME = "session_summaries"
    SUMMARY_TRIGGER_MESSAGES = 26
    SUMMARY_KEEP_MESSAGES = 20

    def __init__(self, max_messages: int = 20):
        self.max_messages = max_messages
        self.config = load_postgres_config()
        self._ensure_schema()

    @property
    def dsn(self) -> str:
        return (
            f"host={self.config['host']} "
            f"port={self.config['port']} "
            f"dbname={self.config['database']} "
            f"user={self.config['user']} "
            f"password={self.config['password']}"
        )

    def _connect(self):
        return psycopg.connect(self.dsn)

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                        id BIGSERIAL PRIMARY KEY,
                        thread_id TEXT NOT NULL,
                        customer_id TEXT NOT NULL DEFAULT '',
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    f"""
                    ALTER TABLE {self.TABLE_NAME}
                    ADD COLUMN IF NOT EXISTS customer_id TEXT NOT NULL DEFAULT ''
                    """
                )
                cursor.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self.TABLE_NAME}_thread_created_idx
                    ON {self.TABLE_NAME} (thread_id, created_at, id)
                    """
                )
                cursor.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self.TABLE_NAME}_customer_idx
                    ON {self.TABLE_NAME} (customer_id, created_at, id)
                    """
                )
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.SUMMARY_TABLE_NAME} (
                        thread_id TEXT PRIMARY KEY,
                        summary TEXT NOT NULL DEFAULT '',
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            connection.commit()

    def get_messages(self, thread_id: str, customer_id: str) -> list[dict[str, str]]:
        """Return all messages for one customer thread."""
        normalized_thread_id = thread_id.strip()
        normalized_customer_id = customer_id.strip()
        if not normalized_thread_id or not normalized_customer_id:
            return []

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT role, content
                    FROM {self.TABLE_NAME}
                    WHERE thread_id = %s AND customer_id = %s
                    ORDER BY created_at ASC, id ASC
                    """,
                    (normalized_thread_id, normalized_customer_id),
                )
                rows = cursor.fetchall()
        return [{"role": str(role), "content": str(content)} for role, content in rows]

    def get_conversation_summary(self, thread_id: str, customer_id: str) -> str:
        """Return summary for one customer thread."""
        normalized_thread_id = thread_id.strip()
        normalized_customer_id = customer_id.strip()
        if not normalized_thread_id or not normalized_customer_id:
            return ""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT summary
                    FROM {self.SUMMARY_TABLE_NAME}
                    WHERE thread_id = %s AND customer_id = %s
                    """,
                    (normalized_thread_id, normalized_customer_id),
                )
                row = cursor.fetchone()
        return str(row[0]).strip() if row and row[0] else ""

    def list_threads(self, customer_id: str, limit: int = 50) -> list[dict[str, str | int]]:
        """List recent threads for one customer."""
        normalized_customer_id = customer_id.strip()
        if not normalized_customer_id:
            return []

        top_n = max(1, limit)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT
                        thread_id,
                        COUNT(*) AS message_count,
                        MAX(created_at) AS last_message_at
                    FROM {self.TABLE_NAME}
                    WHERE customer_id = %s
                    GROUP BY thread_id
                    ORDER BY last_message_at DESC
                    LIMIT %s
                    """,
                    (normalized_customer_id, top_n),
                )
                rows = cursor.fetchall()
        return [
            {
                "thread_id": str(thread_id),
                "title": self._build_thread_title(str(thread_id), normalized_customer_id),
                "message_count": int(message_count),
                "last_message_at": last_message_at.isoformat() if last_message_at else "",
            }
            for thread_id, message_count, last_message_at in rows
        ]

    def thread_belongs_to_customer(self, thread_id: str, customer_id: str) -> bool:
        """Check whether a thread belongs to a customer."""
        normalized_thread_id = thread_id.strip()
        normalized_customer_id = customer_id.strip()
        if not normalized_thread_id or not normalized_customer_id:
            return False

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT EXISTS (
                        SELECT 1
                        FROM {self.TABLE_NAME}
                        WHERE thread_id = %s AND customer_id = %s
                    )
                    """,
                    (normalized_thread_id, normalized_customer_id),
                )
                row = cursor.fetchone()
        return bool(row and row[0])

    def append_user_message(self, thread_id: str, customer_id: str, content: str) -> None:
        """Append a user message."""
        self._append_message(thread_id, customer_id, role="user", content=content)

    def append_assistant_message(self, thread_id: str, customer_id: str, content: str) -> None:
        """Append an assistant message."""
        self._append_message(thread_id, customer_id, role="assistant", content=content)

    def format_recent_history(
        self,
        thread_id: str,
        customer_id: str,
        limit: int | None = None,
    ) -> str:
        """Format recent thread history as plain text."""
        messages = self.get_messages(thread_id, customer_id)
        selected_messages = messages[-limit:] if limit else messages
        lines: list[str] = []
        for message in selected_messages:
            role = message.get("role", "assistant")
            speaker = "用户" if role == "user" else "助手"
            content = message.get("content", "").strip()
            if content:
                lines.append(f"{speaker}：{content}")
        return "\n".join(lines)

    def _append_message(self, thread_id: str, customer_id: str, role: str, content: str) -> None:
        """Insert a message and keep short-term memory bounded."""
        normalized_thread_id = thread_id.strip()
        normalized_customer_id = customer_id.strip()
        normalized_content = content.strip()
        if not normalized_thread_id or not normalized_content:
            return

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO {self.TABLE_NAME} (thread_id, customer_id, role, content)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (normalized_thread_id, normalized_customer_id, role, normalized_content),
                )
                summary = self.get_conversation_summary(
                    normalized_thread_id,
                    normalized_customer_id,
                )
                cursor.execute(
                    f"""
                    SELECT id, role, content
                    FROM {self.TABLE_NAME}
                    WHERE thread_id = %s AND customer_id = %s
                    ORDER BY created_at ASC, id ASC
                    """,
                    (normalized_thread_id, normalized_customer_id),
                )
                rows = cursor.fetchall()
                if len(rows) >= self.SUMMARY_TRIGGER_MESSAGES:
                    rows_to_summarize = rows[: -self.SUMMARY_KEEP_MESSAGES]
                    kept_rows = rows[-self.SUMMARY_KEEP_MESSAGES :]
                    history_text = self._format_history_rows(rows_to_summarize)
                    merged_summary = self._summarize_history(
                        existing_summary=summary,
                        history_text=history_text,
                    )
                    cursor.execute(
                        f"""
                        INSERT INTO {self.SUMMARY_TABLE_NAME} (thread_id, customer_id, summary, updated_at)
                        VALUES (%s, %s, %s, NOW())
                        ON CONFLICT (thread_id, customer_id) DO UPDATE
                        SET summary = EXCLUDED.summary, updated_at = NOW()
                        """,
                        (normalized_thread_id, normalized_customer_id, merged_summary),
                    )
                    keep_ids = [int(row[0]) for row in kept_rows]
                    cursor.execute(
                        f"""
                        DELETE FROM {self.TABLE_NAME}
                        WHERE thread_id = %s AND customer_id = %s
                        AND id <> ALL(%s)
                        """,
                        (normalized_thread_id, normalized_customer_id, keep_ids),
                    )
                else:
                    cursor.execute(
                        f"""
                        DELETE FROM {self.TABLE_NAME}
                        WHERE thread_id = %s AND customer_id = %s
                        AND id NOT IN (
                            SELECT id
                            FROM {self.TABLE_NAME}
                            WHERE thread_id = %s AND customer_id = %s
                            ORDER BY created_at DESC, id DESC
                            LIMIT %s
                        )
                        """,
                        (
                            normalized_thread_id,
                            normalized_customer_id,
                            normalized_thread_id,
                            normalized_customer_id,
                            self.max_messages,
                        ),
                    )
            connection.commit()

    @staticmethod
    def _message_content_to_text(content: object) -> str:
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
                else:
                    text = getattr(item, "text", "") or getattr(item, "content", "")
                    if text:
                        parts.append(str(text))
            return "".join(parts)
        return str(content or "")

    def _summarize_history(self, existing_summary: str, history_text: str) -> str:
        if not history_text.strip():
            return existing_summary.strip()

        prompt = (
            "你是客服对话摘要助手。\n"
            "请把历史对话压缩成简洁摘要，保留以下信息：\n"
            "1. 用户姓名、称呼、身份偏好\n"
            "2. 订单号、手机号后四位、账户 ID\n"
            "3. 用户核心诉求、问题进展、未解决事项\n"
            "4. 重要限制条件、承诺、风险点\n\n"
            f"已有摘要：\n{existing_summary or '无'}\n\n"
            f"新增需要压缩的历史对话：\n{history_text}\n\n"
            "请输出新的合并摘要，使用简洁中文，不要编造信息。"
        )
        response = get_chat_model().invoke(prompt)
        return self._message_content_to_text(getattr(response, "content", response)).strip() or existing_summary

    @staticmethod
    def _format_history_rows(rows: list[tuple[int, str, str]]) -> str:
        lines: list[str] = []
        for _, role, content in rows:
            speaker = "用户" if str(role).strip().lower() == "user" else "助手"
            normalized_content = str(content).strip()
            if normalized_content:
                lines.append(f"{speaker}：{normalized_content}")
        return "\n".join(lines)

    def _build_thread_title(self, thread_id: str, customer_id: str) -> str:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT content
                    FROM {self.TABLE_NAME}
                    WHERE thread_id = %s AND customer_id = %s AND role = 'user'
                    ORDER BY created_at ASC, id ASC
                    LIMIT 1
                    """,
                    (thread_id, customer_id),
                )
                row = cursor.fetchone()

        if not row or not row[0]:
            return thread_id

        content = str(row[0]).strip().replace("\n", " ")
        if "RAG检索内容：" in content and "用户问题：" in content:
            content = content.split("RAG检索内容：", 1)[0].replace("用户问题：", "").strip()
        return content[:18] + "..." if len(content) > 18 else content


session_memory_service = SessionMemoryService()
