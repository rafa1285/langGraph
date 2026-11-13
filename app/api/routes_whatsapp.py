"""FastAPI router for Meta WhatsApp Cloud API webhook endpoints."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.config import settings
from app.middleware.whatsapp_security import verify_whatsapp_signature
from app.services.whatsapp_service import WhatsAppService

router = APIRouter(prefix="/webhook", tags=["WhatsApp"])

_whatsapp_service = WhatsAppService()


@router.get("/whatsapp")
async def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> int:
    """Handle the Meta webhook verification handshake (GET).

    Meta sends ``hub.mode``, ``hub.verify_token`` and ``hub.challenge`` as
    query parameters (with dots replaced by underscores by FastAPI).  Returns
    the challenge as an integer when the token matches; raises 403 otherwise.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        if hub_challenge is None:
            raise HTTPException(status_code=400, detail="Missing hub.challenge")
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@router.post("/whatsapp", dependencies=[Depends(verify_whatsapp_signature)])
async def receive_message(request: Request) -> dict[str, Any]:
    """Handle incoming WhatsApp messages (POST).

    Parses the Meta webhook payload, then immediately returns
    ``{"status": "received"}`` while processing happens in the background.
    """
    body: dict[str, Any] = await request.json()
    parsed = _whatsapp_service.parse_incoming_message(body)

    if parsed:
        from app.services.whatsapp_orchestrator import WhatsAppOrchestrator  # noqa: PLC0415

        orchestrator = WhatsAppOrchestrator()
        asyncio.create_task(orchestrator.handle_incoming(parsed))

    return {"status": "received"}
