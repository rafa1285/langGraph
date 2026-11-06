"""Unit and integration tests for Phase 14: Extend-Agents command,

Notion/Strato IMAP mappings, and 10-artifact materialization.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.routing import AgentID
from app.services.backfill_service import (
    ProjectBackfillService,
    extend_project_with_new_agents,
    resolve_agent_id,
)
from app.services.notion_mcp_service import NotionMCPService, get_notion_agent_metadata
from app.services.office_store import OfficeStore
from app.services.real_mail_bridge import RealMailBridge, resolve_agent_imap_folder
from cli import extend_agents_command


@pytest.fixture(autouse=True)
def enable_mock_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure mock LLM gateway is always used during phase 14 tests."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "USE_MOCK_LLM", True)


@pytest.fixture
def clean_test_workspace(tmp_path: Path) -> Path:
    """Fixture providing an isolated temporary workspace directory."""
    ws = tmp_path / "workspaces"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


@pytest.fixture
def test_office_store(tmp_path: Path) -> OfficeStore:
    """Fixture providing an isolated SQLite OfficeStore."""
    db_path = tmp_path / "test_office_phase14.db"
    return OfficeStore(db_path=db_path)


def _seed_legacy_project_files(project_dir: Path) -> None:
    """Helper to populate a workspace directory with pre-existing legacy deliverables."""
    project_dir.mkdir(parents=True, exist_ok=True)

    # 01 PM
    (project_dir / "01_agente_01_pm.md").write_text(
        """---
origen: "agente_01_pm"
destino_siguiente: "agente_02_architect"
estado_entregable: "PRE_SDD_LISTO"
veredicto: "APROBADO"
puntuacion: 100
---

# Pre-SDD Funcional
## Idea Inicial del Proyecto
Micro-SaaS de validación de esquemas y saneamiento automatizado 100% Zero-Touch.
""",
        encoding="utf-8",
    )

    # 02 Architect
    (project_dir / "02_agente_02_architect.md").write_text(
        """---
origen: "agente_02_architect"
destino_siguiente: "agente_03_laravel, agente_04_fastapi"
estado_entregable: "APROBADO_PARA_DESARROLLO"
veredicto: "APROBADO"
puntuacion: 100
---

# SDD Arquitectura Técnica
## 1. Visión General
Arquitectura desacoplada Laravel 11 + FastAPI.
""",
        encoding="utf-8",
    )

    # 03 Laravel
    (project_dir / "03_agente_03_laravel.md").write_text(
        """---
origen: "agente_03_laravel"
destino_siguiente: "agente_05_qa_php"
estado_entregable: "IMPLEMENTADO_PARA_REVISION"
veredicto: "IMPLEMENTADO"
---

# Implementación Laravel
```php:app/Http/Controllers/ValidatorController.php
<?php
namespace App\\Http\\Controllers;
class ValidatorController {}
```
""",
        encoding="utf-8",
    )

    # 04 FastAPI
    (project_dir / "04_agente_04_fastapi.md").write_text(
        """---
origen: "agente_04_fastapi"
destino_siguiente: "agente_06_qa_python"
estado_entregable: "IMPLEMENTADO_PARA_REVISION"
veredicto: "IMPLEMENTADO"
---

# Implementación FastAPI
```python:api/main.py
from fastapi import FastAPI
app = FastAPI()
```
""",
        encoding="utf-8",
    )

    # 05 QA PHP
    (project_dir / "05_agente_05_qa_php.md").write_text(
        """---
origen: "agente_05_qa_php"
destino_siguiente: "qa_sync_barrier"
estado_entregable: "APROBADO_PARA_DESPLIEGUE"
veredicto: "APROBADO"
puntuacion: 100
---

# Reporte QA PHP
Aprobado sin observaciones.
""",
        encoding="utf-8",
    )

    # 06 QA Python
    (project_dir / "06_agente_06_qa_python.md").write_text(
        """---
origen: "agente_06_qa_python"
destino_siguiente: "qa_sync_barrier"
estado_entregable: "APROBADO_PARA_DESPLIEGUE"
veredicto: "APROBADO"
puntuacion: 100
---

# Reporte QA Python
Aprobado sin observaciones.
""",
        encoding="utf-8",
    )

    # 07 DevOps
    (project_dir / "07_agente_07_devops.md").write_text(
        """---
