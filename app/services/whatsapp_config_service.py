"""WhatsApp configuration management, Meta API connectivity diagnostics, and environment persistence."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_GRAPH_API_VERSION = "v21.0"
_META_BASE_URL = f"https://graph.facebook.com/{_GRAPH_API_VERSION}"


class WhatsAppConfigService:
    """Manages WhatsApp runtime settings, .env persistence, and Meta Graph API diagnostics."""

    def __init__(self, env_path: Path | None = None) -> None:
        self.env_path = env_path or (
            Path(__file__).resolve().parent.parent.parent / ".env"
        )

    async def test_meta_connection(
        self,
        phone_number_id: str | None = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        """Verify connectivity and validity of phone number and access token with Meta Graph API."""
        pid = (phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID or "").strip()
        tok = (access_token or settings.WHATSAPP_ACCESS_TOKEN or "").strip()

        if not pid or not tok:
            return {
                "connected": False,
                "error": "Faltan credenciales: Phone Number ID o Access Token no configurados.",
                "details": None,
            }

        url = f"{_META_BASE_URL}/{pid}"
        headers = {"Authorization": f"Bearer {tok}"}
        params = {
            "fields": "id,display_phone_number,verified_name,quality_rating,code_verification_status"
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers, params=params)
                data = res.json()
                if res.is_success:
                    return {
                        "connected": True,
                        "error": None,
                        "details": {
                            "id": data.get("id", pid),
                            "display_phone_number": data.get("display_phone_number", "N/A"),
                            "verified_name": data.get("verified_name", "N/A"),
                            "quality_rating": data.get("quality_rating", "GREEN"),
                            "code_verification_status": data.get("code_verification_status", "VERIFIED"),
                        },
                    }
                else:
                    error_obj = data.get("error", {})
                    msg = error_obj.get("message", res.text)
                    code = error_obj.get("code")
                    error_detail = f"Error Meta ({code}): {msg}" if code else f"Error Meta: {msg}"
                    return {
                        "connected": False,
                        "error": error_detail,
                        "details": None,
                    }
        except Exception as exc:
            logger.warning("Error checking Meta Graph API connectivity: %s", exc)
            return {
                "connected": False,
                "error": f"Error de red al conectar con Meta: {exc}",
                "details": None,
            }

    def save_env_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Update WhatsApp configuration in the .env file and in runtime settings."""
        lines: list[str] = []
        if self.env_path.exists():
            lines = self.env_path.read_text(encoding="utf-8").splitlines()

        # Build mapping of updated values
        key_map: dict[str, str] = {}
        if "phone_number_id" in updates:
            key_map["WHATSAPP_PHONE_NUMBER_ID"] = str(updates["phone_number_id"] or "").strip()
        if "access_token" in updates:
            key_map["WHATSAPP_ACCESS_TOKEN"] = str(updates["access_token"] or "").strip()
        if "verify_token" in updates:
            key_map["WHATSAPP_VERIFY_TOKEN"] = str(updates["verify_token"] or "agentoffice_verify_2026").strip()
        if "app_secret" in updates:
            key_map["WHATSAPP_APP_SECRET"] = str(updates["app_secret"] or "").strip()
        if "enabled" in updates:
            key_map["WHATSAPP_ENABLED"] = "true" if updates["enabled"] else "false"
        if "allowed_phones" in updates:
            phones = updates["allowed_phones"]
            if isinstance(phones, list):
                key_map["WHATSAPP_ALLOWED_PHONES"] = json.dumps(phones)
            elif isinstance(phones, str):
                key_map["WHATSAPP_ALLOWED_PHONES"] = phones

        updated_keys = set()
        new_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue
            if "=" in line:
                key, _ = line.split("=", 1)
                key = key.strip()
                if key in key_map:
                    new_lines.append(f"{key}={key_map[key]}")
                    updated_keys.add(key)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        # Append any new keys that weren't already in .env
        added_any = False
        for key, val in key_map.items():
            if key not in updated_keys and val:
                if not added_any:
                    new_lines.append("")
                    new_lines.append("# --- WhatsApp Business API (Actualizado desde Dashboard) ---")
                    added_any = True
                new_lines.append(f"{key}={val}")

        self.env_path.write_text("\n".join(new_lines).strip() + "\n", encoding="utf-8")

        # Apply to runtime settings and os.environ
        if "phone_number_id" in updates:
            settings.WHATSAPP_PHONE_NUMBER_ID = str(updates["phone_number_id"]).strip() or None
            os.environ["WHATSAPP_PHONE_NUMBER_ID"] = settings.WHATSAPP_PHONE_NUMBER_ID or ""
        if "access_token" in updates:
            settings.WHATSAPP_ACCESS_TOKEN = str(updates["access_token"]).strip() or None
            os.environ["WHATSAPP_ACCESS_TOKEN"] = settings.WHATSAPP_ACCESS_TOKEN or ""
        if "verify_token" in updates:
            settings.WHATSAPP_VERIFY_TOKEN = str(updates["verify_token"]).strip() or "agentoffice_verify_2026"
            os.environ["WHATSAPP_VERIFY_TOKEN"] = settings.WHATSAPP_VERIFY_TOKEN
        if "app_secret" in updates:
            settings.WHATSAPP_APP_SECRET = str(updates["app_secret"]).strip() or None
            os.environ["WHATSAPP_APP_SECRET"] = settings.WHATSAPP_APP_SECRET or ""
        if "enabled" in updates:
            settings.WHATSAPP_ENABLED = bool(updates["enabled"])
            os.environ["WHATSAPP_ENABLED"] = "true" if settings.WHATSAPP_ENABLED else "false"
        if "allowed_phones" in updates:
            phones = updates["allowed_phones"]
            if isinstance(phones, list):
                settings.WHATSAPP_ALLOWED_PHONES = [str(p).strip() for p in phones if str(p).strip()]
            elif isinstance(phones, str):
                try:
                    parsed = json.loads(phones)
                    if isinstance(parsed, list):
                        settings.WHATSAPP_ALLOWED_PHONES = [str(p).strip() for p in parsed if str(p).strip()]
                    else:
                        settings.WHATSAPP_ALLOWED_PHONES = [str(phones).strip()]
                except Exception:
                    settings.WHATSAPP_ALLOWED_PHONES = [p.strip() for p in phones.split(",") if p.strip()]

        return {
            "status": "success",
            "message": "Configuración guardada correctamente en .env y aplicada en memoria.",
            "current": self.get_summary(),
        }

    def get_summary(self) -> dict[str, Any]:
        """Return a safe summary of current settings (masking access token)."""
        tok = settings.WHATSAPP_ACCESS_TOKEN or ""
        masked_token = f"{tok[:6]}...{tok[-4:]}" if len(tok) > 12 else ("Configurado" if tok else "")
        secret = settings.WHATSAPP_APP_SECRET or ""
        masked_secret = f"{secret[:3]}...{secret[-2:]}" if len(secret) > 6 else ("Configurado" if secret else "")

        return {
            "enabled": bool(settings.WHATSAPP_ENABLED),
            "phone_number_id": settings.WHATSAPP_PHONE_NUMBER_ID or "",
            "access_token_masked": masked_token,
            "has_access_token": bool(tok),
            "verify_token": settings.WHATSAPP_VERIFY_TOKEN or "agentoffice_verify_2026",
            "app_secret_masked": masked_secret,
            "has_app_secret": bool(secret),
            "allowed_phones": list(settings.WHATSAPP_ALLOWED_PHONES or []),
            "webhook_path": "/webhook/whatsapp",
        }
