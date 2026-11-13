"""WhatsApp session store backed by SQLite via aiosqlite."""

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import aiosqlite

from app.core.config import settings


class SessionPhase(StrEnum):
    """Lifecycle phases for a WhatsApp conversation session."""

    INTAKE = "INTAKE"
    BUILDING = "BUILDING"
    DEPLOYING = "DEPLOYING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class WhatsAppSessionStore:
    """Persist and retrieve WhatsApp conversation sessions in SQLite."""

    def __init__(self, db_path: str | None = None) -> None:
        """Initialise the store with an optional custom SQLite path.

        Falls back to ``settings.OFFICE_DB_PATH`` when *db_path* is omitted.
        """
        self._db_path: str = db_path if db_path is not None else settings.OFFICE_DB_PATH

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _ensure_table(self, db: aiosqlite.Connection) -> None:
        """Create the ``whatsapp_sessions`` table if it does not exist."""
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS whatsapp_sessions (
                phone_number       TEXT PRIMARY KEY,
                project_id         TEXT,
                phase              TEXT NOT NULL DEFAULT 'INTAKE',
                conversation_history TEXT NOT NULL DEFAULT '[]',
                intake_answers     TEXT NOT NULL DEFAULT '{}',
                created_at         TEXT NOT NULL,
                updated_at         TEXT NOT NULL
            )
            """
        )
        await db.commit()

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def get_session(self, phone: str) -> dict[str, Any] | None:
        """Return the session for *phone*, or ``None`` if it does not exist.

        ``conversation_history`` and ``intake_answers`` are returned as parsed
        Python objects (list and dict respectively).
        """
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_table(db)
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM whatsapp_sessions WHERE phone_number = ?",
                (phone,),
            ) as cursor:
                row = await cursor.fetchone()

        if row is None:
            return None

        result: dict[str, Any] = dict(row)
        result["conversation_history"] = json.loads(result["conversation_history"])
        result["intake_answers"] = json.loads(result["intake_answers"])
        return result

    async def upsert_session(
        self,
        phone: str,
        project_id: str | None = None,
        phase: str = "INTAKE",
        conversation_history: list[dict[str, str]] | None = None,
        intake_answers: dict[str, str] | None = None,
    ) -> None:
        """Insert or update the session row for *phone*.

        Uses an ``INSERT … ON CONFLICT DO UPDATE`` pattern so that the
        ``created_at`` column is preserved on subsequent updates.
        """
        now: str = datetime.now(UTC).isoformat()
        history_json: str = json.dumps(
            conversation_history if conversation_history is not None else []
        )
        answers_json: str = json.dumps(
            intake_answers if intake_answers is not None else {}
        )

        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_table(db)
            await db.execute(
                """
                INSERT INTO whatsapp_sessions
                    (phone_number, project_id, phase,
                     conversation_history, intake_answers,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(phone_number) DO UPDATE SET
                    project_id           = excluded.project_id,
                    phase                = excluded.phase,
                    conversation_history = excluded.conversation_history,
                    intake_answers       = excluded.intake_answers,
                    updated_at           = excluded.updated_at
                """,
                (
                    phone,
                    project_id,
                    phase,
                    history_json,
                    answers_json,
                    now,
                    now,
                ),
            )
            await db.commit()

    async def delete_session(self, phone: str) -> None:
        """Remove the session for *phone* if it exists."""
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_table(db)
            await db.execute(
                "DELETE FROM whatsapp_sessions WHERE phone_number = ?",
                (phone,),
            )
            await db.commit()
