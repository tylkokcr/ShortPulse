"""WebSocket endpoint streaming real-time render progress for a project."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.connection_manager import connection_manager

router = APIRouter(tags=["render"])


@router.websocket("/ws/render/{project_id}")
async def render_progress_socket(websocket: WebSocket, project_id: str) -> None:
    await connection_manager.connect(project_id, websocket)
    try:
        while True:
            # Client doesn't need to send anything; this just keeps the
            # connection open and lets us detect disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        connection_manager.disconnect(project_id, websocket)
