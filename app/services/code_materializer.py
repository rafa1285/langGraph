"""Code materializer service extracting production files from Markdown deliverables."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.schemas.routing import AgentID

logger = logging.getLogger(__name__)

VALID_EXTENSIONS: set[str] = {
    ".py",
    ".php",
    ".yml",
    ".yaml",
    ".json",
    ".sql",
    ".ini",
    ".conf",
    ".sh",
    ".ps1",
    ".env",
    ".example",
    ".toml",
    ".txt",
    ".md",
    ".xml",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".dist",
    ".lock",
}

DEFAULT_EXCLUDED_AGENTS: set[str] = {
    "agente_10_ciso",
    "agente_05_qa_php",
    "agente_06_qa_python",
    "agente_01_pm",
    "agente_09_growth",
}


class CodeMaterializerService:
    """Extracts, versions, and materializes production code from Markdown deliverables."""

    def __init__(self, workspaces_dir: Path | str | None = None) -> None:
        """Initialize the materializer with workspace root directory."""
        self.workspaces_dir = Path(workspaces_dir or settings.WORKSPACES_DIR)

    @staticmethod
    def is_valid_file_path(path: str) -> bool:
        """Validate whether a candidate path represents a genuine codebase file."""
        if not path or " " in path or path.startswith("http") or "://" in path:
            return False
        if ".." in path:
            return False

        clean = path.replace("\\", "/").strip("/.")
        if not clean:
            return False

        base = os.path.basename(clean).lower()
        if base in (
            "dockerfile",
            "makefile",
            ".env",
            ".env.example",
            ".gitignore",
            ".dockerignore",
        ):
            return True
        if base.startswith("dockerfile."):
            return True

        ext = os.path.splitext(clean)[1].lower()
        return ext in VALID_EXTENSIONS

    def extract_files_from_markdown(
        self,
        text: str,
        default_agent: str = "unknown",
    ) -> list[tuple[str, str]]:
        """Parse Markdown deliverable and extract (relative_path, content) pairs."""
        pattern = re.compile(r"```([^\n]*)\n(.*?)```", re.DOTALL)
        results: list[tuple[str, str]] = []
        last_end = 0

        for match in pattern.finditer(text):
            fence_info = match.group(1).strip()
            code = match.group(2)
            preceding_text = text[last_end:match.start()]
            last_end = match.end()

            # Ignore interactive shell snippets without script extension or shebang
            if fence_info in ("bash", "sh", "shell", "console", "terminal"):
                has_shebang = any(
                    code.strip().startswith(prefix)
                    for prefix in ("#!/bin/bash", "#!/bin/sh", "#!/usr/bin/env")
                )
                has_script_ref = bool(re.search(r"(\.sh|\.ps1)", preceding_text[-120:]))
                if not has_shebang and not has_script_ref:
                    continue

            path: str | None = None

            # 1. Check fence language tag/info (e.g. ```python:app/main.py or file="app/main.py")
            if ":" in fence_info:
                candidate = fence_info.split(":", 1)[1].strip().strip("`\"'")
                if self.is_valid_file_path(candidate):
                    path = candidate
            elif 'file="' in fence_info or "file='" in fence_info:
                m_f = re.search(r'file=[\'"]([^\'"]+)[\'"]', fence_info)
                if m_f and self.is_valid_file_path(m_f.group(1)):
                    path = m_f.group(1)

            # 2. Check preceding lines for headings or inline backticked file path
            if not path:
                lines = [
                    line.strip()
                    for line in preceding_text.strip().splitlines()
                    if line.strip()
                ]
                for line in reversed(lines[-8:]):
                    candidates = re.findall(r"`([a-zA-Z0-9_\-./\\]+)`", line)
                    for cand in candidates:
                        if self.is_valid_file_path(cand):
                            path = cand
                            break
                    if path:
                        break

                    m_hdr = re.match(
                        r"^#{1,6}\s*(?:Archivo:?|File:?|Fichero:?|Plantilla\s+.*?:?)?"
                        r"\s*[`\"']?([a-zA-Z0-9_\-./\\]+)[`\"']?$",
                        line,
                    )
                    if m_hdr and self.is_valid_file_path(m_hdr.group(1)):
                        path = m_hdr.group(1)
                        break

                    for kw in (
                        "docker-compose.prod.yml",
                        "docker-compose.yml",
                        ".env.example",
                        "Dockerfile",
                    ):
                        if kw in line:
                            path = kw
                            break
                    if path:
                        break

            # 3. Check first line of code block for filename comment
            if not path:
                code_lines = [cl.strip() for cl in code.splitlines() if cl.strip()]
                if code_lines:
                    first = code_lines[0]
                    m_comm = re.match(
                        r"^(?:#|//|--|/\*|<!--)\s*(?:(?:filepath|file|path)\s*:?\s*)?"
                        r"[`\"']?([a-zA-Z0-9_\-./\\]+)[`\"']?",
                        first,
                    )
                    if m_comm and self.is_valid_file_path(m_comm.group(1)):
                        path = m_comm.group(1)

            # 4. Check PHP namespace and class structure
            if not path and ("namespace App\\" in code or "namespace " in code):
                ns_m = re.search(r"namespace\s+([A-Za-z0-9_\\]+);", code)
                cl_m = re.search(r"(?:class|enum|interface|trait)\s+([A-Za-z0-9_]+)", code)
                if ns_m and cl_m:
                    ns = ns_m.group(1).replace("App\\", "app/").replace("\\", "/")
                    cl = cl_m.group(1)
                    path = f"{ns}/{cl}.php"

            if path and self.is_valid_file_path(path):
                norm_path = path.replace("\\", "/").strip("/")
                if norm_path.startswith("./"):
                    norm_path = norm_path[2:]

                # Strip leading comment line for JSON, XML and SQL to guarantee clean syntax
                if norm_path.endswith((".json", ".xml", ".sql", ".yaml", ".yml")):
                    code_lines = [cl.strip() for cl in code.splitlines() if cl.strip()]
                    if code_lines:
                        first = code_lines[0]
                        m_comm = re.match(
                            r"^(?:#|//|--|/\*|<!--)\s*(?:(?:filepath|file|path)\s*:?\s*)?"
                            r"[`\"']?([a-zA-Z0-9_\-./\\]+)[`\"']?",
                            first,
                        )
                        if m_comm:
                            lines_raw = code.splitlines(keepends=True)
                            for idx, lr in enumerate(lines_raw):
                                if lr.strip() == first:
                                    code = "".join(lines_raw[idx + 1 :]).lstrip()
                                    break

                results.append((norm_path, code))

        return results

    def _init_git_repo(self, target_dir: Path) -> bool:
        """Initialize a local Git repository and create initial automated commit."""
        if shutil.which("git") is None:
            logger.info("Git CLI no disponible; omitiendo inicialización de repositorio.")
            return False

        try:
            subprocess.run(
                ["git", "init"],
                cwd=target_dir,
                capture_output=True,
                check=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            subprocess.run(
                ["git", "add", "."],
                cwd=target_dir,
                capture_output=True,
                check=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=AgentOffice Bot",
                    "-c",
                    "user.email=bot@agentoffice.local",
                    "commit",
                    "-m",
                    "chore: initial automated build from AgentOffice",
                ],
                cwd=target_dir,
                capture_output=True,
                check=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return True
        except (subprocess.CalledProcessError, OSError) as exc:
            logger.warning("Fallo al inicializar repositorio Git en %s: %s", target_dir, exc)
            return False

    def materialize_project(
        self,
        project_id: str,
        allowed_agents: set[str | AgentID] | None = None,
        init_git: bool = True,
    ) -> tuple[Path, dict[str, Any]]:
        """Materialize project source code into build/ preserving chronological overwrites."""
        source_dir = self.workspaces_dir / project_id
        if not source_dir.exists() or not source_dir.is_dir():
            raise FileNotFoundError(
                f"El directorio del proyecto no existe: {source_dir}"
            )

        build_dir = source_dir / "build"
        build_dir.mkdir(parents=True, exist_ok=True)

        md_files = sorted(
            [
                p
                for p in source_dir.glob("*.md")
                if p.is_file() and p.name != "README.md"
            ],
            key=lambda p: (
                int(p.stem.split("_")[0]) if p.stem.split("_")[0].isdigit() else 999,
                p.name,
            ),
        )

        allowed_str: set[str] | None = None
        if allowed_agents is not None:
            allowed_str = {
                a.value if isinstance(a, AgentID) else str(a) for a in allowed_agents
            }

        files_map: dict[str, dict[str, Any]] = {}

        for md_path in md_files:
            stem_parts = md_path.stem.split("_", 1)
            step_num = int(stem_parts[0]) if stem_parts[0].isdigit() else 0
            agent_name = stem_parts[1] if len(stem_parts) > 1 else "unknown"

            if allowed_str is not None:
                if agent_name not in allowed_str:
                    continue
            else:
                if agent_name in DEFAULT_EXCLUDED_AGENTS:
                    continue

            content = md_path.read_text(encoding="utf-8")
            extracted = self.extract_files_from_markdown(content, default_agent=agent_name)

            for rel_path, code in extracted:
                files_map[rel_path] = {
                    "code": code,
                    "step_number": step_num,
                    "author_agent": agent_name,
                }

        files_manifest: list[dict[str, Any]] = []

        for rel_path in sorted(files_map.keys()):
            data = files_map[rel_path]
            code = data["code"]
            target_path = (build_dir / rel_path).resolve()

            # Guard against directory traversal
            if not target_path.is_relative_to(build_dir.resolve()):
                logger.warning("Ruta insegura detectada y omitida: %s", rel_path)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(code, encoding="utf-8")

            sha256_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
            size_bytes = len(code.encode("utf-8"))

            files_manifest.append(
                {
                    "path": rel_path,
                    "sha256": sha256_hash,
                    "size_bytes": size_bytes,
                    "author_agent": data["author_agent"],
                    "step_number": data["step_number"],
                }
            )

        manifest_data: dict[str, Any] = {
            "project_id": project_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "total_files": len(files_manifest),
            "files": files_manifest,
        }

        manifest_file = build_dir / "MANIFEST.json"
        manifest_file.write_text(
            json.dumps(manifest_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if init_git:
            self._init_git_repo(build_dir)

        return build_dir, manifest_data
