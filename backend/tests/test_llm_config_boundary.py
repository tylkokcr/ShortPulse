"""The LLM block on a request is not the LLM the server runs.

`LLMConfig.base_url` is an address this server then POSTs to. Left as the
client sent it, a request can aim it at anything reachable from inside the
network — cloud metadata on a deployed host, another container, a database
admin port — and read what came back out of the project's `error` field.

Verified exploitable before the fix: a request naming a local listener had
the server deliver three POSTs to it (three, because script generation
retries). This pins the boundary that closed it.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi import FastAPI

from app.api.routes import projects as projects_route
from app.core import config as core_config
from app.schemas.project import LLMProvider
from app.services import project_store


class _Queue:
    def __init__(self):
        self.submitted = []

    async def submit(self, project):
        self.submitted.append(project)


@pytest.fixture
def api(monkeypatch):
    settings = core_config.get_settings()
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "llm_model", "llama3")
    monkeypatch.setattr(settings, "ollama_base_url", "http://ollama.internal:11434")
    monkeypatch.setattr(settings, "openai_api_key", None)
    project_store.configure(None)

    app = FastAPI()
    app.include_router(projects_route.router)
    app.state.db_pool = None
    queue = _Queue()
    app.state.render_queue = queue
    return app, queue


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_a_client_cannot_choose_where_the_server_sends_the_prompt(api):
    """The vulnerability itself: an attacker-supplied base_url became a
    server-side request to that address."""
    app, queue = api
    async with _client(app) as client:
        response = await client.post(
            "/api/projects",
            json={
                "topic": "ssrf",
                "llm": {
                    "provider": "ollama",
                    "base_url": "http://169.254.169.254",
                    "model": "anything",
                },
            },
        )

    assert response.status_code == 201
    queued = queue.submitted[0].config.llm
    assert queued.base_url == "http://ollama.internal:11434"
    assert queued.model == "llama3"


async def test_a_client_cannot_swap_the_provider(api):
    """Choosing the provider would let a request route the prompt — and
    the server's key — somewhere else entirely."""
    app, queue = api
    async with _client(app) as client:
        await client.post(
            "/api/projects",
            json={"topic": "x", "llm": {"provider": "openai", "api_key": "sk-attacker"}},
        )

    queued = queue.submitted[0].config.llm
    assert queued.provider == LLMProvider.OLLAMA
    assert queued.api_key is None


async def test_the_servers_own_key_is_what_reaches_the_provider(api, monkeypatch):
    app, queue = api
    monkeypatch.setattr(core_config.get_settings(), "llm_provider", "openai")
    monkeypatch.setattr(core_config.get_settings(), "openai_api_key", "sk-server-side")

    async with _client(app) as client:
        await client.post("/api/projects", json={"topic": "x"})

    queued = queue.submitted[0].config.llm
    assert queued.provider == LLMProvider.OPENAI
    assert queued.api_key == "sk-server-side"


async def test_temperature_is_still_the_callers_to_set(api):
    """Not everything on the block is dangerous — temperature changes the
    writing, not where the request goes, so it survives."""
    app, queue = api
    async with _client(app) as client:
        await client.post(
            "/api/projects", json={"topic": str(uuid.uuid4()), "llm": {"temperature": 0.2}}
        )

    assert queue.submitted[0].config.llm.temperature == 0.2
