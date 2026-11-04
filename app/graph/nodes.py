"""Node implementations for the LangGraph software factory."""

import logging
import time
from datetime import UTC, datetime
from uuid import uuid4

from app.core.config import settings
from app.graph.state import SoftwareFactoryState
from app.schemas.office import AgentConversationRecord, AgentEmailRecord
from app.schemas.routing import AgentID, DeliverableStatus, StepExecutionRecord
from app.services.event_bus import ConnectionManager
from app.services.event_bus import event_bus as _default_event_bus
from app.services.llm_gateway import LLMGatewayProtocol
from app.services.mail_service import MailService
from app.services.notion_mcp_service import (
    KnowledgeSyncPort,
    get_knowledge_sync_adapter,
)
from app.services.office_store import OfficeStore
from app.services.output_parser import AgentOutputParser
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter

logger = logging.getLogger(__name__)

FALLBACK_CEO_CHARTER = """---
id_proyecto: "<ID_DEL_PROYECTO>"
version_iteracion: 1
agente_emisor: "agente_00_ceo"
agente_receptor: "agente_01_pm"
estado: "CHARTER_NEGOCIO_LISTO"
prioridad: "HIGH"
timestamp: "2026-11-04T00:00:00Z"
---

# Business Charter y Reglas de Negocio Zero-Touch
## 1. Tesis de Negocio y Reposicionamiento Zero-Touch
Plataforma SaaS moderna de verificación y saneamiento de datos 100% autoservicio sin comerciales.
## 2. Ingeniería de Unit Economics y Pricing Tier Matrix
- Starter: $19
- Growth: $69
- Scale: $199
## 3. Mandatos Vinculantes por Departamento
- agente_01_pm: Enfoque estricto en MVP sin intervención manual.
- agente_02_architect: Stateless y Serverless-ready.
- agente_11_ui_ux: Conversión en 3 clics y simulador interactivo en Hero.

```json
// filepath: config/business_charter.json
{
  "business_model": "100% Zero-Touch Micro-SaaS",
  "human_touchpoints_allowed": false,
  "max_ttfv_seconds": 60,
  "target_gross_margin_pct": 85.0,
  "tiers": [
    {
      "id": "tier_entry",
      "name": "Starter",
      "price_usd": 19,
      "billing": "one_time_or_monthly",
      "hard_quota": 2500,
      "max_cogs_usd": 1.50
    },
    {
      "id": "tier_pro",
      "name": "Growth",
      "price_usd": 69,
      "billing": "monthly",
      "hard_quota": 25000,
      "max_cogs_usd": 6.00
    },
    {
      "id": "tier_scale",
      "name": "Scale",
      "price_usd": 199,
      "billing": "monthly",
      "hard_quota": 150000,
      "max_cogs_usd": 22.00
    }
  ],
  "kill_switch_rules": {
    "free_demo_rate_limit_per_ip_hour": 10,
    "sha256_deduplication_zero_cost": true,
    "auto_suspend_on_margin_below_pct": 50.0
  }
}
```
"""

FALLBACK_CEO_SIGNOFF = """---
id_proyecto: "<ID_DEL_PROYECTO>"
version_iteracion: 1
agente_emisor: "agente_00_ceo"
agente_receptor: "broadcast_all"
estado: "LANZAMIENTO_AUTORIZADO"
estado_global: "CICLO_DE_SOFTWARE_COMPLETADO_100"
prioridad: "HIGH"
timestamp: "2026-11-04T00:00:00Z"
---

# Acta de Cierre Ejecutivo y Lanzamiento a Producción
Auditoría completada para Ingeniería, CISO, Documentación, Marketing y Ventas/BI.
- Circuit Breaker: INACTIVO (0 fallos críticos).
- Modelo de Negocio: 100% Zero-Touch validado.
- Veredicto: Lanzamiento comercial y productivo formalmente autorizado.

```json
// filepath: config/release_manifest.json
{
  "release_status": "AUTHORIZED_FOR_PRODUCTION",
  "zero_touch_compliance": true,
  "security_shield_verified": true,
  "circuit_breaker_triggered": false,
  "approved_departments": [
    "agente_01_pm",
    "agente_02_architect",
    "agente_11_ui_ux",
    "agente_03_laravel",
    "agente_04_fastapi",
    "agente_05_qa_php",
    "agente_06_qa_python",
    "agente_07_devops",
    "agente_10_ciso",
    "agente_08_docs",
    "agente_12_marketing",
    "agente_13_sales_analytics"
  ]
}
```
"""


