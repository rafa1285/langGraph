"""n8n Automation and Workflow Provisioning Service for AgentOffice Multi-Project Marketing.

Generates dynamic, importable n8n workflows customized for each project's enabled channels
and automatically provisions them via the n8n REST API to bind webhook ingestion URLs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from app.core.config import settings

if TYPE_CHECKING:
    from app.schemas.office import ProjectMarketingProfile
    from app.services.office_store import OfficeStore

logger = logging.getLogger(__name__)

_LI_BODY = (
    "={{ JSON.stringify({\n"
    "  author: 'urn:li:person:' + ($json.body.payload.account_handle_or_url || 'ID'),\n"
    "  lifecycleState: 'PUBLISHED',\n"
    "  specificContent: {\n"
    "    'com.linkedin.ugc.ShareContent': {\n"
    "      shareCommentary: {\n"
    "        text: $json.body.channels_content.linkedin.headline + '\\n\\n' + "
    "$json.body.channels_content.linkedin.body\n"
    "      },\n"
    "      shareMediaCategory: 'NONE'\n"
    "    }\n"
    "  },\n"
    "  visibility: { 'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC' }\n"
    "}) }}"
)

_TW_BODY = (
    "={{ JSON.stringify({ text: $json.body.channels_content.x_twitter.headline + ' ' + "
    "$json.body.channels_content.x_twitter.body }) }}"
)

_DISCORD_URL = (
    "={{ $json.body.payload.credentials.discord_webhook_url || "
    "'https://discord.com/api/webhooks/YOUR_WEBHOOK_URL' }}"
)

_DISCORD_BODY = (
    "={{ JSON.stringify({\n"
    "  content: '🚀 **' + $json.body.project_name + '** | ' + "
    "$json.body.channels_content.telegram_discord.headline + '\\n' + "
    "$json.body.channels_content.telegram_discord.body\n"
    "}) }}"
)

_DEVTO_KEY = "={{ $json.body.payload.credentials.devto_api_key || 'DEVTO_KEY' }}"

_DEVTO_BODY = (
    "={{ JSON.stringify({\n"
    "  article: {\n"
    "    title: $json.body.channels_content.reddit_devto.headline,\n"
    "    body_markdown: '# ' + $json.body.project_name + '\\n\\n' + "
    "$json.body.channels_content.reddit_devto.body,\n"
    "    published: false,\n"
    "    tags: ['saas', 'tech', 'webdev']\n"
    "  }\n"
    "}) }}"
)

_META_BODY = (
    "={{ JSON.stringify({ caption: $json.body.channels_content.instagram_meta.headline + "
    "'\\n\\n' + $json.body.channels_content.instagram_meta.body }) }}"
)

_TIKTOK_BODY = "={{ JSON.stringify({ title: $json.body.channels_content.tiktok.headline }) }}"

_EMAIL_BODY = (
    "={{ JSON.stringify({\n"
    "  from: 'newsletter@yourdomain.com',\n"
    "  to: ['subscribers@yourdomain.com'],\n"
    "  subject: $json.body.channels_content.email_newsletter.headline,\n"
    "  html: '<p>' + $json.body.channels_content.email_newsletter.body + '</p>'\n"
    "}) }}"
)

_GADS_BODY = (
    "={{ JSON.stringify({ project: $json.body.project_id, event: 'launch_conversion' }) }}"
)

CHANNEL_NODE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "linkedin": {
        "name": "Publicar en LinkedIn",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "parameters": {
            "method": "POST",
            "url": "https://api.linkedin.com/v2/ugcPosts",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "X-Restli-Protocol-Version", "value": "2.0.0"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": _LI_BODY,
        },
    },
    "x_twitter": {
        "name": "Publicar en X (Twitter)",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "parameters": {
            "method": "POST",
            "url": "https://api.twitter.com/2/tweets",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": _TW_BODY,
        },
    },
    "telegram_discord": {
        "name": "Difundir en Discord / Telegram",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "parameters": {
            "method": "POST",
            "url": _DISCORD_URL,
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": _DISCORD_BODY,
        },
    },
    "reddit_devto": {
        "name": "Publicar Borrador en Dev.to",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "parameters": {
            "method": "POST",
            "url": "https://dev.to/api/articles",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "api-key", "value": _DEVTO_KEY},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": _DEVTO_BODY,
        },
    },
    "instagram_meta": {
        "name": "Publicar en Meta / Instagram",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "parameters": {
            "method": "POST",
            "url": "https://graph.facebook.com/v19.0/me/media",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": _META_BODY,
        },
    },
    "tiktok": {
        "name": "Subir Borrador a TikTok",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "parameters": {
            "method": "POST",
            "url": "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": _TIKTOK_BODY,
        },
    },
    "producthunt": {
        "name": "Notificar Lanzamiento Product Hunt",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "parameters": {
            "method": "POST",
            "url": "https://api.producthunt.com/v2/api/graphql",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ query: 'query { viewer { user { id } } }' }) }}",
        },
    },
    "email_newsletter": {
        "name": "Disparar Secuencia Email Newsletter",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "parameters": {
            "method": "POST",
            "url": "https://api.resend.com/emails",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Authorization", "value": "Bearer YOUR_RESEND_KEY"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": _EMAIL_BODY,
        },
    },
    "google_ads": {
        "name": "Registrar Conversión Google Ads",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "parameters": {
            "method": "POST",
            "url": "https://googleads.googleapis.com/v16/customers/CID/conversionUploads:upload",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": _GADS_BODY,
        },
    },
}


def generate_project_n8n_workflow(
    profile: ProjectMarketingProfile,
    workspaces_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Build a complete, valid, and importable n8n workflow JSON for the given project.

    Includes a Webhook trigger node and child HTTP / social nodes for each enabled channel.
    Also saves a local copy in the project's workspace under `marketing/`.
    """
    project_id = profile.project_id
    project_name = profile.project_name or project_id
    active_channels = [c for c in profile.channels if c.enabled]

    webhook_node_name = "Webhook Ingesta Marketing"
    webhook_node: dict[str, Any] = {
        "id": "node_webhook_ingest",
        "name": webhook_node_name,
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 1,
        "position": [240, 300],
        "webhookId": f"marketing-{project_id}",
        "parameters": {
            "path": f"marketing-{project_id}",
            "httpMethod": "POST",
            "responseMode": "onReceived",
            "responseData": "allEntries",
        },
    }

    nodes: list[dict[str, Any]] = [webhook_node]
    channel_targets: list[dict[str, Any]] = []

    y_pos = 100
    for ch in active_channels:
        cid = ch.channel_id
        def_node = CHANNEL_NODE_DEFINITIONS.get(cid)
        if def_node:
            node_copy = {
                "id": f"node_{cid}",
                "name": def_node["name"],
                "type": def_node["type"],
                "typeVersion": def_node.get("typeVersion", 1),
                "position": [560, y_pos],
                "parameters": dict(def_node.get("parameters", {})),
            }
            nodes.append(node_copy)
            channel_targets.append({"node": node_copy["name"], "type": "main", "index": 0})
            y_pos += 140

    if not channel_targets:
        placeholder_node: dict[str, Any] = {
            "id": "node_placeholder",
            "name": "Modo Local (Sin Canales Activos)",
            "type": "n8n-nodes-base.noOp",
            "typeVersion": 1,
            "position": [560, 300],
            "parameters": {},
        }
        nodes.append(placeholder_node)
        channel_targets.append({"node": placeholder_node["name"], "type": "main", "index": 0})

    connections: dict[str, Any] = {
        webhook_node_name: {
            "main": [channel_targets],
        }
    }

    workflow_data: dict[str, Any] = {
        "name": f"AgentOffice Marketing - {project_name}",
        "nodes": nodes,
        "connections": connections,
        "active": False,
        "settings": {
            "executionOrder": "v1",
        },
        "tags": [
            {"name": "agentoffice"},
            {"name": "marketing"},
            {"name": profile.marketing_type},
        ],
    }

    # Save copy to project workspace
    base_dir = Path(workspaces_dir or settings.WORKSPACES_DIR).resolve()
    target_dir = (base_dir / project_id / "marketing").resolve()
    if not target_dir.is_relative_to(base_dir):
        raise ValueError(
            f"Path traversal detectado: el project_id '{project_id}' está fuera del workspace."
        )
    target_dir.mkdir(parents=True, exist_ok=True)

    wf_file_custom = target_dir / f"n8n_workflow_{project_id}.json"
    wf_file_standard = target_dir / "n8n_workflow.json"

    formatted_json = json.dumps(workflow_data, indent=2, ensure_ascii=False)
    wf_file_custom.write_text(formatted_json, encoding="utf-8")
    wf_file_standard.write_text(formatted_json, encoding="utf-8")

    return workflow_data


