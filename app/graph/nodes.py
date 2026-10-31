"""Node implementations for the LangGraph software factory."""

from datetime import UTC, datetime

from app.graph.state import SoftwareFactoryState
from app.schemas.routing import AgentID, DeliverableStatus, StepExecutionRecord
from app.services.llm_gateway import LLMGatewayProtocol
from app.services.output_parser import AgentOutputParser
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter


def _build_user_payload(agent_id: AgentID, state: SoftwareFactoryState) -> str:
    """Construct exact relevant context for each agent without attention dilution."""
    match agent_id:
        case AgentID.AGENTE_01_PM:
            return f"# Idea Inicial del Proyecto\n{state['idea_inicial']}"

        case AgentID.AGENTE_02_ARCHITECT:
            return f"# Documento Pre-SDD Funcional\n{state['pre_sdd_doc']}"

        case AgentID.AGENTE_03_LARAVEL:
            parts = [f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}"]
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
            return (
                f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}\n\n"
                f"# Código PHP / Laravel a Auditar\n{state['codigo_php']}"
            )

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

        case _:
            return state.get("idea_inicial", "")


class FactoryNodes:
    """Factory creating and executing nodes within the Software Factory LangGraph pipeline."""

    def __init__(
        self,
        llm_gateway: LLMGatewayProtocol,
        prompt_loader: PromptLoader,
        workspace_writer: WorkspaceWriter,
    ) -> None:
        """Initialize FactoryNodes with required gateway, prompt loader, and workspace writer."""
        self.llm_gateway = llm_gateway
        self.prompt_loader = prompt_loader
        self.workspace_writer = workspace_writer

    async def _execute_agent_step(
        self,
        agent_id: AgentID,
        state: SoftwareFactoryState,
    ) -> tuple[str, DeliverableStatus, str, StepExecutionRecord]:
        """Execute common workflow for LLM-powered agents: prompt, call, parse, write, record."""
        step_number = len(state.get("execution_history", [])) + 1
        system_prompt = await self.prompt_loader.load_prompt(agent_id)
        payload = _build_user_payload(agent_id, state)

        raw_output = await self.llm_gateway.invoke_agent(agent_id, system_prompt, payload)
        header = AgentOutputParser.parse_routing_header(agent_id, raw_output)

        artifact_path = await self.workspace_writer.save_deliverable(
            project_id=state["project_id"],
            step_number=step_number,
            agent_id=agent_id,
            content=raw_output,
        )

        record = StepExecutionRecord(
            step_number=step_number,
            agent_id=agent_id,
            status=header.estado_entregable,
            target_next=header.destino_siguiente,
            artifact_path=artifact_path,
            timestamp_iso=datetime.now(UTC).isoformat(),
        )

        return raw_output, header.estado_entregable, header.destino_siguiente, record

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
            updates["retry_counts"] = {"qa_php": current_retries + 1}

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
            updates["retry_counts"] = {"qa_python": current_retries + 1}

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
            updates["retry_counts"] = {"ciso": current_ciso_retries + 1}

            culprit = header.culpable_detectado or AgentID.AGENTE_07_DEVOPS
            updates["ciso_culprit"] = culprit

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
