"""WhatsApp request signature verification middleware."""

from __future__ import annotations

import hashlib
import hmac

from fastapi import HTTPException, Request

from app.core.config import settings


async def verify_whatsapp_signature(request: Request) -> None:
    """Verify the ``X-Hub-Signature-256`` header sent by Meta.

    When ``settings.WHATSAPP_APP_SECRET`` is *None* (development mode) the
    check is skipped entirely.  In production, a missing or invalid signature
    raises :class:`~fastapi.HTTPException` with status 401.
    """
    secret: str | None = settings.WHATSAPP_APP_SECRET
    if secret is None:
        return

    signature_header: str | None = request.headers.get("X-Hub-Signature-256")
    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")

    body: bytes = await request.body()
    expected_digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    expected_signature = f"sha256={expected_digest}"

    if not hmac.compare_digest(signature_header, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid WhatsApp signature")
