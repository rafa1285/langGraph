"""Persistent SQLite storage for agent conversations, internal emails, and telemetry."""

import json
from pathlib import Path
from typing import cast
from uuid import UUID

import aiosqlite

from app.core.config import settings
from app.schemas.office import AgentConversationRecord, AgentEmailRecord, EmailPriority
from app.schemas.routing import AgentID, DeliverableStatus


class OfficeStore:
    """Async store managing conversations, emails, and telemetry persisted in SQLite."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        """Initialize the store with a specific or default SQLite database path."""
        if db_path is None:
            self.db_path = Path(settings.OFFICE_DB_PATH)
        else:
            self.db_path = Path(db_path)

    async def init_db(self) -> None:
        """Initialize database tables and indexes if they do not already exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_conversations (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    step_number INTEGER NOT NULL,
                    agent_id TEXT NOT NULL,
                    system_prompt TEXT NOT NULL,
                    user_payload TEXT NOT NULL,
                    raw_response TEXT NOT NULL,
                    status TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    score INTEGER,
                    culprit TEXT,
                    duration_ms INTEGER NOT NULL,
                    estimated_tokens_in INTEGER NOT NULL,
                    estimated_tokens_out INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_emails (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    step_number INTEGER NOT NULL,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    cc TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body_summary TEXT NOT NULL,
                    attached_deliverable_path TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    is_read INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_conv_project "
                "ON agent_conversations(project_id, step_number);"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_email_recipient "
                "ON agent_emails(project_id, recipient, is_read);"
            )
            await db.commit()

    async def save_conversation(self, record: AgentConversationRecord) -> None:
        """Persist an agent conversation record to SQLite."""
        await self.init_db()
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO agent_conversations (
                    id, project_id, step_number, agent_id, system_prompt,
                    user_payload, raw_response, status, verdict, score,
                    culprit, duration_ms, estimated_tokens_in,
                    estimated_tokens_out, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    str(record.id),
                    record.project_id,
                    record.step_number,
                    record.agent_id.value,
                    record.system_prompt,
                    record.user_payload,
                    record.raw_response,
                    record.status.value,
                    record.verdict,
                    record.score,
                    record.culprit,
                    record.duration_ms,
                    record.estimated_tokens_in,
                    record.estimated_tokens_out,
                    record.created_at.isoformat(),
                ),
            )
            await db.commit()

    async def get_conversations(
        self,
        project_id: str,
        agent_id: AgentID | None = None,
    ) -> list[AgentConversationRecord]:
        """Retrieve stored conversations for a project, optionally filtered by agent."""
        await self.init_db()
        query = (
            "SELECT id, project_id, step_number, agent_id, system_prompt, "
            "user_payload, raw_response, status, verdict, score, culprit, "
            "duration_ms, estimated_tokens_in, estimated_tokens_out, created_at "
            "FROM agent_conversations WHERE project_id = ?"
        )
        params: list[str] = [project_id]
        if agent_id is not None:
            query += " AND agent_id = ?"
            params.append(agent_id.value)
        query += " ORDER BY step_number ASC, created_at ASC"

        records: list[AgentConversationRecord] = []
        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    records.append(
                        AgentConversationRecord(
                            id=UUID(row[0]),
                            project_id=row[1],
                            step_number=row[2],
                            agent_id=AgentID(row[3]),
                            system_prompt=row[4],
                            user_payload=row[5],
                            raw_response=row[6],
                            status=DeliverableStatus(row[7]),
                            verdict=row[8],
                            score=row[9],
                            culprit=row[10],
                            duration_ms=row[11],
                            estimated_tokens_in=row[12],
                            estimated_tokens_out=row[13],
                            created_at=row[14],
                        )
                    )
        return records

    async def save_email(self, email: AgentEmailRecord) -> None:
        """Persist an internal agent email to SQLite."""
        await self.init_db()
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO agent_emails (
                    id, project_id, step_number, sender, recipient,
                    cc, subject, body_summary, attached_deliverable_path,
                    priority, is_read, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    str(email.id),
                    email.project_id,
                    email.step_number,
                    email.sender,
                    email.recipient,
                    json.dumps(email.cc),
                    email.subject,
                    email.body_summary,
                    email.attached_deliverable_path,
                    email.priority,
                    1 if email.is_read else 0,
                    email.created_at.isoformat(),
                ),
            )
            await db.commit()

    async def get_emails(
        self,
        project_id: str,
        agent_id: AgentID | None = None,
        unread_only: bool = False,
    ) -> list[AgentEmailRecord]:
        """Query emails for a project with optional agent and unread filters."""
        await self.init_db()
        query = (
            "SELECT id, project_id, step_number, sender, recipient, cc, "
            "subject, body_summary, attached_deliverable_path, priority, "
            "is_read, created_at FROM agent_emails WHERE project_id = ?"
        )
        params: list[str | int] = [project_id]

        if agent_id is not None:
            agent_addr = f"%{agent_id.value}%"
            query += " AND (recipient LIKE ? OR sender LIKE ?)"
            params.extend([agent_addr, agent_addr])

        if unread_only:
            query += " AND is_read = 0"

        query += " ORDER BY step_number ASC, created_at ASC"

        emails: list[AgentEmailRecord] = []
        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    emails.append(
                        AgentEmailRecord(
                            id=UUID(row[0]),
                            project_id=row[1],
                            step_number=row[2],
                            sender=row[3],
                            recipient=row[4],
                            cc=cast(list[str], json.loads(row[5])),
                            subject=row[6],
                            body_summary=row[7],
                            attached_deliverable_path=row[8],
                            priority=cast(EmailPriority, row[9]),
                            is_read=bool(row[10]),
                            created_at=row[11],
                        )
                    )
        return emails

    async def get_email_by_id(self, email_id: UUID | str) -> AgentEmailRecord | None:
        """Find and return an email by its unique ID."""
        await self.init_db()
        str_id = str(email_id)
        query = (
            "SELECT id, project_id, step_number, sender, recipient, cc, "
            "subject, body_summary, attached_deliverable_path, priority, "
            "is_read, created_at FROM agent_emails WHERE id = ?"
        )
        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute(query, [str_id]) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                return AgentEmailRecord(
                    id=UUID(row[0]),
                    project_id=row[1],
                    step_number=row[2],
                    sender=row[3],
                    recipient=row[4],
                    cc=cast(list[str], json.loads(row[5])),
                    subject=row[6],
                    body_summary=row[7],
                    attached_deliverable_path=row[8],
                    priority=cast(EmailPriority, row[9]),
                    is_read=bool(row[10]),
                    created_at=row[11],
                )

    async def mark_emails_as_read(self, email_ids: list[UUID | str]) -> None:
        """Mark a list of email IDs as read."""
        if not email_ids:
            return
        await self.init_db()
        placeholders = ",".join("?" for _ in email_ids)
        str_ids = [str(eid) for eid in email_ids]
        query = f"UPDATE agent_emails SET is_read = 1 WHERE id IN ({placeholders})"
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(query, str_ids)
            await db.commit()
