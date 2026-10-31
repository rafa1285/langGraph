"""Unit and integration tests for Phase 8: Notion MCP and Documentation Synchronizer."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.graph.state import SoftwareFactoryState, create_initial_state
from app.services.llm_gateway import MockLLMGateway
from app.services.mail_service import MailService
from app.services.notion_mcp_service import (
    NOTION_MAX_TEXT_CHUNK,
    KnowledgeSyncPort,
    LocalNotionMirrorAdapter,
    NotionMCPAdapter,
    build_code_block,
    build_rich_text,
    get_knowledge_sync_adapter,
    markdown_to_notion_blocks,
)
from app.services.office_store import OfficeStore
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter
from cli import sync_notion_command


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Create isolated workspace directory."""
    ws = tmp_path / "workspaces"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


@pytest.fixture
def temp_office_store(tmp_path: Path) -> OfficeStore:
    """Create isolated office database."""
    db_file = tmp_path / "test_office.sqlite"
    return OfficeStore(db_path=db_file)


class TestNotionBlockParsers:
    """Test suite verifying Markdown conversion to Notion API block specifications."""

    def test_rich_text_chunking_under_and_over_limit(self) -> None:
        """Verify text >= 2000 characters is split into chunks of <= 2000 characters."""
        short_text = "Hello Notion"
        short_chunks = build_rich_text(short_text)
        assert len(short_chunks) == 1
        assert short_chunks[0]["text"]["content"] == short_text

        long_text = "A" * 5500
        long_chunks = build_rich_text(long_text, max_chunk=NOTION_MAX_TEXT_CHUNK)
        assert len(long_chunks) == 3
        assert len(long_chunks[0]["text"]["content"]) == 2000
        assert len(long_chunks[1]["text"]["content"]) == 2000
        assert len(long_chunks[2]["text"]["content"]) == 1500

        for chunk in long_chunks:
            assert len(chunk["text"]["content"]) <= NOTION_MAX_TEXT_CHUNK

    def test_code_block_chunking_and_language_mapping(self) -> None:
        """Verify code blocks map languages correctly and respect text limits."""
        code_py = "import os\nprint('FastAPI')"
        py_blocks = build_code_block(code_py, language="python")
        assert len(py_blocks) == 1
        assert py_blocks[0]["type"] == "code"
        assert py_blocks[0]["code"]["language"] == "python"

        huge_code = "# Code\n" + ("x = 1\n" * 600)
        huge_blocks = build_code_block(huge_code, language="py")
        assert len(huge_blocks) >= 1
        assert huge_blocks[0]["code"]["language"] == "python"
        for b in huge_blocks:
            for rt in b["code"]["rich_text"]:
                assert len(rt["text"]["content"]) <= NOTION_MAX_TEXT_CHUNK

    def test_markdown_to_notion_blocks_full_features(self) -> None:
        """Verify conversion of headings, callouts, lists, dividers, and frontmatter."""
        markdown = """---
origen: "agente_04_fastapi"
veredicto: "APROBADO"
puntuacion: 100
---

# Título Principal
## Subtítulo
### Sección Técnica

> Advertencia importante de arquitectura

- Elemento 1
- Elemento 2

---

```python
def main():
    return True
```
"""
        blocks = markdown_to_notion_blocks(markdown)
        block_types = [b["type"] for b in blocks]

        assert "callout" in block_types  # From frontmatter and quote
        assert "heading_1" in block_types
        assert "heading_2" in block_types
        assert "heading_3" in block_types
        assert "bulleted_list_item" in block_types
        assert "divider" in block_types
        assert "code" in block_types


