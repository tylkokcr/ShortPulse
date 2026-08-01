"""Tracks WebSocket subscribers per project and broadcasts render progress."""

from __future__ import annotations

import logging

from fastapi import WebSocket

from app.schemas.project import RenderProgress

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[WebSocket]] = {}

    async def connect(self, project_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._subscribers.setdefault(project_id, set()).add(websocket)

    def disconnect(self, project_id: str, websocket: WebSocket) -> None:
        subscribers = self._subscribers.get(project_id)
        if subscribers:
            subscribers.discard(websocket)
            if not subscribers:
                self._subscribers.pop(project_id, None)

    async def broadcast(self, progress: RenderProgress) -> None:
        subscribers = self._subscribers.get(progress.project_id, set())
        stale: list[WebSocket] = []
        payload = progress.model_dump(mode="json")
        for websocket in subscribers:
            try:
                await websocket.send_json(payload)
            except Exception:
                logger.debug("Dropping stale websocket for project %s", progress.project_id)
                stale.append(websocket)
        for websocket in stale:
            subscribers.discard(websocket)


connection_manager = ConnectionManager()
