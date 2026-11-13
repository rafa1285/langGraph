"""FastAPI router for Meta WhatsApp Cloud API webhook endpoints and Dashboard WhatsApp Hub."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.config import settings
from app.middleware.whatsapp_security import verify_whatsapp_signature
from app.services.session_store import WhatsAppSessionStore
from app.services.whatsapp_config_service import WhatsAppConfigService
from app.services.whatsapp_service import WhatsAppService

router = APIRouter(tags=["WhatsApp & WhatsApp Hub"])

_whatsapp_service = WhatsAppService()
_config_service = WhatsAppConfigService()
_session_store = WhatsAppSessionStore()


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------


class WhatsAppConfigRequest(BaseModel):
    """Payload to save and apply WhatsApp settings."""

    phone_number_id: str | None = Field(default=None, description="Meta Phone Number ID")
    access_token: str | None = Field(default=None, description="Meta User/System User Access Token")
    verify_token: str | None = Field(default="agentoffice_verify_2026", description="Webhook Verify Token")
    app_secret: str | None = Field(default=None, description="Meta App Secret for HMAC verification")
    enabled: bool = Field(default=False, description="Enable or disable WhatsApp Gateway")
    allowed_phones: list[str] = Field(default_factory=list, description="Whitelist of authorized phone numbers")


class WhatsAppSimulateRequest(BaseModel):
    """Payload to test incoming WhatsApp messages via Dashboard Sandbox."""

    phone: str = Field(default="+34600123456", description="Emulated sender phone number")
    text: str = Field(..., description="Message text sent by the simulated user")


# ---------------------------------------------------------------------------
# Meta Webhook Endpoints (Public)
# ---------------------------------------------------------------------------


@router.get("/webhook/whatsapp")
async def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> int:
    """Handle the Meta webhook verification handshake (GET).

    Meta sends ``hub.mode``, ``hub.verify_token`` and ``hub.challenge`` as
    query parameters. Returns the challenge as an integer when the token matches;
    raises 403 otherwise.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        if hub_challenge is None:
            raise HTTPException(status_code=400, detail="Missing hub.challenge")
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@router.post("/webhook/whatsapp", dependencies=[Depends(verify_whatsapp_signature)])
async def receive_message(request: Request) -> dict[str, Any]:
    """Handle incoming WhatsApp messages (POST).

    Parses the Meta webhook payload, then immediately returns
    ``{"status": "received"}`` while processing happens in the background.
    """
    if not settings.WHATSAPP_ENABLED:
        return {"status": "disabled", "detail": "WhatsApp gateway is currently disabled in settings"}

    body: dict[str, Any] = await request.json()
    parsed = _whatsapp_service.parse_incoming_message(body)

    if parsed:
        # Check whitelist if configured
        sender = parsed.get("sender", "")
        if settings.WHATSAPP_ALLOWED_PHONES and sender not in settings.WHATSAPP_ALLOWED_PHONES:
            return {"status": "ignored", "detail": "Sender not in allowed whitelist"}

        from app.services.whatsapp_orchestrator import WhatsAppOrchestrator  # noqa: PLC0415

        orchestrator = WhatsAppOrchestrator(
            wa_service=_whatsapp_service,
            session_store=_session_store,
        )
        asyncio.create_task(orchestrator.handle_incoming(parsed))

    return {"status": "received"}


# ---------------------------------------------------------------------------
# WhatsApp Hub / Dashboard Admin Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/v1/whatsapp/status")
async def get_status(test_meta: bool = Query(default=False)) -> dict[str, Any]:
    """Return runtime configuration summary, active sessions count, and optional Meta API connectivity test."""
    summary = _config_service.get_summary()

    # Query active sessions
    try:
        sessions = await _session_store.list_sessions()
        summary["active_sessions_count"] = len(sessions)
    except Exception:
        summary["active_sessions_count"] = 0

    meta_health: dict[str, Any] | None = None
    if test_meta:
        meta_health = await _config_service.test_meta_connection()

    return {
        "status": "online" if settings.WHATSAPP_ENABLED else "disabled",
        "config": summary,
        "meta_connectivity": meta_health,
    }


@router.post("/api/v1/whatsapp/config")
async def update_config(payload: WhatsAppConfigRequest) -> dict[str, Any]:
    """Save and update WhatsApp configuration in .env and runtime settings."""
    updates = payload.model_dump()
    result = _config_service.save_env_config(updates)
    return result


@router.get("/api/v1/whatsapp/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    """List all stored WhatsApp conversation sessions."""
    return await _session_store.list_sessions()


@router.get("/api/v1/whatsapp/sessions/{phone}")
async def get_session_detail(phone: str) -> dict[str, Any]:
    """Fetch complete session history and intake state for a specific phone number."""
    session = await _session_store.get_session(phone)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/api/v1/whatsapp/sessions/{phone}/reset")
async def reset_session(phone: str) -> dict[str, Any]:
    """Reset/delete a session for a given phone number."""
    await _session_store.delete_session(phone)
    return {"status": "success", "message": f"Sesión para {phone} reiniciada correctamente."}


@router.post("/api/v1/whatsapp/simulate")
async def simulate_message(payload: WhatsAppSimulateRequest) -> dict[str, Any]:
    """Simulate an incoming WhatsApp message via Dashboard Sandbox without needing Meta."""
    phone = payload.phone.strip()
    text = payload.text.strip()
    if not phone or not text:
        raise HTTPException(status_code=400, detail="El teléfono y el mensaje no pueden estar vacíos")

    from app.services.whatsapp_orchestrator import WhatsAppOrchestrator  # noqa: PLC0415

    orchestrator = WhatsAppOrchestrator(
        wa_service=_whatsapp_service,
        session_store=_session_store,
    )
    parsed = {
        "sender": phone,
        "text": text,
        "message_id": f"wamid.sim_{int(asyncio.get_event_loop().time() * 1000)}",
        "timestamp": str(int(asyncio.get_event_loop().time())),
        "type": "text",
    }

    # Execute orchestrator directly to handle intake or command
    await orchestrator.handle_incoming(parsed)

    # Retrieve updated session
    session = await _session_store.get_session(phone)
    last_reply = ""
    if session and session.get("conversation_history"):
        history = session["conversation_history"]
        for msg in reversed(history):
            if msg.get("role") == "agent":
                last_reply = msg.get("content", "")
                break

    return {
        "status": "success",
        "phone": phone,
        "sent_text": text,
        "reply": last_reply,
        "session": session,
    }
