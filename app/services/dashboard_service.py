"""Real-time LangGraph streaming service for Operations Dashboard and Request Pipeline."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
import logging
import re
from typing import Any, AsyncIterator
import uuid
import yaml

from app.core.config import settings
from app.schemas.routing import AgentID, DeliverableStatus
from app.services.llm_gateway import MockLLMGateway
from app.services.office_store import OfficeStore
from app.services.orchestrator_service import OrchestratorService
from app.services.output_parser import AgentOutputParser

logger = logging.getLogger(__name__)

# Official mapping of agent / node identifiers to human-readable names and icons
AGENT_DISPLAY_MAP: dict[str, str] = {
    "agente_00_ceo": "👑 CEO",
    "agente_00_ceo_charter": "👑 CEO",
    "node_00_ceo_charter": "👑 CEO",
    "agente_00_ceo_signoff": "👑 CEO",
    "node_00_ceo_signoff": "👑 CEO",
    "agente_01_pm": "📋 Product Manager",
    "agente_02_architect": "🏛️ Software Architect",
    "agente_11_ui_ux": "🎨 UI/UX Designer",
    "agente_03_laravel": "🐘 Dev PHP (Laravel)",
    "agente_04_fastapi": "⚡ Dev Python (FastAPI)",
    "agente_05_qa_php": "🔬 QA PHP (Pest)",
    "agente_06_qa_python": "🐍 QA Python (Pytest)",
    "qa_sync_barrier": "⚖️ QA Sync Barrier",
    "agente_07_devops": "⚙️ DevOps & Docker",
    "agente_10_ciso": "🛡️ CISO Security",
    "agente_08_docs": "📚 Docs & RAG",
    "agente_12_marketing": "📣 Marketing TOFU",
    "agente_13_sales_analytics": "💹 Sales & BI",
    "agente_09_growth": "📈 Growth Hacker",
    "user": "👔 Boss",
}

# The 7 Pipeline Stages for the Request Pipeline
PIPELINE_STAGES: list[tuple[str, str]] = [
    ("stage-received", "Received"),
    ("stage-ceo-charter", "CEO Charter"),
    ("stage-pm-design", "PM & Design"),
    ("stage-coding", "Coding"),
    ("stage-qa-ciso", "QA & CISO"),
    ("stage-growth-docs", "Growth & Docs"),
    ("stage-ceo-signoff", "CEO Signoff"),
]


def map_node_to_pipeline_stage(node_name: str, status: str = "") -> tuple[int, str, str]:
    """Map a LangGraph node name and status to one of the 7 Request Pipeline stages.

    Returns:
        (stage_index, stage_id, stage_name)
    """
    node = (node_name or "").lower().strip()
    st = (status or "").upper().strip()

    # Stage 6: CEO Signoff
    if "signoff" in node or st in ("LANZAMIENTO_AUTORIZADO", "CICLO_DE_SOFTWARE_COMPLETADO_100"):
        return (6, "stage-ceo-signoff", "CEO Signoff")

    # Stage 5: Growth & Docs
    if any(k in node for k in ("docs", "marketing", "sales", "growth", "agente_08", "agente_09", "agente_12", "agente_13")):
        return (5, "stage-growth-docs", "Growth & Docs")

    # Stage 4: QA & CISO
    if any(k in node for k in ("qa", "ciso", "barrier", "agente_05", "agente_06", "agente_10", "agente_14")):
        return (4, "stage-qa-ciso", "QA & CISO")

    # Stage 3: Coding
    if any(k in node for k in ("laravel", "fastapi", "devops", "agente_03", "agente_04", "agente_07")):
        return (3, "stage-coding", "Coding")

    # Stage 2: PM & Design
    if any(k in node for k in ("pm", "architect", "ui_ux", "agente_01", "agente_02", "agente_11")):
        return (2, "stage-pm-design", "PM & Design")

    # Stage 1: CEO Charter
    if any(k in node for k in ("charter", "ceo", "agente_00")):
        return (1, "stage-ceo-charter", "CEO Charter")

    # Stage 0: Received (Default / Start)
    return (0, "stage-received", "Received")


def get_agent_name(agent_id_or_node: str) -> str:
    """Return formatted human-friendly name with icon for an agent ID."""
    clean = agent_id_or_node.strip()
    for k, v in AGENT_DISPLAY_MAP.items():
        if k in clean:
            return v
    return f"🤖 {clean}"


def get_tool_description(node_name: str) -> str:
    """Return tool description message when an automated verification tool is invoked."""
    node = node_name.lower()
    if "qa_php" in node or "05" in node:
        return "Pest PHP Suite: Ejecutando batería de tests unitarios y validación de sintaxis..."
    if "qa_python" in node or "06" in node:
        return "Pytest Async Engine: Verificando endpoints y esquemas OpenAPI en FastAPI..."
    if "barrier" in node:
        return "QA Sync Barrier: Verificando compuertas concurrentes de calidad PHP y Python..."
    if "devops" in node or "07" in node:
        return "Docker Engine: Validando Dockerfile multi-stage y políticas de compilación..."
    if "ciso" in node or "10" in node:
        return "CISO SAST Scanner: Ejecutando auditoría de vulnerabilidades y prevención de secretos..."
    if "signoff" in node:
        return "CEO Zero-Touch Governor: Verificando unit economics y umbral de margen bruto ≥ 80%..."
    return f"Herramienta automatizada de validación en nodo {node_name}..."


class DashboardStreamService:
    """Singleton service to execute LangGraph workflows and broadcast SSE events in real-time."""

    def __init__(self, orchestrator: OrchestratorService | None = None) -> None:
        self.orchestrator = orchestrator
        self.office_store = OfficeStore()
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self._project_tasks: dict[str, asyncio.Task[Any]] = {}
        self._project_states: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def set_orchestrator(self, orchestrator: OrchestratorService) -> None:
        """Inject initialized orchestrator instance."""
        self.orchestrator = orchestrator

    async def publish_event(self, project_id: str, event: dict[str, Any]) -> None:
        """Append an event to project history and broadcast to all active SSE subscribers."""
        # Ensure standard envelope
        if "time" not in event:
            event["time"] = datetime.now(UTC).strftime("%H:%M:%S")
        if "project_id" not in event:
            event["project_id"] = project_id
        if "event_type" not in event:
            event["event_type"] = "activity_log"

        async with self._lock:
            if project_id not in self._events:
                self._events[project_id] = []
            self._events[project_id].append(event)
            queues = list(self._subscribers.get(project_id, []))

        for q in queues:
            try:
                q.put_nowait(event)
            except Exception as exc:
                logger.warning("Fallo al entregar evento SSE a la cola de %s: %s", project_id, exc)

    async def subscribe(self, project_id: str) -> AsyncIterator[dict[str, Any]]:
        """Register a subscriber queue, yield past events, and stream new live events."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async with self._lock:
            if project_id not in self._subscribers:
                self._subscribers[project_id] = []
            self._subscribers[project_id].append(queue)
            past_events = list(self._events.get(project_id, []))

        # If no in-memory events yet, check SQLite for existing project conversations
        if not past_events:
            loaded_events = await self._load_events_from_db(project_id)
            if loaded_events:
                async with self._lock:
                    if not self._events.get(project_id):
                        self._events[project_id] = list(loaded_events)
                past_events = loaded_events

        try:
            # First, replay all past events for immediate hydration
            for ev in past_events:
                yield ev

            # Then stream newly incoming events
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield ev
                except TimeoutError:
                    # Keep-alive heartbeat comment
                    yield {"event_type": "ping", "time": datetime.now(UTC).strftime("%H:%M:%S")}
        finally:
            async with self._lock:
                if project_id in self._subscribers and queue in self._subscribers[project_id]:
                    self._subscribers[project_id].remove(queue)
                    if not self._subscribers[project_id]:
                        del self._subscribers[project_id]

    async def _load_events_from_db(self, project_id: str) -> list[dict[str, Any]]:
        """Reconstruct activity log events from SQLite agent_conversations table."""
        try:
            store = OfficeStore()
            convs = await store.get_conversations(project_id)
            if not convs:
                return []

            events: list[dict[str, Any]] = []
            # Synthesize initial Boss request
            events.append({
                "time": convs[0].created_at.strftime("%H:%M:%S") if convs[0].created_at else "00:00:00",
                "category": "user",
                "agent": "👔 Boss",
                "msg": f"Request from Boss: Proyecto inicializado ({project_id})",
                "stage_index": 0,
                "stage_id": "stage-received",
                "stage_name": "Received",
                "project_id": project_id,
                "tokens": 0,
                "cost": 0.0,
            })

            cum_tokens = 0
            for c in convs:
                agent_id = c.agent_id.value if hasattr(c.agent_id, "value") else str(c.agent_id)
                status_val = c.status.value if hasattr(c.status, "value") else str(c.status)
                st_idx, st_id, st_name = map_node_to_pipeline_stage(agent_id, status_val)
                step_tokens = c.estimated_tokens_in + c.estimated_tokens_out
                cum_tokens += step_tokens
                t_str = c.created_at.strftime("%H:%M:%S") if c.created_at else "00:00:00"
                agent_name = get_agent_name(agent_id)
                verdict = c.verdict or "APROBADO"
                status_clean = status_val.replace("_", " ") if status_val else "COMPLETADO"

                # Extract human-readable summary from raw_response
                summary = ""
                if c.raw_response:
                    dash_m = re.search(r"^\s*---\s*\n(.*?)\n---", c.raw_response, re.DOTALL)
                    if dash_m:
                        try:
                            fm = yaml.safe_load(dash_m.group(1))
                            if isinstance(fm, dict):
                                summary = str(fm.get("resumen") or fm.get("descripcion") or fm.get("objetivo") or "")
                        except Exception:
                            pass
                    if not summary:
                        clean_body = re.sub(r"^\s*---\s*\n.*?\n---\s*", "", c.raw_response, flags=re.DOTALL).strip()
                        lines = [line.strip().lstrip("#").strip() for line in clean_body.splitlines() if line.strip() and not line.strip().startswith("```")]
                        if lines:
                            summary = lines[0][:140]

                # 1. Tool event if QA, CISO, or DevOps
                if any(k in agent_id for k in ("qa", "ciso", "devops")):
                    events.append({
                        "time": t_str,
                        "category": "tool",
                        "agent": agent_name,
                        "msg": get_tool_description(agent_id),
                        "stage_index": st_idx,
                        "stage_id": st_id,
                        "stage_name": st_name,
                        "project_id": project_id,
                        "tokens": cum_tokens,
                    })

                # 2. Working / Response event
                desc_text = f"Entregable emitido: {summary}" if summary else f"Entregable emitido con veredicto {verdict}"
                events.append({
                    "time": t_str,
                    "category": "response",
                    "agent": agent_name,
                    "msg": f"{desc_text} [{status_clean}]",
                    "stage_index": st_idx,
                    "stage_id": st_id,
                    "stage_name": st_name,
                    "project_id": project_id,
                    "tokens": cum_tokens,
                })

                # 3. Delegate event
                events.append({
                    "time": t_str,
                    "category": "delegate",
                    "agent": agent_name,
                    "msg": f"{agent_name} avanzó etapa [{status_clean}]",
                    "stage_index": st_idx,
                    "stage_id": st_id,
                    "stage_name": st_name,
                    "project_id": project_id,
                    "tokens": cum_tokens,
                })

                # 4. Done event if approved
                if verdict == "APROBADO" or "AUTORIZADO" in status_val:
                    events.append({
                        "time": t_str,
                        "category": "done",
                        "agent": agent_name,
                        "msg": f"Etapa {st_name} validada con éxito.",
                        "stage_index": st_idx,
                        "stage_id": st_id,
                        "stage_name": st_name,
                        "project_id": project_id,
                        "tokens": cum_tokens,
                    })

            return events
        except Exception as exc:
            logger.exception("Error reconstruyendo eventos para %s: %s", project_id, exc)
            return []

    async def start_run(
        self,
        prompt: str,
        project_id: str | None = None,
        mock: bool | None = None,
    ) -> str:
        """Launch background execution of LangGraph workflow and begin event streaming."""
        if not prompt or not prompt.strip():
            raise ValueError("El prompt o mandato de negocio no puede estar vacío.")

        pid = project_id.strip() if project_id and project_id.strip() else f"proj_{uuid.uuid4().hex[:8]}"

        # 1. Register initial User event
        now_hms = datetime.now(UTC).strftime("%H:%M:%S")
        initial_event = {
            "time": now_hms,
            "category": "user",
            "agent": "👔 Boss",
            "msg": f"Request from Boss: {prompt.strip()}",
            "stage_index": 0,
            "stage_id": "stage-received",
            "stage_name": "Received",
            "project_id": pid,
            "tokens": len(prompt) // 4,
            "cost": 0.0,
            "saved": 0.0,
            "status": "RUNNING",
        }
        await self.publish_event(pid, initial_event)

        # 2. Update in-memory state
        self._project_states[pid] = {
            "project_id": pid,
            "status": "RUNNING",
            "prompt": prompt,
            "stage_index": 0,
            "stage_id": "stage-received",
            "stage_name": "Received",
            "tokens": len(prompt) // 4,
            "cost": 0.0,
            "saved": 0.0,
            "current_node": "START",
        }

        # 3. Launch execution task
        task = asyncio.create_task(self._execute_workflow_stream(pid, prompt, mock=mock))
        self._project_tasks[pid] = task
        return pid

    async def _execute_workflow_stream(
        self,
        project_id: str,
        prompt: str,
        mock: bool | None = None,
    ) -> None:
        """Execute the LangGraph workflow, extract frontmatters, and stream events."""
        if self.orchestrator is None:
            logger.error("Orchestrator no inyectado en DashboardStreamService.")
            return

        # Handle Mock override if requested
        original_gateway = self.orchestrator.nodes.llm_gateway
        use_mock = mock is True or settings.USE_MOCK_LLM
        if use_mock:
            self.orchestrator.nodes.llm_gateway = MockLLMGateway()

        cumulative_tokens = len(prompt) // 4
        cumulative_cost = round(cumulative_tokens * (settings.LLM_INPUT_COST_PER_MILLION / 1_000_000.0), 6)
        saved_usd = 0.0

        try:
            async for chunk in self.orchestrator.stream_project(project_id, prompt):
                for node_name, updates in chunk.items():
                    now_hms = datetime.now(UTC).strftime("%H:%M:%S")

                    # Deliverable text
                    raw_text = ""
                    if isinstance(updates, dict):
                        for k, v in updates.items():
                            if isinstance(v, str) and len(v) > len(raw_text):
                                raw_text = v

                    # Extract YAML frontmatter
                    fm: dict[str, Any] = {}
                    if raw_text:
                        dash_m = re.search(r"^\s*---\s*\n(.*?)\n---", raw_text, re.DOTALL)
                        if dash_m:
                            try:
                                parsed = yaml.safe_load(dash_m.group(1))
                                if isinstance(parsed, dict):
                                    fm = parsed
                            except Exception:
                                pass

                    # Extract attributes or fall back
                    agente_emisor = str(fm.get("agente_emisor") or node_name)
                    agente_receptor = str(fm.get("agente_receptor") or fm.get("destino_siguiente") or "siguiente_fase")
                    estado = str(fm.get("estado") or fm.get("estado_entregable") or "COMPLETADO")
                    version_iteracion = fm.get("version_iteracion") or 1

                    # Stage mapping
                    st_idx, st_id, st_name = map_node_to_pipeline_stage(node_name, estado)

                    # Token accounting
                    step_tokens = max(1, len(raw_text) // 4) if raw_text else 200
                    step_cost = round(step_tokens * (settings.LLM_OUTPUT_COST_PER_MILLION / 1_000_000.0), 6)
                    cumulative_tokens += step_tokens
                    cumulative_cost += step_cost

                    agent_display = get_agent_name(node_name)

                    # KPI snapshot to embed in events
                    kpi_snapshot = {
                        "tokens": cumulative_tokens,
                        "tokens_str": f"{cumulative_tokens:,}",
                        "cost": f"${cumulative_cost:.4f}",
                        "cost_numeric": round(cumulative_cost, 4),
                        "saved": f"${saved_usd:.2f}",
                        "health": 100,
                        "agents_ready": 13,
                        "agents_total": 13,
                    }

                    # 1. Emit 🔵 Tool event if tool / check node
                    if any(k in node_name.lower() for k in ("qa", "ciso", "barrier", "devops")):
                        tool_ev = {
                            "time": now_hms,
                            "category": "tool",
                            "agent": agent_display,
                            "msg": get_tool_description(node_name),
                            "stage_index": st_idx,
                            "stage_id": st_id,
                            "stage_name": st_name,
                            "project_id": project_id,
                            "tokens": cumulative_tokens,
                            "cost": cumulative_cost,
                            "kpis": kpi_snapshot,
                        }
                        await self.publish_event(project_id, tool_ev)
                        await asyncio.sleep(0.05)

                    # 2. Emit 🟣 Response / ⚡ Working event
                    resp_ev = {
                        "time": now_hms,
                        "category": "response",
                        "agent": agent_display,
                        "msg": f"Entregable generado: [{estado}] (Iteración v{version_iteracion})",
                        "stage_index": st_idx,
                        "stage_id": st_id,
                        "stage_name": st_name,
                        "project_id": project_id,
                        "tokens": cumulative_tokens,
                        "cost": cumulative_cost,
                        "kpis": kpi_snapshot,
                    }
                    await self.publish_event(project_id, resp_ev)
                    await asyncio.sleep(0.05)

                    # 3. Emit ⚡ Delegate event
                    del_ev = {
                        "time": now_hms,
                        "category": "delegate",
                        "agent": agent_display,
                        "msg": f"{agente_emisor} delegó a {agente_receptor} [Estado: {estado}]",
                        "stage_index": st_idx,
                        "stage_id": st_id,
                        "stage_name": st_name,
                        "project_id": project_id,
                        "tokens": cumulative_tokens,
                        "cost": cumulative_cost,
                        "kpis": kpi_snapshot,
                    }
                    await self.publish_event(project_id, del_ev)
                    await asyncio.sleep(0.05)

                    # 4. Emit ✅ Done event
                    done_ev = {
                        "time": now_hms,
                        "category": "done",
                        "agent": agent_display,
                        "msg": f"Paso {node_name} culminó etapa {st_name}.",
                        "stage_index": st_idx,
                        "stage_id": st_id,
                        "stage_name": st_name,
                        "project_id": project_id,
                        "tokens": cumulative_tokens,
                        "cost": cumulative_cost,
                        "kpis": kpi_snapshot,
                    }
                    await self.publish_event(project_id, done_ev)

                    # Update internal state
                    self._project_states[project_id] = {
                        "project_id": project_id,
                        "status": "RUNNING",
                        "stage_index": st_idx,
                        "stage_id": st_id,
                        "stage_name": st_name,
                        "current_node": node_name,
                        "tokens": cumulative_tokens,
                        "cost": cumulative_cost,
                        "saved": saved_usd,
                    }

                    # 5. Check if complete cycle finished (CEO Signoff)
                    if "signoff" in node_name or estado in ("LANZAMIENTO_AUTORIZADO", "CICLO_DE_SOFTWARE_COMPLETADO_100"):
                        saved_usd += 240.0
                        kpi_snapshot["saved"] = f"${saved_usd:.2f}"
                        completion_ev = {
                            "time": now_hms,
                            "category": "done",
                            "agent": "👑 CEO",
                            "msg": "LANZAMIENTO_AUTORIZADO: Ciclo de software 100% completado (+ $240.00 ahorrados)",
                            "stage_index": 6,
                            "stage_id": "stage-ceo-signoff",
                            "stage_name": "CEO Signoff",
                            "project_id": project_id,
                            "tokens": cumulative_tokens,
                            "cost": cumulative_cost,
                            "saved": saved_usd,
                            "kpis": kpi_snapshot,
                            "status": "COMPLETED",
                        }
                        await self.publish_event(project_id, completion_ev)
                        self._project_states[project_id]["status"] = "COMPLETED"
                        self._project_states[project_id]["saved"] = saved_usd

            # End of stream marks completion if not already marked
            if self._project_states.get(project_id, {}).get("status") != "COMPLETED":
                saved_usd += 240.0
                now_hms = datetime.now(UTC).strftime("%H:%M:%S")
                final_ev = {
                    "time": now_hms,
                    "category": "done",
                    "agent": "👑 CEO",
                    "msg": "Ejecución finalizada con éxito (+ $240.00 ahorrados)",
                    "stage_index": 6,
                    "stage_id": "stage-ceo-signoff",
                    "stage_name": "CEO Signoff",
                    "project_id": project_id,
                    "tokens": cumulative_tokens,
                    "cost": cumulative_cost,
                    "saved": saved_usd,
                    "status": "COMPLETED",
                }
                await self.publish_event(project_id, final_ev)
                self._project_states[project_id]["status"] = "COMPLETED"
                self._project_states[project_id]["saved"] = saved_usd

        except Exception as exc:
            logger.exception("Error durante streaming de proyecto %s: %s", project_id, exc)
            now_hms = datetime.now(UTC).strftime("%H:%M:%S")
            err_ev = {
                "time": now_hms,
                "category": "user",
                "agent": "⚠️ System Alert",
                "msg": f"Error en ejecución del grafo: {exc}",
                "stage_index": 0,
                "stage_id": "stage-received",
                "stage_name": "Received",
                "project_id": project_id,
                "status": "FAILED",
            }
            await self.publish_event(project_id, err_ev)
            if project_id in self._project_states:
                self._project_states[project_id]["status"] = "FAILED"
        finally:
            if use_mock:
                self.orchestrator.nodes.llm_gateway = original_gateway

    async def get_state(self, project_id: str | None = None) -> dict[str, Any]:
        """Return the current dashboard state, pipeline stage, and events for a project."""
        pid = project_id.strip() if project_id and project_id.strip() else None

        # If no project_id specified, find latest in memory or in database
        if not pid:
            if self._project_states:
                pid = list(self._project_states.keys())[-1]
            else:
                # Check DB for visible projects
                projects = await OfficeStore().list_projects()
                if projects:
                    pid = projects[-1]["project_id"]

        if not pid:
            return {
                "project_id": "",
                "status": "IDLE",
                "stage_index": 0,
                "stage_id": "stage-received",
                "stage_name": "Received",
                "events": [],
                "tokens": 0,
                "cost": 0.0,
                "saved": 0.0,
                "health": 100,
                "current_node": None,
                "pasos_completados": 0,
            }

        # Check in-memory events first
        events = list(self._events.get(pid, []))
        if not events:
            events = await self._load_events_from_db(pid)
            if events:
                self._events[pid] = list(events)

        st = self._project_states.get(pid, {})
        status = st.get("status")
        if not status:
            # Check DB or checkpoint
            if self.orchestrator is not None:
                p_state = await self.orchestrator.get_project_state(pid)
                if p_state:
                    history = p_state.get("execution_history", [])
                    completed_enums = (
                        DeliverableStatus.LANZAMIENTO_AUTORIZADO,
                        DeliverableStatus.CICLO_DE_SOFTWARE_COMPLETADO_100,
                        DeliverableStatus.BLINDADO_APTO_PRODUCCION,
                    )
                    last_status = history[-1].status if history else None
                    if (
                        p_state.get("current_status") in completed_enums
                        or last_status in completed_enums
                    ):
                        status = "COMPLETED"
                    else:
                        status = "RUNNING"
                else:
                    status = "COMPLETED" if events else "IDLE"
            else:
                status = "COMPLETED" if events else "IDLE"

        # Check if project has already reached launch authorization or 100% completion
        has_launch_authorization = any(
            "AUTORIZADO" in (e.get("msg") or "")
            or "COMPLETADO_100" in (e.get("msg") or "")
            or e.get("stage_index") == 6
            for e in events
        )
        if has_launch_authorization:
            status = "COMPLETED"
            stage_idx = 6
            stage_id = "stage-ceo-signoff"
            stage_name = "CEO Signoff"
        else:
            stage_idx = st.get("stage_index")
            stage_id = st.get("stage_id")
            stage_name = st.get("stage_name")

            if stage_idx is None:
                if events:
                    stage_idx = max(e.get("stage_index", 0) for e in events)
                    if stage_idx < len(PIPELINE_STAGES):
                        stage_id, stage_name = PIPELINE_STAGES[stage_idx]
                    else:
                        stage_id, stage_name = "stage-ceo-signoff", "CEO Signoff"
                else:
                    stage_idx = 0
                    stage_id = "stage-received"
                    stage_name = "Received"

        tokens = st.get("tokens") or (events[-1].get("tokens", 0) if events else 0)
        cost = st.get("cost") or round(tokens * (settings.LLM_OUTPUT_COST_PER_MILLION / 1_000_000.0), 4)
        saved = st.get("saved", 240.0 if status == "COMPLETED" else 0.0)

        return {
            "project_id": pid,
            "status": status,
            "stage_index": stage_idx,
            "stage_id": stage_id,
            "stage_name": stage_name,
            "current_node": st.get("current_node"),
            "events": events,
            "tokens": tokens,
            "cost": cost,
            "saved": saved,
            "health": 100 if status == "COMPLETED" else 92,
            "pasos_completados": len(events),
        }


# Global singleton instance
dashboard_stream_service = DashboardStreamService()
