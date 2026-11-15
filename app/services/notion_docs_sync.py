"""Service for converting Markdown manuals into native Notion blocks and syncing live."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

NOTION_API_BASE_URL = "https://api.notion.com/v1"
NOTION_API_VERSION = "2022-06-28"
NOTION_MAX_TEXT_CHUNK = 2000
NOTION_MAX_BLOCKS_PER_BATCH = 100

SUPPORTED_CODE_LANGUAGES: set[str] = {
    "abap", "arduino", "bash", "basic", "c", "clojure", "coffeescript", "cpp",
    "csharp", "css", "dart", "diff", "docker", "elixir", "elm", "erlang",
    "flow", "fortran", "fsharp", "gherkin", "glsl", "go", "graphql", "groovy",
    "haskell", "html", "java", "javascript", "json", "julia", "kotlin", "latex",
    "less", "lisp", "livescript", "lua", "makefile", "markdown", "markup",
    "matlab", "mermaid", "nix", "objective-c", "ocaml", "pascal", "perl", "php",
    "plain text", "powershell", "prolog", "protobuf", "python", "r", "reason",
    "ruby", "rust", "sass", "scala", "scheme", "scss", "shell", "sql", "swift",
    "typescript", "vb.net", "verilog", "vhdl", "visual basic", "webassembly",
    "xml", "yaml",
}

LANGUAGE_ALIAS_MAP: dict[str, str] = {
    "dockerfile": "docker",
    "sh": "bash",
    "zsh": "bash",
    "ps1": "powershell",
    "yml": "yaml",
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "text": "plain text",
    "txt": "plain text",
}


def normalize_code_language(lang: str | None) -> str:
    """Normalize language identifier for Notion code blocks."""
    if not lang:
        return "plain text"
    cleaned = lang.strip().lower()
    mapped = LANGUAGE_ALIAS_MAP.get(cleaned, cleaned)
    if mapped in SUPPORTED_CODE_LANGUAGES:
        return mapped
    return "plain text"


def split_text_chunks(text: str, max_chars: int = NOTION_MAX_TEXT_CHUNK) -> list[str]:
    """Split text into chunks smaller than max_chars without breaking mid-word when possible."""
    if not text:
        return [""]
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        split_idx = remaining.rfind("\n", 0, max_chars)
        if split_idx == -1:
            split_idx = remaining.rfind(" ", 0, max_chars)
        if split_idx == -1:
            split_idx = max_chars

        chunks.append(remaining[:split_idx].strip())
        remaining = remaining[split_idx:].lstrip()

    if remaining:
        chunks.append(remaining)
    return chunks


def build_rich_text(text: str) -> list[dict[str, Any]]:
    """Build a list of Notion rich text objects from a string, splitting if necessary."""
    chunks = split_text_chunks(text, max_chars=NOTION_MAX_TEXT_CHUNK)
    elements: list[dict[str, Any]] = []
    for c in chunks:
        if c:
            elements.append({"type": "text", "text": {"content": c}})
    if not elements:
        elements.append({"type": "text", "text": {"content": ""}})
    return elements


def extract_document_title(markdown_content: str, fallback_title: str) -> str:
    """Extract document title from the first level-1 markdown heading."""
    for line in markdown_content.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("# "):
            raw_title = trimmed[2:].strip()
            # Remove leading markdown links if formatted like # [Title](...)
            return raw_title
    return fallback_title


def markdown_to_notion_blocks(markdown_text: str) -> list[dict[str, Any]]:
    """Parse Markdown text into a list of Notion block objects."""
    blocks: list[dict[str, Any]] = []

    # 1. Process frontmatter if present
    content = markdown_text
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", markdown_text, re.DOTALL)
    if fm_match:
        fm_content = fm_match.group(1).strip()
        blocks.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": "📋"},
                "rich_text": build_rich_text(f"METADATOS AGENTOFFICE:\n{fm_content}"),
            },
        })
        content = markdown_text[fm_match.end() :]

    # 2. Tokenize by code blocks
    code_pattern = re.compile(r"```([a-zA-Z0-9_\-./\\]*)\n(.*?)```", re.DOTALL)
    last_idx = 0

    for match in code_pattern.finditer(content):
        preceding = content[last_idx : match.start()]
        lang = match.group(1).strip()
        code_text = match.group(2)
        last_idx = match.end()

        # Parse preceding prose
        _parse_markdown_lines(preceding, blocks)

        # Append code block
        normalized_lang = normalize_code_language(lang)
        # Notion permits max 100 rich text elements per code block
        rich_chunks = build_rich_text(code_text)
        for i in range(0, len(rich_chunks), 100):
            blocks.append({
                "object": "block",
                "type": "code",
                "code": {
                    "language": normalized_lang,
                    "rich_text": rich_chunks[i : i + 100],
                },
            })

    # Remaining text after last code block
    remaining = content[last_idx:]
    _parse_markdown_lines(remaining, blocks)

    return blocks


def _parse_markdown_lines(text: str, blocks: list[dict[str, Any]]) -> None:
    """Parse prose markdown lines into headings, lists, quotes, dividers, tables, and paragraphs."""
    lines = text.split("\n")
    i = 0
    total = len(lines)

    while i < total:
        line = lines[i]
        trimmed = line.strip()

        if not trimmed:
            i += 1
            continue

        # Check for Horizontal Divider
        if re.match(r"^(?:---|\*\*\*|___)$", trimmed):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue

        # Check for Headings
        if trimmed.startswith("### "):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": build_rich_text(trimmed[4:].strip())},
            })
            i += 1
            continue
        if trimmed.startswith("## "):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": build_rich_text(trimmed[3:].strip())},
            })
            i += 1
            continue
        if trimmed.startswith("# "):
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {"rich_text": build_rich_text(trimmed[2:].strip())},
            })
            i += 1
            continue

        # Check for Blockquotes / Callouts
        if trimmed.startswith("> "):
            quote_lines: list[str] = [trimmed[2:].strip()]
            i += 1
            while i < total and lines[i].strip().startswith("> "):
                quote_lines.append(lines[i].strip()[2:].strip())
                i += 1
            quote_text = "\n".join(quote_lines)

            # Detect callouts with alerts
            if quote_text.startswith("[!NOTE]") or quote_text.startswith("[!TIP]"):
                clean_body = re.sub(r"^\[!(?:NOTE|TIP)\]\s*", "", quote_text)
                blocks.append({
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "icon": {"type": "emoji", "emoji": "💡"},
                        "rich_text": build_rich_text(clean_body),
                    },
                })
            elif (
                quote_text.startswith("[!IMPORTANT]")
                or quote_text.startswith("[!WARNING]")
                or quote_text.startswith("[!CAUTION]")
            ):
                clean_body = re.sub(r"^\[!(?:IMPORTANT|WARNING|CAUTION)\]\s*", "", quote_text)
                blocks.append({
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "icon": {"type": "emoji", "emoji": "⚠️"},
                        "rich_text": build_rich_text(clean_body),
                    },
                })
            else:
                blocks.append({
                    "object": "block",
                    "type": "quote",
                    "quote": {"rich_text": build_rich_text(quote_text)},
                })
            continue

        # Check for Bulleted List
        if re.match(r"^[-*+]\s+", trimmed):
            item_text = re.sub(r"^[-*+]\s+", "", trimmed)
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": build_rich_text(item_text)},
            })
            i += 1
            continue

        # Check for Numbered List
        if re.match(r"^\d+\.\s+", trimmed):
            item_text = re.sub(r"^\d+\.\s+", "", trimmed)
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": build_rich_text(item_text)},
            })
            i += 1
            continue

        # Check for Markdown Table
        if trimmed.startswith("|") and trimmed.endswith("|"):
            table_lines: list[str] = [trimmed]
            i += 1
            while i < total and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                table_lines.append(lines[i].strip())
                i += 1

            parsed_table = _parse_markdown_table(table_lines)
            if parsed_table:
                blocks.append(parsed_table)
            else:
                # Fallback to code block if table is malformed
                blocks.append({
                    "object": "block",
                    "type": "code",
                    "code": {
                        "language": "plain text",
                        "rich_text": build_rich_text("\n".join(table_lines)),
                    },
                })
            continue

        # Standard Paragraph: accumulate contiguous non-empty lines
        para_lines: list[str] = [trimmed]
        i += 1
        while (
            i < total
            and lines[i].strip()
            and not lines[i].strip().startswith(("#", ">", "|", "---", "***"))
            and not re.match(r"^[-*+]\s+", lines[i].strip())
            and not re.match(r"^\d+\.\s+", lines[i].strip())
        ):
            para_lines.append(lines[i].strip())
            i += 1

        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": build_rich_text(" ".join(para_lines))},
        })


def _parse_markdown_table(table_lines: list[str]) -> dict[str, Any] | None:
    """Parse Markdown table lines into a native Notion table block."""
    if len(table_lines) < 2:
        return None

    rows: list[list[str]] = []
    for line in table_lines:
        # Check if delimiter line (e.g. | :--- | :--- |)
        if re.match(r"^\|(?:\s*:?-+:?\s*\|)+$", line.strip()):
            continue
        cells = [c.strip() for c in line.strip().split("|")[1:-1]]
        rows.append(cells)

    if not rows:
        return None

    col_count = max(len(r) for r in rows)
    if col_count == 0:
        return None

    # Standardize row lengths to col_count
    table_children: list[dict[str, Any]] = []
    for r in rows:
        padded = r + [""] * (col_count - len(r))
        table_children.append({
            "type": "table_row",
            "table_row": {
                "cells": [build_rich_text(cell) for cell in padded[:col_count]]
            },
        })

    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": col_count,
            "has_column_header": True,
            "has_row_header": False,
            "children": table_children,
        },
    }


class NotionDocsSyncService:
    """Asynchronous service to synchronize local Markdown documentation with Notion pages."""

    def __init__(
        self,
        api_key: str | None = None,
        parent_page_id: str | None = None,
    ) -> None:
        """Initialize service with explicit or settings credentials."""
        self.api_key = api_key or settings.NOTION_API_KEY or ""
        self.parent_page_id = (
            parent_page_id
            or settings.NOTION_PARENT_PAGE_ID
            or ""
        ).replace("-", "")

    def _get_headers(self) -> dict[str, str]:
        """Construct secure authorization headers."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": NOTION_API_VERSION,
            "Content-Type": "application/json",
        }

    async def list_child_pages(self, parent_id: str | None = None) -> dict[str, str]:
        """List all child pages under the parent page, returning {normalized_title: page_id}."""
        pid = (parent_id or self.parent_page_id).replace("-", "")
        if not pid or not self.api_key:
            return {}

        headers = self._get_headers()
        url = f"{NOTION_API_BASE_URL}/blocks/{pid}/children"
        child_pages: dict[str, str] = {}
        has_more = True
        next_cursor: str | None = None

        async with httpx.AsyncClient(timeout=15.0) as client:
            while has_more:
                params: dict[str, Any] = {"page_size": 100}
                if next_cursor:
                    params["start_cursor"] = next_cursor

                res = await client.get(url, headers=headers, params=params)
                if res.status_code != 200:
                    logger.warning(
                        "Error listing Notion child blocks: %s - %s",
                        res.status_code,
                        res.text[:200],
                    )
                    break

                data = res.json()
                for b in data.get("results", []):
                    if b.get("type") == "child_page":
                        title = b.get("child_page", {}).get("title", "")
                        page_id = b.get("id", "")
                        if title and page_id:
                            child_pages[title.strip()] = page_id

                has_more = data.get("has_more", False)
                next_cursor = data.get("next_cursor")

        return child_pages

    async def clear_page_blocks(self, page_id: str) -> int:
        """Archive all existing child blocks inside a page to prepare for idempotent overwrite."""
        pid = page_id.replace("-", "")
        headers = self._get_headers()
        deleted_count = 0

        async with httpx.AsyncClient(timeout=15.0) as client:
            url = f"{NOTION_API_BASE_URL}/blocks/{pid}/children"
            res = await client.get(url, headers=headers, params={"page_size": 100})
            if res.status_code != 200:
                return 0

            blocks = res.json().get("results", [])
            for b in blocks:
                block_id = b.get("id")
                if block_id:
                    del_res = await client.delete(
                        f"{NOTION_API_BASE_URL}/blocks/{block_id}",
                        headers=headers,
                    )
                    if del_res.status_code == 200:
                        deleted_count += 1
                    # Brief throttle to prevent Notion 429
                    await asyncio.sleep(0.05)

        return deleted_count

    async def append_blocks_in_batches(
        self,
        page_id: str,
        blocks: list[dict[str, Any]],
    ) -> int:
        """Append blocks in batches of maximum 100 blocks per request."""
        pid = page_id.replace("-", "")
        headers = self._get_headers()
        url = f"{NOTION_API_BASE_URL}/blocks/{pid}/children"
        total_appended = 0

        async with httpx.AsyncClient(timeout=15.0) as client:
            for i in range(0, len(blocks), NOTION_MAX_BLOCKS_PER_BATCH):
                batch = blocks[i : i + NOTION_MAX_BLOCKS_PER_BATCH]
                res = await client.patch(url, headers=headers, json={"children": batch})
                if res.status_code in (200, 201):
                    total_appended += len(batch)
                else:
                    logger.error(
                        "Failed to append batch to Notion page %s: %s - %s",
                        page_id,
                        res.status_code,
                        res.text[:300],
                    )
                # Respect Notion rate limits
                await asyncio.sleep(0.1)

        return total_appended

    async def sync_document(
        self,
        title: str,
        markdown_content: str,
        parent_id: str | None = None,
        existing_child_pages: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Idempotently sync a single Markdown document to Notion."""
        pid = (parent_id or self.parent_page_id).replace("-", "")
        if not self.api_key or not pid:
            raise ValueError("NOTION_API_KEY y NOTION_PARENT_PAGE_ID son obligatorios.")

        headers = self._get_headers()
        blocks = markdown_to_notion_blocks(markdown_content)

        # 1. Check if document already exists
        child_pages = existing_child_pages or await self.list_child_pages(pid)
        target_page_id: str | None = None

        # Look for exact or normalized title match
        norm_target = title.strip().lower()
        for existing_title, existing_id in child_pages.items():
            norm_existing = existing_title.strip().lower()
            if norm_existing == norm_target:
                target_page_id = existing_id
                break
            # Match by chapter indicator only if key topic terms also match
            ch_match = re.search(r"cap[ií]tulo\s+(\d+)", norm_target)
            if ch_match:
                ch_num = ch_match.group(1)
                ch_label = f"capítulo {ch_num}"
                alt_label = f"capitulo {ch_num}"
                if ch_label in norm_existing or alt_label in norm_existing:
                    ignore_words = {"capitulo", "manual", "usuario", "agentoffice"}
                    target_words = set(re.findall(r"\w{4,}", norm_target)) - ignore_words
                    existing_words = set(re.findall(r"\w{4,}", norm_existing)) - ignore_words
                    if target_words & existing_words:
                        target_page_id = existing_id
                        break

        action = "updated"
        page_url = ""

        async with httpx.AsyncClient(timeout=15.0) as client:
            if target_page_id:
                # Update existing page
                logger.info("Updating existing Notion page '%s' (ID: %s)", title, target_page_id)
                await self.clear_page_blocks(target_page_id)
                await self.append_blocks_in_batches(target_page_id, blocks)
                clean_id = target_page_id.replace('-', '')
                page_url = f"https://notion.so/{clean_id}"
            else:
                # Create brand new child page
                logger.info("Creating new Notion page '%s' under parent %s", title, pid)
                create_payload: dict[str, Any] = {
                    "parent": {"page_id": pid},
                    "properties": {
                        "title": {
                            "title": [{"type": "text", "text": {"content": title}}]
                        }
                    },
                    # Include first batch of blocks directly in creation
                    "children": blocks[:NOTION_MAX_BLOCKS_PER_BATCH],
                }
                res = await client.post(
                    f"{NOTION_API_BASE_URL}/pages",
                    headers=headers,
                    json=create_payload,
                )
                if res.status_code not in (200, 201):
                    err_msg = res.text[:300]
                    raise RuntimeError(
                        f"Error creating Notion page '{title}': HTTP {res.status_code} - {err_msg}"
                    )
                data = res.json()
                target_page_id = str(data.get("id", ""))
                clean_id = target_page_id.replace('-', '')
                page_url = str(data.get("url", f"https://notion.so/{clean_id}"))
                action = "created"

                # Append remaining blocks if total > 100
                if len(blocks) > NOTION_MAX_BLOCKS_PER_BATCH:
                    remaining_blocks = blocks[NOTION_MAX_BLOCKS_PER_BATCH:]
                    await self.append_blocks_in_batches(target_page_id, remaining_blocks)

        return {
            "title": title,
            "page_id": target_page_id,
            "url": page_url,
            "status": action,
            "blocks_count": len(blocks),
        }

    async def sync_all_docs(
        self,
        docs_dir: Path | str,
        extra_files: list[Path | str] | None = None,
    ) -> list[dict[str, Any]]:
        """Scan documentation directory and sync all manuals plus extra files to Notion."""
        d_dir = Path(docs_dir)
        files_to_sync: list[Path] = []

        if d_dir.exists():
            files_to_sync.extend(sorted(d_dir.glob("*.md")))

        if extra_files:
            for ef in extra_files:
                p = Path(ef)
                if p.exists() and p not in files_to_sync:
                    files_to_sync.append(p)

        existing_pages = await self.list_child_pages()
        results: list[dict[str, Any]] = []

        for f in files_to_sync:
            try:
                content = f.read_text(encoding="utf-8")
                title = extract_document_title(content, fallback_title=f.stem)
                res = await self.sync_document(
                    title=title,
                    markdown_content=content,
                    existing_child_pages=existing_pages,
                )
                results.append(res)
                # Keep tracking updated pages
                if res.get("page_id"):
                    existing_pages[title] = str(res["page_id"])
            except Exception as err:
                logger.error("Failed to sync file %s to Notion: %s", f.name, err)
                results.append({"file": f.name, "error": str(err)})

        return results