origen: "agente_07_devops"
destino_siguiente: "agente_10_ciso"
estado_entregable: "INFRAESTRUCTURA_LISTA_PARA_PRODUCCION"
veredicto: "APROBADO"
puntuacion: 100
---

# Infraestructura DevOps
```yaml:docker-compose.yml
services:
  app:
    image: validator:latest
```
""",
        encoding="utf-8",
    )

    # 10 CISO
    (project_dir / "10_agente_10_ciso.md").write_text(
        """---
origen: "agente_10_ciso"
destino_siguiente: "agente_08_docs"
estado_entregable: "BLINDADO_APTO_PRODUCCION"
veredicto: "APROBADO"
puntuacion: 100
---

# Dictamen CISO
Blindado sin vulnerabilidades críticas.
""",
        encoding="utf-8",
    )

    # 08 Docs
    (project_dir / "08_agente_08_docs.md").write_text(
        """---
origen: "agente_08_docs"
destino_siguiente: "agente_09_growth"
estado_entregable: "DOCUMENTACION_Y_RAG_LISTOS"
veredicto: "APROBADO"
puntuacion: 100
---

# Documentación Técnica
API Docs y especificación OpenAPI.
""",
        encoding="utf-8",
    )

    # 09 Growth (Legacy)
    (project_dir / "09_agente_09_growth.md").write_text(
        """---
origen: "agente_09_growth"
destino_siguiente: "end_pipeline"
estado_entregable: "CICLO_DE_SOFTWARE_COMPLETADO_100"
veredicto: "APROBADO"
puntuacion: 100
---

# Estrategia Growth Legacy
Plan preliminar de captación.
""",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_extend_existing_project_generates_all_10_artifacts(
    clean_test_workspace: Path,
    test_office_store: OfficeStore,
) -> None:
    """Verify extending a legacy project executes 5 new steps and materializes all 10 artifacts."""
    project_id = "proj_legacy_extend_test"
    project_dir = clean_test_workspace / project_id
    _seed_legacy_project_files(project_dir)

    service = ProjectBackfillService(
        workspaces_dir=clean_test_workspace,
        office_store=test_office_store,
    )

    result = await service.extend_project_with_new_agents(project_id)

    # 1. Verify result payload
    assert result["project_id"] == project_id
    assert result["status"] == "EXTENDED_OK"
    expected_nodes = [
        "agente_00_ceo_charter",
        "agente_11_ui_ux",
        "agente_12_marketing",
        "agente_13_sales_analytics",
        "agente_00_ceo_signoff",
    ]
    assert result["executed_nodes"] == expected_nodes

    build_dir = project_dir / "build"
    assert build_dir.exists() and build_dir.is_dir()

    # 2. Verify all 10 new artifacts exist physically in build/
    artifact_paths = [
        "config/business_charter.json",
        "config/release_manifest.json",
        "tailwind.config.js",
        "resources/css/design_tokens.css",
        "public/robots.txt",
        "public/sitemap.xml",
        "config/seo_metadata.json",
        "config/stripe_plans.json",
        "config/ai_sales_playbook.json",
        "database/analytics_schema.sql",
    ]

    for rel_path in artifact_paths:
        f_path = build_dir / rel_path
        assert f_path.exists(), f"Artefacto requerido {rel_path} no fue materializado en build/"
        content = f_path.read_text(encoding="utf-8").strip()
        assert len(content) > 0, f"Artefacto {rel_path} está vacío"

        # Validate clean JSON without syntax-breaking comments
        if rel_path.endswith(".json"):
            data = json.loads(content)
            assert isinstance(data, dict), f"JSON {rel_path} no es un diccionario válido"

        # Validate SQL schema
        if rel_path.endswith(".sql"):
            assert "CREATE TABLE" in content or "create table" in content.lower()

        # Validate CSS
        if rel_path.endswith(".css"):
            assert "--color-" in content or ":root" in content

        # Validate JS
        if rel_path.endswith(".js"):
            assert "module.exports" in content or "export default" in content

        # Validate XML
        if rel_path.endswith(".xml"):
            assert "<urlset" in content

        # Validate TXT
        if rel_path.endswith(".txt"):
            assert "User-agent:" in content

    # 3. Verify SQLite conversations and emails records were created for new agents
    convs = await test_office_store.get_conversations(project_id)
    conv_agents = {c.agent_id for c in convs}
    assert AgentID.AGENTE_00_CEO in conv_agents
    assert AgentID.AGENTE_11_UI_UX in conv_agents
    assert AgentID.AGENTE_12_MARKETING in conv_agents
    assert AgentID.AGENTE_13_SALES_ANALYTICS in conv_agents

    emails = await test_office_store.get_emails(project_id)
    senders = {e.sender for e in emails}
    assert (
        "ceo@agentoffice.local" in senders
        or "agente_00_ceo@agentoffice.local" in senders
    )
    assert "agente_11_ui_ux@agentoffice.local" in senders
    assert "agente_12_marketing@agentoffice.local" in senders
    assert "agente_13_sales_analytics@agentoffice.local" in senders


@pytest.mark.asyncio
async def test_cli_extend_agents_command(
    clean_test_workspace: Path,
    test_office_store: OfficeStore,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify CLI extend-agents execution command and user-facing output."""
    project_id = "proj_cli_extend_test"
    project_dir = clean_test_workspace / project_id
    _seed_legacy_project_files(project_dir)

    # Monkeypatch settings to point to clean_test_workspace
    from app.core.config import settings

    monkeypatch.setattr(settings, "WORKSPACES_DIR", str(clean_test_workspace))

    # Test error handling on non-existent project
    await extend_agents_command(project_id="non_existent_project")
    captured_err = capsys.readouterr()
    assert "[ERROR]" in captured_err.out

    # Test valid extension
    await extend_agents_command(project_id=project_id)
    captured = capsys.readouterr()
    assert "Extensión de Agentes Completada" in captured.out
    assert "agente_00_ceo_charter" in captured.out
    assert "agente_11_ui_ux" in captured.out
    assert "agente_12_marketing" in captured.out
    assert "agente_13_sales_analytics" in captured.out
    assert "agente_00_ceo_signoff" in captured.out
    assert "EXTENDED_OK" in captured.out

    # Verify build/ was created with artifacts
    build_dir = project_dir / "build"
    assert (build_dir / "config" / "business_charter.json").exists()
    assert (build_dir / "tailwind.config.js").exists()


