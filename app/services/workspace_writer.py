"""Workspace writer service for persisting agent deliverables asynchronously."""

import asyncio
from pathlib import Path

from app.core.config import settings
from app.schemas.routing import AgentID


class WorkspaceWriter:
    """Service to asynchronously persist project deliverables to workspaces."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        """Initialize the writer with an optional custom workspace base directory."""
        if base_dir is None:
            self.base_dir = Path(settings.WORKSPACES_DIR)
        else:
            self.base_dir = Path(base_dir)

    def _sync_save(
        self,
        project_id: str,
        step_number: int,
        agent_id: AgentID,
        content: str,
    ) -> str:
        """Synchronous write routine intended to be called inside asyncio.to_thread."""
        target_dir = self.base_dir / project_id
        target_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{step_number:02d}_{agent_id.value}.md"
        file_path = target_dir / filename
        file_path.write_text(content, encoding="utf-8")

        if file_path.is_absolute():
            try:
                return file_path.relative_to(Path.cwd()).as_posix()
            except ValueError:
                return (Path(self.base_dir.name) / project_id / filename).as_posix()

        return file_path.as_posix()

    async def save_deliverable(
        self,
        project_id: str,
        step_number: int,
        agent_id: AgentID,
        content: str,
    ) -> str:
        """Asynchronously save deliverable content to workspaces/{project_id}/{filename}."""
        return await asyncio.to_thread(
            self._sync_save,
            project_id,
            step_number,
            agent_id,
            content,
        )
