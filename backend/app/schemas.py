"""API request and response schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Chat request payload."""

    query: str = Field(..., min_length=1, description="User query")
    extra_context: str = Field("", description="Additional context")
    thread_id: str = Field("session-default", description="Conversation thread ID")
    customer_id: str = Field("customer-default", min_length=1, description="Customer identity ID")


class StreamChunk(BaseModel):
    """Streaming response chunk."""

    type: Literal["delta", "done", "error"] = Field(..., description="Chunk type")
    content: str = Field("", description="Chunk content")


class HistoryMessage(BaseModel):
    """Conversation history message."""

    role: str = Field(..., description="Message role")
    content: str = Field(..., description="Message content")


class ThreadSummary(BaseModel):
    """Thread summary item."""

    thread_id: str = Field(..., description="Conversation thread ID")
    title: str = Field(..., description="Conversation title")
    message_count: int = Field(..., description="Message count")
    last_message_at: str = Field(..., description="Last message time")


class ThreadCreateRequest(BaseModel):
    """Thread create request."""

    thread_id: str = Field(..., min_length=1, description="Conversation thread ID")
    title: str = Field("新建对话", description="Conversation title")
