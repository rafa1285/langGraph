"""Chat schemas for 1-on-1 agent chat endpoint."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatMessageRequest(BaseModel):
    """Request body for sending a chat message to an agent."""

    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(..., min_length=1, max_length=4000)
    project_id: str | None = Field(default=None)
    session_id: str = Field(..., description="UUID string identifying the chat session")


class ChatTurn(BaseModel):
    """A single turn in a chat conversation."""

    model_config = ConfigDict(frozen=True)

    id: str
    session_id: str
    agent_id: str
    project_id: str | None
    role: str  # "user" | "agent"
    content: str
    created_at: str  # ISO 8601


class ChatMessageResponse(BaseModel):
    """Response after sending a message to an agent."""

    model_config = ConfigDict(frozen=True)

    agent_id: str
    response: str
    session_id: str
    timestamp_iso: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


class ChatHistoryResponse(BaseModel):
    """Paginated chat history."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    agent_id: str
    turns: list[ChatTurn]
    total: int
