"""Retrospective hydration service rebuilding conversations, emails, and sync states."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.graph.state import SoftwareFactoryState
from app.schemas.office import AgentConversationRecord
from app.schemas.routing import AgentID, DeliverableStatus, StepExecutionRecord
from app.services.code_materializer import CodeMaterializerService
from app.services.mail_service import MailService
from app.services.notion_mcp_service import (
    KnowledgeSyncPort,
    get_knowledge_sync_adapter,
)
from app.services.office_store import OfficeStore
from app.services.output_parser import AgentOutputParser
from app.services.prompt_loader import PromptLoader
from app.services.real_mail_bridge import RealMailBridge

logger = logging.getLogger(__name__)

AGENT_ALIASES: dict[str, AgentID] = {
    # 00 CEO
    "ceo": AgentID.AGENTE_00_CEO,
    "00_ceo": AgentID.AGENTE_00_CEO,
    "agente_00_ceo": AgentID.AGENTE_00_CEO,
    # 01 PM
    "pm": AgentID.AGENTE_01_PM,
    "01_pm": AgentID.AGENTE_01_PM,
    "agente_01_pm": AgentID.AGENTE_01_PM,
    # 02 Architect
    "architect": AgentID.AGENTE_02_ARCHITECT,
    "02_architect": AgentID.AGENTE_02_ARCHITECT,
    "agente_02_architect": AgentID.AGENTE_02_ARCHITECT,
    # 03 Laravel
    "laravel": AgentID.AGENTE_03_LARAVEL,
    "03_laravel": AgentID.AGENTE_03_LARAVEL,
    "agente_03_laravel": AgentID.AGENTE_03_LARAVEL,
    # 04 FastAPI
    "fastapi": AgentID.AGENTE_04_FASTAPI,
    "04_fastapi": AgentID.AGENTE_04_FASTAPI,
    "agente_04_fastapi": AgentID.AGENTE_04_FASTAPI,
    # 05 QA PHP
    "qa_php": AgentID.AGENTE_05_QA_PHP,
    "05_qa_php": AgentID.AGENTE_05_QA_PHP,
    "agente_05_qa_php": AgentID.AGENTE_05_QA_PHP,
    # 06 QA Python
    "qa_python": AgentID.AGENTE_06_QA_PYTHON,
    "06_qa_python": AgentID.AGENTE_06_QA_PYTHON,
    "agente_06_qa_python": AgentID.AGENTE_06_QA_PYTHON,
    # 07 DevOps
    "devops": AgentID.AGENTE_07_DEVOPS,
    "07_devops": AgentID.AGENTE_07_DEVOPS,
    "agente_07_devops": AgentID.AGENTE_07_DEVOPS,
    # 08 Docs
    "docs": AgentID.AGENTE_08_DOCS,
    "08_docs": AgentID.AGENTE_08_DOCS,
    "agente_08_docs": AgentID.AGENTE_08_DOCS,
    # 09 Growth (Legacy)
    "growth": AgentID.AGENTE_09_GROWTH,
    "09_growth": AgentID.AGENTE_09_GROWTH,
    "agente_09_growth": AgentID.AGENTE_09_GROWTH,
    # 10 CISO
    "ciso": AgentID.AGENTE_10_CISO,
    "10_ciso": AgentID.AGENTE_10_CISO,
    "agente_10_ciso": AgentID.AGENTE_10_CISO,
    # 11 UI/UX
    "ui_ux": AgentID.AGENTE_11_UI_UX,
    "11_ui_ux": AgentID.AGENTE_11_UI_UX,
    "agente_11_ui_ux": AgentID.AGENTE_11_UI_UX,
    # 12 Marketing
    "marketing": AgentID.AGENTE_12_MARKETING,
    "12_marketing": AgentID.AGENTE_12_MARKETING,
    "agente_12_marketing": AgentID.AGENTE_12_MARKETING,
    # 13 Sales Analytics
    "sales": AgentID.AGENTE_13_SALES_ANALYTICS,
    "sales_analytics": AgentID.AGENTE_13_SALES_ANALYTICS,
    "13_sales_analytics": AgentID.AGENTE_13_SALES_ANALYTICS,
    "agente_13_sales_analytics": AgentID.AGENTE_13_SALES_ANALYTICS,
    # 14 QA UI/UX
    "qa_ui_ux": AgentID.AGENTE_14_QA_UI_UX,
    "14_qa_ui_ux": AgentID.AGENTE_14_QA_UI_UX,
    "agente_14_qa_ui_ux": AgentID.AGENTE_14_QA_UI_UX,
}


def resolve_agent_id(agent_str: str) -> AgentID:
    """Resolve an agent name or alias string to a canonical AgentID enum member."""
    clean = agent_str.strip().lower()
    if clean in AGENT_ALIASES:
        return AGENT_ALIASES[clean]
    try:
        return AgentID(clean)
    except ValueError:
        return AgentID.AGENTE_01_PM


class ProjectBackfillService:
    """Hydrates database records retrospectively from historical markdown deliverables."""

    def __init__(
        self,
        office_store: OfficeStore | None = None,
        mail_service: MailService | None = None,
        workspaces_dir: Path | str | None = None,
        prompts_dir: Path | str | None = None,
        real_mail_bridge: RealMailBridge | None = None,
        knowledge_sync: KnowledgeSyncPort | None = None,
    ) -> None:
        """Initialize backfill service with storage, prompts, and sync bridges."""
        self.office_store = office_store or OfficeStore()
        self.mail_service = mail_service or MailService(self.office_store)
        self.workspaces_dir = Path(workspaces_dir or settings.WORKSPACES_DIR)
        self.prompts_dir = Path(prompts_dir or settings.PROMPTS_DIR)
        self.prompt_loader = PromptLoader(prompts_dir=self.prompts_dir)
        self.real_mail_bridge = real_mail_bridge or RealMailBridge()
        self.knowledge_sync = knowledge_sync

    async def backfill_project(
        self,
        project_id: str,
        sync_real_mail: bool = False,
        sync_notion: bool = False,
    ) -> dict[str, Any]:
        """Scan historical markdown files, reconstruct SQLite records, and sync destinations."""
        project_dir = self.workspaces_dir / project_id
        if not project_dir.exists() or not project_dir.is_dir():
            raise FileNotFoundError(
                f"Directorio de proyecto no encontrado: {project_dir}"
            )

        md_files = sorted(
            [
                p
                for p in project_dir.glob("*.md")
                if p.is_file() and p.name not in ("README.md", "INDEX.md")
            ],
            key=lambda p: (
                int(p.stem.split("_")[0]) if p.stem.split("_")[0].isdigit() else 999,
                p.name,
            ),
        )

        existing_convs = await self.office_store.get_conversations(project_id)
        existing_conv_keys = {
            (c.step_number, c.agent_id.value) for c in existing_convs
        }

        existing_emails = await self.office_store.get_emails(project_id)
        existing_email_keys = {
            (e.step_number, e.sender) for e in existing_emails
        }

        conversations_added = 0
        emails_added = 0
        last_status = "PENDIENTE"
        last_agent = "unknown"
        last_verdict = "APROBADO"
        max_step = 0

        for md_path in md_files:
            stem_parts = md_path.stem.split("_", 1)
            step_num = int(stem_parts[0]) if stem_parts[0].isdigit() else 0
            agent_str = stem_parts[1] if len(stem_parts) > 1 else "unknown"
            if step_num > max_step:
                max_step = step_num

            content = md_path.read_text(encoding="utf-8")
            agent_enum = resolve_agent_id(agent_str)

            header = AgentOutputParser.parse_routing_header(agent_enum, content)
            last_status = header.estado_entregable.value
            last_agent = agent_str
            last_verdict = header.veredicto or "APROBADO"

            # 1. Backfill conversation record if missing
            conv_key = (step_num, agent_enum.value)
            if conv_key not in existing_conv_keys:
                try:
                    system_prompt = await self.prompt_loader.load_prompt(agent_enum)
                except Exception:
                    system_prompt = f"Prompt para {agent_enum.value}"

                tokens_in = max(1, len(system_prompt) // 4)
                tokens_out = max(1, len(content) // 4)
                culprit_val = (
                    header.culpable_detectado.value
                    if isinstance(header.culpable_detectado, AgentID)
                    else (str(header.culpable_detectado) if header.culpable_detectado else None)
                )

                conv_record = AgentConversationRecord(
                    project_id=project_id,
                    step_number=step_num,
                    agent_id=agent_enum,
                    system_prompt=system_prompt,
                    user_payload=f"Payload reconstruido para paso {step_num}",
                    raw_response=content,
                    status=header.estado_entregable,
                    verdict=header.veredicto or "APROBADO",
                    score=header.puntuacion or 100,
                    culprit=culprit_val,
                    duration_ms=500,
                    estimated_tokens_in=tokens_in,
                    estimated_tokens_out=tokens_out,
                )
                await self.office_store.save_conversation(conv_record)
                existing_conv_keys.add(conv_key)
                conversations_added += 1

            # 2. Backfill handoff email if missing
            sender_addr = f"{agent_enum.value}@agentoffice.local"
            email_key = (step_num, sender_addr)
            if email_key not in existing_email_keys:
                sent = await self.mail_service.send_handoff_email(
                    project_id=project_id,
                    step_number=step_num,
                    sender_id=agent_enum,
                    target_next=header.destino_siguiente,
                    header=header,
                    artifact_path=str(md_path),
                    raw_output=content,
                )
                emails_added += len(sent)
                existing_email_keys.add(email_key)

        # 3. Synchronize with real email bridge if requested
        real_mail_synced = 0
        if sync_real_mail:
            all_emails = await self.office_store.get_emails(project_id)
            for em in all_emails:
                deliverable_to_attach = em.attached_deliverable_path
                ok = await self.real_mail_bridge.sync_email_record(
                    email_record=em,
                    send_smtp=False,
                    deliverable_path=deliverable_to_attach,
                )
                if ok:
                    real_mail_synced += 1

        # 4. Synchronize with Notion MCP / Local Mirror if requested
        notion_synced = 0
        if sync_notion:
            sync_adapter = self.knowledge_sync or get_knowledge_sync_adapter()
            await sync_adapter.create_project_hub(
                project_id=project_id,
                title=f"Factoría de Software - {project_id}",
                summary=f"Estado: {last_status} | Último agente: {last_agent}",
            )

            for md_path in md_files:
                stem_parts = md_path.stem.split("_", 1)
                step_num = int(stem_parts[0]) if stem_parts[0].isdigit() else 0
                agent_name = stem_parts[1] if len(stem_parts) > 1 else "unknown"
                content = md_path.read_text(encoding="utf-8")
                agent_e = resolve_agent_id(agent_name)
                h = AgentOutputParser.parse_routing_header(agent_e, content)

                await sync_adapter.append_deliverable_page(
                    project_id=project_id,
                    step_number=step_num,
                    agent_id=agent_name,
                    deliverable_title=h.estado_entregable.value,
                    markdown_content=content,
                )
                notion_synced += 1

            all_emails = await self.office_store.get_emails(project_id)
            for em in all_emails:
                await sync_adapter.log_agent_email(
                    project_id=project_id,
                    email_data=em.model_dump(mode="json"),
                )

            await sync_adapter.update_project_status(
                project_id=project_id,
                status_data={
                    "current_status": last_status,
                    "last_agent": last_agent,
                    "steps_completed": max_step,
                    "verdict": last_verdict,
                },
            )

        return {
            "project_id": project_id,
            "total_deliverables_found": len(md_files),
            "conversations_added": conversations_added,
            "emails_added": emails_added,
            "real_mail_synced": real_mail_synced,
            "notion_synced": notion_synced,
        }

    async def extend_project_with_new_agents(
        self,
        project_id: str,
        real_mail: bool = False,
        sync_notion: bool = False,
        nodes: Any | None = None,
    ) -> dict[str, Any]:
        """Extend existing legacy project with CEO, UI/UX, Marketing, and Sales agents."""
        project_dir = self.workspaces_dir / project_id
        if not project_dir.exists() or not project_dir.is_dir():
            raise FileNotFoundError(
                f"Directorio de proyecto no encontrado: {project_dir}"
            )

        md_files = sorted(
            [
                p
                for p in project_dir.glob("*.md")
                if p.is_file() and p.name not in ("README.md", "INDEX.md")
            ],
            key=lambda p: (
                int(p.stem.split("_")[0]) if p.stem.split("_")[0].isdigit() else 999,
                p.name,
            ),
        )

        files_by_agent: dict[AgentID, str] = {}
        ceo_charter_content = ""
        ceo_signoff_content = ""

        for md_path in md_files:
            stem_parts = md_path.stem.split("_", 1)
            agent_str = stem_parts[1] if len(stem_parts) > 1 else "unknown"
            agent_enum = resolve_agent_id(agent_str)
            content = md_path.read_text(encoding="utf-8")

            if agent_enum == AgentID.AGENTE_00_CEO:
                if any(
                    k in content.lower()
                    for k in ("signoff", "acta", "cierre", "lanzamiento", "release_manifest")
                ):
                    ceo_signoff_content = content
                else:
                    ceo_charter_content = content
            else:
                files_by_agent[agent_enum] = content

        idea_inicial = f"Proyecto {project_id}"
        pre_sdd = files_by_agent.get(AgentID.AGENTE_01_PM, "")
        if pre_sdd:
            idea_match = re.search(
                r"#+\s*(?:Idea Inicial|Requisitos|Idea|Proyecto)[:\s]*(.*?)(?=\n#+|$)",
                pre_sdd,
                re.DOTALL | re.IGNORECASE,
            )
            if idea_match and idea_match.group(1).strip():
                idea_inicial = idea_match.group(1).strip()

        # Reconstruct SQLite conversations if missing
        existing_convs = await self.office_store.get_conversations(project_id)
        if not existing_convs and md_files:
            await self.backfill_project(project_id, sync_real_mail=False, sync_notion=False)
            existing_convs = await self.office_store.get_conversations(project_id)

        execution_history: list[StepExecutionRecord] = []
        for c in existing_convs:
            execution_history.append(
                StepExecutionRecord(
                    step_number=c.step_number,
                    agent_id=c.agent_id,
                    status=c.status,
                    target_next="",
                    artifact_path=f"workspaces/{project_id}/{c.step_number:02d}_{c.agent_id.value}.md",
                    timestamp_iso=(
                        c.created_at.isoformat()
                        if hasattr(c, "created_at") and c.created_at
                        else ""
                    ),
                )
            )

        if not execution_history and md_files:
            for md_path in md_files:
                stem_parts = md_path.stem.split("_", 1)
                step_num = int(stem_parts[0]) if stem_parts[0].isdigit() else 1
                agent_str = stem_parts[1] if len(stem_parts) > 1 else "unknown"
                agent_enum = resolve_agent_id(agent_str)
                execution_history.append(
                    StepExecutionRecord(
                        step_number=step_num,
                        agent_id=agent_enum,
                        status=DeliverableStatus.APROBADO_PARA_DESARROLLO,
                        target_next="",
                        artifact_path=str(md_path),
                        timestamp_iso="",
                    )
                )

        state: SoftwareFactoryState = {
            "project_id": project_id,
            "idea_inicial": idea_inicial,
            "ceo_charter": ceo_charter_content,
            "pre_sdd_doc": pre_sdd,
            "sdd_arquitectura": files_by_agent.get(AgentID.AGENTE_02_ARCHITECT, ""),
            "ui_ux_spec": files_by_agent.get(AgentID.AGENTE_11_UI_UX, ""),
            "requiere_php": (
                AgentID.AGENTE_03_LARAVEL in files_by_agent
                or bool(files_by_agent.get(AgentID.AGENTE_03_LARAVEL))
            ),
            "requiere_python": (
                AgentID.AGENTE_04_FASTAPI in files_by_agent
                or bool(files_by_agent.get(AgentID.AGENTE_04_FASTAPI))
            ),
            "codigo_php": files_by_agent.get(AgentID.AGENTE_03_LARAVEL, ""),
            "codigo_python": files_by_agent.get(AgentID.AGENTE_04_FASTAPI, ""),
            "reporte_qa_php": files_by_agent.get(AgentID.AGENTE_05_QA_PHP, ""),
            "reporte_qa_python": files_by_agent.get(AgentID.AGENTE_06_QA_PYTHON, ""),
            "infraestructura_docker": files_by_agent.get(AgentID.AGENTE_07_DEVOPS, ""),
            "dictamen_ciso": files_by_agent.get(AgentID.AGENTE_10_CISO, ""),
            "documentacion_rag": files_by_agent.get(AgentID.AGENTE_08_DOCS, ""),
            "estrategia_growth": files_by_agent.get(AgentID.AGENTE_09_GROWTH, ""),
            "marketing_spec": files_by_agent.get(AgentID.AGENTE_12_MARKETING, ""),
            "sales_analytics_spec": files_by_agent.get(AgentID.AGENTE_13_SALES_ANALYTICS, ""),
            "ceo_signoff": ceo_signoff_content,
            "ceo_approved": bool(ceo_signoff_content),
            "status_qa_php": (
                DeliverableStatus.APROBADO_PARA_DESPLIEGUE
                if files_by_agent.get(AgentID.AGENTE_05_QA_PHP)
                else DeliverableStatus.PENDIENTE
            ),
            "status_qa_python": (
                DeliverableStatus.APROBADO_PARA_DESPLIEGUE
                if files_by_agent.get(AgentID.AGENTE_06_QA_PYTHON)
                else DeliverableStatus.PENDIENTE
            ),
            "status_ciso": (
                DeliverableStatus.BLINDADO_APTO_PRODUCCION
                if files_by_agent.get(AgentID.AGENTE_10_CISO)
                else DeliverableStatus.PENDIENTE
            ),
            "ciso_culprit": None,
            "current_status": DeliverableStatus.APROBADO_PARA_DESPLIEGUE,
            "halt_reason": None,
            "retry_counts": {},
            "execution_history": execution_history,
        }

        # Setup FactoryNodes if not provided
        if nodes is not None:
            factory_nodes = nodes
        else:
            from app.graph.nodes import FactoryNodes
            from app.services.llm_gateway import (
                GeminiLLMGateway,
                LLMGatewayProtocol,
                MockLLMGateway,
            )
            from app.services.workspace_writer import WorkspaceWriter

            llm_gw: LLMGatewayProtocol = (
                MockLLMGateway() if settings.USE_MOCK_LLM else GeminiLLMGateway()
            )
            writer = WorkspaceWriter(base_dir=self.workspaces_dir)
            sync_port = self.knowledge_sync
            if sync_notion and sync_port is None:
                sync_port = get_knowledge_sync_adapter()

            factory_nodes = FactoryNodes(
                llm_gateway=llm_gw,
                prompt_loader=self.prompt_loader,
                workspace_writer=writer,
                office_store=self.office_store,
                mail_service=self.mail_service,
                knowledge_sync=sync_port if sync_notion else None,
            )

        sync_adapter = self.knowledge_sync or get_knowledge_sync_adapter()
        if sync_notion:
            await sync_adapter.create_project_hub(
                project_id=project_id,
                title=f"Factoría de Software - {project_id}",
                summary="Extensión con 4 nuevos departamentos (CEO, UI/UX, Marketing, Sales)",
            )

        executed_nodes = [
            "agente_00_ceo_charter",
            "agente_11_ui_ux",
            "agente_12_marketing",
            "agente_13_sales_analytics",
            "agente_00_ceo_signoff",
        ]

        charter_fn = getattr(
            factory_nodes,
            "node_00_ceo_charter",
            getattr(factory_nodes, "ceo_charter_node", None),
        )
        ui_ux_fn = getattr(
            factory_nodes, "node_11_ui_ux", getattr(factory_nodes, "ui_ux_node", None)
        )
        marketing_fn = getattr(
            factory_nodes,
            "node_12_marketing",
            getattr(factory_nodes, "marketing_node", None),
        )
        sales_fn = getattr(
            factory_nodes,
            "node_13_sales_analytics",
            getattr(factory_nodes, "sales_analytics_node", None),
        )
        signoff_fn = getattr(
            factory_nodes,
            "node_00_ceo_signoff",
            getattr(factory_nodes, "ceo_signoff_node", None),
        )

        if (
            charter_fn is None
            or ui_ux_fn is None
            or marketing_fn is None
            or sales_fn is None
            or signoff_fn is None
        ):
            raise AttributeError("FactoryNodes does not implement all required extension nodes.")

        # 1. CEO Charter
        res_charter = await charter_fn(state)
        state.update(res_charter)
        hist = res_charter.get("execution_history")
        if isinstance(hist, list):
            state["execution_history"].extend(hist)

        # 2. UI/UX
        res_ui_ux = await ui_ux_fn(state)
        state.update(res_ui_ux)
        hist = res_ui_ux.get("execution_history")
        if isinstance(hist, list):
            state["execution_history"].extend(hist)

        # 3. Marketing
        res_marketing = await marketing_fn(state)
        state.update(res_marketing)
        hist = res_marketing.get("execution_history")
        if isinstance(hist, list):
            state["execution_history"].extend(hist)

        # 4. Sales & Analytics
        res_sales = await sales_fn(state)
        state.update(res_sales)
        hist = res_sales.get("execution_history")
        if isinstance(hist, list):
            state["execution_history"].extend(hist)

        # 5. CEO Signoff
        res_signoff = await signoff_fn(state)
        state.update(res_signoff)
        hist = res_signoff.get("execution_history")
        if isinstance(hist, list):
            state["execution_history"].extend(hist)

        # Materialize files in build/
        materializer = CodeMaterializerService(workspaces_dir=self.workspaces_dir)
        _build_dir, manifest_data = materializer.materialize_project(project_id)
        materialized_files: list[str] = [
            item["path"] for item in manifest_data.get("files", []) if "path" in item
        ]

        if real_mail:
            all_emails = await self.office_store.get_emails(project_id)
            for em in all_emails:
                await self.real_mail_bridge.sync_email_record(
                    email_record=em,
                    send_smtp=False,
                    deliverable_path=em.attached_deliverable_path,
                )

        if sync_notion:
            await sync_adapter.update_project_status(
                project_id=project_id,
                status_data={
                    "current_status": "LANZAMIENTO_AUTORIZADO",
                    "last_agent": "agente_00_ceo",
                    "steps_completed": len(state["execution_history"]),
                    "verdict": "APROBADO",
                },
            )

        return {
            "project_id": project_id,
            "executed_nodes": executed_nodes,
            "materialized_files": materialized_files,
            "status": "EXTENDED_OK",
        }


async def extend_project_with_new_agents(
    project_id: str,
    real_mail: bool = False,
    sync_notion: bool = False,
    workspaces_dir: Path | str | None = None,
    office_store: OfficeStore | None = None,
    mail_service: MailService | None = None,
    real_mail_bridge: RealMailBridge | None = None,
    knowledge_sync: KnowledgeSyncPort | None = None,
    nodes: Any | None = None,
) -> dict[str, Any]:
    """Convenience function delegating project extension to ProjectBackfillService."""
    service = ProjectBackfillService(
        office_store=office_store,
        mail_service=mail_service,
        workspaces_dir=workspaces_dir,
        real_mail_bridge=real_mail_bridge,
        knowledge_sync=knowledge_sync,
    )
    return await service.extend_project_with_new_agents(
        project_id=project_id,
        real_mail=real_mail,
        sync_notion=sync_notion,
        nodes=nodes,
    )