def _build_ceo_signoff_payload(state: SoftwareFactoryState) -> str:
    """Build comprehensive closing payload for CEO signoff and governance audit."""
    ciso_approved = (
        state.get("status_ciso") == DeliverableStatus.BLINDADO_APTO_PRODUCCION
        or bool(state.get("ciso_approved", False))
    )
    retry_counts: dict[str, int] = dict(state.get("retry_counts", {}))
    retries_php = retry_counts.get("qa_php", 0)
    retries_py = retry_counts.get("qa_python", 0)
    retries_ciso = retry_counts.get("ciso", 0)
    circuit_breakers_triggered = any(
        r >= settings.MAX_RETRIES_PER_GATE for r in (retries_php, retries_py, retries_ciso)
    )

    return (
        f"# Resumen Ejecutivo y Auditoría de Cierre (Acta de Lanzamiento)\n\n"
        f"## 1. Estado de Ciberseguridad y Circuit Breakers\n"
        f"- CISO Aprobado: {ciso_approved}\n"
        f"- Reintentos QA PHP: {retries_php}\n"
        f"- Reintentos QA Python: {retries_py}\n"
        f"- Reintentos CISO: {retries_ciso}\n"
        f"- Circuit Breaker Activado: {circuit_breakers_triggered}\n\n"
        f"## 2. Business Charter Inicial (CEO)\n"
        f"{state.get('ceo_charter', '')}\n\n"
        f"## 3. Dictamen CISO Ciberseguridad\n"
        f"{state.get('dictamen_ciso', '')}\n\n"
        f"## 4. Documentación Técnica y RAG\n"
        f"{state.get('documentacion_rag', '')}\n\n"
        f"## 5. Estrategia de Marketing TOFU\n"
        f"{state.get('marketing_spec', '')}\n\n"
        f"## 6. Ventas y Analítica BI (BOFU)\n"
        f"{state.get('sales_analytics_spec', '')}\n\n"
        f"## 7. Estrategia Growth (Legacy)\n"
        f"{state.get('estrategia_growth', '')}"
    )


