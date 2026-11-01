"""Real email bridge integrating RFC 5322 MIME messages with Strato IMAP and SMTP."""

from __future__ import annotations

import asyncio
import imaplib
import logging
import re
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path

from app.core.config import settings
from app.schemas.office import AgentEmailRecord

logger = logging.getLogger(__name__)


class RealMailBridge:
    """Connects internal agent communication to live Strato IMAP/SMTP services."""

    def __init__(
        self,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        imap_host: str | None = None,
        imap_port: int | None = None,
        mail_username: str | None = None,
        mail_password: str | None = None,
        real_mail_enabled: bool | None = None,
    ) -> None:
        """Initialize mail bridge with configurable or default Strato credentials."""
        self.smtp_host = smtp_host or settings.SMTP_HOST
        self.smtp_port = smtp_port or settings.SMTP_PORT
        self.imap_host = imap_host or settings.IMAP_HOST
        self.imap_port = imap_port or settings.IMAP_PORT
        self.mail_username = mail_username or settings.MAIL_USERNAME
        self.mail_password = mail_password or settings.MAIL_PASSWORD
        self.enabled = (
            real_mail_enabled
            if real_mail_enabled is not None
            else settings.REAL_MAIL_ENABLED
        )

    def build_rfc5322_message(
        self,
        email_record: AgentEmailRecord,
        deliverable_path: Path | str | None = None,
    ) -> EmailMessage:
        """Construct RFC 5322 multipart message with executive HTML summary and attachment."""
        msg = EmailMessage()

        mailbox_addr = self.mail_username or "bot@agentoffice.local"
        sender_display = email_record.sender.split("@")[0]
        recipient_display = email_record.recipient.split("@")[0]

        msg["From"] = f'"{sender_display}" <{mailbox_addr}>'
        msg["To"] = f'"{recipient_display}" <{mailbox_addr}>'
        msg["Subject"] = (
            f"[{email_record.project_id}][{email_record.priority}] {email_record.subject}"
        )

        plain_text = (
            f"AgentOffice Internal Dispatch\n"
            f"=============================\n"
            f"Project:  {email_record.project_id}\n"
            f"Step:     {email_record.step_number}\n"
            f"From:     {email_record.sender}\n"
            f"To:       {email_record.recipient}\n"
            f"Priority: {email_record.priority}\n\n"
            f"Summary:\n{email_record.body_summary}\n"
        )
        msg.set_content(plain_text)

        html_body = (
            f"<!DOCTYPE html><html><body>"
            f"<h2 style='color:#1a365d;'>AgentOffice Internal Dispatch</h2>"
            f"<table style='border-collapse:collapse;font-family:sans-serif;'>"
            f"<tr><td><b>Project:</b></td><td>{email_record.project_id}</td></tr>"
            f"<tr><td><b>Step:</b></td><td>{email_record.step_number}</td></tr>"
            f"<tr><td><b>From:</b></td><td>{email_record.sender}</td></tr>"
            f"<tr><td><b>To:</b></td><td>{email_record.recipient}</td></tr>"
            f"<tr><td><b>Priority:</b></td><td>{email_record.priority}</td></tr>"
            f"</table><hr/>"
            f"<h3>Executive Report & Instructions</h3>"
            f"<div style='background:#f7fafc;padding:12px;border-left:4px solid #3182ce;'>"
            f"<pre style='font-family:monospace;white-space:pre-wrap;'>"
            f"{email_record.body_summary}</pre></div></body></html>"
        )
        msg.add_alternative(html_body, subtype="html")

        # Resolve deliverable attachment
        target_path: Path | None = None
        if deliverable_path:
            p = Path(deliverable_path)
            if p.exists() and p.is_file():
                target_path = p
        elif email_record.attached_deliverable_path:
            p = Path(email_record.attached_deliverable_path)
            if p.exists() and p.is_file():
                target_path = p

        if target_path is not None:
            raw_bytes = target_path.read_bytes()
            msg.add_attachment(
                raw_bytes,
                maintype="text",
                subtype="markdown",
                filename=target_path.name,
            )

        return msg

    def _detect_imap_separator(self, imap: imaplib.IMAP4) -> str:
        """Query IMAP server for hierarchy separator character (e.g. '.' or '/')."""
        try:
            status, folder_list = imap.list('""', '""')
            if status == "OK" and folder_list:
                for entry in folder_list:
                    if isinstance(entry, bytes):
                        entry_str = entry.decode("utf-8", errors="ignore")
                    else:
                        entry_str = str(entry)
                    m = re.search(r'\((?:[^)]*)\)\s+"([^"]+)"', entry_str)
                    if m:
                        return m.group(1)
        except Exception as exc:
            logger.debug("No se pudo detectar separador IMAP automáticamente: %s", exc)
        return "."

    def _sync_imap_sync(
        self,
        email_record: AgentEmailRecord,
        msg: EmailMessage,
    ) -> bool:
        """Synchronously connect to IMAP SSL, create hierarchy folders and append message."""
        if not self.mail_username or not self.mail_password:
            logger.warning("Credenciales de correo no configuradas; omitiendo sincronización IMAP")
            return False

        imap: imaplib.IMAP4_SSL | None = None
        try:
            imap = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            imap.login(self.mail_username, self.mail_password)

            sep = self._detect_imap_separator(imap)
            recipient_agent = email_record.recipient.split("@")[0]

            # Build hierarchy: INBOX.AgentOffice.<project_id>.<recipient_agent>
            parts = ["INBOX", "AgentOffice", email_record.project_id, recipient_agent]
            for i in range(2, len(parts) + 1):
                folder_name = sep.join(parts[:i])
                try:
                    imap.create(f'"{folder_name}"')
                except Exception:
                    pass

            target_folder = sep.join(parts)
            date_time = imaplib.Time2Internaldate(time.time())
            imap.append(
                f'"{target_folder}"',
                "(\\Seen)",
                date_time,
                msg.as_bytes(),
            )
            return True
        except Exception as exc:
            logger.error(
                "Fallo al sincronizar correo en IMAP (%s): %s",
                email_record.id,
                exc,
            )
            return False
        finally:
            if imap is not None:
                try:
                    imap.logout()
                except Exception:
                    pass

    def _send_smtp_sync(self, msg: EmailMessage) -> bool:
        """Synchronously send message via Strato SMTP SSL."""
        if not self.mail_username or not self.mail_password:
            logger.warning("Credenciales de correo no configuradas; omitiendo envío SMTP")
            return False

        server: smtplib.SMTP_SSL | None = None
        try:
            server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
            server.login(self.mail_username, self.mail_password)
            server.send_message(msg)
            return True
        except Exception as exc:
            logger.error("Fallo al enviar correo por SMTP: %s", exc)
            return False
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    pass

    async def sync_email_record(
        self,
        email_record: AgentEmailRecord,
        send_smtp: bool = False,
        deliverable_path: Path | str | None = None,
    ) -> bool:
        """Build RFC 5322 message, append to agent IMAP folder, and optionally dispatch SMTP."""
        msg = self.build_rfc5322_message(email_record, deliverable_path=deliverable_path)
        imap_ok = await asyncio.to_thread(self._sync_imap_sync, email_record, msg)
        smtp_ok = True
        if send_smtp:
            smtp_ok = await asyncio.to_thread(self._send_smtp_sync, msg)
        return imap_ok and smtp_ok
