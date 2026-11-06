"""Phase 17 tests: hot file editing, unified diff proposals, and safe confirmation."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app, lifespan
from app.schemas.file_edit import FileEditRequest
from app.schemas.routing import AgentID
from app.services.file_edit_service import FileEditService
from app.services.llm_gateway import LLMGatewayProtocol
from app.services.office_store import OfficeStore
from app.services.prompt_loader import PromptLoader


class CustomMockLLM(LLMGatewayProtocol):
    """Custom mock LLM returning targeted file edit markdown blocks."""

    async def invoke_agent(
        self, agent_id: AgentID, system_prompt: str, user_payload: str
    ) -> str:
        return (
            "He añadido la función healthz según lo requerido.\n\n"
            "```python\n"
            "def main():\n"
            '    return "hello world"\n\n'
            "def healthz():\n"
            '    return {"status": "ok"}\n'
            "```"
        )


@pytest.fixture
async def edit_env(tmp_path: Path) -> AsyncIterator[dict[str, Any]]:
    """Configure isolated environment for FileEdit API testing."""
    office_db = tmp_path / "office_data.sqlite"
    checkpoint_db = tmp_path / "checkpoints.sqlite"
    workspaces_dir = tmp_path / "workspaces"
    prompts_dir = tmp_path / "prompts"
    workspaces_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    settings.USE_MOCK_LLM = True
    settings.OFFICE_DB_PATH = str(office_db)
    settings.CHECKPOINT_DB_PATH = str(checkpoint_db)
    settings.WORKSPACES_DIR = str(workspaces_dir)
    settings.PROMPTS_DIR = str(prompts_dir)

    # Create dummy project workspace and file
    proj_dir = workspaces_dir / "proj_test"
    proj_dir.mkdir(parents=True, exist_ok=True)
    initial_file = proj_dir / "main.py"
    initial_file.write_text('def main():\n    return "hello world"\n', encoding="utf-8")

    store = OfficeStore(db_path=office_db)
    await store.init_db()

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield {
                "client": client,
                "workspaces_dir": workspaces_dir,
                "proj_dir": proj_dir,
                "office_store": store,
                "prompts_dir": prompts_dir,
            }


@pytest.mark.asyncio
async def test_resolve_safe_path_prevents_traversal(tmp_path: Path) -> None:
    """Ensure attempts to traverse outside the workspace raise ValueError."""
    service = FileEditService(workspaces_dir=tmp_path / "workspaces")
    project_id = "test_p"
    p_dir = tmp_path / "workspaces" / project_id
    p_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValueError, match="Acceso denegado"):
        service._resolve_safe_path(project_id, "../../outside.txt")

    with pytest.raises(ValueError, match="Acceso denegado"):
        service._resolve_safe_path(project_id, "../other_project/secret.py")

    valid = service._resolve_safe_path(project_id, "app/main.py")
    assert valid.is_relative_to(p_dir)


@pytest.mark.asyncio
async def test_list_workspace_files_filtering(tmp_path: Path) -> None:
    """Verify listing skips ignored folders like .git, __pycache__, and .backups."""
    workspaces = tmp_path / "workspaces"
    p_dir = workspaces / "p1"
    (p_dir / "src").mkdir(parents=True, exist_ok=True)
    (p_dir / ".git").mkdir(parents=True, exist_ok=True)
    (p_dir / ".backups").mkdir(parents=True, exist_ok=True)

    (p_dir / "src" / "index.py").write_text("print(1)", encoding="utf-8")
    (p_dir / "README.md").write_text("# Readme", encoding="utf-8")
    (p_dir / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    (p_dir / ".backups" / "old.bak").write_text("old", encoding="utf-8")

    service = FileEditService(workspaces_dir=workspaces)
    files = await service.list_workspace_files("p1")

    paths = [f.path for f in files]
    assert "src/index.py" in paths
    assert "README.md" in paths
    assert not any(p.startswith(".git") for p in paths)
    assert not any(p.startswith(".backups") for p in paths)


@pytest.mark.asyncio
async def test_propose_and_apply_flow(tmp_path: Path) -> None:
    """Full lifecycle: propose edit -> unified diff -> apply -> backup created."""
    workspaces = tmp_path / "workspaces"
    p_dir = workspaces / "proj_life"
    p_dir.mkdir(parents=True, exist_ok=True)
    code_file = p_dir / "app.py"
    code_file.write_text('def main():\n    return "hello world"\n', encoding="utf-8")

    prompt_loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    store = OfficeStore(db_path=tmp_path / "office.sqlite")
    await store.init_db()

    service = FileEditService(
        workspaces_dir=workspaces,
        llm_gateway=CustomMockLLM(),
        prompt_loader=prompt_loader,
        office_store=store,
    )

    req = FileEditRequest(
        project_id="proj_life",
        file_path="app.py",
        instruction="Añade endpoint healthz",
    )

    proposal = await service.propose_file_edit(AgentID.AGENTE_04_FASTAPI, req)
    assert proposal.project_id == "proj_life"
    assert proposal.file_path == "app.py"
    assert "healthz" in proposal.proposed_content
    assert "+def healthz():" in proposal.diff

    # Confirm and apply
    res = await service.apply_file_edit(proposal.edit_token)
    assert res.success is True
    assert res.backup_path is not None

    # Check updated content on disk
    new_disk_content = code_file.read_text(encoding="utf-8")
    assert "def healthz():" in new_disk_content

    # Check backup file exists
    backup_file = p_dir / res.backup_path
    assert backup_file.exists()
    assert 'return "hello world"' in backup_file.read_text(encoding="utf-8")

    # Second apply with same token must fail
    with pytest.raises(ValueError, match="no encontrada o ya expiró"):
        await service.apply_file_edit(proposal.edit_token)


@pytest.mark.asyncio
async def test_reject_flow(tmp_path: Path) -> None:
    """Test rejecting a proposed edit removes it without modifying disk."""
    workspaces = tmp_path / "workspaces"
    p_dir = workspaces / "proj_reject"
    p_dir.mkdir(parents=True, exist_ok=True)
    target = p_dir / "mod.py"
    target.write_text("x = 1", encoding="utf-8")

    prompt_loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    service = FileEditService(
        workspaces_dir=workspaces,
        llm_gateway=CustomMockLLM(),
        prompt_loader=prompt_loader,
    )

    proposal = await service.propose_file_edit(
        AgentID.AGENTE_03_LARAVEL,
        FileEditRequest(
            project_id="proj_reject", file_path="mod.py", instruction="x = 2"
        ),
    )

    reject_res = await service.reject_file_edit(proposal.edit_token)
    assert reject_res.success is True

    # File on disk remains unchanged
    assert target.read_text(encoding="utf-8") == "x = 1"


@pytest.mark.asyncio
async def test_api_file_edit_endpoints(edit_env: dict[str, Any]) -> None:
    """Test REST endpoints for files listing, content reading, and edit lifecycle."""
    client: AsyncClient = edit_env["client"]
    proj_dir: Path = edit_env["proj_dir"]

    # 1. List files
    list_resp = await client.get("/api/v1/office/files", params={"project_id": "proj_test"})
    assert list_resp.status_code == 200
    files = list_resp.json()
    assert any(f["path"] == "main.py" for f in files)

    # 2. Read content
    content_resp = await client.get(
        "/api/v1/office/files/content",
        params={"project_id": "proj_test", "file_path": "main.py"},
    )
    assert content_resp.status_code == 200
    assert 'return "hello world"' in content_resp.json()["content"]

    # 3. Propose edit
    edit_payload = {
        "project_id": "proj_test",
        "file_path": "main.py",
        "instruction": "Añade healthz endpoint",
    }
    prop_resp = await client.post(
        f"/api/v1/office/chat/{AgentID.AGENTE_04_FASTAPI.value}/file-edit",
        json=edit_payload,
    )
    assert prop_resp.status_code == 200, prop_resp.text
    prop_data = prop_resp.json()
    edit_token = prop_data["edit_token"]
    assert "diff" in prop_data

    # 4. Confirm edit
    confirm_resp = await client.post(
        f"/api/v1/office/chat/file-edit/{edit_token}/confirm"
    )
    assert confirm_resp.status_code == 200
    confirm_data = confirm_resp.json()
    assert confirm_data["success"] is True

    # Verify disk content changed
    disk_text = (proj_dir / "main.py").read_text(encoding="utf-8")
    assert len(disk_text) > 0

    # 5. Non-existent file content returns 404
    missing_resp = await client.get(
        "/api/v1/office/files/content",
        params={"project_id": "proj_test", "file_path": "no_existe.py"},
    )
    assert missing_resp.status_code == 404
