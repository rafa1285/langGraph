"""Vercel deployer service building serverless web packages and deploying to Vercel Cloud."""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.schemas.office import AgentEmailRecord
from app.services.code_materializer import CodeMaterializerService
from app.services.notion_mcp_service import get_knowledge_sync_adapter
from app.services.office_store import OfficeStore
from app.services.real_mail_bridge import RealMailBridge

logger = logging.getLogger(__name__)

FALLBACK_RAG_CHUNKS: list[dict[str, Any]] = [
    {
        "id_chunk": "KB-BILLING-001",
        "categoria": "Facturación y Créditos",
        "intencion_usuario": [
            "¿Cómo se cobran los créditos?",
            "¿Qué pasa si un correo da Unknown?",
            "¿Me cobran si un correo falla o da timeout?",
            "Política de reembolso de créditos",
            "Coste por correo electrónico",
        ],
        "contexto_autocontenido": (
            "En ValidatorHQ la regla de negocio tarifaria establece que 1 crédito equivale a 1 "
            "verificación concluyente. Solo se cobran los correos que devuelven estados "
            "definitivos: DELIVERABLE, UNDELIVERABLE o RISKY. Si un correo resulta en estado "
            "UNKNOWN debido a problemas de red, el sistema libera la reserva automáticamente."
        ),
        "respuesta_resolutiva": (
            "Solo pagas por los resultados concluyentes. Si un correo resulta en estado 'UNKNOWN' "
            "debido a fallas de red o demoras del servidor remoto, el crédito reservado se te "
            "reembolsa de forma 100% automática a tu cuenta al finalizar el lote."
        ),
    },
    {
        "id_chunk": "KB-BILLING-002",
        "categoria": "Facturación y Créditos",
        "intencion_usuario": [
            "¿Me cobran los correos duplicados?",
            "Tengo correos repetidos en mi lista",
            "Deduplicación de archivos",
            "¿Cómo manejan los emails duplicados en el CSV?",
        ],
        "contexto_autocontenido": (
            "La plataforma ValidatorHQ realiza una deduplicación automática y gratuita durante la "
            "fase de ingesta previa al procesamiento mediante SHA-256."
        ),
        "respuesta_resolutiva": (
            "La deduplicación es gratis. Si tu archivo contiene direcciones repetidas, "
            "nuestro motor solo cobrará y analizará las direcciones únicas. En el reporte final "
            "verás los duplicados etiquetados como 'DUPLICATE' a coste cero."
        ),
    },
    {
        "id_chunk": "KB-GDPR-001",
        "categoria": "Privacidad y Cumplimiento",
        "intencion_usuario": [
            "¿Cuánto tiempo guardan mis archivos?",
            "¿Por qué ya no puedo descargar mi lista?",
            "Mis datos aparecen como PURGED",
            "Política de retención GDPR",
            "Borrado automático de datos",
        ],
        "contexto_autocontenido": (
            "ValidatorHQ almacena los archivos subidos durante exactamente 15 días naturales "
            "posteriores a la finalización del trabajo bajo normativa GDPR."
        ),
        "respuesta_resolutiva": (
            "Tus archivos y resultados se conservan durante un máximo de 15 días naturales por "
            "cumplimiento estricto de la normativa GDPR. Pasado este tiempo se destruyen."
        ),
    },
    {
        "id_chunk": "KB-GDPR-002",
        "categoria": "Privacidad y Cumplimiento",
        "intencion_usuario": [
            "Quiero borrar mis datos inmediatamente",
            "Derecho al olvido",
            "Eliminar lista procesada ahora mismo",
            "Cómo borrar un trabajo sin esperar 15 días",
        ],
        "contexto_autocontenido": (
            "Los usuarios disponen de un botón denominado 'Eliminar Resultados Ahora' para purga "
            "física irrevocable e instantánea."
        ),
        "respuesta_resolutiva": (
            "Puedes eliminar tus datos en cualquier momento sin esperar los 15 días automáticos "
            "haciendo clic en 'Eliminar Resultados Ahora' en tu panel de control."
        ),
    },
    {
        "id_chunk": "KB-ENGINE-001",
        "categoria": "Motor de Verificación",
        "intencion_usuario": [
            "¿Qué significa el estado Catch-All?",
            "¿Por qué un correo aparece como RISKY?",
            "¿Es seguro enviar a correos Catch-All?",
            "Diferencia entre Deliverable y Risky",
        ],
        "contexto_autocontenido": (
            "Catch-All acepta cualquier mensaje entrante. ValidatorHQ lo clasifica como RISKY "
            "porque no se puede garantizar que pertenezca a un usuario real."
        ),
        "respuesta_resolutiva": (
            "El estado 'RISKY' con motivo 'CATCH_ALL' significa que el servidor de destino acepta "
            "cualquier nombre. No garantiza que el buzón pertenezca a una persona real."
        ),
    },
    {
        "id_chunk": "KB-ENGINE-002",
        "categoria": "Motor de Verificación",
        "intencion_usuario": [
            "¿Ustedes envían correos reales a mis contactos?",
            "¿Mis clientes sabrán que estoy validando su correo?",
            "¿Se envía algún email durante la prueba?",
            "Cómo funciona la prueba SMTP",
        ],
        "contexto_autocontenido": (
            "ValidatorHQ no envía ningún correo electrónico a los destinatarios. Ejecuta un "
            "handshake técnico SMTP no intrusivo y corta la conexión antes del comando DATA."
        ),
        "respuesta_resolutiva": (
            "No se envían correos. Realizamos una simulación técnica directa con el "
            "servidor MX deteniendo la conexión antes de transferir datos."
        ),
    },
    {
        "id_chunk": "KB-ERRORS-001",
        "categoria": "Errores de Usuario",
        "intencion_usuario": [
            "Error al subir archivo CSV",
            "Dice que no se detecta la columna de correo",
            "Archivo malformado o ilegible",
            "Límite de tamaño al subir lista",
        ],
        "contexto_autocontenido": (
            "Se admiten archivos .csv y .txt hasta 50.000 filas o 15 MB con codificación UTF-8."
        ),
        "respuesta_resolutiva": (
            "Asegúrate de que tu archivo esté en formato .CSV o .TXT (hasta 15 MB o 50.000 filas), "
            "guardado en UTF-8 y delimitado por comas (,)."
        ),
    },
    {
        "id_chunk": "KB-SECURITY-001",
        "categoria": "Seguridad de Red",
        "intencion_usuario": [
            "¿Qué significa el error SSRF_BLOCKED?",
            "Mi correo propio aparece como bloqueado por política de seguridad",
            "Error de seguridad en la verificación",
        ],
        "contexto_autocontenido": (
            "El motor incorpora blindaje anti-SSRF bloqueando conexiones a rangos privados, "
            "loopback o enlaces de metadatos cloud."
        ),
        "respuesta_resolutiva": (
            "El motivo 'SSRF_BLOCKED' indica que el servidor MX del dominio resuelve a una IP "
            "privada o interna protegida. Se bloquea para prevenir brechas de seguridad."
        ),
    },
]


