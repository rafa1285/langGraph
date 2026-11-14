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
    is_visible: int = 1
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


LLMProvider = Literal[
    "google", "groq", "mistral", "openrouter", "openai", "anthropic", "deepseek", "custom"
]
LLMTier = Literal["free", "paid"]
LLMPingStatus = Literal[
    "ok", "missing_api_key", "auth_error", "rate_limited", "timeout", "provider_error"
]


class LLMModelCatalogItem(BaseModel):
    """Global catalog entry for an LLM model."""

    model_config = ConfigDict(extra="ignore")

    model_id: str
    display_name: str
    provider: str
    base_url: str | None = None
    api_key_env: str
    tier: str = "free"
    default_temperature: float = 0.2
    default_max_tokens: int = 4096
    is_active: bool = True
    has_api_key: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class LLMModelCatalogCreate(BaseModel):
    """Payload to create a new model in the catalog."""

    model_config = ConfigDict(extra="ignore")

    model_id: str
    display_name: str
    provider: str
    base_url: str | None = None
    api_key_env: str
    tier: str = "free"
    default_temperature: float = 0.2
    default_max_tokens: int = 4096
    is_active: bool = True


class LLMModelCatalogUpdate(BaseModel):
    """Payload to update an existing model in the catalog."""

    model_config = ConfigDict(extra="ignore")

    display_name: str | None = None
    provider: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    tier: str | None = None
    default_temperature: float | None = None
    default_max_tokens: int | None = None
    is_active: bool | None = None


class AssignedModelItem(BaseModel):
    """Reference to an assigned model in an agent's fallback chain."""

    model_config = ConfigDict(extra="ignore")

    model_id: str
    enabled: bool = True
    priority: int = 1
    display_name: str | None = None
    provider: str | None = None
    tier: str | None = None
    has_api_key: bool | None = None


class AgentLLMConfig(BaseModel):
    """Dynamic LLM configuration and fallback chain assigned to an agent."""

    model_config = ConfigDict(extra="ignore")

    agent_id: str
    assigned_models: list[AssignedModelItem]
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout: int = 60
    max_retries: int = 1
    updated_at: str | None = None


class AgentLLMConfigUpdate(BaseModel):
    """Payload to update an agent's LLM routing configuration."""

    model_config = ConfigDict(extra="ignore")

    assigned_models: list[AssignedModelItem]
    temperature: float | None = None
    max_tokens: int | None = None
    timeout: int | None = None
    max_retries: int | None = None


class LLMModelPingResponse(BaseModel):
    """Diagnosis result of a connection ping test for an LLM model."""

    model_config = ConfigDict(extra="ignore")

    model_id: str
    provider: str
    success: bool
    status: LLMPingStatus
    latency_ms: int | None = None
    http_status: int | None = None
    message: str


class AgentChainLinkPing(BaseModel):
    """Diagnostic status for an individual link in an agent's fallback chain."""

    model_config = ConfigDict(extra="ignore")

    model_id: str
    display_name: str
    provider: str
    tier: str
    priority: int
    role_label: str
    enabled: bool
    ping_result: LLMModelPingResponse


class AgentLLMChainPingResponse(BaseModel):
    """Diagnostic result of testing an agent's entire active model chain."""

    model_config = ConfigDict(extra="ignore")

    agent_id: str
    effective_model_id: str | None = None
    effective_provider: str | None = None
    chain_status: list[AgentChainLinkPing] = Field(default_factory=list)
    all_ok: bool = False
    message: str = ""

