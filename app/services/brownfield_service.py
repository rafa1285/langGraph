"""Brownfield GitHub audit and evolution service."""

from __future__ import annotations

import base64
import logging
import re
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx

from app.core.config import settings
from app.schemas.brownfield import (
    AuditFinding,
    AuditReport,
    BrownfieldApproveRequest,
    BrownfieldAuditRequest,
)
from app.schemas.routing import AgentID
from app.services.llm_gateway import LLMGatewayProtocol
from app.services.office_store import OfficeStore
from app.services.prompt_loader import PromptLoader

if TYPE_CHECKING:
    from app.services.orchestrator_service import OrchestratorService

logger = logging.getLogger(__name__)

_KEY_MANIFESTS = [
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "composer.json",
    "Dockerfile",
    "docker-compose.yml",
    "README.md",
]


def parse_github_url(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from GitHub URL or 'owner/repo' shorthand."""
    cleaned = url.strip().rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    m = re.search(r"(?:github\.com[:/])?([^/:]+)/([^/:]+)$", cleaned)
    if not m:
        raise ValueError(
            f"URL de repositorio inválida: '{url}'. Use 'owner/repo' o 'https://github.com/owner/repo'"
        )
    return m.group(1), m.group(2)


def _extract_score(text: str, default: int = 75) -> int:
    """Extract integer score 0-100 from LLM response text."""
    m = re.search(r"(?:puntuaci[oó]n|score|calificaci[oó]n)[:\s]+(\d{1,3})", text, re.IGNORECASE)
    if m:
        try:
            val = int(m.group(1))
            return max(0, min(100, val))
        except ValueError:
            pass
    return default


class BrownfieldService:
    """Manages read-only repository diagnosis, audit report generation, and refactor launch."""

    def __init__(
        self,
        github_token: str | None = None,
        llm_gateway: LLMGatewayProtocol | None = None,
        prompt_loader: PromptLoader | None = None,
        office_store: OfficeStore | None = None,
        orchestrator: OrchestratorService | None = None,
    ) -> None:
        self.github_token = github_token or settings.GITHUB_TOKEN
        self._llm = llm_gateway
        self._prompt_loader = prompt_loader
        self._store = office_store or OfficeStore()
        self._orchestrator = orchestrator

    async def _fetch_repo_data(
        self,
        owner: str,
        repo: str,
        branch: str,
        auth_token: str | None = None,
    ) -> dict[str, Any]:
        """Fetch repository metadata, languages, file tree, and key manifests via GitHub API."""
        token = auth_token or self.github_token
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AgentOffice-Brownfield/2.0",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        data: dict[str, Any] = {
            "languages": {},
            "tree": [],
            "manifests": {},
            "description": "",
            "default_branch": branch,
        }

        async with httpx.AsyncClient(headers=headers, timeout=12.0) as client:
            # 1. Repo info
            try:
                r_info = await client.get(f"https://api.github.com/repos/{owner}/{repo}")
                if r_info.status_code == 200:
                    info_json = r_info.json()
                    data["description"] = info_json.get("description") or ""
                    data["default_branch"] = info_json.get("default_branch") or branch
            except Exception as e:
                logger.warning("No se pudo obtener información de repo %s/%s: %s", owner, repo, e)

            # 2. Languages
            try:
                r_lang = await client.get(f"https://api.github.com/repos/{owner}/{repo}/languages")
                if r_lang.status_code == 200:
                    data["languages"] = r_lang.json()
            except Exception as e:
                logger.warning("No se pudieron obtener lenguajes de %s/%s: %s", owner, repo, e)

            # 3. Git Tree
            tree_paths: list[str] = []
            try:
                r_tree = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
                )
                if r_tree.status_code == 200:
                    tree_items = r_tree.json().get("tree", [])
                    tree_paths = [item["path"] for item in tree_items if item.get("type") == "blob"]
                    data["tree"] = tree_paths
            except Exception as e:
                logger.warning("No se pudo obtener árbol de archivos: %s", e)

            # 4. Key manifests
            candidates = [p for p in tree_paths if any(p.endswith(m) for m in _KEY_MANIFESTS)][:8]
            for file_path in candidates:
                try:
                    r_file = await client.get(
                        f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}?ref={branch}"
                    )
                    if r_file.status_code == 200:
                        content_b64 = r_file.json().get("content", "")
                        if content_b64:
                            raw_bytes = base64.b64decode(content_b64)
                            decoded = raw_bytes.decode("utf-8", errors="replace")
                            data["manifests"][file_path] = decoded[:3000]
                except Exception:
                    pass

        # Fallback if tree was empty (offline/mock)
        if not data["tree"]:
            data["tree"] = [
                "src/main.py",
                "requirements.txt",
                "Dockerfile",
                "README.md",
                "tests/test_main.py",
            ]
            data["languages"] = {"Python": 15000}
            data["manifests"]["requirements.txt"] = (
                "fastapi>=0.100.0\nuvicorn>=0.23.0\npydantic>=2.0"
            )
            data["manifests"]["Dockerfile"] = (
                "FROM python:3.12-slim\nWORKDIR /app\nCOPY . .\n"
            )

        return data

    async def start_audit(self, request: BrownfieldAuditRequest) -> AuditReport:
        """Run read-only diagnosis with CISO and Architect, generating an executive report."""
        owner, repo = parse_github_url(request.repo_url)
        repo_data = await self._fetch_repo_data(
            owner, repo, request.branch, auth_token=request.auth_token
        )

        tree = repo_data.get("tree", [])
        manifests = repo_data.get("manifests", {})
        languages = repo_data.get("languages", {})

        manifest_summary = "\n\n".join(
            f"=== {name} ===\n{content}" for name, content in manifests.items()
        )

        # ── CISO Diagnosis ───────────────────────────────────────────────────
        ciso_prompt = (
            "Eres el CISO (Chief Information Security Officer) en MODO DIAGNÓSTICO.\n"
            "Tu tarea es AUDITAR la seguridad del repositorio (sin modificar código).\n"
            "Analiza dependencias, contenedores, credenciales y buenas prácticas.\n"
            "NO incluyas bloque YAML.\n"
            "Proporciona:\n"
            "1. Puntuación de Seguridad (formato: 'Puntuación: XX / 100')\n"
            "2. Dictamen ejecutivo de riesgos.\n"
            "3. Lista de vulnerabilidades o debilidades encontradas.\n"
            "4. Recomendaciones prioritarias de seguridad."
        )

        ciso_payload = (
            f"REPOSITORIO: {owner}/{repo} (Rama: {request.branch})\n"
            f"ÁRBOL DE ARCHIVOS:\n" + "\n".join(tree[:60]) + "\n\n"
            f"ARCHIVOS DE CONFIGURACIÓN Y DEPENDENCIAS:\n{manifest_summary}"
        )

        ciso_response = (
            await self._llm.invoke_agent(
                agent_id=AgentID.AGENTE_10_CISO,
                system_prompt=ciso_prompt,
                user_payload=ciso_payload,
            )
            if self._llm
            else (
                "Puntuación: 78/100\nDictamen CISO: Repositorio con postura aceptable. "
                "Se detectan dependencias sin versiones fijadas."
            )
        )

        # ── Architect Diagnosis ───────────────────────────────────────────────
        arch_prompt = (
            "Eres el Arquitecto de Software Principal en MODO DIAGNÓSTICO BROWNFIELD.\n"
            "Tu tarea es evaluar la arquitectura técnica, modularidad y deuda técnica.\n"
            "NO incluyas bloque YAML.\n"
            "Proporciona:\n"
            "1. Puntuación de Arquitectura (formato: 'Puntuación: XX / 100')\n"
            "2. Dictamen técnico de estructura y calidad.\n"
            "3. Anti-patrones o deuda técnica identificada.\n"
            "4. Recomendaciones de refactorización para la siguiente fase."
        )

        arch_payload = (
            f"REPOSITORIO: {owner}/{repo} (Rama: {request.branch})\n"
            f"LENGUAJES: {list(languages.keys())}\n"
            f"ÁRBOL DE ARCHIVOS:\n" + "\n".join(tree[:80]) + "\n\n"
            f"MANIFESTS DETECTADOS:\n{manifest_summary}"
        )

        arch_response = (
            await self._llm.invoke_agent(
                agent_id=AgentID.AGENTE_02_ARCHITECT,
                system_prompt=arch_prompt,
                user_payload=arch_payload,
            )
            if self._llm
            else "Puntuación: 82/100\nDictamen Arquitectura: Estructura modular estándar. "
            "Recomendado segregar capas de servicio y desacoplar lógica de enrutamiento."
        )

        score_ciso = _extract_score(ciso_response, default=75)
        score_arch = _extract_score(arch_response, default=80)
        health_score = int((score_ciso + score_arch) / 2)

        # Build findings list
        findings: list[AuditFinding] = [
            AuditFinding(
                category="security",
                severity="warning" if score_ciso >= 70 else "critical",
                title="Auditoría de Dependencias y Superficie de Ataque (CISO)",
                description="Revisión por el CISO. Revisar detalles en el dictamen adjunto.",
            ),
            AuditFinding(
                category="architecture",
                severity="info" if score_arch >= 75 else "warning",
                title="Evaluación Estructural y Deuda Técnica (Arquitecto)",
                description="Estructura examinada conforme a los patrones de la Software Factory.",
            ),
        ]

        if "Dockerfile" not in "".join(tree):
            findings.append(
                AuditFinding(
                    category="maintainability",
                    severity="warning",
                    title="Falta de contenedorización",
                    description="No se detectó Dockerfile en la raíz del repositorio.",
                    file_path="Dockerfile",
                )
            )

        recommendations = [
            "Actualizar y fijar versiones de dependencias críticas.",
            "Refactorizar rutas monolíticas hacia arquitectura hexagonal desacoplada.",
            "Añadir suites de pruebas unitarias y de integración automatizadas.",
            "Configurar escaneo continuo de vulnerabilidades y secretos.",
        ]

        project_id = f"bf_{uuid4().hex[:8]}"

        report = AuditReport(
            project_id=project_id,
            repo_url=request.repo_url,
            branch=request.branch,
            depth=request.depth,
            health_score=health_score,
            languages=languages,
            dependencies_count=len(manifests),
            dependencies_sample=list(manifests.keys()),
            key_files_scanned=tree[:20],
            ciso_verdict=ciso_response,
            architect_verdict=arch_response,
            findings=findings,
            recommendations=recommendations,
            status="pending_approval",
        )

        await self._store.save_audit_report(report)
        return report

    async def get_audit_report(self, project_id: str) -> AuditReport | None:
        """Fetch audit report from storage."""
        return await self._store.get_audit_report(project_id)

    async def approve_and_start_refactor(
        self,
        project_id: str,
        request: BrownfieldApproveRequest,
    ) -> str:
        """Approve audit report and trigger the refactoring pipeline with brownfield context."""
        report = await self._store.get_audit_report(project_id)
        if report is None:
            raise KeyError(f"Informe de auditoría '{project_id}' no encontrado.")
        if report.status != "pending_approval":
            raise ValueError(f"El informe ya está en estado '{report.status}'.")

        await self._store.update_audit_status(project_id, "approved")

        refactor_idea = (
            f"[BROWNFIELD EVOLUTION] Repositorio: {report.repo_url} (Rama: {report.branch})\n"
            f"Alcance de Refactorización: {', '.join(request.scope)}\n"
            f"{request.refactor_prompt or ''}\n\n"
            f"=== CONTEXTO DE AUDITORÍA PREVIA ===\n"
            f"Puntuación de Salud: {report.health_score}/100\n"
            f"Recomendaciones:\n" + "\n".join(f"- {r}" for r in report.recommendations)
        )

        if self._orchestrator is not None:
            return await self._orchestrator.start_project(
                idea_inicial=refactor_idea,
                project_id=project_id,
            )
        return project_id

    async def reject_audit(self, project_id: str) -> None:
        """Reject brownfield audit report."""
        report = await self._store.get_audit_report(project_id)
        if report is None:
            raise KeyError(f"Informe de auditoría '{project_id}' no encontrado.")
        await self._store.update_audit_status(project_id, "rejected")