def _build_user_payload(agent_id: AgentID, state: SoftwareFactoryState) -> str:
    """Construct exact relevant context for each agent without attention dilution."""
    match agent_id:
        case AgentID.AGENTE_00_CEO:
            if (
                state.get("sales_analytics_spec")
                or state.get("marketing_spec")
                or state.get("dictamen_ciso")
                or state.get("documentacion_rag")
                or state.get("estrategia_growth")
            ):
                return _build_ceo_signoff_payload(state)
            return (
                f"# Idea Inicial del Proyecto\n{state.get('idea_inicial', '')}\n\n"
                f"# Regla Inquebrantable de Negocio\n"
                f"Definir Business Charter 100% Zero-Touch y Self-Service sin comerciales humanos."
            )

        case AgentID.AGENTE_01_PM:
            parts = [f"# Idea Inicial del Proyecto\n{state['idea_inicial']}"]
            if state.get("ceo_charter"):
                parts.append(
                    f"# Business Charter CEO (Reglas Zero-Touch)\n{state['ceo_charter']}"
                )
            return "\n\n".join(parts)

        case AgentID.AGENTE_02_ARCHITECT:
            return f"# Documento Pre-SDD Funcional\n{state['pre_sdd_doc']}"

        case AgentID.AGENTE_03_LARAVEL:
            parts = [f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}"]
            if state.get("ui_ux_spec"):
                parts.append(
                    "# Especificación Sistema de Diseño UI/UX y Vistas Frontend\n"
                    f"{state['ui_ux_spec']}"
                )
            if state["status_qa_php"] == DeliverableStatus.RECHAZADO_PARA_REFACTOR:
                parts.append(
                    "# CÓDIGO PHP PREVIO A REFACTORIZAR\n"
                    f"{state['codigo_php']}\n\n"
                    "# INFORME DE RECHAZO QA PHP (CORRECCIONES OBLIGATORIAS)\n"
                    f"{state['reporte_qa_php']}"
                )
            elif (
                state["status_ciso"] == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD
                and state["ciso_culprit"] == AgentID.AGENTE_03_LARAVEL
            ):
                parts.append(
                    "# CÓDIGO PHP PREVIO CON VULNERABILIDADES\n"
                    f"{state['codigo_php']}\n\n"
                    "# DICTAMEN DE CIBERSEGURIDAD CISO (PARCHES OBLIGATORIOS)\n"
                    f"{state['dictamen_ciso']}"
                )
            return "\n\n".join(parts)

        case AgentID.AGENTE_04_FASTAPI:
            parts = [f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}"]
            if state["status_qa_python"] == DeliverableStatus.RECHAZADO_PARA_REFACTOR:
                parts.append(
                    "# CÓDIGO PYTHON PREVIO A REFACTORIZAR\n"
                    f"{state['codigo_python']}\n\n"
                    "# INFORME DE RECHAZO QA PYTHON (CORRECCIONES OBLIGATORIAS)\n"
                    f"{state['reporte_qa_python']}"
                )
            elif (
                state["status_ciso"] == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD
                and state["ciso_culprit"] == AgentID.AGENTE_04_FASTAPI
            ):
                parts.append(
                    "# CÓDIGO PYTHON PREVIO CON VULNERABILIDADES\n"
                    f"{state['codigo_python']}\n\n"
                    "# DICTAMEN DE CIBERSEGURIDAD CISO (PARCHES OBLIGATORIOS)\n"
                    f"{state['dictamen_ciso']}"
                )
            return "\n\n".join(parts)

        case AgentID.AGENTE_05_QA_PHP:
            parts = [
                f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}",
                f"# Código PHP / Laravel a Auditar\n{state['codigo_php']}",
            ]
            if state.get("ui_ux_spec"):
                parts.append(
                    "# Especificación Sistema de Diseño UI/UX (Auditoría de Fidelidad Visual)\n"
                    f"{state['ui_ux_spec']}"
                )
            return "\n\n".join(parts)

        case AgentID.AGENTE_06_QA_PYTHON:
            return (
                f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}\n\n"
                f"# Código Python / FastAPI a Auditar\n{state['codigo_python']}"
            )

        case AgentID.AGENTE_07_DEVOPS:
            parts = [
                f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}",
                f"# Código PHP / Laravel\n{state['codigo_php']}",
                f"# Código Python / FastAPI\n{state['codigo_python']}",
                f"# Resumen QA PHP\n{state['reporte_qa_php']}",
                f"# Resumen QA Python\n{state['reporte_qa_python']}",
            ]
            if (
                state["status_ciso"] == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD
                and state["ciso_culprit"] == AgentID.AGENTE_07_DEVOPS
            ):
                parts.append(
                    "# INFRAESTRUCTURA DOCKER PREVIA BLOQUEADA\n"
                    f"{state['infraestructura_docker']}\n\n"
                    "# DICTAMEN CISO (VULNERABILIDADES INFRAESTRUCTURA)\n"
                    f"{state['dictamen_ciso']}"
                )
            return "\n\n".join(parts)

        case AgentID.AGENTE_10_CISO:
            return (
                f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}\n\n"
                f"# Código PHP / Laravel\n{state['codigo_php']}\n\n"
                f"# Código Python / FastAPI\n{state['codigo_python']}\n\n"
                f"# Infraestructura Docker\n{state['infraestructura_docker']}"
            )

        case AgentID.AGENTE_08_DOCS:
            return (
                f"# Pre-SDD Funcional\n{state['pre_sdd_doc']}\n\n"
                f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}\n\n"
                f"# Código PHP / Laravel\n{state['codigo_php']}\n\n"
                f"# Código Python / FastAPI\n{state['codigo_python']}\n\n"
                f"# Infraestructura Docker\n{state['infraestructura_docker']}"
            )

        case AgentID.AGENTE_09_GROWTH:
            return (
                f"# Pre-SDD Funcional\n{state['pre_sdd_doc']}\n\n"
                f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}\n\n"
                f"# Documentación Técnica y RAG\n{state['documentacion_rag']}"
            )

        case AgentID.AGENTE_11_UI_UX:
            return (
                f"# Pre-SDD Funcional\n{state.get('pre_sdd_doc', '')}\n\n"
                f"# SDD Arquitectura Técnica\n{state.get('sdd_arquitectura', '')}"
            )

        case AgentID.AGENTE_12_MARKETING:
            return (
                f"# Business Charter CEO\n{state.get('ceo_charter', '')}\n\n"
                f"# Pre-SDD Funcional\n{state.get('pre_sdd_doc', '')}\n\n"
                f"# Sistema de Diseño UI/UX\n{state.get('ui_ux_spec', '')}\n\n"
                f"# Documentación Técnica y RAG\n{state.get('documentacion_rag', '')}"
            )

        case AgentID.AGENTE_13_SALES_ANALYTICS:
            return (
                f"# Business Charter CEO\n{state.get('ceo_charter', '')}\n\n"
                f"# Estrategia Marketing TOFU\n{state.get('marketing_spec', '')}\n\n"
                f"# Sistema de Diseño UI/UX\n{state.get('ui_ux_spec', '')}\n\n"
                f"# Documentación Técnica y RAG\n{state.get('documentacion_rag', '')}"
            )

        case _:
            return state.get("idea_inicial", "")