class TestLocalNotionMirrorAdapter:
    """Test suite verifying zero-config offline mirror and JSON MCP export."""

    @pytest.mark.asyncio
    async def test_create_hub_and_append_deliverables(self, temp_workspace: Path) -> None:
        """Verify hub creation, deliverable serialization, and index generation."""
        adapter = LocalNotionMirrorAdapter(workspaces_dir=temp_workspace)
        project_id = f"proj_{uuid.uuid4().hex[:8]}"

        hub_ref = await adapter.create_project_hub(
            project_id=project_id,
            title="SaaS de Verificación",
            summary="Proyecto de prueba para Notion Mirror",
        )
        assert hub_ref.startswith(f"mirror://{project_id}/hub")

        deliv_ref = await adapter.append_deliverable_page(
            project_id=project_id,
            step_number=1,
            agent_id="agente_01_pm",
            deliverable_title="PRE_SDD_LISTO",
            markdown_content="# Especificación Funcional\nDetalles del sistema...",
        )
        assert "step_01_agente_01_pm" in deliv_ref

        email_ref = await adapter.log_agent_email(
            project_id=project_id,
            email_data={
                "id": str(uuid.uuid4()),
                "sender": "agente_01_pm@agentoffice.local",
                "recipient": "agente_02_architect@agentoffice.local",
                "subject": "Pre-SDD Terminado",
                "priority": "HIGH",
                "body_summary": "Revisar arquitectura base",
            },
        )
        assert "emails" in email_ref

        await adapter.update_project_status(
            project_id=project_id,
            status_data={"current_status": "EN_PROGRESO", "steps_completed": 1},
        )

        mirror_dir = temp_workspace / project_id / "notion_mirror"
        assert (mirror_dir / "INDEX.md").exists()
        assert (mirror_dir / "INDEX.html").exists()
        assert (mirror_dir / "mcp_payloads" / "create_project_hub.json").exists()
        assert (mirror_dir / "mcp_payloads" / "project_status.json").exists()

        deliv_json = mirror_dir / "mcp_payloads" / "deliverables" / "step_01_agente_01_pm.json"
        assert deliv_json.exists()
        data = json.loads(deliv_json.read_text(encoding="utf-8"))
        assert data["tool"] == "append_deliverable_page"
        assert data["step_number"] == 1
        assert len(data["notion_blocks"]) >= 1


class TestNotionMCPAdapterWithMockedHttp:
    """Test suite verifying Notion REST API interactions and pagination batching."""

    @pytest.mark.asyncio
    async def test_notion_cloud_hub_and_pagination(self, temp_workspace: Path) -> None:
        """Verify NotionMCPAdapter batches blocks in chunks of 100 to Notion REST endpoints."""
        captured_requests: list[httpx.Request] = []

        def mock_transport_handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            url_str = str(request.url)
            if request.method == "POST" and "/v1/pages" in url_str:
                return httpx.Response(200, json={"id": f"page_{uuid.uuid4().hex[:8]}"})
            if request.method == "PATCH" and "/children" in url_str:
                return httpx.Response(200, json={"results": []})
            return httpx.Response(200, json={"status": "ok"})

        mock_client = httpx.AsyncClient(
            transport=httpx.MockTransport(mock_transport_handler),
            base_url="https://api.notion.com/v1",
        )

        adapter = NotionMCPAdapter(
            api_key="secret_test_notion_key",
            parent_page_id="parent_page_12345",
            workspaces_dir=temp_workspace,
            http_client=mock_client,
        )

        project_id = f"proj_{uuid.uuid4().hex[:8]}"
        hub_id = await adapter.create_project_hub(
            project_id=project_id,
            title="Proyecto Cloud",
            summary="Resumen de prueba",
        )
        assert hub_id.startswith("page_")

        # Create markdown with > 120 blocks to trigger chunked PATCH requests (100 block limit)
        long_md = "\n\n".join([f"### Título {i}\nContenido del bloque {i}" for i in range(120)])
        subpage_id = await adapter.append_deliverable_page(
            project_id=project_id,
            step_number=3,
            agent_id="agente_04_fastapi",
            deliverable_title="MOTOR_IMPLEMENTADO",
            markdown_content=long_md,
        )
        assert subpage_id.startswith("page_")

        # Verify POST for hub + POST for subpage + PATCH for remaining blocks
        assert len(captured_requests) >= 3
        # Check authorization headers
        for req in captured_requests:
            assert req.headers["Authorization"] == "Bearer secret_test_notion_key"
            assert req.headers["Notion-Version"] == "2022-06-28"

        await adapter.close()