async def provision_workflow_in_n8n(
    profile: ProjectMarketingProfile,
    n8n_base_url: str = "",
    n8n_api_key: str = "",
    office_store: OfficeStore | None = None,
    workspaces_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Generate workflow, provision it in n8n via REST API, and store resulting webhook_url.

    If n8n is unreachable or API key is not supplied, configures local webhook URL gracefully.
    """
    project_id = profile.project_id
    base_url = (n8n_base_url or settings.N8N_BASE_URL or "http://localhost:5678").rstrip("/")
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        raise ValueError(f"Esquema de n8n_base_url no permitido: '{base_url}'")
    api_key = n8n_api_key or settings.N8N_API_KEY or ""

    workflow_json = generate_project_n8n_workflow(profile, workspaces_dir=workspaces_dir)
    # n8n v2 public API strictly validates CreateWorkflowPublicDto fields
    allowed_api_fields = {
        "name", "nodes", "connections", "settings", "nodeGroups",
        "staticData", "pinData", "projectId", "parentFolderId", "shared", "description"
    }
    api_payload = {k: v for k, v in workflow_json.items() if k in allowed_api_fields}

    live_connected = False
    workflow_id = f"local_wf_{project_id}"
    error_msg: str | None = None

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-N8N-API-KEY"] = api_key

    # Attempt REST provisioning against n8n API
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(
                f"{base_url}/api/v1/workflows",
                headers=headers,
                json=api_payload,
            )
            if resp.status_code in (200, 201):
                live_connected = True
                data = resp.json()
                workflow_id = str(data.get("id") or data.get("data", {}).get("id") or workflow_id)
                logger.info(
                    "Workflow successfully provisioned in n8n for project %s (ID: %s)",
                    project_id,
                    workflow_id,
                )
                # Auto-publish workflow to activate webhooks in n8n
                try:
                    await client.post(
                        f"{base_url}/api/v1/workflows/{workflow_id}/publish",
                        headers=headers,
                        json={},
                    )
                    logger.info("Workflow %s published and live in n8n", workflow_id)
                except Exception as pub_exc:
                    logger.warning("Failed to auto-publish workflow %s: %s", workflow_id, pub_exc)
            else:
                error_msg = f"HTTP {resp.status_code}: {resp.text[:120]}"
                logger.warning("n8n API responded with error: %s", error_msg)
    except Exception as exc:
        error_msg = str(exc)
        logger.info("Could not connect to live n8n instance at %s: %s", base_url, exc)

    # Standard webhook URL generated by n8n
    webhook_url = f"{base_url}/webhook/marketing-{project_id}"

    # Auto-assign webhook_url to project's social_ads_publisher tool in office_store
    if office_store:
        try:
            persisted_profile = await office_store.get_project_marketing_config(project_id)
            tool_found = False
            for t in persisted_profile.tools:
                if t.tool_id == "social_ads_publisher":
                    t.credentials["webhook_url"] = webhook_url
                    t.is_configured = True
                    tool_found = True
                    break

            if tool_found:
                await office_store.save_project_marketing_config(project_id, persisted_profile)
                logger.info("Auto-assigned webhook_url '%s' to project %s", webhook_url, project_id)
        except Exception as exc:
            logger.warning("Failed to save webhook_url in office_store: %s", exc)

    msg = (
        f"Workflow aprovisionado con éxito en n8n ({workflow_id}) y vinculado al webhook."
        if live_connected
        else f"Flujo generado y webhook local configurado: {webhook_url} (Instancia n8n offline)."
    )

    return {
        "status": "provisioned" if live_connected else "configured_local",
        "project_id": project_id,
        "workflow_id": workflow_id,
        "webhook_url": webhook_url,
        "n8n_base_url": base_url,
        "live_n8n_connected": live_connected,
        "active_channels": [c.channel_id for c in profile.channels if c.enabled],
        "api_error": error_msg,
        "message": msg,
        "workflow_json": workflow_json,
    }