class VercelDeployerService:
    """Service responsible for bundling and deploying serverless applications to Vercel."""

    def __init__(
        self,
        workspaces_dir: Path | str | None = None,
        vercel_token: str | None = None,
        vercel_team_id: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize with workspace root and optional Vercel credentials."""
        self.workspaces_dir = Path(workspaces_dir or settings.WORKSPACES_DIR)
        self.vercel_token = vercel_token or settings.VERCEL_TOKEN
        self.vercel_team_id = vercel_team_id or settings.VERCEL_TEAM_ID
        self._custom_client = client or http_client
        self.templates_dir = Path(__file__).parent.parent / "templates" / "vercel"

    def extract_rag_chunks(self, project_id: str) -> list[dict[str, Any]]:
        """Extract RAG chunks from any docs markdown deliverable or fallback to defaults."""
        proj_dir = self.workspaces_dir / project_id
        candidates = [proj_dir / "21_agente_08_docs.md"]
        candidates.extend(sorted(proj_dir.glob("*agente_08_docs.md")))
        candidates.extend(sorted(proj_dir.glob("*docs*.md")))

        seen: set[Path] = set()
        for docs_file in candidates:
            if docs_file in seen or not docs_file.exists():
                continue
            seen.add(docs_file)
            try:
                content = docs_file.read_text(encoding="utf-8")
                match = re.search(
                    r"```json\s*(\[\s*\{\s*\"(?:id_chunk|chunk_id)\"[\s\S]*?\])\s*```",
                    content,
                )
                if match:
                    parsed: list[dict[str, Any]] = json.loads(match.group(1))
                    if isinstance(parsed, list) and len(parsed) > 0:
                        normalized: list[dict[str, Any]] = []
                        for item in parsed:
                            if not isinstance(item, dict):
                                continue
                            norm_item = dict(item)
                            if "chunk_id" in norm_item and "id_chunk" not in norm_item:
                                norm_item["id_chunk"] = norm_item["chunk_id"]
                            if "topic" in norm_item and "categoria" not in norm_item:
                                norm_item["categoria"] = norm_item["topic"]
                            if "content" in norm_item and "respuesta_resolutiva" not in norm_item:
                                norm_item["respuesta_resolutiva"] = norm_item["content"]
                                norm_item["contexto_autocontenido"] = norm_item["content"]
                            if "keywords" in norm_item and "intencion_usuario" not in norm_item:
                                norm_item["intencion_usuario"] = norm_item["keywords"]
                            normalized.append(norm_item)
                        return normalized
            except Exception as exc:
                logger.warning("No se pudo parsear bloques RAG de %s: %s", docs_file, exc)

        return list(FALLBACK_RAG_CHUNKS)

    def _detect_project_title(self, project_id: str) -> str:
        """Detect human-readable project title from deliverables or return default."""
        proj_dir = self.workspaces_dir / project_id
        candidates = (
            "02_agente_01_pm.md",
            "01_agente_00_ceo.md",
            "04_agente_11_ui_ux.md",
            "05_agente_04_fastapi.md",
            "12_agente_08_docs.md",
        )
        for name in candidates:
            cand_path = proj_dir / name
            if cand_path.exists():
                try:
                    text = cand_path.read_text(encoding="utf-8")
                    m = re.search(r"##\s*Proyecto:\s*([^—–\n\r]+)", text)
                    if m:
                        title = m.group(1).strip()
                        if title and len(title) > 2:
                            return title
                except Exception:
                    pass
        return "ValidatorHQ Serverless Engine"

    def _compile_custom_frontend(self, project_id: str, dist_dir: Path, public_dir: Path) -> bool:
        """Compile materialized Blade templates or custom HTML into standalone frontend assets."""
        build_dir = self.workspaces_dir / project_id / "build"
        views_dir = build_dir / "resources" / "views"
        layout_path = views_dir / "layouts" / "app.blade.php"
        hero_path = views_dir / "landing" / "hero_simulator.blade.php"

        if layout_path.exists() and hero_path.exists():
            try:
                layout = layout_path.read_text(encoding="utf-8")
                hero = hero_path.read_text(encoding="utf-8")

                index_html = self._render_blade(layout, hero)
                (dist_dir / "index.html").write_text(index_html, encoding="utf-8")
                (public_dir / "index.html").write_text(index_html, encoding="utf-8")

                # Compile confirmation view if present
                confirm_path = views_dir / "booking" / "confirmation.blade.php"
                if confirm_path.exists():
                    confirm_raw = confirm_path.read_text(encoding="utf-8")
                    confirm_html = self._render_blade(layout, confirm_raw)
                    (dist_dir / "confirmation.html").write_text(confirm_html, encoding="utf-8")
                    (public_dir / "confirmation.html").write_text(confirm_html, encoding="utf-8")

                # Compile admin dashboard if present
                admin_path = views_dir / "admin" / "dashboard.blade.php"
                if admin_path.exists():
                    admin_raw = admin_path.read_text(encoding="utf-8")
                    admin_html = self._render_blade(layout, admin_raw)
                    (dist_dir / "admin.html").write_text(admin_html, encoding="utf-8")
                    (public_dir / "admin.html").write_text(admin_html, encoding="utf-8")

                return True
            except Exception as exc:
                logger.warning("Fallo al compilar vistas Blade para %s: %s", project_id, exc)

        # Check for static HTML generated by marketing
        mkt_html = self.workspaces_dir / project_id / "marketing" / "landing_page.html"
        if mkt_html.exists():
            content = mkt_html.read_text(encoding="utf-8")
            if len(content.strip()) > 100:
                (dist_dir / "index.html").write_text(content, encoding="utf-8")
                (public_dir / "index.html").write_text(content, encoding="utf-8")
                return True

        return False

    @staticmethod
    def _render_blade(layout_str: str, view_str: str) -> str:
        """Render a child Blade view into its parent layout and clean template syntax."""
        sec_m = re.search(r"@section\(['\"]content['\"]\)([\s\S]*?)@endsection", view_str)
        content = sec_m.group(1) if sec_m else view_str
        rendered = re.sub(r"@yield\(['\"]content['\"]\)", content, layout_str)
        rendered = re.sub(r"@csrf", "", rendered)
        rendered = re.sub(r"@stack\(['\"].*?['\"]\)", "", rendered)
        rendered = re.sub(r"@extends\(['\"].*?['\"]\)", "", rendered)
        rendered = re.sub(r"@section\(['\"].*?['\"]\)", "", rendered)
        rendered = re.sub(r"@endsection", "", rendered)
        rendered = re.sub(r"\{\{\s*date\(['\"]Y['\"]\)\s*\}\}", "2026", rendered)
        return rendered

    def _build_docs_html(self, project_id: str, project_title: str) -> str:
        """Build documentation portal HTML from Agent 08 deliverable or template."""
        proj_dir = self.workspaces_dir / project_id
        docs_files = sorted(proj_dir.glob("*agente_08_docs.md"))
        if not docs_files:
            docs_files = sorted(proj_dir.glob("*docs*.md"))

        if not docs_files or "ValidatorHQ" in project_title:
            docs_template = self.templates_dir / "docs.html"
            if docs_template.exists():
                return docs_template.read_text(encoding="utf-8")
            return f"<!DOCTYPE html><html><body><h1>{project_title} Docs</h1></body></html>"

        rag_chunks = self.extract_rag_chunks(project_id)
        faq_items_html = ""
        badge_cls = (
            "text-xs font-semibold px-2 py-0.5 rounded "
            "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
        )
        for chunk in rag_chunks[:8]:
            cat = chunk.get("categoria") or chunk.get("topic") or "General"
            q = chunk.get("intencion_usuario", ["Consulta"])
            q_str = q[0] if isinstance(q, list) and q else str(q)
            ans = chunk.get("respuesta_resolutiva") or chunk.get("content") or ""
            faq_items_html += (
                f'<div class="p-4 rounded-xl border border-slate-800 bg-slate-900/60 mb-4">\n'
                f'  <span class="{badge_cls}">{cat}</span>\n'
                f'  <h4 class="text-sm font-bold text-white mt-2">{q_str}</h4>\n'
                f'  <p class="text-xs text-slate-300 mt-1 leading-relaxed">{ans}</p>\n'
                f"</div>\n"
            )

        font_link = (
            '<link href="https://fonts.googleapis.com/css2?'
            'family=Plus+Jakarta+Sans:wght@400;600;700&display=swap" rel="stylesheet">'
        )
        return (
            "<!DOCTYPE html>\n"
            '<html lang="es" class="dark bg-slate-950 text-slate-100">\n<head>\n'
            '  <meta charset="UTF-8">\n'
            '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f"  <title>{project_title} — Documentación Técnica &amp; API</title>\n"
            '  <script src="https://cdn.tailwindcss.com"></script>\n'
            f"  {font_link}\n"
            "  <style>body { font-family: 'Plus Jakarta Sans', sans-serif; }</style>\n"
            "</head>\n"
            '<body class="min-h-screen bg-slate-950 antialiased">\n'
            '  <header class="sticky top-0 z-40 border-b border-slate-800 bg-slate-950/80">\n'
            '    <div class="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">\n'
            '      <a href="/" class="flex items-center gap-3">\n'
            '        <div class="h-9 w-9 rounded-lg bg-emerald-500 flex items-center '
            'justify-center font-bold text-slate-950">A</div>\n'
            f'        <span class="text-lg font-bold text-white">{project_title}</span>\n'
            "      </a>\n"
            '      <div class="flex items-center gap-4">\n'
            '        <a href="/" class="text-xs font-semibold px-3 py-1.5 rounded-lg '
            'border border-slate-700 text-slate-300 hover:text-white">Reservar Cita</a>\n'
            '        <a href="/admin" class="text-xs font-semibold px-3 py-1.5 rounded-lg '
            'bg-emerald-500 text-slate-950">Panel CRM</a>\n'
            "      </div>\n"
            "    </div>\n"
            "  </header>\n"
            '  <main class="max-w-5xl mx-auto px-4 py-12">\n'
            '    <div class="mb-12">\n'
            '      <span class="text-xs font-semibold text-emerald-400 bg-emerald-500/10 '
            'px-3 py-1 rounded-full border border-emerald-500/20">Portal Técnico Oficial</span>\n'
            f'      <h1 class="text-3xl font-extrabold text-white mt-4">{project_title} '
            "— API Reference</h1>\n"
            '      <p class="text-slate-400 text-sm mt-2">Especificación técnica, endpoints '
            "RESTful, webhooks y base de conocimiento RAG 24/7.</p>\n"
            "    </div>\n"
            '    <section class="mb-12">\n'
            '      <h2 class="text-xl font-bold text-white mb-4">Endpoints Principales</h2>\n'
            '      <div class="space-y-3">\n'
            '        <div class="p-4 rounded-xl border border-slate-800 bg-slate-900/50 '
            'flex items-center justify-between">\n'
            '          <span class="font-mono text-xs text-emerald-400">'
            "GET /api/v1/availability</span>\n"
            '          <span class="text-xs text-slate-400">'
            "Consulta de turnos disponibles</span>\n"
            "        </div>\n"
            '        <div class="p-4 rounded-xl border border-slate-800 bg-slate-900/50 '
            'flex items-center justify-between">\n'
            '          <span class="font-mono text-xs text-indigo-400">'
            "POST /api/v1/checkout/create-session</span>\n"
            '          <span class="text-xs text-slate-400">'
            "Creación de reserva y pago instantáneo</span>\n"
            "        </div>\n"
            '        <div class="p-4 rounded-xl border border-slate-800 bg-slate-900/50 '
            'flex items-center justify-between">\n'
            '          <span class="font-mono text-xs text-indigo-400">'
            "POST /api/v1/ai/rag/query</span>\n"
            '          <span class="text-xs text-slate-400">'
            "Consulta RAG IA autónoma</span>\n"
            "        </div>\n"
            '        <div class="p-4 rounded-xl border border-slate-800 bg-slate-900/50 '
            'flex items-center justify-between">\n'
            '          <span class="font-mono text-xs text-emerald-400">GET /api/health</span>\n'
            '          <span class="text-xs text-slate-400">Healthcheck serverless</span>\n'
            "        </div>\n"
            "      </div>\n"
            "    </section>\n"
            '    <section class="mb-12">\n'
            '      <h2 class="text-xl font-bold text-white mb-4">Base de Conocimiento RAG</h2>\n'
            f'      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">\n{faq_items_html}\n</div>\n'
            "    </section>\n"
            "  </main>\n"
            f'  <footer class="border-t border-slate-800 py-6 text-center text-xs text-slate-500">'
            f"&copy; 2026 {project_title}. Generado por AgentOffice.</footer>\n"
            "</body>\n</html>"
        )


    def build_vercel_bundle(self, project_id: str) -> Path:
        """Build the full serverless distribution directory for Vercel."""
        # 0. Ensure project deliverables are materialized into build/
        try:
            materializer = CodeMaterializerService(self.workspaces_dir)
            materializer.materialize_project(project_id, init_git=False)
        except Exception as mat_err:
            logger.warning("Materialización previa omitida para %s: %s", project_id, mat_err)

        dist_dir = self.workspaces_dir / project_id / "vercel_dist"
        api_dir = dist_dir / "api"
        public_dir = dist_dir / "public"
        dist_dir.mkdir(parents=True, exist_ok=True)
        api_dir.mkdir(parents=True, exist_ok=True)
        public_dir.mkdir(parents=True, exist_ok=True)

        rag_chunks = self.extract_rag_chunks(project_id)
        rag_json = json.dumps(rag_chunks, indent=2, ensure_ascii=False)

        # 1. Save RAG dataset
        (api_dir / "rag_chunks.json").write_text(rag_json, encoding="utf-8")
        (dist_dir / "rag_chunks.json").write_text(rag_json, encoding="utf-8")

        # 2. Save api/index.py with project metadata
        project_title = self._detect_project_title(project_id)
        api_template = self.templates_dir / "api_index.py"
        if api_template.exists():
            api_py_content = (
                api_template.read_text(encoding="utf-8")
                .replace("{{project_id}}", project_id)
                .replace("{{project_title}}", project_title)
            )
        else:
            api_py_content = (
                f'from fastapi import FastAPI\napp = FastAPI(title="{project_title}")\n'
                f'@app.get("/api/health")\ndef h(): return {{"project_id": "{project_id}"}}\n'
            )
        (api_dir / "index.py").write_text(api_py_content, encoding="utf-8")

        # 3. Save requirements.txt
        requirements_txt = "fastapi>=0.110.0\npydantic>=2.6.0\n"
        (dist_dir / "requirements.txt").write_text(requirements_txt, encoding="utf-8")

        # 4. Save vercel.json with clean rewrites
        vercel_json = json.dumps(
            {
                "version": 2,
                "rewrites": [
                    {
                        "source": "/api/(.*)",
                        "destination": "/api/index.py",
                    },
                    {
                        "source": "/booking/confirmation",
                        "destination": "/confirmation.html",
                    },
                    {
                        "source": "/admin/dashboard",
                        "destination": "/admin.html",
                    },
                    {
                        "source": "/admin",
                        "destination": "/admin.html",
                    },
                    {
                        "source": "/docs",
                        "destination": "/docs.html",
                    },
                ],
            },
            indent=2,
        )
        (dist_dir / "vercel.json").write_text(vercel_json, encoding="utf-8")

        # 5. Save index.html (custom compiled Blade/marketing or fallback to template)
        compiled_custom = self._compile_custom_frontend(project_id, dist_dir, public_dir)
        if not compiled_custom:
            index_template = self.templates_dir / "index.html"
            if index_template.exists():
                index_html = index_template.read_text(encoding="utf-8")
            else:
                index_html = "<!DOCTYPE html><html><body><h1>ValidatorHQ Demo</h1></body></html>"
            (dist_dir / "index.html").write_text(index_html, encoding="utf-8")
            (public_dir / "index.html").write_text(index_html, encoding="utf-8")

        # 6. Save docs.html (custom project portal or fallback template)
        docs_html = self._build_docs_html(project_id, project_title)
        (dist_dir / "docs.html").write_text(docs_html, encoding="utf-8")
        (public_dir / "docs.html").write_text(docs_html, encoding="utf-8")

        return dist_dir


    async def deploy_to_vercel(
        self,
        project_id: str,
        project_name: str = "validator-hq-saas",
        sync_notifications: bool = True,
    ) -> dict[str, Any]:
        """Bundle and deploy serverless application to Vercel Cloud."""
        bundle_path = self.build_vercel_bundle(project_id)

        # Collect files to upload
        files_payload: list[dict[str, str]] = []
        for file_path in bundle_path.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(bundle_path).as_posix()
                content = file_path.read_text(encoding="utf-8")
                files_payload.append({"file": rel_path, "data": content})

        if not self.vercel_token:
            return {
                "success": False,
                "project_id": project_id,
                "project_name": project_name,
                "deployment_url": None,
                "bundle_path": str(bundle_path),
                "total_files": len(files_payload),
                "email_logged": False,
                "error": "VERCEL_TOKEN no configurado en entorno",
            }

        endpoint = "https://api.vercel.com/v13/deployments"
        if self.vercel_team_id:
            endpoint += f"?teamId={self.vercel_team_id}"

        headers = {
            "Authorization": f"Bearer {self.vercel_token}",
            "Content-Type": "application/json",
        }

        body = {
            "name": project_name,
            "target": "production",
            "projectSettings": {"framework": None},
            "files": files_payload,
        }

        client = self._custom_client or httpx.AsyncClient(timeout=60.0)
        close_client = self._custom_client is None

        try:
            resp = await client.post(endpoint, headers=headers, json=body)
            if resp.status_code not in (200, 201):
                return {
                    "success": False,
                    "project_id": project_id,
                    "project_name": project_name,
                    "deployment_url": None,
                    "bundle_path": str(bundle_path),
                    "total_files": len(files_payload),
                    "email_logged": False,
                    "error": f"Vercel API error HTTP {resp.status_code}: {resp.text}",
                }

            data = resp.json()
            raw_url = data.get("url")
            # If production alias exists, prioritize canonical domain over transient preview hash
            aliases = data.get("alias")
            target_alias = f"{project_name}.vercel.app"
            canonical_url: str | None = None
            if isinstance(aliases, list) and aliases:
                for al in aliases:
                    al_str = str(al)
                    if al_str == target_alias:
                        canonical_url = al_str
                        break
                if not canonical_url:
                    canonical_url = str(aliases[0])

            if not canonical_url:
                canonical_url = target_alias if target_alias else (raw_url or "vercel.app")

            deployment_url = f"https://{canonical_url}"

            # Attempt to disable preview SSO protection and enforce zero-config static framework
            try:
                sso_endpoint = f"https://api.vercel.com/v9/projects/{project_name}"
                if self.vercel_team_id:
                    sso_endpoint += f"?teamId={self.vercel_team_id}"
                await client.patch(
                    sso_endpoint,
                    headers=headers,
                    json={"ssoProtection": None, "framework": None},
                )
            except Exception as sso_err:
                logger.debug("Aviso ignorado al actualizar configuración Vercel: %s", sso_err)

        finally:
            if close_client:
                await client.aclose()

        email_logged = False
        if sync_notifications:
            try:
                email_record = AgentEmailRecord(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    step_number=99,
                    sender="agente_07_devops@agentoffice.local",
                    recipient="ceo@agentoffice.local",
                    cc=["agente_08_docs@agentoffice.local", "agente_09_growth@agentoffice.local"],
                    subject=(
                        f"[Vercel Deploy] {project_name} desplegado en producción: {deployment_url}"
                    ),
                    body_summary=(
                        f"Despliegue serverless completado exitosamente en Vercel Cloud.\n"
                        f"Proyecto: {project_id}\n"
                        f"Nombre: {project_name}\n"
                        f"URL Pública: {deployment_url}\n"
                        f"Endpoint Salud: {deployment_url}/api/health\n"
                        f"Simulador en Vivo: {deployment_url}/#demo\n"
                        f"Portal Documentación: {deployment_url}/docs.html\n"
                        f"Archivos Desplegados: {len(files_payload)}"
                    ),
                    attached_deliverable_path=str(bundle_path / "vercel.json"),
                    priority="HIGH",
                    is_read=False,
                )

                office_store = OfficeStore()
                await office_store.save_email(email_record)
                email_logged = True

                if settings.REAL_MAIL_ENABLED:
                    bridge = RealMailBridge()
                    await bridge.sync_email_record(email_record)

                if settings.NOTION_MCP_ENABLED and settings.NOTION_API_KEY:
                    notion_adapter = get_knowledge_sync_adapter()
                    await notion_adapter.update_project_status(
                        project_id=project_id,
                        status_data={"status": f"DESPLEGADO_VERCEL - {deployment_url}"},
                    )
            except Exception as notify_err:
                logger.warning("Fallo al registrar notificaciones de Vercel: %s", notify_err)

        return {
            "success": True,
            "project_id": project_id,
            "project_name": project_name,
            "deployment_url": deployment_url,
            "bundle_path": str(bundle_path),
            "total_files": len(files_payload),
            "email_logged": email_logged,
            "error": None,
        }
