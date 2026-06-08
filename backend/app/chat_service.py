"""Main chat orchestration service."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator

from langsmith import traceable, tracing_context

from backend.app.schemas import ChatRequest, StreamChunk
from backend.flows.action.action_agent import run_action_agent
from backend.flows.qa.answer_generator import split_text_chunks, stream_answer_chunks
from backend.flows.qa.knowledge_retriever import retrieve_context
from backend.memory.session_memory_service import session_memory_service
from backend.memory.user_memory_service import user_memory_service
from backend.routers.action_router import route_action_query
from backend.routers.request_router import route_query


class ChatService:
    """Route each request to QA or action execution."""

    @traceable(name="chat_stream")
    def stream_chat(self, payload: ChatRequest) -> Iterator[str]:
        """Stream SSE response chunks."""
        history_messages = session_memory_service.get_messages(
            payload.thread_id,
            payload.customer_id,
        )
        conversation_summary = session_memory_service.get_conversation_summary(
            payload.thread_id,
            payload.customer_id,
        )
        recent_history_text = session_memory_service.format_recent_history(
            payload.thread_id,
            payload.customer_id,
            limit=8,
        )
        long_term_memory_text = user_memory_service.format_memories(payload.customer_id)

        history_parts: list[str] = []
        if long_term_memory_text:
            history_parts.append(f"客户长期记忆：\n{long_term_memory_text}")
        if conversation_summary:
            history_parts.append(f"历史摘要：\n{conversation_summary}")
        if recent_history_text:
            history_parts.append(f"最近对话：\n{recent_history_text}")
        history_text = "\n\n".join(history_parts)

        project_name = os.getenv("LANGSMITH_PROJECT", "customer-agent3")
        tracing_enabled = os.getenv("LANGSMITH_TRACING", "true").lower() == "true"
        metadata = {
            "thread_id": payload.thread_id,
            "customer_id": payload.customer_id,
            "query": payload.query,
            "extra_context": payload.extra_context,
            "history_turns": len(history_messages),
        }

        with tracing_context(
            project_name=project_name,
            metadata=metadata,
            enabled=tracing_enabled,
        ):
            decision = route_query(
                payload.query,
                payload.extra_context,
                history_text=history_text,
            )

            if decision.route == "qa":
                retrieval_context = retrieve_context(
                    payload.query,
                    conversation_history=history_text,
                )
                answer_parts: list[str] = []
                for text in stream_answer_chunks(
                    query=payload.query,
                    extra_context=payload.extra_context,
                    retrieval_context=retrieval_context,
                    conversation_history=history_text,
                ):
                    answer_parts.append(text)
                    delta_payload = StreamChunk(type="delta", content=text).model_dump()
                    yield self._format_sse("delta", delta_payload)

                final_answer = "".join(answer_parts).strip()
                session_memory_service.append_user_message(
                    payload.thread_id,
                    payload.customer_id,
                    self._build_qa_memory_message(payload.query, retrieval_context),
                )
                session_memory_service.append_assistant_message(
                    payload.thread_id,
                    payload.customer_id,
                    final_answer,
                )
                self._refresh_long_term_memory(payload.thread_id, payload.customer_id)

                done_payload = {
                    "type": "done",
                    "content": "",
                    "thread_id": payload.thread_id,
                    "customer_id": payload.customer_id,
                    "route": decision.route,
                    "reason": decision.reason,
                    "answer": final_answer,
                }
                yield self._format_sse("done", done_payload)
                return

            action_decision = route_action_query(
                payload.query,
                payload.extra_context,
                history_text=history_text,
            )
            answer = run_action_agent(
                payload.query,
                category=action_decision.category,
                history_messages=history_messages,
            )
            session_memory_service.append_user_message(
                payload.thread_id,
                payload.customer_id,
                payload.query,
            )
            session_memory_service.append_assistant_message(
                payload.thread_id,
                payload.customer_id,
                answer,
            )
            self._refresh_long_term_memory(payload.thread_id, payload.customer_id)

            for text in split_text_chunks(answer):
                delta_payload = StreamChunk(type="delta", content=text).model_dump()
                yield self._format_sse("delta", delta_payload)

            done_payload = {
                "type": "done",
                "content": "",
                "thread_id": payload.thread_id,
                "customer_id": payload.customer_id,
                "route": decision.route,
                "reason": decision.reason,
                "action_category": action_decision.category,
                "action_reason": action_decision.reason,
                "answer": answer,
            }
            yield self._format_sse("done", done_payload)

    def _refresh_long_term_memory(self, thread_id: str, customer_id: str) -> None:
        """Extract long-term memory every few turns."""
        recent_messages = session_memory_service.get_messages(thread_id, customer_id)
        user_memory_service.maybe_extract_and_store_memories(
            customer_id=customer_id,
            recent_messages=recent_messages,
        )

    @staticmethod
    def _format_sse(event: str, payload: dict) -> str:
        """Encode an SSE event payload."""
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    @staticmethod
    def _build_qa_memory_message(query: str, retrieval_context: str) -> str:
        """Store the user question together with retrieval context in short-term memory."""
        normalized_query = query.strip()
        normalized_context = retrieval_context.strip()
        if not normalized_context:
            return normalized_query
        return f"用户问题：\n{normalized_query}\n\nRAG检索内容：\n{normalized_context}"


chat_service = ChatService()
