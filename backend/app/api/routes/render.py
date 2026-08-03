"""WebSocket endpoint streaming real-time render progress for a project."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.services import project_store
from app.services.connection_manager import connection_manager
from app.services.media_tokens import InvalidMediaToken

logger = logging.getLogger(__name__)

router = APIRouter(tags=["render"])


@router.websocket("/ws/render/{project_id}")
async def render_progress_socket(
    websocket: WebSocket, project_id: str, token: str | None = None
) -> None:
    """Stream render progress for a project.

    Authentication happens here rather than in the middleware, because
    Starlette's HTTP middleware never sees a WebSocket handshake — which is
    how this endpoint stayed wide open even with REQUIRE_AUTH on, letting
    anyone who knew a project id watch its progress.

    A browser can't put an Authorization header on a WebSocket either, so
    the credential is the same short-lived signed token used for video
    URLs, obtained from /api/projects/{id}/stream-token.

    Unowned projects stay open: that's the self-hosted install, where there
    are no accounts to check against.
    """
    owner = await project_store.owner_of(project_id)
    if owner is not None:
        signer = websocket.app.state.media_signer
        try:
            if token is None:
                raise InvalidMediaToken("No token supplied")
            signer.verify(project_id, token)
        except InvalidMediaToken as exc:
            logger.info("Refused progress socket for %s: %s", project_id, exc)
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

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
