"""Notion MCP synchronization service and local zero-config mirror adapter."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

NOTION_API_BASE_URL = "https://api.notion.com/v1"
NOTION_API_VERSION = "2022-06-28"
NOTION_MAX_TEXT_CHUNK = 2000
NOTION_MAX_BLOCKS_PER_REQUEST = 100

NOTION_LANGUAGES: dict[str, str] = {
    "python": "python",
    "py": "python",
    "php": "php",
    "bash": "bash",
    "sh": "bash",
    "shell": "shell",
    "yaml": "yaml",
    "yml": "yaml",
    "json": "json",
    "javascript": "javascript",
    "js": "javascript",
    "typescript": "typescript",
    "ts": "typescript",
    "html": "html",
    "css": "css",
    "sql": "sql",
    "dockerfile": "dockerfile",
    "markdown": "markdown",
    "md": "markdown",
    "ini": "plain text",
    "conf": "plain text",
}


def build_rich_text(content: str, max_chunk: int = NOTION_MAX_TEXT_CHUNK) -> list[dict[str, Any]]:
    """Split content into an array of rich_text objects of <= 2000 chars each."""
    if not content:
        return [{"type": "text", "text": {"content": ""}}]

    chunks: list[dict[str, Any]] = []
    for i in range(0, len(content), max_chunk):
        chunk_str = content[i : i + max_chunk]
        chunks.append({"type": "text", "text": {"content": chunk_str}})
    return chunks


def build_heading_1(text: str) -> dict[str, Any]:
    """Create a Notion heading_1 block."""
    return {
        "object": "block",
        "type": "heading_1",
        "heading_1": {"rich_text": build_rich_text(text)},
    }


def build_heading_2(text: str) -> dict[str, Any]:
    """Create a Notion heading_2 block."""
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": build_rich_text(text)},
    }


def build_heading_3(text: str) -> dict[str, Any]:
    """Create a Notion heading_3 block."""
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {"rich_text": build_rich_text(text)},
    }


def build_paragraph(text: str) -> dict[str, Any]:
    """Create a Notion paragraph block."""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": build_rich_text(text)},
    }


def build_bullet_item(text: str) -> dict[str, Any]:
    """Create a Notion bulleted_list_item block."""
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": build_rich_text(text)},
    }


def build_code_block(code: str, language: str = "plain text") -> list[dict[str, Any]]:
    """Create one or more Notion code blocks respecting rich_text chunk limits."""
    notion_lang = NOTION_LANGUAGES.get(language.lower().strip(), "plain text")
    rich_chunks = build_rich_text(code, max_chunk=NOTION_MAX_TEXT_CHUNK)

    # Notion permits maximum 100 text elements in a single rich_text array
    blocks: list[dict[str, Any]] = []
    for i in range(0, len(rich_chunks), 100):
        group = rich_chunks[i : i + 100]
        blocks.append(
            {
                "object": "block",
                "type": "code",
                "code": {
                    "language": notion_lang,
                    "rich_text": group,
                },
            }
        )
    return blocks


def build_callout(text: str, emoji: str = "💡") -> dict[str, Any]:
    """Create a Notion callout block with custom emoji icon."""
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": emoji},
            "rich_text": build_rich_text(text),
        },
    }


def build_divider() -> dict[str, Any]:
    """Create a Notion divider block."""
    return {
        "object": "block",
        "type": "divider",
        "divider": {},
    }


def markdown_to_notion_blocks(markdown_text: str) -> list[dict[str, Any]]:
    """Convert Markdown deliverable content into a list of Notion API blocks."""
    blocks: list[dict[str, Any]] = []

    # 1. Process and format YAML frontmatter if present
    content = markdown_text
    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", markdown_text, re.DOTALL)
    if frontmatter_match:
        fm_content = frontmatter_match.group(1).strip()
        blocks.append(
            build_callout(
                f"📋 CABECERA DE CONTROL AGENTOFFICE:\n{fm_content}",
                emoji="📋",
            )
        )
        content = markdown_text[frontmatter_match.end() :]

    # 2. Tokenize by fenced code blocks vs standard text
    pattern = re.compile(r"```([a-zA-Z0-9_\-./\\]*)\n(.*?)```", re.DOTALL)
    last_idx = 0

    for match in pattern.finditer(content):
        preceding = content[last_idx : match.start()]
        lang = match.group(1).strip()
        code = match.group(2)
        last_idx = match.end()

        # Parse preceding markdown prose
        _parse_markdown_prose(preceding, blocks)

        # Parse code block
        code_blocks = build_code_block(code, language=lang or "plain text")
        blocks.extend(code_blocks)

    remaining = content[last_idx:]
    _parse_markdown_prose(remaining, blocks)

    return blocks


def _parse_markdown_prose(text: str, blocks: list[dict[str, Any]]) -> None:
    """Helper converting prose lines (headings, bullets, dividers, paragraphs) to blocks."""
    lines = text.splitlines()
    buffer: list[str] = []

    def flush_buffer() -> None:
        if buffer:
            paragraph_text = "\n".join(buffer).strip()
            if paragraph_text:
                blocks.append(build_paragraph(paragraph_text))
            buffer.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_buffer()
            continue

        if stripped in ("---", "***", "___"):
            flush_buffer()
            blocks.append(build_divider())
        elif stripped.startswith("# "):
            flush_buffer()
            blocks.append(build_heading_1(stripped[2:].strip()))
        elif stripped.startswith("## "):
            flush_buffer()
            blocks.append(build_heading_2(stripped[3:].strip()))
        elif stripped.startswith("### "):
            flush_buffer()
            blocks.append(build_heading_3(stripped[4:].strip()))
        elif stripped.startswith("#### "):
            flush_buffer()
            blocks.append(build_heading_3(stripped[5:].strip()))
        elif stripped.startswith(("- ", "* ", "+ ")):
            flush_buffer()
            blocks.append(build_bullet_item(stripped[2:].strip()))
        elif stripped.startswith("> "):
            flush_buffer()
            blocks.append(build_callout(stripped[2:].strip(), emoji="💬"))
        else:
            buffer.append(line)

    flush_buffer()


@runtime_checkable
class KnowledgeSyncPort(Protocol):
    """Hexagonal port defining documentation and project hub synchronization."""

    async def create_project_hub(
        self,
        project_id: str,
        title: str,
        summary: str = "",
    ) -> str:
        """Create or initialize project main hub page and return its identifier."""
        ...

    async def append_deliverable_page(
        self,
        project_id: str,
        step_number: int,
        agent_id: str,
        deliverable_title: str,
        markdown_content: str,
    ) -> str:
        """Append an agent deliverable page under the project hub."""
        ...

    async def log_agent_email(
        self,
        project_id: str,
        email_data: dict[str, Any],
    ) -> str:
        """Record an internal agent email into the project hub."""
        ...

    async def update_project_status(
        self,
        project_id: str,
        status_data: dict[str, Any],
    ) -> None:
        """Update overall status, metrics, and progress in the project hub."""
        ...


class LocalNotionMirrorAdapter:
    """Zero-config offline adapter mirroring Notion hierarchy and exporting MCP payloads."""

    def __init__(self, workspaces_dir: Path | str | None = None) -> None:
        """Initialize local mirror adapter rooted in workspaces directory."""
        self.workspaces_dir = Path(workspaces_dir or settings.WORKSPACES_DIR)

    def _get_mirror_dir(self, project_id: str) -> Path:
        """Ensure and return the notion_mirror root directory for a project."""
        mirror_dir = self.workspaces_dir / project_id / "notion_mirror"
        (mirror_dir / "mcp_payloads" / "deliverables").mkdir(parents=True, exist_ok=True)
        (mirror_dir / "mcp_payloads" / "emails").mkdir(parents=True, exist_ok=True)
        return mirror_dir

    def _update_index(self, project_id: str) -> None:
        """Regenerate navigable INDEX.html and INDEX.md documentation files."""
        mirror_dir = self._get_mirror_dir(project_id)
        mcp_dir = mirror_dir / "mcp_payloads"

        hub_file = mcp_dir / "create_project_hub.json"
        hub_data: dict[str, Any] = {}
        if hub_file.exists():
            hub_data = json.loads(hub_file.read_text(encoding="utf-8"))

        deliv_files = sorted((mcp_dir / "deliverables").glob("*.json"))
        email_files = sorted((mcp_dir / "emails").glob("*.json"))

        status_file = mcp_dir / "project_status.json"
        status_data: dict[str, Any] = {}
        if status_file.exists():
            status_data = json.loads(status_file.read_text(encoding="utf-8"))

        # Build INDEX.md
        md_lines = [
            f"# Notion Knowledge Hub: {project_id}",
            f"**Título:** {hub_data.get('title', project_id)}  ",
            f"**Actualizado:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            f"**Estado:** `{status_data.get('current_status', 'ACTIVO')}`\n",
            "---",
            "## 📦 Entregables de los Agentes",
        ]
        for df in deliv_files:
            item = json.loads(df.read_text(encoding="utf-8"))
            stem = df.stem
            step = item.get("step_number", 0)
            agent = item.get("agent_id", "unknown")
            title = item.get("title", stem)
            blocks_count = len(item.get("notion_blocks", []))
            json_link = f"[JSON MCP](mcp_payloads/deliverables/{stem}.json)"
            md_link = f"[{title}](mcp_payloads/deliverables/{stem}.md)"
            md_lines.append(
                f"- **[Paso {step:02d} - {agent}]** {md_link} "
                f"(`{blocks_count}` bloques Notion) | {json_link}"
            )

        md_lines.extend(["\n---", "## 📬 Correos Internos Auditados"])
        for ef in email_files:
            em = json.loads(ef.read_text(encoding="utf-8"))
            subj = em.get("subject", "Sin Asunto")
            sender = em.get("sender", "-")
            recip = em.get("recipient", "-")
            prio = em.get("priority", "NORMAL")
            md_lines.append(
                f"- **[{prio}]** `{sender}` ➔ `{recip}`: *{subj}* "
                f"([Ver JSON](mcp_payloads/emails/{ef.name}))"
            )

        (mirror_dir / "INDEX.md").write_text("\n".join(md_lines), encoding="utf-8")

        # Build interactive INDEX.html
        proj_title = hub_data.get("title", project_id)
        proj_status = status_data.get("current_status", "SINCRONIZADO")
        proj_summary = hub_data.get(
            "summary",
            "Sincronización automatizada de la Factoría de Software.",
        )
        css_style = (
            "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', "
            "Roboto, sans-serif; margin: 0; padding: 24px; background: #0f172a; "
            "color: #f8fafc; line-height: 1.6; }\n"
            ".container { max-width: 1000px; margin: 0 auto; }\n"
            "h1 { color: #38bdf8; border-bottom: 2px solid #334155; padding-bottom: 12px; }\n"
            "h2 { color: #94a3b8; margin-top: 32px; }\n"
            ".card { background: #1e293b; border-radius: 8px; padding: 16px; "
            "margin-bottom: 16px; border: 1px solid #334155; }\n"
            ".badge { display: inline-block; padding: 4px 8px; border-radius: 4px; "
            "font-size: 12px; font-weight: bold; }\n"
            ".badge-ok { background: #065f46; color: #34d399; }\n"
            ".badge-prio { background: #831843; color: #f472b6; }\n"
            "a { color: #38bdf8; text-decoration: none; }\n"
            "a:hover { text-decoration: underline; }\n"
            "table { width: 100%; border-collapse: collapse; margin-top: 12px; }\n"
            "th, td { padding: 10px; border-bottom: 1px solid #334155; text-align: left; }\n"
            "th { color: #94a3b8; }\n"
        )
        html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Notion Knowledge Hub - {project_id}</title>
  <style>
{css_style}  </style>
</head>
<body>
  <div class="container">
    <h1>🚀 Notion Knowledge Hub &middot; {project_id}</h1>
    <div class="card">
      <p><strong>Proyecto:</strong> {project_id} &middot; <strong>Título:</strong> {proj_title}</p>
      <p><strong>Estado:</strong> <span class="badge badge-ok">{proj_status}</span></p>
      <p><strong>Resumen:</strong> {proj_summary}</p>
    </div>

    <h2>📦 Entregables de los Agentes ({len(deliv_files)})</h2>
    <div class="card">
      <table>
        <thead>
          <tr>
            <th>Paso</th><th>Agente</th><th>Entregable</th><th>Bloques</th><th>Payloads</th>
          </tr>
        </thead>
        <tbody>
"""
        for df in deliv_files:
            item = json.loads(df.read_text(encoding="utf-8"))
            step = item.get("step_number", 0)
            agent = item.get("agent_id", "unknown")
            title = item.get("title", df.stem)
            blocks_cnt = len(item.get("notion_blocks", []))
            json_href = f"mcp_payloads/deliverables/{df.stem}.json"
            md_href = f"mcp_payloads/deliverables/{df.stem}.md"
            html_content += f"""          <tr>
            <td><strong>{step:02d}</strong></td>
            <td><code>{agent}</code></td>
            <td>{title}</td>
            <td>{blocks_cnt} bloques</td>
            <td><a href="{json_href}">JSON MCP</a> &middot; <a href="{md_href}">MD</a></td>
          </tr>
"""
        html_content += f"""        </tbody>
      </table>
    </div>

    <h2>📬 Correos Internos Auditados ({len(email_files)})</h2>
    <div class="card">
      <table>
        <thead>
          <tr><th>Remitente</th><th>Destinatario</th><th>Prioridad</th><th>Asunto</th><th>Payload</th></tr>
        </thead>
        <tbody>
"""
        for ef in email_files:
            em = json.loads(ef.read_text(encoding="utf-8"))
            subj = em.get("subject", "Sin Asunto")
            sender = em.get("sender", "-")
            recip = em.get("recipient", "-")
            prio = em.get("priority", "NORMAL")
            html_content += f"""          <tr>
            <td><code>{sender}</code></td>
            <td><code>{recip}</code></td>
            <td><span class="badge badge-prio">{prio}</span></td>
            <td>{subj}</td>
            <td><a href="mcp_payloads/emails/{ef.name}">JSON</a></td>
          </tr>
"""
        html_content += """        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""
        (mirror_dir / "INDEX.html").write_text(html_content, encoding="utf-8")

    async def create_project_hub(
        self,
        project_id: str,
        title: str,
        summary: str = "",
    ) -> str:
        """Create the project hub local payload and register index."""
        mirror_dir = self._get_mirror_dir(project_id)
        blocks = [
            build_heading_1(f"Software Factory Hub: {title}"),
            build_callout(
                summary or f"Espacio central de conocimiento para el proyecto {project_id}.",
                emoji="🏛️",
            ),
            build_divider(),
        ]
        payload = {
            "tool": "create_project_hub",
            "project_id": project_id,
            "title": title,
            "summary": summary,
            "created_at": datetime.now(UTC).isoformat(),
            "notion_blocks": blocks,
        }
        target = mirror_dir / "mcp_payloads" / "create_project_hub.json"
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        self._update_index(project_id)
        return f"mirror://{project_id}/hub"

    async def append_deliverable_page(
        self,
        project_id: str,
        step_number: int,
        agent_id: str,
        deliverable_title: str,
        markdown_content: str,
    ) -> str:
        """Serialize deliverable Markdown into Notion blocks and store local MCP payload."""
        mirror_dir = self._get_mirror_dir(project_id)
        blocks = markdown_to_notion_blocks(markdown_content)

        payload = {
            "tool": "append_deliverable_page",
            "project_id": project_id,
            "step_number": step_number,
            "agent_id": agent_id,
            "title": deliverable_title,
            "timestamp": datetime.now(UTC).isoformat(),
            "total_blocks": len(blocks),
            "notion_blocks": blocks,
        }

        stem = f"step_{step_number:02d}_{agent_id}"
        json_target = mirror_dir / "mcp_payloads" / "deliverables" / f"{stem}.json"
        md_target = mirror_dir / "mcp_payloads" / "deliverables" / f"{stem}.md"

        json_target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        md_target.write_text(markdown_content, encoding="utf-8")

        self._update_index(project_id)
        return f"mirror://{project_id}/deliverables/{stem}"

    async def log_agent_email(
        self,
        project_id: str,
        email_data: dict[str, Any],
    ) -> str:
        """Store internal agent email payload and update navigable mirror."""
        mirror_dir = self._get_mirror_dir(project_id)
        email_id = str(email_data.get("id", datetime.now(UTC).timestamp()))

        blocks = [
            build_callout(
                f"✉️ DE: {email_data.get('sender')}\n"
                f"PARA: {email_data.get('recipient')}\n"
                f"ASUNTO: {email_data.get('subject')}\n"
                f"PRIORIDAD: {email_data.get('priority', 'NORMAL')}\n\n"
                f"{email_data.get('body_summary', '')}",
                emoji="✉️",
            ),
            build_divider(),
        ]

        payload = {
            "tool": "log_agent_email",
            "project_id": project_id,
            "email": email_data,
            "logged_at": datetime.now(UTC).isoformat(),
            "notion_blocks": blocks,
        }

        target = mirror_dir / "mcp_payloads" / "emails" / f"email_{email_id[:8]}.json"
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        self._update_index(project_id)
        return f"mirror://{project_id}/emails/{email_id[:8]}"

    async def update_project_status(
        self,
        project_id: str,
        status_data: dict[str, Any],
    ) -> None:
        """Store status update payload and refresh index."""
        mirror_dir = self._get_mirror_dir(project_id)
        payload = {
            "tool": "update_project_status",
            "project_id": project_id,
            "status": status_data,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        target = mirror_dir / "mcp_payloads" / "project_status.json"
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        self._update_index(project_id)


class NotionMCPAdapter:
    """Production Notion REST API adapter implementing KnowledgeSyncPort."""

    def __init__(
        self,
        api_key: str,
        parent_page_id: str | None = None,
        workspaces_dir: Path | str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize adapter with Notion credentials and optional HTTP client."""
        self.api_key = api_key
        self.parent_page_id = parent_page_id
        self.workspaces_dir = Path(workspaces_dir or settings.WORKSPACES_DIR)
        self._client = http_client
        self._hub_pages: dict[str, str] = {}
        self._mirror = LocalNotionMirrorAdapter(workspaces_dir=self.workspaces_dir)

    def _get_client(self) -> httpx.AsyncClient:
        """Obtain or instantiate an authenticated HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=NOTION_API_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Notion-Version": NOTION_API_VERSION,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        else:
            if "Authorization" not in self._client.headers:
                self._client.headers["Authorization"] = f"Bearer {self.api_key}"
            if "Notion-Version" not in self._client.headers:
                self._client.headers["Notion-Version"] = NOTION_API_VERSION
        return self._client

    async def close(self) -> None:
        """Close managed HTTP client session."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def create_project_hub(
        self,
        project_id: str,
        title: str,
        summary: str = "",
    ) -> str:
        """Create Notion parent page for the project and cache page ID."""
        await self._mirror.create_project_hub(project_id, title, summary)

        if not self.parent_page_id:
            logger.info(
                "NOTION_PARENT_PAGE_ID no configurado; operando con registro espejo para %s.",
                project_id,
            )
            fake_id = f"notion_hub_{project_id}"
            self._hub_pages[project_id] = fake_id
            return fake_id

        client = self._get_client()
        initial_blocks = [
            build_heading_1(f"Software Factory Hub: {title}"),
            build_callout(
                summary or f"Espacio central de conocimiento para el proyecto {project_id}.",
                emoji="🏛️",
            ),
            build_divider(),
        ]

        payload = {
            "parent": {"page_id": self.parent_page_id},
            "properties": {
                "title": {
                    "title": [
                        {
                            "type": "text",
                            "text": {"content": f"Project Hub: {project_id} - {title}"},
                        }
                    ]
                }
            },
            "children": initial_blocks[:NOTION_MAX_BLOCKS_PER_REQUEST],
        }

        resp = await client.post("/pages", json=payload)
        resp.raise_for_status()
        data = resp.json()
        page_id = str(data["id"])
        self._hub_pages[project_id] = page_id
        return page_id

    async def append_deliverable_page(
        self,
        project_id: str,
        step_number: int,
        agent_id: str,
        deliverable_title: str,
        markdown_content: str,
    ) -> str:
        """Create subpage under the hub and append blocks in chunks of <= 100 blocks."""
        await self._mirror.append_deliverable_page(
            project_id=project_id,
            step_number=step_number,
            agent_id=agent_id,
            deliverable_title=deliverable_title,
            markdown_content=markdown_content,
        )

        hub_id = self._hub_pages.get(project_id)
        if not hub_id:
            hub_id = await self.create_project_hub(
                project_id,
                title=f"Project {project_id}",
                summary="Generado automáticamente por AgentOffice",
            )

        if not self.parent_page_id:
            return f"notion_subpage_{project_id}_{step_number}"

        client = self._get_client()
        blocks = markdown_to_notion_blocks(markdown_content)

        # 1. Create subpage under hub page with initial chunk of blocks
        first_batch = blocks[:NOTION_MAX_BLOCKS_PER_REQUEST]
        page_title = f"[{step_number:02d}] {agent_id}: {deliverable_title}"

        subpage_payload = {
            "parent": {"page_id": hub_id},
            "properties": {
                "title": {
                    "title": [{"type": "text", "text": {"content": page_title[:2000]}}]
                }
            },
            "children": first_batch,
        }

        resp = await client.post("/pages", json=subpage_payload)
        resp.raise_for_status()
        subpage_id = str(resp.json()["id"])

        # 2. Append remaining blocks in batches of 100
        for i in range(NOTION_MAX_BLOCKS_PER_REQUEST, len(blocks), NOTION_MAX_BLOCKS_PER_REQUEST):
            batch = blocks[i : i + NOTION_MAX_BLOCKS_PER_REQUEST]
            patch_resp = await client.patch(
                f"/blocks/{subpage_id}/children",
                json={"children": batch},
            )
            patch_resp.raise_for_status()

        return subpage_id

    async def log_agent_email(
        self,
        project_id: str,
        email_data: dict[str, Any],
    ) -> str:
        """Append an email notification callout to the project hub."""
        await self._mirror.log_agent_email(project_id, email_data)

        hub_id = self._hub_pages.get(project_id)
        if not hub_id or not self.parent_page_id:
            return f"notion_email_{email_data.get('id', 'local')}"

        client = self._get_client()
        callout = build_callout(
            f"✉️ DE: {email_data.get('sender')}\n"
            f"PARA: {email_data.get('recipient')}\n"
            f"ASUNTO: {email_data.get('subject')}\n"
            f"PRIORIDAD: {email_data.get('priority', 'NORMAL')}\n\n"
            f"{email_data.get('body_summary', '')}",
            emoji="✉️",
        )

        resp = await client.patch(
            f"/blocks/{hub_id}/children",
            json={"children": [callout, build_divider()]},
        )
        resp.raise_for_status()
        return "notion_block_email"

    async def update_project_status(
        self,
        project_id: str,
        status_data: dict[str, Any],
    ) -> None:
        """Update project hub status callout or properties."""
        await self._mirror.update_project_status(project_id, status_data)

        hub_id = self._hub_pages.get(project_id)
        if not hub_id or not self.parent_page_id:
            return

        client = self._get_client()
        status_callout = build_callout(
            f"📊 ESTADO ACTUAL: {status_data.get('current_status', 'EN PROGRESO')}\n"
            f"PASOS COMPLETADOS: {status_data.get('steps_completed', '-')}\n"
            f"ÚLTIMA ACTUALIZACIÓN: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            emoji="📊",
        )
        try:
            await client.patch(
                f"/blocks/{hub_id}/children",
                json={"children": [status_callout]},
            )
        except Exception as exc:
            logger.warning("Fallo al actualizar estado en Notion para %s: %s", project_id, exc)


def get_knowledge_sync_adapter(
    workspaces_dir: Path | str | None = None,
    force_local: bool = False,
    http_client: httpx.AsyncClient | None = None,
) -> KnowledgeSyncPort:
    """Return NotionMCPAdapter if configured, otherwise fallback to LocalNotionMirrorAdapter."""
    if force_local or not settings.NOTION_API_KEY:
        return LocalNotionMirrorAdapter(workspaces_dir=workspaces_dir)

    return NotionMCPAdapter(
        api_key=settings.NOTION_API_KEY,
        parent_page_id=settings.NOTION_PARENT_PAGE_ID,
        workspaces_dir=workspaces_dir,
        http_client=http_client,
    )
