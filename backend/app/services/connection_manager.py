"""Tracks WebSocket subscribers per project and broadcasts render progress."""

from __future__ import annotations

import logging

from fastapi import WebSocket

from app.schemas.project import RenderProgress

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[WebSocket]] = {}
        # The latest progress of each project, sent to whoever connects
        # after it. Without it a page opened — or a socket reconnected —
        # in the middle of a long step said "Starting..." until the next
        # message, and a transcription of an hour of audio sends none for
        # most of the time it takes.
        self._last: dict[str, dict] = {}

    async def connect(self, project_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._subscribers.setdefault(project_id, set()).add(websocket)
        last = self._last.get(project_id)
        if last is not None:
            try:
                await websocket.send_json(last)
            except Exception:
                logger.debug("Could not replay progress to a new socket for %s", project_id)

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
        if progress.stage in ("done", "failed"):
            # Finished: the project row says so from here on, and a
            # replayed "done" would race the page's own reload.
            self._last.pop(progress.project_id, None)
        else:
            self._last[progress.project_id] = payload
        for websocket in subscribers:
            try:
                await websocket.send_json(payload)
            except Exception:
                logger.debug("Dropping stale websocket for project %s", progress.project_id)
                stale.append(websocket)
        for websocket in stale:
            subscribers.discard(websocket)


connection_manager = ConnectionManager()
