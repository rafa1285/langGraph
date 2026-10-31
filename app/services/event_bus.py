"""Real-time WebSocket event bus managing live client connections and project events."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections per project and broadcasts events in real-time."""

    def __init__(self) -> None:
        """Initialize connection manager with active connection registry."""
        self._active_connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, project_id: str, websocket: WebSocket) -> None:
        """Accept WebSocket connection and register to project channel."""
        await websocket.accept()
        async with self._lock:
            if project_id not in self._active_connections:
                self._active_connections[project_id] = []
            self._active_connections[project_id].append(websocket)
        logger.info("Cliente WebSocket conectado al canal del proyecto %s", project_id)

    async def disconnect(self, project_id: str, websocket: WebSocket) -> None:
        """Remove WebSocket connection from project channel."""
        async with self._lock:
            if project_id in self._active_connections:
                if websocket in self._active_connections[project_id]:
                    self._active_connections[project_id].remove(websocket)
                if not self._active_connections[project_id]:
                    del self._active_connections[project_id]
        logger.info("Cliente WebSocket desconectado del canal del proyecto %s", project_id)

    async def broadcast(
        self,
        project_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """Broadcast JSON event message to all clients connected to project_id channel."""
        message = {
            "project_id": project_id,
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": data,
        }
        text_payload = json.dumps(message, ensure_ascii=False, default=str)

        async with self._lock:
            sockets = list(self._active_connections.get(project_id, []))

        dead_sockets: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_text(text_payload)
            except Exception as exc:
                logger.warning("Error enviando WebSocket a cliente de %s: %s", project_id, exc)
                dead_sockets.append(ws)

        if dead_sockets:
            async with self._lock:
                for dead in dead_sockets:
                    conns = self._active_connections.get(project_id, [])
                    if dead in conns:
                        conns.remove(dead)
                if (
                    project_id in self._active_connections
                    and not self._active_connections[project_id]
                ):
                    del self._active_connections[project_id]


event_bus = ConnectionManager()
