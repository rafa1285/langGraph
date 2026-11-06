"""Service for hot file editing, unified diff computation, and safe workspace file writes."""

from __future__ import annotations

import asyncio
import difflib
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.schemas.file_edit import (
    FileEditConfirmResponse,
    FileEditProposal,
    FileEditRejectResponse,
    FileEditRequest,
    ProjectFileContent,
    ProjectFileInfo,
)
from app.schemas.routing import AgentID
from app.services.llm_gateway import LLMGatewayProtocol
from app.services.office_store import OfficeStore
from app.services.prompt_loader import PromptLoader

_IGNORED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".backups",
    "node_modules",
    ".idea",
    ".vscode",
}


def _extract_code(raw_response: str) -> tuple[str, str]:
    """Extract full code and explanation from LLM output.

    If triple backticks are present, selects the largest code block.
    """
    pattern = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
    matches = list(pattern.finditer(raw_response))
    if matches:
        largest_match = max(matches, key=lambda m: len(m.group(1)))
        code = largest_match.group(1)
        explanation = raw_response[: largest_match.start()].strip()
        return code, explanation
    return raw_response.strip(), ""


class FileEditService:
    """Manages hot file modifications with diff preview and approval workflow."""

    def __init__(
        self,
        workspaces_dir: Path | str | None = None,
        llm_gateway: LLMGatewayProtocol | None = None,
        prompt_loader: PromptLoader | None = None,
        office_store: OfficeStore | None = None,
    ) -> None:
        self.workspaces_dir = Path(workspaces_dir or settings.WORKSPACES_DIR)
        self._llm = llm_gateway
        self._prompt_loader = prompt_loader
        self._store = office_store
        self._pending_proposals: dict[str, FileEditProposal] = {}

    def _resolve_safe_path(self, project_id: str, file_path: str) -> Path:
        """Resolve path and verify it stays strictly inside the project workspace."""
        workspace_root = (self.workspaces_dir / project_id).resolve()
        target_path = (workspace_root / file_path).resolve()
        if not target_path.is_relative_to(workspace_root):
            raise ValueError(
                f"Acceso denegado: la ruta '{file_path}' está fuera del workspace del proyecto."
            )
        return target_path

    async def list_workspace_files(self, project_id: str) -> list[ProjectFileInfo]:
        """List all accessible files in the project workspace."""

        def _scan() -> list[ProjectFileInfo]:
            root = (self.workspaces_dir / project_id).resolve()
            if not root.exists() or not root.is_dir():
                return []

            files: list[ProjectFileInfo] = []
            for path in root.rglob("*"):
                # Check if path contains any ignored directory components
                rel_parts = path.relative_to(root).parts
                if any(ignored in rel_parts for ignored in _IGNORED_DIRS):
                    continue

                if path.is_file():
                    stat = path.stat()
                    mod_iso = datetime.fromtimestamp(stat.st_mtime, UTC).isoformat()
                    files.append(
                        ProjectFileInfo(
                            path=path.relative_to(root).as_posix(),
                            size=stat.st_size,
                            is_dir=False,
                            last_modified=mod_iso,
                        )
                    )
            return sorted(files, key=lambda f: f.path)

        return await asyncio.to_thread(_scan)

    async def read_file_content(
        self, project_id: str, file_path: str
    ) -> ProjectFileContent:
        """Read full text content of a workspace file."""
        target_path = self._resolve_safe_path(project_id, file_path)

        def _read() -> tuple[str, int]:
            if not target_path.exists() or not target_path.is_file():
                raise FileNotFoundError(
                    f"El archivo '{file_path}' no existe en el proyecto '{project_id}'."
                )
            text = target_path.read_text(encoding="utf-8", errors="replace")
            return text, target_path.stat().st_size

        content, size = await asyncio.to_thread(_read)
        return ProjectFileContent(
            project_id=project_id,
            file_path=file_path,
            content=content,
            size=size,
        )

    async def propose_file_edit(
        self, agent_id: AgentID, request: FileEditRequest
    ) -> FileEditProposal:
        """Generate a modified file proposal and unified diff via agent LLM invocation."""
        if self._llm is None or self._prompt_loader is None:
            raise RuntimeError(
                "LLMGateway y PromptLoader son requeridos para proponer ediciones."
            )

        target_path = self._resolve_safe_path(request.project_id, request.file_path)

        def _get_original() -> str:
            if target_path.exists() and target_path.is_file():
                return target_path.read_text(encoding="utf-8", errors="replace")
            return ""

        original_content = await asyncio.to_thread(_get_original)
        agent_system_prompt = await self._prompt_loader.load_prompt(agent_id)

        edit_system_prompt = (
            f"{agent_system_prompt}\n\n"
            "=== MODO EDICIÓN DE ARCHIVOS EN CALIENTE ===\n"
            f"Estás actuando como {agent_id.value} modificando un archivo del proyecto.\n"
            "NO incluyas bloque YAML de enrutamiento.\n"
            "Devuelve el archivo COMPLETO y DEFINITIVO listo para guardar en disco.\n"
            "Debes encerrar el contenido del archivo en un bloque de código markdown "
            "con triple comilla e indicar el lenguaje (ej: ```python o ```php).\n"
            "Si deseas agregar una breve explicación de lo modificado, "
            "escríbela antes del bloque de código."
        )

        user_payload = (
            f"=== ARCHIVO A MODIFICAR ===\n"
            f"Ruta: {request.file_path}\n\n"
            f"=== CONTENIDO ACTUAL ===\n"
            f"{original_content if original_content else '(Archivo nuevo o vacío)'}\n\n"
            f"=== INSTRUCCIÓN DEL USUARIO ===\n"
            f"{request.instruction}"
        )

        raw_llm_response = await self._llm.invoke_agent(
            agent_id=agent_id,
            system_prompt=edit_system_prompt,
            user_payload=user_payload,
        )

        proposed_code, explanation = _extract_code(raw_llm_response)

        orig_lines = original_content.splitlines(keepends=True)
        prop_lines = proposed_code.splitlines(keepends=True)
        diff_lines = list(
            difflib.unified_diff(
                orig_lines,
                prop_lines,
                fromfile=f"a/{request.file_path}",
                tofile=f"b/{request.file_path}",
            )
        )
        diff_text = "".join(diff_lines)
        if not diff_text:
            diff_text = f"# Sin cambios detectados en {request.file_path}"

        edit_token = str(uuid4())
        proposal = FileEditProposal(
            edit_token=edit_token,
            agent_id=agent_id.value,
            project_id=request.project_id,
            file_path=request.file_path,
            original_content=original_content,
            proposed_content=proposed_code,
            diff=diff_text,
            explanation=explanation or "Modificación propuesta según las instrucciones.",
        )

        self._pending_proposals[edit_token] = proposal
        return proposal

    async def apply_file_edit(self, edit_token: str) -> FileEditConfirmResponse:
        """Confirm and write the proposed file edit to disk, creating a backup."""
        proposal = self._pending_proposals.get(edit_token)
        if proposal is None:
            raise ValueError(
                f"Propuesta de edición '{edit_token}' no encontrada o ya expiró."
            )

        target_path = self._resolve_safe_path(proposal.project_id, proposal.file_path)

        def _write() -> str | None:
            backup_rel: str | None = None
            # Create backup if original exists
            if target_path.exists() and target_path.is_file():
                backup_dir = (
                    self.workspaces_dir / proposal.project_id / ".backups"
                ).resolve()
                backup_dir.mkdir(parents=True, exist_ok=True)
                timestamp_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
                safe_name = proposal.file_path.replace("/", "_").replace("\\", "_")
                backup_file = backup_dir / f"{safe_name}.{timestamp_str}.bak"
                backup_file.write_text(proposal.original_content, encoding="utf-8")
                backup_rel = (
                    backup_file.relative_to(
                        (self.workspaces_dir / proposal.project_id).resolve()
                    )
                ).as_posix()

            # Ensure parent directories exist
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(proposal.proposed_content, encoding="utf-8")
            return backup_rel

        backup_path = await asyncio.to_thread(_write)

        # Log into chat session if store is available
        if self._store is not None:
            session_id = str(uuid4())
            await self._store.save_chat_turn(
                turn_id=str(uuid4()),
                session_id=session_id,
                agent_id=proposal.agent_id,
                project_id=proposal.project_id,
                role="user",
                content=f"[SOLICITUD EDICIÓN] Modificar {proposal.file_path}",
            )
            await self._store.save_chat_turn(
                turn_id=str(uuid4()),
                session_id=session_id,
                agent_id=proposal.agent_id,
                project_id=proposal.project_id,
                role="agent",
                content=(
                    f"✓ Archivo `{proposal.file_path}` modificado y guardado correctamente.\n"
                    f"```diff\n{proposal.diff}\n```"
                ),
            )

        del self._pending_proposals[edit_token]

        return FileEditConfirmResponse(
            success=True,
            message=f"Archivo '{proposal.file_path}' actualizado correctamente.",
            project_id=proposal.project_id,
            file_path=proposal.file_path,
            backup_path=backup_path,
        )

    async def reject_file_edit(self, edit_token: str) -> FileEditRejectResponse:
        """Reject and discard a pending file edit proposal."""
        if edit_token in self._pending_proposals:
            del self._pending_proposals[edit_token]
            return FileEditRejectResponse(
                success=True,
                message="Propuesta de edición descartada con éxito.",
                edit_token=edit_token,
            )
        return FileEditRejectResponse(
            success=False,
            message="La propuesta no existía o ya fue procesada.",
            edit_token=edit_token,
        )
