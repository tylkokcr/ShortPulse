"""Authentication on the render-progress WebSocket.

This endpoint was wide open. Starlette's HTTP middleware never sees a
WebSocket handshake, so REQUIRE_AUTH didn't apply to it: a probe against a
server with auth switched on still got a 101, meaning anyone who knew a
project id could watch someone else's render.

The handler is called directly with a stub socket rather than driven
through TestClient, which would need its own event loop and couldn't share
the database fixtures. What matters here is the accept/refuse decision, and
that is entirely in this function.
"""

from __future__ import annotations

import pytest

from app.api.routes.render import render_progress_socket
from app.services import project_store
from app.services.media_tokens import MediaTokenSigner

PROJECT = "11111111-1111-1111-1111-111111111111"
OWNER = "22222222-2222-2222-2222-222222222222"


class StubApp:
    def __init__(self, signer):
        self.state = type("S", (), {"media_signer": signer})()


class StubWebSocket:
    """Records what the handler did instead of speaking the protocol."""

    def __init__(self, signer):
        self.app = StubApp(signer)
        self.closed_with: int | None = None
        self.accepted = False

    async def close(self, code: int = 1000):
        self.closed_with = code

    async def accept(self):
        self.accepted = True

    async def receive_text(self):
        # One "message", then behave like the client hung up.
        from starlette.websockets import WebSocketDisconnect

        raise WebSocketDisconnect(1000)


@pytest.fixture
def signer():
    return MediaTokenSigner("socket-test-secret", ttl_s=900)


@pytest.fixture
def owned(monkeypatch):
    async def owner_of(project_id):
        return OWNER

    monkeypatch.setattr(project_store, "owner_of", owner_of)


@pytest.fixture
def unowned(monkeypatch):
    async def owner_of(project_id):
        return None

    monkeypatch.setattr(project_store, "owner_of", owner_of)


async def test_an_owned_project_refuses_a_socket_with_no_token(signer, owned):
    ws = StubWebSocket(signer)
    await render_progress_socket(ws, PROJECT, token=None)

    assert ws.closed_with == 1008
    assert not ws.accepted


async def test_an_owned_project_refuses_a_forged_token(signer, owned):
    forged, _ = MediaTokenSigner("not-our-secret").sign(PROJECT)
    ws = StubWebSocket(signer)
    await render_progress_socket(ws, PROJECT, token=forged)

    assert ws.closed_with == 1008


async def test_a_token_for_another_project_is_refused(signer, owned):
    other_token, _ = signer.sign("99999999-9999-9999-9999-999999999999")
    ws = StubWebSocket(signer)
    await render_progress_socket(ws, PROJECT, token=other_token)

    assert ws.closed_with == 1008


async def test_an_expired_token_is_refused(owned):
    expired_signer = MediaTokenSigner("socket-test-secret", ttl_s=-1)
    token, _ = expired_signer.sign(PROJECT)
    ws = StubWebSocket(MediaTokenSigner("socket-test-secret", ttl_s=900))
    await render_progress_socket(ws, PROJECT, token=token)

    assert ws.closed_with == 1008


async def test_a_valid_token_is_accepted(signer, owned):
    token, _ = signer.sign(PROJECT)
    ws = StubWebSocket(signer)
    await render_progress_socket(ws, PROJECT, token=token)

    assert ws.closed_with is None
    assert ws.accepted


async def test_a_self_hosted_project_needs_no_token(signer, unowned):
    """No owner means no accounts — the self-hosted install must keep its
    progress bar without inventing a credential it has no way to get."""
    ws = StubWebSocket(signer)
    await render_progress_socket(ws, PROJECT, token=None)

    assert ws.closed_with is None
    assert ws.accepted
