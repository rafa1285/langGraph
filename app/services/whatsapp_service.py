"""WhatsApp Cloud API transport service (Meta Graph API v21.0)."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings

_BASE_URL = "https://graph.facebook.com/v21.0"
_MAX_CHUNK = 4000


class WhatsAppService:
    """Transport layer for sending and receiving WhatsApp messages via Meta Cloud API."""

    def __init__(
        self,
        phone_number_id: str | None = None,
        access_token: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._phone_number_id: str | None = phone_number_id
        self._access_token: str | None = access_token
        self._is_default_client: bool = http_client is None
        self._client: httpx.AsyncClient = http_client or httpx.AsyncClient()

    @property
    def phone_number_id(self) -> str:
        """Return explicitly passed phone_number_id or fall back to current settings."""
        return self._phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID or ""

    @property
    def access_token(self) -> str:
        """Return explicitly passed access_token or fall back to current settings."""
        return self._access_token or settings.WHATSAPP_ACCESS_TOKEN or ""

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    async def send_text_message(self, to: str, body: str) -> dict[str, Any]:
        """Send a text message to *to*, chunking at 4 000 chars if necessary.

        Returns the last API response dict.  If multiple chunks are sent, the
        response from the final chunk is returned.
        """
        pid = self.phone_number_id
        tok = self.access_token

        # Graceful fallback when credentials are not configured in local environment
        if (not pid or not tok) and self._is_default_client:
            return {
                "messaging_product": "whatsapp",
                "contacts": [{"input": to, "wa_id": to}],
                "messages": [{"id": f"wamid.local_mock_{to}"}],
            }

        if body:
            chunks: list[str] = [body[i : i + _MAX_CHUNK] for i in range(0, len(body), _MAX_CHUNK)]
        else:
            chunks = [""]
        result: dict[str, Any] = {}
        url = f"{_BASE_URL}/{pid}/messages"
        headers = {
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json",
        }
        for chunk in chunks:
            payload: dict[str, Any] = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": chunk},
            }
            try:
                response = await self._client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
            except httpx.HTTPError:
                if self._is_default_client:
                    return {
                        "messaging_product": "whatsapp",
                        "messages": [{"id": f"wamid.mock_local_{to}"}],
                    }
                raise
        return result

    # ------------------------------------------------------------------
    # Inbound
    # ------------------------------------------------------------------

    def parse_incoming_message(self, webhook_body: dict[str, Any]) -> dict[str, Any] | None:
        """Extract the first text message from a Meta webhook payload.

        Returns a dict with keys ``sender``, ``text``, ``message_id``,
        ``timestamp`` and ``type``, or *None* when the payload contains no
        processable message.
        """
        try:
            entry: list[Any] = webhook_body.get("entry", [])
            if not entry:
                return None
            changes: list[Any] = entry[0].get("changes", [])
            if not changes:
                return None
            value: dict[str, Any] = changes[0].get("value", {})
            messages: list[Any] = value.get("messages", [])
            if not messages:
                return None
            message: dict[str, Any] = messages[0]
            msg_type: str = message.get("type", "")
            text: str = ""
            if msg_type == "text":
                text = message.get("text", {}).get("body", "")
            return {
                "sender": message.get("from", ""),
                "text": text,
                "message_id": message.get("id", ""),
                "timestamp": message.get("timestamp", ""),
                "type": msg_type,
            }
        except (KeyError, IndexError, TypeError):
            return None
