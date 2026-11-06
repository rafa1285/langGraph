"""Schemas for Brownfield GitHub repository audit and refactoring workflows."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BrownfieldAuditRequest(BaseModel):
    """Request to initiate a Brownfield audit on a GitHub repository."""

    model_config = ConfigDict(str_strip_whitespace=True)

    repo_url: str = Field(
        ...,
        min_length=3,
        description="URL o 'owner/repo' del repositorio en GitHub",
        examples=["https://github.com/fastapi/fastapi", "owner/my-repo"],
    )
    branch: str = Field(
        default="main",
        description="Rama del repositorio a inspeccionar",
    )
    depth: Literal["surface", "deep"] = Field(
        default="deep",
        description="Profundidad del análisis: 'surface' (rápido) o 'deep' (código completo)",
    )
    auth_token: str | None = Field(
        default=None,
        description="Token de GitHub opcional (o usa GITHUB_TOKEN configurado)",
    )


class AuditFinding(BaseModel):
    """A specific vulnerability, anti-pattern, or technical debt finding."""

    model_config = ConfigDict(frozen=True)

    category: Literal["security", "architecture", "dependencies", "maintainability"]
    severity: Literal["critical", "warning", "info"]
    title: str
    description: str
    file_path: str | None = None


class AuditReport(BaseModel):
    """Consolidated executive software health audit report from CISO and Architect."""

    model_config = ConfigDict(frozen=True)

    project_id: str
    repo_url: str
    branch: str
    depth: str
    health_score: int = Field(..., ge=0, le=100, description="Puntuación de salud 0-100")
    languages: dict[str, int] = Field(default_factory=dict)
    dependencies_count: int = 0
    dependencies_sample: list[str] = Field(default_factory=list)
    key_files_scanned: list[str] = Field(default_factory=list)
    ciso_verdict: str
    architect_verdict: str
    findings: list[AuditFinding] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    status: Literal["pending_approval", "approved", "rejected"] = "pending_approval"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class BrownfieldApproveRequest(BaseModel):
    """User approval request to begin refactoring based on the audit report."""

    model_config = ConfigDict(str_strip_whitespace=True)

    scope: list[str] = Field(
        default_factory=lambda: ["security_fixes", "architecture_refactor"],
        description="Alcance acordado para la evolución del software",
    )
    refactor_prompt: str | None = Field(
        default=None,
        description="Instrucciones adicionales para guiar la refactorización",
    )


class BrownfieldAuditStartResponse(BaseModel):
    """Immediate response after initiating a brownfield audit."""

    model_config = ConfigDict(frozen=True)

    project_id: str
    repo_url: str
    status: str
    message: str