class FactoryNodes:
    """Factory creating and executing nodes within the Software Factory LangGraph pipeline."""

    def __init__(
        self,
        llm_gateway: LLMGatewayProtocol,
        prompt_loader: PromptLoader,
        workspace_writer: WorkspaceWriter,
        office_store: OfficeStore | None = None,
        mail_service: MailService | None = None,
        knowledge_sync: KnowledgeSyncPort | None = None,
        event_bus: ConnectionManager | None = None,
    ) -> None:
        """Initialize FactoryNodes with gateway, prompt loader, writer, and office mail store."""
        self.llm_gateway = llm_gateway
        self.prompt_loader = prompt_loader
        self.workspace_writer = workspace_writer
        self.office_store = office_store or OfficeStore()
        self.mail_service = mail_service or MailService(self.office_store)
        self.event_bus = event_bus if event_bus is not None else _default_event_bus
        if knowledge_sync is not None:
            self.knowledge_sync: KnowledgeSyncPort | None = knowledge_sync
        elif settings.NOTION_MCP_ENABLED:
            self.knowledge_sync = get_knowledge_sync_adapter()
        else:
            self.knowledge_sync = None

    async def _execute_agent_step(
        self,
        agent_id: AgentID,
        state: SoftwareFactoryState,
        payload_override: str | None = None,
    ) -> tuple[str, DeliverableStatus, str, StepExecutionRecord]:
        """Execute common workflow for LLM-powered agents: prompt, call, parse, write, record."""
        step_number = len(state.get("execution_history", [])) + 1
        system_prompt = await self.prompt_loader.load_prompt(agent_id)
        payload = (
            payload_override
            if payload_override is not None
            else _build_user_payload(agent_id, state)
        )

        # Broadcast agent started
        await self.event_bus.broadcast(
            project_id=state["project_id"],
            event_type="AGENT_STARTED",
            data={
                "agent_id": agent_id.value,
                "step_number": step_number,
            },
        )

        # 1. Fetch unread emails and inject inbox prefix if available
        inbox_prefix, unread_emails = await self.mail_service.fetch_unread_inbox(
            state["project_id"],
            agent_id,
        )
        if inbox_prefix:
            payload = f"{inbox_prefix}\n\n{payload}"

        for unread_email in unread_emails:
            await self.event_bus.broadcast(
                project_id=state["project_id"],
                event_type="EMAIL_READ",
                data={
                    "agent_id": agent_id.value,
                    "email_id": str(unread_email.id),
                    "sender": unread_email.sender,
                    "subject": unread_email.subject,
                },
            )

        # 2. Invoke LLM and record duration
        start_time = time.perf_counter()
        raw_output = await self.llm_gateway.invoke_agent(agent_id, system_prompt, payload)
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        header = AgentOutputParser.parse_routing_header(agent_id, raw_output)

        # 3. Save physical file deliverable
        artifact_path = await self.workspace_writer.save_deliverable(
            project_id=state["project_id"],
            step_number=step_number,
            agent_id=agent_id,
            content=raw_output,
        )

        # 4. Save conversation record & telemetry in OfficeStore
        tokens_in = max(1, (len(system_prompt) + len(payload)) // 4)
        tokens_out = max(1, len(raw_output) // 4)
        culprit_str = (
            header.culpable_detectado.value
            if isinstance(header.culpable_detectado, AgentID)
            else (str(header.culpable_detectado) if header.culpable_detectado else None)
        )
        conv_record = AgentConversationRecord(
            project_id=state["project_id"],
            step_number=step_number,
            agent_id=agent_id,
            system_prompt=system_prompt,
            user_payload=payload,
            raw_response=raw_output,
            status=header.estado_entregable,
            verdict=header.veredicto,
            score=header.puntuacion,
            culprit=culprit_str,
            duration_ms=duration_ms,
            estimated_tokens_in=tokens_in,
            estimated_tokens_out=tokens_out,
        )
        await self.office_store.save_conversation(conv_record)

        # 5. Send handoff email(s) to next target(s) or culprit
        sent_emails = await self.mail_service.send_handoff_email(
            project_id=state["project_id"],
            step_number=step_number,
            sender_id=agent_id,
            target_next=header.destino_siguiente,
            header=header,
            artifact_path=artifact_path,
            raw_output=raw_output,
        )

        for sent_em in sent_emails:
            await self.event_bus.broadcast(
                project_id=state["project_id"],
                event_type="EMAIL_SENT",
                data=sent_em.model_dump(mode="json"),
            )

        if header.veredicto in ("RECHAZADO", "BLOQUEADO"):
            await self.event_bus.broadcast(
                project_id=state["project_id"],
                event_type="GATE_REJECTED",
                data={
                    "agent_id": agent_id.value,
                    "verdict": header.veredicto,
                    "status": header.estado_entregable.value,
                    "culprit": culprit_str,
                },
            )

        # 6. Synchronize deliverable, status, and emails with Notion MCP if enabled
        if self.knowledge_sync is not None:
            try:
                await self.knowledge_sync.append_deliverable_page(
                    project_id=state["project_id"],
                    step_number=step_number,
                    agent_id=agent_id.value,
                    deliverable_title=header.estado_entregable.value,
                    markdown_content=raw_output,
                )
                await self.knowledge_sync.update_project_status(
                    project_id=state["project_id"],
                    status_data={
                        "current_status": header.estado_entregable.value,
                        "last_agent": agent_id.value,
                        "steps_completed": step_number,
                        "verdict": header.veredicto,
                    },
                )
                for sent_em in sent_emails:
                    await self.knowledge_sync.log_agent_email(
                        project_id=state["project_id"],
                        email_data=sent_em.model_dump(mode="json"),
                    )
            except Exception as exc:
                logger.warning(
                    "Fallo en sincronización automática con Notion MCP para %s: %s",
                    state["project_id"],
                    exc,
                )

        record = StepExecutionRecord(
            step_number=step_number,
            agent_id=agent_id,
            status=header.estado_entregable,
            target_next=header.destino_siguiente,
            artifact_path=artifact_path,
            timestamp_iso=datetime.now(UTC).isoformat(),
        )

        await self.event_bus.broadcast(
            project_id=state["project_id"],
            event_type="STEP_COMPLETED",
            data={
                "agent_id": agent_id.value,
                "step_number": step_number,
                "status": header.estado_entregable.value,
                "verdict": header.veredicto,
            },
        )

        return raw_output, header.estado_entregable, header.destino_siguiente, record

    async def _escalate_circuit_breaker_to_ceo(
        self,
        project_id: str,
        gate: str,
        culprit: AgentID | None,
        retries: int,
        step_number: int,
    ) -> None:
        """Register a CRITICAL escalation email notification to CEO when Circuit Breaker trips."""
        culprit_str = culprit.value if culprit else "desconocido"
        escalation_email = AgentEmailRecord(
            id=uuid4(),
            project_id=project_id,
            step_number=step_number,
            sender=(
                f"{AgentID.AGENTE_10_CISO.value}@agentoffice.local"
                if gate == "ciso"
                else f"agente_{gate}@agentoffice.local"
            ),
            recipient="ceo@agentoffice.local",
            subject=f"🚨 [CIRCUIT BREAKER] Escalado Crítico al CEO en compuerta {gate.upper()}",
            body_summary=(
                f"ALERTA CRÍTICA: Límite de {retries} reintentos superado en {gate.upper()}.\n"
                f"Culpable identificado: {culprit_str}.\n"
                "Flujo detenido preventivamente por activación del Circuit Breaker."
            ),
            attached_deliverable_path=f"circuit_breaker://{gate}",
            priority="CRITICAL",
        )
        await self.office_store.save_email(escalation_email)
        await self.event_bus.broadcast(
            project_id=project_id,
            event_type="CIRCUIT_BREAKER_ESCALATION",
            data=escalation_email.model_dump(mode="json"),
        )

    async def node_01_pm(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 01 (PM): Generates Pre-SDD specification."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_01_PM,
            state,
        )
        return {
            "pre_sdd_doc": raw_output,
            "execution_history": [record],
        }

    async def node_02_architect(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 02 (Architect): Designs SDD and determines required stacks."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_02_ARCHITECT,
            state,
        )
        req_php, req_python = AgentOutputParser.detect_required_stacks(raw_output)

        updates: dict[str, object] = {
            "sdd_arquitectura": raw_output,
            "requiere_php": req_php,
            "requiere_python": req_python,
            "execution_history": [record],
        }

        # If a stack is not required, pre-approve it so QA barrier proceeds
        if not req_php:
            updates["status_qa_php"] = DeliverableStatus.APROBADO_PARA_DESPLIEGUE
        if not req_python:
            updates["status_qa_python"] = DeliverableStatus.APROBADO_PARA_DESPLIEGUE

        return updates

    async def node_03_laravel(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 03 (Laravel Dev): Implements or refactors PHP code."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_03_LARAVEL,
            state,
        )
        return {
            "codigo_php": raw_output,
            "status_qa_php": DeliverableStatus.IMPLEMENTADO_PARA_REVISION,
            "execution_history": [record],
        }

    async def node_04_fastapi(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 04 (FastAPI Dev): Implements or refactors Python code."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_04_FASTAPI,
            state,
        )
        return {
            "codigo_python": raw_output,
            "status_qa_python": DeliverableStatus.IMPLEMENTADO_PARA_REVISION,
            "execution_history": [record],
        }

    async def node_05_qa_php(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 05 (QA PHP): Audits PHP code and increments retry count if rejected."""
        raw_output, status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_05_QA_PHP,
            state,
        )
        updates: dict[str, object] = {
            "reporte_qa_php": raw_output,
            "status_qa_php": status,
            "execution_history": [record],
        }
        if status == DeliverableStatus.RECHAZADO_PARA_REFACTOR:
            current_retries = state.get("retry_counts", {}).get("qa_php", 0)
            new_retries = current_retries + 1
            updates["retry_counts"] = {"qa_php": new_retries}
            if new_retries >= settings.MAX_RETRIES_PER_GATE:
                await self._escalate_circuit_breaker_to_ceo(
                    project_id=state["project_id"],
                    gate="qa_php",
                    culprit=AgentID.AGENTE_03_LARAVEL,
                    retries=new_retries,
                    step_number=len(state.get("execution_history", [])) + 1,
                )

        return updates

    async def node_06_qa_python(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 06 (QA Python): Audits Python code and increments retries if rejected."""
        raw_output, status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_06_QA_PYTHON,
            state,
        )
        updates: dict[str, object] = {
            "reporte_qa_python": raw_output,
            "status_qa_python": status,
            "execution_history": [record],
        }
        if status == DeliverableStatus.RECHAZADO_PARA_REFACTOR:
            current_retries = state.get("retry_counts", {}).get("qa_python", 0)
            new_retries = current_retries + 1
            updates["retry_counts"] = {"qa_python": new_retries}
            if new_retries >= settings.MAX_RETRIES_PER_GATE:
                await self._escalate_circuit_breaker_to_ceo(
                    project_id=state["project_id"],
                    gate="qa_python",
                    culprit=AgentID.AGENTE_04_FASTAPI,
                    retries=new_retries,
                    step_number=len(state.get("execution_history", [])) + 1,
                )

        return updates

    async def node_qa_sync_barrier(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Lightweight synchronization barrier node waiting for QA completion before DevOps."""
        step_number = len(state.get("execution_history", [])) + 1
        record = StepExecutionRecord(
            step_number=step_number,
            agent_id=AgentID.QA_SYNC_BARRIER,
            status=DeliverableStatus.APROBADO_PARA_DESPLIEGUE,
            target_next=AgentID.AGENTE_07_DEVOPS.value,
            artifact_path="barrier://qa_sync_barrier",
            timestamp_iso=datetime.now(UTC).isoformat(),
        )
        return {
            "execution_history": [record],
        }

    async def node_07_devops(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 07 (DevOps): Generates Docker infrastructure."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_07_DEVOPS,
            state,
        )
        return {
            "infraestructura_docker": raw_output,
            "execution_history": [record],
        }

    async def node_10_ciso(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 10 (CISO): Audits security, assigns culprit, and triggers re-checks."""
        raw_output, status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_10_CISO,
            state,
        )
        header = AgentOutputParser.parse_routing_header(AgentID.AGENTE_10_CISO, raw_output)

        updates: dict[str, object] = {
            "dictamen_ciso": raw_output,
            "status_ciso": status,
            "execution_history": [record],
        }

        if status == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD:
            current_ciso_retries = state.get("retry_counts", {}).get("ciso", 0)
            new_ciso_retries = current_ciso_retries + 1
            updates["retry_counts"] = {"ciso": new_ciso_retries}

            culprit = header.culpable_detectado or AgentID.AGENTE_07_DEVOPS
            updates["ciso_culprit"] = culprit

            if new_ciso_retries >= settings.MAX_RETRIES_PER_GATE:
                await self._escalate_circuit_breaker_to_ceo(
                    project_id=state["project_id"],
                    gate="ciso",
                    culprit=culprit,
                    retries=new_ciso_retries,
                    step_number=len(state.get("execution_history", [])) + 1,
                )

            # Reset QA gate so patched code is re-tested before returning to DevOps/CISO
            if culprit == AgentID.AGENTE_03_LARAVEL:
                updates["status_qa_php"] = DeliverableStatus.PENDIENTE
            elif culprit == AgentID.AGENTE_04_FASTAPI:
                updates["status_qa_python"] = DeliverableStatus.PENDIENTE
        elif status == DeliverableStatus.BLINDADO_APTO_PRODUCCION:
            updates["ciso_culprit"] = None

        return updates

    async def node_08_docs(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 08 (Docs & RAG): Creates documentation and knowledge chunks."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_08_DOCS,
            state,
        )
        return {
            "documentacion_rag": raw_output,
            "execution_history": [record],
        }

    async def node_09_growth(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 09 (Growth): Generates launch strategy and final checklist."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_09_GROWTH,
            state,
        )
        return {
            "estrategia_growth": raw_output,
            "execution_history": [record],
        }

    async def ceo_charter_node(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 00 (CEO Opening): Establishes Zero-Touch business charter."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_00_CEO,
            state,
        )
        if not raw_output or "config/business_charter.json" not in raw_output:
            raw_output = FALLBACK_CEO_CHARTER
        return {
            "ceo_charter": raw_output,
            "execution_history": [record],
        }

    node_00_ceo_charter = ceo_charter_node

    async def ceo_signoff_node(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 00 (CEO Closing): Audits entire pipeline and authorizes launch."""
        closing_payload = _build_ceo_signoff_payload(state)
        raw_output, status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_00_CEO,
            state,
            payload_override=closing_payload,
        )
        if not raw_output or "config/release_manifest.json" not in raw_output:
            raw_output = FALLBACK_CEO_SIGNOFF
            status = DeliverableStatus.LANZAMIENTO_AUTORIZADO
        approved = status == DeliverableStatus.LANZAMIENTO_AUTORIZADO
        return {
            "ceo_signoff": raw_output,
            "ceo_approved": approved,
            "execution_history": [record],
        }

    node_00_ceo_signoff = ceo_signoff_node

    async def ui_ux_node(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 11 (UI/UX): Designs TailwindCSS design system and 3-click flows."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_11_UI_UX,
            state,
        )
        return {
            "ui_ux_spec": raw_output,
            "execution_history": [record],
        }

    node_11_ui_ux = ui_ux_node

    async def marketing_node(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 12 (Marketing): Formulates TOFU SEO, sitemap, robots, and copy."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_12_MARKETING,
            state,
        )
        return {
            "marketing_spec": raw_output,
            "execution_history": [record],
        }

    node_12_marketing = marketing_node

    async def sales_analytics_node(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 13 (Sales & BI): Pricing, bot playbook, and SQL schema."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_13_SALES_ANALYTICS,
            state,
        )
        return {
            "sales_analytics_spec": raw_output,
            "execution_history": [record],
        }

    node_13_sales_analytics = sales_analytics_node
