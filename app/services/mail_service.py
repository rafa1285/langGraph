"""Internal agent email service providing handoff emails and inbox injection."""

import re

from app.schemas.office import AgentEmailRecord, EmailPriority
from app.schemas.routing import AgentID, RoutingHeader
from app.services.office_store import OfficeStore


class MailService:
    """Service handling internal asynchronous email communications between factory agents."""

    def __init__(self, store: OfficeStore | None = None) -> None:
        """Initialize the mail service with an OfficeStore instance."""
        self.store = store or OfficeStore()

    def _extract_body_snippet(self, raw_output: str, max_chars: int = 500) -> str:
        """Strip YAML frontmatter and return the initial text snippet as summary."""
        cleaned = re.sub(r"^---.*?---\s*", "", raw_output, flags=re.DOTALL).strip()
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        snippet = " ".join(lines)
        if len(snippet) > max_chars:
            return snippet[:max_chars] + "..."
        return snippet or "Sin contenido adicional en el entregable."

    async def send_handoff_email(
        self,
        project_id: str,
        step_number: int,
        sender_id: AgentID,
        target_next: str,
        header: RoutingHeader,
        artifact_path: str,
        raw_output: str,
    ) -> list[AgentEmailRecord]:
        """Generate and persist handoff email(s) for the next step or detected culprit."""
        sender_addr = f"{sender_id.value}@agentoffice.local"
        snippet = self._extract_body_snippet(raw_output)

        is_critical = header.veredicto in ("RECHAZADO", "BLOQUEADO")
        recipients: list[str] = []
        priority: EmailPriority = "NORMAL"

        if is_critical and header.culpable_detectado:
            culprit_val = (
                header.culpable_detectado.value
                if isinstance(header.culpable_detectado, AgentID)
                else str(header.culpable_detectado)
            )
            recipients = [f"{culprit_val}@agentoffice.local"]
            priority = "CRITICAL"
            subject = (
                f"🚨 URGENTE: {header.veredicto} emitido por {sender_id.value} "
                "- Requiere refactorización inmediata"
            )
            tasks = (
                f"Subsanar los fallos señalados en el dictamen adjunto ({artifact_path}) "
                "y volver a entregar el artefacto corregido."
            )
        elif is_critical:
            priority = "CRITICAL"
            targets = [t.strip() for t in target_next.split(",") if t.strip()]
            recipients = [
                t if "@" in t else f"{t}@agentoffice.local"
                for t in targets
                if "barrier" not in t.lower() and "end" not in t.lower()
            ]
            if not recipients:
                recipients = ["supervision_calidad@agentoffice.local"]
            subject = f"🚨 URGENTE: {header.veredicto} emitido por {sender_id.value}"
            tasks = (
                f"Revisar y corregir el código según el reporte adjunto ({artifact_path})."
            )
        else:
            if sender_id in (AgentID.AGENTE_01_PM, AgentID.AGENTE_10_CISO):
                priority = "HIGH"
            else:
                priority = "NORMAL"

            targets = [t.strip() for t in target_next.split(",") if t.strip()]
            for t in targets:
                lower_t = t.lower()
                if "qa_sync_barrier" in lower_t:
                    recipients.append("agente_07_devops@agentoffice.local")
                elif "end" in lower_t:
                    recipients.append("director_proyectos@agentoffice.local")
                else:
                    addr = t if "@" in t else f"{t}@agentoffice.local"
                    recipients.append(addr)

            if not recipients:
                recipients = ["director_proyectos@agentoffice.local"]

            subject = (
                f"📋 Entregable {header.estado_entregable.value} emitido por "
                f"{sender_id.value}"
            )
            tasks = (
                f"Consumir el entregable adjunto ({artifact_path}) y proceder con la "
                "siguiente fase del proyecto."
            )

        # Remove duplicate recipients while preserving order
        unique_recipients = list(dict.fromkeys(recipients))
        score_display = f"{header.puntuacion}/100" if header.puntuacion is not None else "N/A"

        body_summary = (
            f"ESTADO: {header.estado_entregable.value}\n"
            f"VEREDICTO: {header.veredicto}\n"
            f"PUNTUACIÓN: {score_display}\n"
            f"ADJUNTO: {artifact_path}\n\n"
            f"RESUMEN EJECUTIVO:\n{snippet}\n\n"
            f"TAREAS REQUERIDAS:\n{tasks}"
        )

        sent_emails: list[AgentEmailRecord] = []
        for recipient in unique_recipients:
            email = AgentEmailRecord(
                project_id=project_id,
                step_number=step_number,
                sender=sender_addr,
                recipient=recipient,
                cc=[],
                subject=subject,
                body_summary=body_summary,
                attached_deliverable_path=artifact_path,
                priority=priority,
                is_read=False,
            )
            await self.store.save_email(email)
            sent_emails.append(email)

        return sent_emails

    async def send_email(
        self,
        project_id: str,
        sender: str,
        recipient: str,
        subject: str,
        body_summary: str,
        step_number: int = 0,
        cc: list[str] | None = None,
        attached_deliverable_path: str = "",
        priority: EmailPriority = "NORMAL",
    ) -> AgentEmailRecord:
        """Send and persist a direct email message between any identities."""
        email = AgentEmailRecord(
            project_id=project_id,
            step_number=step_number,
            sender=sender,
            recipient=recipient,
            cc=cc or [],
            subject=subject,
            body_summary=body_summary,
            attached_deliverable_path=attached_deliverable_path,
            priority=priority,
            is_read=False,
        )
        await self.store.save_email(email)
        return email

    async def fetch_unread_inbox(
        self,
        project_id: str,
        agent_id: AgentID,
    ) -> tuple[str, list[AgentEmailRecord]]:
        """Retrieve unread emails for an agent, build Markdown prefix, and mark as read."""
        all_unread = await self.store.get_emails(project_id, unread_only=True)
        # Filter for this agent
        agent_unread = [
            email for email in all_unread if agent_id.value in email.recipient
        ]

        if not agent_unread:
            return "", []

        # Mark as read
        await self.store.mark_emails_as_read([email.id for email in agent_unread])

        lines: list[str] = [
            "### 📬 BANDEJA DE ENTRADA (CORREOS RECIBIDOS DE OTROS AGENTES)\n",
            f"Has recibido {len(agent_unread)} correo(s) prioritario(s) en tu bandeja:\n",
        ]

        for idx, email in enumerate(agent_unread, start=1):
            date_str = email.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            lines.extend(
                [
                    f"#### ✉️ Correo {idx}: {email.subject}",
                    f"- **De:** {email.sender}",
                    f"- **Prioridad:** {email.priority}",
                    f"- **Fecha:** {date_str}",
                    f"- **Entregable Adjunto:** {email.attached_deliverable_path}",
                    "- **Mensaje:**",
                    f"{email.body_summary}\n",
                    "---\n",
                ]
            )

        return "\n".join(lines), agent_unread
