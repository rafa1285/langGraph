"""Offline automated tests for NotionDocsSyncService and Markdown-to-Notion block conversion."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.notion_docs_sync import (
    NotionDocsSyncService,
    extract_document_title,
    markdown_to_notion_blocks,
    normalize_code_language,
    split_text_chunks,
)


def test_normalize_code_language() -> None:
    """Verify normalization of code block languages and alias resolution."""
    assert normalize_code_language("python") == "python"
    assert normalize_code_language("py") == "python"
    assert normalize_code_language("mermaid") == "mermaid"
    assert normalize_code_language("dockerfile") == "docker"
    assert normalize_code_language("sh") == "bash"
    assert normalize_code_language("ps1") == "powershell"
    assert normalize_code_language("UNKNOWN_LANG_XYZ") == "plain text"
    assert normalize_code_language(None) == "plain text"


def test_split_text_chunks() -> None:
    """Verify that text chunking strictly respects max character limits."""
    short_text = "Texto breve"
    assert split_text_chunks(short_text, max_chars=100) == ["Texto breve"]

    long_text = "palabra " * 300
    chunks = split_text_chunks(long_text, max_chars=100)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 100


def test_extract_document_title() -> None:
    """Verify extraction of title from first H1 heading with fallback."""
    md = "# 📖 Manual de Prueba — AgentOffice\n\nContenido de prueba..."
    assert extract_document_title(md, "Fallback") == "📖 Manual de Prueba — AgentOffice"

    md_no_h1 = "## Subtítulo\n\nTexto..."
    assert extract_document_title(md_no_h1, "Fallback Title") == "Fallback Title"


def test_markdown_to_notion_blocks_conversion() -> None:
    """Verify comprehensive conversion from Markdown syntax to Notion block structures."""
    markdown_input = """---
version: 2.5
---

# Título Principal

Texto de introducción en párrafo.

## Subsección 1

> [!NOTE]
> Nota importante para el usuario.

- Elemento lista viñeta 1
- Elemento lista viñeta 2

1. Primer paso numerado
2. Segundo paso numerado

---

### Diagrama de Arquitectura

```mermaid
flowchart TD
    A[Inicio] --> B[Fin]
```

```python
def saludo() -> str:
    return "Hola"
```

| Parámetro | Tipo | Descripción |
| :--- | :--- | :--- |
| id | str | Identificador |
| activo | bool | Estado |
"""
    blocks = markdown_to_notion_blocks(markdown_input)

    types = [b["type"] for b in blocks]
    assert "callout" in types  # From frontmatter or alert
    assert "heading_1" in types
    assert "heading_2" in types
    assert "heading_3" in types
    assert "paragraph" in types
    assert "bulleted_list_item" in types
    assert "numbered_list_item" in types
    assert "divider" in types
    assert "code" in types
    assert "table" in types

    # Verify mermaid language preservation
    mermaid_blocks = [
        b for b in blocks
        if b["type"] == "code" and b.get("code", {}).get("language") == "mermaid"
    ]
    assert len(mermaid_blocks) == 1
    assert "flowchart TD" in mermaid_blocks[0]["code"]["rich_text"][0]["text"]["content"]


@pytest.mark.asyncio
async def test_notion_docs_sync_service_create_and_update(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify idempotent sync_document flow (create and update) with 100% offline mocks."""
    service = NotionDocsSyncService(
        api_key="secret_test_mock_token_12345",
        parent_page_id="test-parent-page-uuid",
    )

    # 1. Test creation when page does not exist
    mock_post_res = MagicMock()
    mock_post_res.status_code = 200
    mock_post_res.json.return_value = {
        "id": "new-page-id-9999",
        "url": "https://notion.so/new-page-id-9999",
    }

    mock_patch_res = MagicMock()
    mock_patch_res.status_code = 200
    mock_patch_res.json.return_value = {"results": []}

    mock_get_res = MagicMock()
    mock_get_res.status_code = 200
    mock_get_res.json.return_value = {"results": [], "has_more": False}

    with (
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch("httpx.AsyncClient.patch", new_callable=AsyncMock) as mock_patch,
        patch("httpx.AsyncClient.delete", new_callable=AsyncMock) as mock_del,
    ):
        mock_get.return_value = mock_get_res
        mock_post.return_value = mock_post_res
        mock_patch.return_value = mock_patch_res
        mock_del.return_value = MagicMock(status_code=200)

        # Sync new document
        res_create = await service.sync_document(
            title="Capítulo Nuevo",
            markdown_content="# Capítulo Nuevo\n\nContenido nuevo.",
            existing_child_pages={},
        )
        assert res_create["status"] == "created"
        assert res_create["page_id"] == "new-page-id-9999"
        mock_post.assert_called_once()

        # 2. Test update when page already exists
        existing_pages = {"Capítulo Nuevo": "existing-page-id-8888"}
        res_update = await service.sync_document(
            title="Capítulo Nuevo",
            markdown_content="# Capítulo Nuevo\n\nContenido actualizado.",
            existing_child_pages=existing_pages,
        )
        assert res_update["status"] == "updated"
        assert res_update["page_id"] == "existing-page-id-8888"
        mock_patch.assert_called()

        # 3. Test update when page has embedded Notion URL in markdown
        md_with_notion_url = (
            "# Capítulo Especial\n\n"
            "> [Ver página en Notion](https://app.notion.com/p/419be4dde97381a69a4cdd5cfdb670db?pvs=204)\n\n"
            "Texto explicativo..."
        )
        existing_pages_by_id = {"Otro Título": "419be4dd-e973-81a6-9a4c-dd5cfdb670db"}
        res_embedded = await service.sync_document(
            title="Capítulo Especial",
            markdown_content=md_with_notion_url,
            existing_child_pages=existing_pages_by_id,
        )
        assert res_embedded["status"] == "updated"
        assert "419be4dd" in res_embedded["page_id"]