def test_notion_and_mail_mappings_for_new_agents() -> None:
    """Verify metadata mappings in NotionMCPService and IMAP folder resolution in RealMailBridge."""
    # 1. Notion metadata for new agents and legacy
    ceo_meta = NotionMCPService.get_agent_metadata(AgentID.AGENTE_00_CEO)
    assert ceo_meta["icon"] == "👔"
    assert "CEO" in ceo_meta["title"]

    ui_meta = NotionMCPService.get_agent_metadata(AgentID.AGENTE_11_UI_UX)
    assert ui_meta["icon"] == "🎨"
    assert "UI/UX" in ui_meta["title"]

    mkt_meta = NotionMCPService.get_agent_metadata(AgentID.AGENTE_12_MARKETING)
    assert mkt_meta["icon"] == "📣"
    assert "Marketing" in mkt_meta["title"]

    sales_meta = NotionMCPService.get_agent_metadata(AgentID.AGENTE_13_SALES_ANALYTICS)
    assert sales_meta["icon"] == "📈"
    assert "Sales & BI" in sales_meta["title"]

    growth_meta = NotionMCPService.get_agent_metadata(AgentID.AGENTE_09_GROWTH)
    assert growth_meta["icon"] in ("🌱", "🚀")
    assert "Growth" in growth_meta["title"]

    # Also check string lookup helper
    assert get_notion_agent_metadata("agente_00_ceo")["icon"] == "👔"
    assert get_notion_agent_metadata("agente_11_ui_ux")["icon"] == "🎨"

    # 2. Strato IMAP folders resolution
    assert RealMailBridge.resolve_agent_imap_folder(AgentID.AGENTE_00_CEO) == "AgentOffice/00_CEO"
    assert resolve_agent_imap_folder("ceo") == "AgentOffice/00_CEO"
    assert resolve_agent_imap_folder("agente_00_ceo") == "AgentOffice/00_CEO"

    assert (
        RealMailBridge.resolve_agent_imap_folder(AgentID.AGENTE_11_UI_UX)
        == "AgentOffice/11_UI_UX"
    )
    assert resolve_agent_imap_folder("ui_ux") == "AgentOffice/11_UI_UX"
    assert resolve_agent_imap_folder("agente_11_ui_ux") == "AgentOffice/11_UI_UX"

    assert (
        RealMailBridge.resolve_agent_imap_folder(AgentID.AGENTE_12_MARKETING)
        == "AgentOffice/12_Marketing"
    )
    assert resolve_agent_imap_folder("marketing") == "AgentOffice/12_Marketing"
    assert resolve_agent_imap_folder("agente_12_marketing") == "AgentOffice/12_Marketing"

    assert (
        RealMailBridge.resolve_agent_imap_folder(AgentID.AGENTE_13_SALES_ANALYTICS)
        == "AgentOffice/13_Sales_Analytics"
    )
    assert resolve_agent_imap_folder("sales") == "AgentOffice/13_Sales_Analytics"
    assert resolve_agent_imap_folder("sales_analytics") == "AgentOffice/13_Sales_Analytics"
    assert (
        resolve_agent_imap_folder("agente_13_sales_analytics")
        == "AgentOffice/13_Sales_Analytics"
    )

    assert (
        RealMailBridge.resolve_agent_imap_folder(AgentID.AGENTE_09_GROWTH)
        == "AgentOffice/09_Growth"
    )


