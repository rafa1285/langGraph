"""Pydantic schemas for the Telemetry & Dashboard operations engine."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KpiTelemetryResponse(BaseModel):
    """Real-time aggregated KPIs for the top status bar and office HUD."""

    model_config = ConfigDict(extra="forbid")

    projects_count: int = Field(..., description="Total unique projects in database and workspaces")
    total_tokens: int = Field(..., description="Total tokens consumed across all agent executions")
    total_tokens_in: int = Field(..., description="Prompt/input tokens")
    total_tokens_out: int = Field(..., description="Completion/output tokens")
    estimated_cost_usd: float = Field(..., description="Total estimated cost in USD")
    today_tokens: int = Field(..., description="Tokens consumed today")
    today_cost_usd: float = Field(..., description="Cost incurred today in USD")
    saved_usd: float = Field(..., description="Estimated development savings in USD")
    health_score: int = Field(..., description="System health percentage (0-100%)")
    agents_ready: int = Field(..., description="Count of agents currently ready/operational")
    agents_total: int = Field(..., description="Total configured agents in the office")
    circuit_breakers_tripped: int = Field(..., description="Count of active circuit breaker blocks")
    last_updated: str = Field(..., description="ISO 8601 timestamp of last telemetry sample")


class DashboardTelemetryResponse(BaseModel):
    """Real telemetry metrics computed exclusively from real LangGraph state and database."""

    model_config = ConfigDict(extra="forbid")

    projects: int = Field(..., description="Real count of projects")
    tokens: int = Field(..., description="Real sum of tokens consumed")
    tokens_in: int = Field(..., description="Input prompt tokens")
    tokens_out: int = Field(..., description="Output completion tokens")
    cost: str = Field(..., description="Formatted cost in USD (e.g. $0.0000)")
    cost_numeric: float = Field(..., description="Raw cost float")
    today: str = Field(..., description="Formatted today cost in USD (e.g. $0.0000)")
    today_numeric: float = Field(..., description="Raw today cost float")
    saved: str = Field(..., description="Formatted savings in USD (e.g. $0.00)")
    saved_numeric: float = Field(..., description="Raw saved float")
    agents_ready: int = Field(..., description="Count of ready/compiled agent nodes")
    agents_total: int = Field(..., description="Total compiled agent nodes in graph")
    agents_ready_str: str = Field(..., description="Formatted status (e.g. 13/13 Agents Ready)")
    health_score: int = Field(..., description="System health score (0-100)")
    circuit_breakers_tripped: int = Field(..., description="Active circuit breakers")
    last_updated: str = Field(..., description="ISO 8601 timestamp")


class AgentThoughtItem(BaseModel):
    """Individual agent reasoning / thought record from execution history."""

    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    step_number: int
    agent_id: str
    agent_name: str
    verdict: str
    score: int | None = None
    status: str
    duration_ms: int
    tokens_in: int
    tokens_out: int
    created_at: str
    snippet: str
    raw_response: str
    system_prompt: str
    user_payload: str
    culprit: str | None = None


class ThoughtsListResponse(BaseModel):
    """Paginated or filtered list of agent thoughts."""

    model_config = ConfigDict(extra="forbid")

    total: int
    project_id: str | None = None
    agent_id: str | None = None
    thoughts: list[AgentThoughtItem]


class AgentStatItem(BaseModel):
    """Aggregated usage and performance stats for a single agent."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    name: str
    icon: str
    room: str
    status: str  # idle | working | reviewing | blocked | done
    tasks_count: int
    total_tokens: int
    avg_duration_ms: int
    approval_rate: float
    rework_count: int


class AgentStatsResponse(BaseModel):
    """Collection of usage stats for all configured agents."""

    model_config = ConfigDict(extra="forbid")

    total_agents: int
    agents: list[AgentStatItem]


class TierEconomics(BaseModel):
    """Zero-Touch pricing tier economics audit."""

    model_config = ConfigDict(extra="forbid")

    name: str
    price_usd: float
    stripe_fee_usd: float
    max_cogs_usd: float
    net_margin_pct: float
    compliant: bool


class AgentCostItem(BaseModel):
    """Cost and token usage attributed to a specific agent."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    name: str
    tokens: int
    cost_usd: float
    pct_of_total: float


class CostBreakdownResponse(BaseModel):
    """Detailed analytics on token expenditure and ROI."""

    model_config = ConfigDict(extra="forbid")

    total_tokens: int
    total_tokens_in: int
    total_tokens_out: int
    total_cost_usd: float
    today_cost_usd: float
    saved_usd: float
    by_agent: list[AgentCostItem]
    pricing_tiers: list[TierEconomics]


class CircuitBreakerItem(BaseModel):
    """Circuit breaker status for a project or pipeline flow."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    iteration: int
    max_iterations: int
    tripped: bool
    status: str
    last_verdict: str


class SecurityEventItem(BaseModel):
    """Security, CISO or governance audit entry."""

    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    timestamp: str
    agent_id: str
    level: str  # CRITICAL | WARNING | INFO
    message: str
    culprit: str | None = None


class SecurityBreakersResponse(BaseModel):
    """Security posture, circuit breaker monitor and CISO logs."""

    model_config = ConfigDict(extra="forbid")

    circuit_breakers_tripped: int
    max_allowed_loops: int
    projects_monitored: list[CircuitBreakerItem]
    recent_security_events: list[SecurityEventItem]
    zero_touch_compliant: bool
    data_minimization_gdpr: bool


class DatabaseTableInfo(BaseModel):
    """SQLite database table summary."""

    model_config = ConfigDict(extra="forbid")

    name: str
    row_count: int
    columns: list[str]


class DatabaseTablesResponse(BaseModel):
    """List of all SQLite tables in the office store."""

    model_config = ConfigDict(extra="forbid")

    database_path: str
    tables: list[DatabaseTableInfo]


class DatabaseQueryResponse(BaseModel):
    """Result of querying a database table."""

    model_config = ConfigDict(extra="forbid")

    table: str
    total_rows: int
    columns: list[str]
    rows: list[dict[str, Any]]


class ArtifactItem(BaseModel):
    """File or deliverable metadata in project workspace."""

    model_config = ConfigDict(extra="forbid")

    name: str
    relative_path: str
    size_bytes: int
    file_type: str  # json | markdown | python | yaml | other
    modified_at: str


class ArtifactsListResponse(BaseModel):
    """Collection of artifacts discovered in a project workspace."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    total_files: int
    artifacts: list[ArtifactItem]


class ArtifactContentResponse(BaseModel):
    """Full text or json content of an inspected workspace artifact."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    file_path: str
    file_type: str
    size_bytes: int
    content: str
