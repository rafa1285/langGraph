"""Pydantic schemas for agent conversations, internal email, and telemetry."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.routing import AgentID, DeliverableStatus

EmailPriority = Literal["NORMAL", "HIGH", "CRITICAL"]


class AgentConversationRecord(BaseModel):
    """Immutable audit record of a single LLM agent invocation and telemetry."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    project_id: str
    step_number: int
    agent_id: AgentID
    system_prompt: str
    user_payload: str
    raw_response: str
    status: DeliverableStatus
    verdict: str | None = None
    score: int | None = None
    culprit: str | None = None
    duration_ms: int
    estimated_tokens_in: int
    estimated_tokens_out: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentEmailRecord(BaseModel):
    """Immutable record of an internal handoff or notification email between agents."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    project_id: str
    step_number: int
    sender: str
    recipient: str
    cc: list[str] = Field(default_factory=list)
    subject: str
    body_summary: str
    attached_deliverable_path: str
    priority: EmailPriority = "NORMAL"
    is_read: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
