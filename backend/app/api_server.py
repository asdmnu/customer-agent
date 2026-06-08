"""FastAPI service entrypoint."""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.chat_service import chat_service
from backend.app.schemas import ChatRequest, HistoryMessage, ThreadSummary
from backend.core.paths import get_abs_path
from backend.memory.session_memory_service import session_memory_service


ENV_PATH = Path(get_abs_path(".env"))
load_dotenv(dotenv_path=ENV_PATH)


app = FastAPI(title="Customer Agent 3 API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/chat")
def chat(payload: ChatRequest) -> StreamingResponse:
    """Streaming chat endpoint."""
    return StreamingResponse(
        chat_service.stream_chat(payload),
        media_type="text/event-stream",
    )


@app.get("/threads", response_model=list[ThreadSummary])
def list_threads(customer_id: str, limit: int = 50) -> list[ThreadSummary]:
    """List recent threads for one customer."""
    return [
        ThreadSummary(**item)
        for item in session_memory_service.list_threads(customer_id=customer_id, limit=limit)
    ]


@app.get("/threads/{thread_id}/messages", response_model=list[HistoryMessage])
def get_thread_messages(thread_id: str, customer_id: str) -> list[HistoryMessage]:
    """Read messages for one thread after ownership check."""
    if not session_memory_service.thread_belongs_to_customer(thread_id, customer_id):
        raise HTTPException(status_code=404, detail="Thread not found for current customer")
    return [
        HistoryMessage(**item)
        for item in session_memory_service.get_messages(thread_id, customer_id)
    ]
