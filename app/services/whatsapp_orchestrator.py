"""WhatsApp Orchestrator: Coordinates intake, pipeline execution, and delivery."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from app.core.config import settings
from app.services.intake_agent import IntakeAgent
from app.services.session_store import SessionPhase, WhatsAppSessionStore
from app.services.whatsapp_service import WhatsAppService

logger = logging.getLogger(__name__)

AGENT_EMOJI_MAP: dict[str, str] = {
    "agente_00_ceo_charter": "👔",
    "agente_00_ceo": "👔",
    "agente_01_pm": "📋",
    "agente_02_architect": "🏗️",
    "agente_11_ui_ux": "🎨",
    "agente_03_laravel": "🐘",
    "agente_04_fastapi": "⚡",
    "agente_05_qa_php": "🧪",
    "agente_06_qa_python": "🔬",
    "qa_sync_barrier": "🔄",
    "agente_07_devops": "🚀",
    "agente_10_ciso": "🛡️",
    "agente_08_docs": "📚",
    "agente_09_growth": "🌱",
    "agente_12_marketing": "📣",
    "agente_13_sales_analytics": "📈",
    "agente_00_ceo_signoff": "✅",
}


class WhatsAppOrchestrator:
    """Master coordinator connecting WhatsApp to the full Software Factory pipeline."""

    def __init__(
        self,
        wa_service: WhatsAppService | None = None,
        session_store: WhatsAppSessionStore | None = None,
        intake_agent: IntakeAgent | None = None,
    ) -> None:
        """Initialise with optional service overrides, falling back to defaults."""
        self.wa: WhatsAppService = wa_service if wa_service is not None else WhatsAppService()
        self.sessions: WhatsAppSessionStore = (
            session_store if session_store is not None else WhatsAppSessionStore()
        )
        self.intake: IntakeAgent = intake_agent if intake_agent is not None else IntakeAgent()

    # ------------------------------------------------------------------
    # Message dispatcher
    # ------------------------------------------------------------------

    async def handle_incoming(self, parsed_msg: dict[str, Any]) -> None:
        """Entry point for processing parsed inbound WhatsApp messages."""
        phone: str = parsed_msg.get("sender") or parsed_msg.get("from") or ""
        text: str = parsed_msg.get("text", "").strip()

        if not phone or not text:
            return

        # Special commands
        cmd = text.lower()
        if cmd in ("/nuevo", "/reset", "/new"):
            await self.sessions.delete_session(phone)
            await self.wa.send_text_message(
                phone,
                "🔄 Sesión reiniciada. Cuéntame tu idea de proyecto y la construimos juntos 🚀",
            )
            return

        if cmd in ("/estado", "/status"):
            session = await self.sessions.get_session(phone)
            if session:
                project_id = session.get("project_id") or "Sin asignar"
                phase = session.get("phase", SessionPhase.INTAKE.value)
                await self.wa.send_text_message(
                    phone,
                    f"📊 *Estado actual:*\n• Proyecto: {project_id}\n• Fase: {phase}",
                )
            else:
                await self.wa.send_text_message(
                    phone,
                    "No hay ningún proyecto activo en este momento. "
                    "Escríbeme tu idea para comenzar 💡",
                )
            return

        session = await self.sessions.get_session(phone)

        if session is None:
            await self._start_intake(phone, text)
        elif session.get("phase") == SessionPhase.INTAKE.value:
            await self._continue_intake(phone, text, session)
        elif session.get("phase") == SessionPhase.BUILDING.value:
            await self.wa.send_text_message(
                phone,
                "⏳ Tu proyecto está siendo construido por nuestro equipo de 13 agentes IA. "
                "Te avisaré con cada avance. Puedes escribir /estado para ver la fase actual.",
            )
        elif session.get("phase") == SessionPhase.DEPLOYING.value:
            await self.wa.send_text_message(
                phone,
                "🚀 Desplegando tu aplicación en Vercel... ¡Casi está lista!",
            )
        elif session.get("phase") == SessionPhase.COMPLETED.value:
            await self.wa.send_text_message(
                phone,
                "✅ Tu último proyecto ya fue entregado y desplegado. "
                "Escribe /nuevo para iniciar un nuevo proyecto 🚀",
            )
        else:
            await self.wa.send_text_message(
                phone,
                "⚠️ Hubo un detalle con la sesión anterior. Escribe /nuevo para comenzar de nuevo.",
            )

    # ------------------------------------------------------------------
    # Intake flow
    # ------------------------------------------------------------------

    async def _start_intake(self, phone: str, first_message: str) -> None:
        """Start a new intake dialogue from the user's initial idea."""
        history: list[dict[str, str]] = [{"role": "user", "content": first_message}]
        reply, is_complete, refined_idea = await self.intake.process_message(
            first_message, []
        )
        history.append({"role": "agent", "content": reply})

        if is_complete:
            await self._launch_pipeline(phone, refined_idea, history)
        else:
            await self.sessions.upsert_session(
                phone=phone,
                phase=SessionPhase.INTAKE.value,
                conversation_history=history,
            )
            await self.wa.send_text_message(phone, reply)

    async def _continue_intake(
        self, phone: str, text: str, session: dict[str, Any]
    ) -> None:
        """Continue an existing intake conversation."""
        history = list(session.get("conversation_history") or [])
        history.append({"role": "user", "content": text})

        reply, is_complete, refined_idea = await self.intake.process_message(
            text, history[:-1]
        )
        history.append({"role": "agent", "content": reply})

        if is_complete:
            await self._launch_pipeline(phone, refined_idea, history)
        else:
            await self.sessions.upsert_session(
                phone=phone,
                phase=SessionPhase.INTAKE.value,
                conversation_history=history,
            )
            await self.wa.send_text_message(phone, reply)

    # ------------------------------------------------------------------
    # Pipeline execution & delivery
    # ------------------------------------------------------------------

    async def _launch_pipeline(
        self, phone: str, refined_idea: str, history: list[dict[str, str]]
    ) -> None:
        """Lock session into BUILDING phase and launch background pipeline."""
        project_id = f"proj_{uuid.uuid4().hex[:8]}"

        await self.sessions.upsert_session(
            phone=phone,
            project_id=project_id,
            phase=SessionPhase.BUILDING.value,
            conversation_history=history,
        )

        launch_announcement = (
            f"🏗️ ¡Requisitos completados! Lanzando la construcción del proyecto *{project_id}*\n\n"
            "El equipo de 13 agentes IA entra en acción:\n"
            "👔 CEO → 📋 PM → 🏗️ Arquitecto → 🎨 UI/UX → "
            "🐘 Laravel → ⚡ FastAPI → 🧪 QA PHP → 🔬 QA Python → "
            "🚀 DevOps → 🛡️ CISO → 📚 Docs → 📣 Marketing → 📈 Sales → 👔 CEO Signoff\n\n"
            "⏱️ Te iré informando en tiempo real de cada paso completado."
        )
        await self.wa.send_text_message(phone, launch_announcement)

        asyncio.create_task(
            self._run_pipeline_and_notify(phone, project_id, refined_idea)
        )

    async def _run_pipeline_and_notify(
        self, phone: str, project_id: str, idea: str
    ) -> None:
        """Execute the factory pipeline with streaming, deploy to Vercel, and notify."""
        from app.services.orchestrator_service import OrchestratorService
        from app.services.vercel_deployer import VercelDeployerService

        orchestrator = OrchestratorService()
        await orchestrator.initialize()

        completed_agents: set[str] = set()

        try:
            # 1. Stream pipeline execution (Phase 4 Real-time updates)
            async for chunk in orchestrator.stream_project(
                project_id=project_id, idea_inicial=idea
            ):
                for node_name in chunk.keys():
                    if node_name not in completed_agents:
                        completed_agents.add(node_name)
                        emoji = AGENT_EMOJI_MAP.get(node_name, "⚙️")
                        progress = f"{len(completed_agents)}/13"
                        await self.wa.send_text_message(
                            phone,
                            f"{emoji} [{progress}] *{node_name}* completado ✓",
                        )

            # 2. Transition to DEPLOYING phase
            await self.sessions.upsert_session(
                phone=phone,
                project_id=project_id,
                phase=SessionPhase.DEPLOYING.value,
            )
            await self.wa.send_text_message(
                phone,
                "⚙️ Pipeline de ingeniería completado con éxito.\n🚀 Desplegando en Vercel...",
            )

            # 3. Deploy to Vercel
            deployer = VercelDeployerService()
            project_slug = f"agentoffice-{project_id.replace('proj_', '')}"
            deploy_result = await deployer.deploy_to_vercel(
                project_id=project_id,
                project_name=project_slug,
                sync_notifications=True,
            )

            # 4. Resolve Notion User Manual link generated by Agent 08 Docs
            docs_url = self._resolve_notion_manual_url(project_id)

            # 5. Send final delivery or error report
            if deploy_result.get("success"):
                deployment_url = deploy_result.get("deployment_url", "")
                await self.sessions.upsert_session(
                    phone=phone,
                    project_id=project_id,
                    phase=SessionPhase.COMPLETED.value,
                )
                delivery_message = (
                    f"🎉 *¡Tu aplicación está lista y en producción!*\n\n"
                    f"🌐 *App desplegada en Vercel:*\n{deployment_url}\n\n"
                    f"📚 *Manual de usuario (Agente 08 Docs):*\n{docs_url}\n\n"
                    f"Escribe /nuevo cuando quieras crear otro proyecto 🚀"
                )
                await self.wa.send_text_message(phone, delivery_message)
            else:
                error_msg = deploy_result.get("error") or "Error en despliegue Vercel"
                await self.sessions.upsert_session(
                    phone=phone,
                    project_id=project_id,
                    phase=SessionPhase.ERROR.value,
                )
                failure_message = (
                    "⚠️ El pipeline se completó pero ocurrió una incidencia al desplegar "
                    f"en Vercel:\n{error_msg}\n\n"
                    f"📚 *Manual y especificaciones del Agente 08:*\n{docs_url}\n\n"
                    "Escribe /nuevo para reiniciar o reintentar."
                )
                await self.wa.send_text_message(phone, failure_message)

        except Exception as exc:
            logger.exception("Error executing WhatsApp pipeline for %s: %s", project_id, exc)
            await self.sessions.upsert_session(
                phone=phone,
                project_id=project_id,
                phase=SessionPhase.ERROR.value,
            )
            await self.wa.send_text_message(
                phone,
                f"❌ Ocurrió un error inesperado al procesar el proyecto: {exc}\n"
                "Escribe /nuevo para reiniciar e intentar de nuevo.",
            )
        finally:
            await orchestrator.close()

    def _resolve_notion_manual_url(self, project_id: str) -> str:
        """Return the URL for the user manual generated by Agent 08 (Docs)."""
        if settings.NOTION_MCP_ENABLED and settings.NOTION_API_KEY:
            if settings.NOTION_PARENT_PAGE_ID:
                clean_id = settings.NOTION_PARENT_PAGE_ID.replace("-", "")
                return f"https://www.notion.so/{clean_id}"
        return f"http://localhost:8080/api/v1/projects/{project_id}/deliverables"
