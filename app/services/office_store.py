"""Persistent SQLite storage for agent conversations, internal emails, and telemetry."""

import json
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import aiosqlite

from app.core.config import settings
from app.schemas.brownfield import AuditReport
from app.schemas.chat import ChatTurn
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
            await db.execute("PRAGMA journal_mode = WAL;")
            await db.execute("PRAGMA synchronous = NORMAL;")
            await db.execute("PRAGMA busy_timeout = 5000;")
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
                    is_visible INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                """
            )
            # Ensure is_visible column exists on existing databases
            async with db.execute("PRAGMA table_info(agent_conversations);") as cur:
                existing_cols = [r[1] for r in await cur.fetchall()]
                if "is_visible" not in existing_cols:
                    await db.execute("ALTER TABLE agent_conversations ADD COLUMN is_visible INTEGER NOT NULL DEFAULT 1;")
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
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    project_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_session "
                "ON chat_sessions(session_id, created_at);"
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS brownfield_audits (
                    project_id TEXT PRIMARY KEY,
                    repo_url TEXT NOT NULL,
                    branch TEXT NOT NULL,
                    depth TEXT NOT NULL,
                    health_score INTEGER NOT NULL,
                    report_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_bf_status "
                "ON brownfield_audits(status, created_at);"
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
                    estimated_tokens_out, is_visible, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                    record.is_visible,
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
            "duration_ms, estimated_tokens_in, estimated_tokens_out, created_at, "
            "COALESCE(is_visible, 1) "
            "FROM agent_conversations WHERE project_id = ?"
        )
        params: list[str] = [project_id]
        if agent_id is not None:
            query += " AND agent_id = ?"
            params.append(agent_id.value)
        query += " ORDER BY created_at ASC, step_number ASC"

        records: list[AgentConversationRecord] = []
        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    try:
                        rec_id = UUID(str(row[0]))
                    except (ValueError, TypeError):
                        import uuid as _uuid
                        rec_id = _uuid.uuid4()

                    try:
                        aid = AgentID(row[3])
                    except ValueError:
                        aid = AgentID.AGENTE_00_CEO

                    try:
                        st_val = DeliverableStatus(row[7])
                    except ValueError:
                        st_val = DeliverableStatus.PENDIENTE

                    records.append(
                        AgentConversationRecord(
                            id=rec_id,
                            project_id=row[1],
                            step_number=row[2],
                            agent_id=aid,
                            system_prompt=row[4],
                            user_payload=row[5],
                            raw_response=row[6],
                            status=st_val,
                            verdict=row[8],
                            score=row[9],
                            culprit=row[10],
                            duration_ms=row[11],
                            estimated_tokens_in=row[12],
                            estimated_tokens_out=row[13],
                            created_at=row[14],
                            is_visible=int(row[15]),
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
        recipient: str | None = None,
        sender: str | None = None,
        priority: EmailPriority | None = None,
        unread_only: bool = False,
    ) -> list[AgentEmailRecord]:
        """Query emails for a project with optional filters for recipient, sender, and priority."""
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

        if recipient is not None:
            query += " AND recipient LIKE ?"
            params.append(f"%{recipient}%")

        if sender is not None:
            query += " AND sender LIKE ?"
            params.append(f"%{sender}%")

        if priority is not None:
            query += " AND priority = ?"
            params.append(priority)

        if unread_only:
            query += " AND is_read = 0"

        query += " ORDER BY created_at ASC, step_number ASC"

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

    async def get_all_projects_summary(self) -> dict[str, dict[str, Any]]:
        """Retrieve aggregated telemetry and latest status per project from SQLite."""
        await self.init_db()
        telemetry_query = (
            "SELECT project_id, COUNT(id), COALESCE(SUM(duration_ms), 0), "
            "COALESCE(SUM(estimated_tokens_in), 0), COALESCE(SUM(estimated_tokens_out), 0), "
            "MAX(created_at) FROM agent_conversations WHERE is_visible = 1 GROUP BY project_id"
        )
        status_query = (
            "SELECT project_id, status FROM agent_conversations WHERE is_visible = 1 "
            "ORDER BY created_at ASC, step_number ASC"
        )
        email_projects_query = (
            "SELECT DISTINCT project_id FROM agent_emails "
            "WHERE project_id IN (SELECT DISTINCT project_id FROM agent_conversations WHERE is_visible = 1)"
        )

        summaries: dict[str, dict[str, Any]] = {}
        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute(telemetry_query) as cursor:
                for row in await cursor.fetchall():
                    summaries[row[0]] = {
                        "project_id": row[0],
                        "steps_completed": row[1],
                        "total_duration_ms": row[2],
                        "total_tokens_in": row[3],
                        "total_tokens_out": row[4],
                        "updated_at": row[5] or "",
                        "current_status": "COMPLETED",
                    }
            async with db.execute(status_query) as cursor:
                for row in await cursor.fetchall():
                    pid, st = row[0], row[1]
                    if pid in summaries:
                        prev = summaries[pid].get("current_status")
                        if prev in ("LANZAMIENTO_AUTORIZADO", "CICLO_DE_SOFTWARE_COMPLETADO_100") and st not in (
                            "LANZAMIENTO_AUTORIZADO",
                            "CICLO_DE_SOFTWARE_COMPLETADO_100",
                        ):
                            continue
                        summaries[pid]["current_status"] = st
            async with db.execute(email_projects_query) as cursor:
                for row in await cursor.fetchall():
                    pid = row[0]
                    if pid not in summaries:
                        summaries[pid] = {
                            "project_id": pid,
                            "steps_completed": 0,
                            "total_duration_ms": 0,
                            "total_tokens_in": 0,
                            "total_tokens_out": 0,
                            "updated_at": "",
                            "current_status": "PENDIENTE",
                        }
            try:
                bf_query = "SELECT project_id, repo_url, status, updated_at FROM brownfield_audits"
                async with db.execute(bf_query) as cursor:
                    for row in await cursor.fetchall():
                        pid = row[0]
                        if pid not in summaries:
                            summaries[pid] = {
                                "project_id": pid,
                                "steps_completed": 1,
                                "total_duration_ms": 0,
                                "total_tokens_in": 0,
                                "total_tokens_out": 0,
                                "updated_at": row[3] or "",
                                "current_status": row[2] or "AUDITED",
                                "project_name": row[1],
                            }
            except Exception:
                pass
        return summaries

    async def save_chat_turn(
        self,
        turn_id: str,
        session_id: str,
        agent_id: str,
        project_id: str | None,
        role: str,
        content: str,
    ) -> None:
        """Persist a single chat turn to SQLite."""
        await self.init_db()
        from datetime import UTC, datetime

        created_at = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT INTO chat_sessions (
                    id, session_id, agent_id, project_id, role, content, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (turn_id, session_id, agent_id, project_id, role, content, created_at),
            )
            await db.commit()

    async def get_chat_history(
        self, session_id: str, limit: int = 50
    ) -> list[ChatTurn]:
        """Retrieve turns for a chat session, ordered chronologically (oldest first)."""
        await self.init_db()
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT id, session_id, agent_id, project_id, role, content, created_at
                FROM chat_sessions
                WHERE session_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (session_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            ChatTurn(
                id=str(row["id"]),
                session_id=str(row["session_id"]),
                agent_id=str(row["agent_id"]),
                project_id=row["project_id"],
                role=str(row["role"]),
                content=str(row["content"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    async def save_audit_report(self, report: AuditReport) -> None:
        """Persist or update an executive brownfield audit report."""
        await self.init_db()
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO brownfield_audits (
                    project_id, repo_url, branch, depth, health_score,
                    report_json, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.project_id,
                    report.repo_url,
                    report.branch,
                    report.depth,
                    report.health_score,
                    report.model_dump_json(),
                    report.status,
                    report.created_at,
                    report.updated_at,
                ),
            )
            await db.commit()

    async def get_audit_report(self, project_id: str) -> AuditReport | None:
        """Retrieve a saved brownfield audit report by its project_id."""
        await self.init_db()
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT report_json FROM brownfield_audits WHERE project_id = ?
                """,
                (project_id,),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        return AuditReport.model_validate_json(row["report_json"])

    async def update_audit_status(self, project_id: str, new_status: str) -> None:
        """Update audit report status (e.g. pending_approval -> approved | rejected)."""
        report = await self.get_audit_report(project_id)
        if report is None:
            raise KeyError(f"Informe de auditoría para '{project_id}' no encontrado.")

        from datetime import UTC, datetime

        now_iso = datetime.now(UTC).isoformat()
        updated_report = report.model_copy(
            update={"status": new_status, "updated_at": now_iso}
        )
        await self.save_audit_report(updated_report)
