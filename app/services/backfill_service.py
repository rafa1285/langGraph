"""Retrospective hydration service rebuilding conversations, emails, and sync states."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.schemas.office import AgentConversationRecord
from app.schemas.routing import AgentID
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

            try:
                agent_enum = AgentID(agent_str)
            except ValueError:
                agent_enum = AgentID.AGENTE_01_PM

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
                try:
                    agent_e = AgentID(agent_name)
                except ValueError:
                    agent_e = AgentID.AGENTE_01_PM
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