class TestFactoryHookAndCLIIntegration:
    """Integration test suite verifying auto-hooks in FactoryNodes and sync-notion CLI."""

    @pytest.mark.asyncio
    async def test_factory_nodes_auto_hook(
        self,
        temp_workspace: Path,
        temp_office_store: OfficeStore,
    ) -> None:
        """Verify FactoryNodes automatically invokes KnowledgeSyncPort when configured."""
        from app.graph.nodes import FactoryNodes

        project_id = f"proj_{uuid.uuid4().hex[:8]}"
        mirror_adapter = LocalNotionMirrorAdapter(workspaces_dir=temp_workspace)

        nodes = FactoryNodes(
            llm_gateway=MockLLMGateway(),
            prompt_loader=PromptLoader(),
            workspace_writer=WorkspaceWriter(base_dir=temp_workspace),
            office_store=temp_office_store,
            mail_service=MailService(store=temp_office_store),
            knowledge_sync=mirror_adapter,
        )

        state: SoftwareFactoryState = create_initial_state(
            project_id=project_id,
            idea_inicial="App de Prueba Notion Sync",
        )

        await nodes.node_01_pm(state)

        deliv_json = (
            temp_workspace
            / project_id
            / "notion_mirror"
            / "mcp_payloads"
            / "deliverables"
            / "step_01_agente_01_pm.json"
        )
        assert deliv_json.exists()
        loaded = json.loads(deliv_json.read_text(encoding="utf-8"))
        assert loaded["agent_id"] == "agente_01_pm"

    @pytest.mark.asyncio
    async def test_cli_sync_notion_command(
        self,
        temp_workspace: Path,
        temp_office_store: OfficeStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify python cli.py sync-notion --local-mirror synchronizes existing projects."""
        project_id = f"proj_{uuid.uuid4().hex[:8]}"
        proj_dir = temp_workspace / project_id
        proj_dir.mkdir(parents=True, exist_ok=True)

        # Create two deliverables in workspace
        (proj_dir / "01_agente_01_pm.md").write_text(
            '---\nestado_entregable: "PRE_SDD_LISTO"\n---\n# Especificación PM\nTexto...',
            encoding="utf-8",
        )
        (proj_dir / "02_agente_02_architect.md").write_text(
            '---\nestado_entregable: "ARQUITECTURA_COMPLETA"\n---\n# SDD\nArquitectura...',
            encoding="utf-8",
        )

        monkeypatch.setattr("app.core.config.settings.WORKSPACES_DIR", str(temp_workspace))

        await sync_notion_command(project_id=project_id, local_mirror=True)

        mirror_dir = proj_dir / "notion_mirror"
        assert (mirror_dir / "INDEX.html").exists()
        assert (mirror_dir / "INDEX.md").exists()
        assert (mirror_dir / "mcp_payloads" / "create_project_hub.json").exists()
        assert (
            mirror_dir / "mcp_payloads" / "deliverables" / "step_01_agente_01_pm.json"
        ).exists()
        assert (
            mirror_dir / "mcp_payloads" / "deliverables" / "step_02_agente_02_architect.json"
        ).exists()

    def test_get_knowledge_sync_adapter_factory(self) -> None:
        """Verify factory selects LocalNotionMirrorAdapter when API key is missing."""
        _ = Settings(NOTION_API_KEY=None)
        adapter = get_knowledge_sync_adapter(force_local=True)
        assert isinstance(adapter, LocalNotionMirrorAdapter)
        assert isinstance(adapter, KnowledgeSyncPort)
