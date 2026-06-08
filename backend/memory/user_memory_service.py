"""Long-term user memory service."""

from __future__ import annotations

import json

import psycopg

from backend.core.config import load_postgres_config
from backend.models.factory import get_chat_model


class UserMemoryService:
    """Persist customer memories keyed by customer identity."""

    TABLE_NAME = "user_memories"
    EXTRACTION_TRIGGER_MESSAGES = 12

    def __init__(self):
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
                        customer_id TEXT NOT NULL,
                        memory_type TEXT NOT NULL,
                        fact TEXT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self.TABLE_NAME}_customer_idx
                    ON {self.TABLE_NAME} (customer_id)
                    """
                )
                cursor.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self.TABLE_NAME}_customer_type_idx
                    ON {self.TABLE_NAME} (customer_id, memory_type)
                    """
                )
            connection.commit()

    def list_memories(self, customer_id: str) -> list[dict[str, str]]:
        normalized_customer_id = customer_id.strip()
        if not normalized_customer_id:
            return []

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT memory_type, fact
                    FROM {self.TABLE_NAME}
                    WHERE customer_id = %s
                    ORDER BY id ASC
                    """,
                    (normalized_customer_id,),
                )
                rows = cursor.fetchall()
        return [{"memory_type": str(memory_type), "fact": str(fact)} for memory_type, fact in rows]

    def format_memories(self, customer_id: str) -> str:
        memories = self.list_memories(customer_id)
        if not memories:
            return ""
        lines = [f"{index}. {item['fact']}" for index, item in enumerate(memories, start=1)]
        return "\n".join(lines)

    def add_memory(self, customer_id: str, memory_type: str, fact: str) -> None:
        normalized_customer_id = customer_id.strip()
        normalized_memory_type = memory_type.strip()
        normalized_fact = fact.strip()
        if not normalized_customer_id or not normalized_memory_type or not normalized_fact:
            return

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT 1
                    FROM {self.TABLE_NAME}
                    WHERE customer_id = %s
                    AND memory_type = %s
                    AND fact = %s
                    LIMIT 1
                    """,
                    (normalized_customer_id, normalized_memory_type, normalized_fact),
                )
                if cursor.fetchone():
                    return

                cursor.execute(
                    f"""
                    INSERT INTO {self.TABLE_NAME} (customer_id, memory_type, fact)
                    VALUES (%s, %s, %s)
                    """,
                    (normalized_customer_id, normalized_memory_type, normalized_fact),
                )
            connection.commit()

    def maybe_extract_and_store_memories(
        self,
        customer_id: str,
        recent_messages: list[dict[str, str]],
    ) -> None:
        normalized_customer_id = customer_id.strip()
        if not normalized_customer_id:
            return
        if len(recent_messages) < self.EXTRACTION_TRIGGER_MESSAGES:
            return
        if len(recent_messages) % self.EXTRACTION_TRIGGER_MESSAGES != 0:
            return

        extracted_memories = self._extract_memories(recent_messages[-self.EXTRACTION_TRIGGER_MESSAGES :])
        for item in extracted_memories:
            self.add_memory(
                customer_id=normalized_customer_id,
                memory_type=item.get("memory_type", ""),
                fact=item.get("fact", ""),
            )

    def _extract_memories(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        history_text = self._format_messages(messages)
        if not history_text:
            return []

        prompt = (
            "你是客服系统的长期记忆提取器。\n"
            "请根据下面多轮对话，提取值得长期记住的客户事实。\n\n"
            "只提取以下类型：\n"
            "1. profile：身份信息，如姓名、称呼、号码后四位、账户身份\n"
            "2. preference：稳定偏好，如短信通知、电话联系、语言偏好\n"
            "3. constraint：长期限制条件\n"
            "4. issue：持续性问题，后续还可能再次提起\n\n"
            "不要提取寒暄、一次性提问、泛知识问题，也不要编造信息。\n"
            "如果没有可保存内容，返回 {\"memories\": []}。\n"
            "输出必须是严格 JSON，格式如下：\n"
            "{\"memories\":[{\"memory_type\":\"profile\",\"fact\":\"客户姓名是张三\"}]}\n\n"
            f"对话内容：\n{history_text}"
        )
        response = get_chat_model().invoke(prompt)
        content = self._message_content_to_text(getattr(response, "content", response)).strip()
        return self._parse_memories(content)

    @staticmethod
    def _format_messages(messages: list[dict[str, str]]) -> str:
        lines: list[str] = []
        for item in messages:
            role = item.get("role", "").strip().lower()
            content = item.get("content", "").strip()
            if not content:
                continue
            speaker = "用户" if role == "user" else "助手"
            lines.append(f"{speaker}：{content}")
        return "\n".join(lines)

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

    @staticmethod
    def _parse_memories(raw_text: str) -> list[dict[str, str]]:
        if not raw_text:
            return []

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            start = raw_text.find("{")
            end = raw_text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return []
            try:
                payload = json.loads(raw_text[start : end + 1])
            except json.JSONDecodeError:
                return []

        memories = payload.get("memories", [])
        if not isinstance(memories, list):
            return []

        normalized_memories: list[dict[str, str]] = []
        for item in memories:
            if not isinstance(item, dict):
                continue
            memory_type = str(item.get("memory_type", "")).strip()
            fact = str(item.get("fact", "")).strip()
            if memory_type and fact:
                normalized_memories.append({"memory_type": memory_type, "fact": fact})
        return normalized_memories


user_memory_service = UserMemoryService()