def test_agent_alias_resolution() -> None:
    """Verify alias mapping helper in BackfillService for canonical AgentIDs."""
    assert resolve_agent_id("00_ceo") == AgentID.AGENTE_00_CEO
    assert resolve_agent_id("ceo") == AgentID.AGENTE_00_CEO
    assert resolve_agent_id("11_ui_ux") == AgentID.AGENTE_11_UI_UX
    assert resolve_agent_id("ui_ux") == AgentID.AGENTE_11_UI_UX
    assert resolve_agent_id("12_marketing") == AgentID.AGENTE_12_MARKETING
    assert resolve_agent_id("marketing") == AgentID.AGENTE_12_MARKETING
    assert resolve_agent_id("13_sales_analytics") == AgentID.AGENTE_13_SALES_ANALYTICS
    assert resolve_agent_id("sales") == AgentID.AGENTE_13_SALES_ANALYTICS
    assert resolve_agent_id("qa_ui_ux") == AgentID.AGENTE_14_QA_UI_UX
    assert resolve_agent_id("14_qa_ui_ux") == AgentID.AGENTE_14_QA_UI_UX
    assert resolve_agent_id("agente_14_qa_ui_ux") == AgentID.AGENTE_14_QA_UI_UX
    assert resolve_agent_id("growth") == AgentID.AGENTE_09_GROWTH
    assert resolve_agent_id("pm") == AgentID.AGENTE_01_PM
    assert get_notion_agent_metadata("agente_14_qa_ui_ux")["icon"] == "🎯"
    assert resolve_agent_imap_folder("agente_14_qa_ui_ux") == "AgentOffice/14_QA_UI_UX"


@pytest.mark.asyncio
async def test_extend_project_with_real_mail_and_notion_sync(
    clean_test_workspace: Path,
    test_office_store: OfficeStore,
) -> None:
    """Verify extend_project_with_new_agents interacts with real_mail and notion sync ports."""
    project_id = "proj_sync_extend_test"
    project_dir = clean_test_workspace / project_id
    _seed_legacy_project_files(project_dir)

    mock_mail_bridge = MagicMock()
    mock_mail_bridge.sync_email_record = AsyncMock(return_value=True)

    mock_knowledge_sync = MagicMock()
    mock_knowledge_sync.create_project_hub = AsyncMock(return_value="https://notion.so/hub")
    mock_knowledge_sync.append_deliverable_page = AsyncMock(return_value="page_123")
    mock_knowledge_sync.log_agent_email = AsyncMock(return_value="email_123")
    mock_knowledge_sync.update_project_status = AsyncMock(return_value=True)

    res = await extend_project_with_new_agents(
        project_id=project_id,
        real_mail=True,
        sync_notion=True,
        workspaces_dir=clean_test_workspace,
        office_store=test_office_store,
        real_mail_bridge=mock_mail_bridge,
        knowledge_sync=mock_knowledge_sync,
    )

    assert res["status"] == "EXTENDED_OK"
    assert mock_knowledge_sync.create_project_hub.called
    assert mock_knowledge_sync.update_project_status.called
    assert mock_mail_bridge.sync_email_record.called
