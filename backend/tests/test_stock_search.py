"""Stock search query construction.

These pin a failure that cost whole renders: Pexels sits behind Cloudflare,
and a long natural-language visual prompt intermittently came back as a 403
HTML challenge page instead of an API response. `raise_for_status` turned
that into an exception that propagated out of the pipeline, so one blocked
scene threw away every scene rendered before it.
"""

from __future__ import annotations

import httpx
import pytest

from app.engines.visual_engine import _fetch_stock_media, stock_search_terms
from app.schemas.project import Scene, SceneAudio, SceneVisual


def test_a_descriptive_sentence_becomes_a_keyword_query():
    terms = stock_search_terms(
        "a large-scale model or diagram of the ISS, with various modules and solar panels labeled"
    )
    assert terms == "large-scale model diagram iss modules solar"


def test_filler_and_punctuation_are_dropped():
    assert stock_search_terms("A close-up shot of a honey jar, warm golden lighting") == (
        "close-up honey jar warm golden lighting"
    )


def test_a_prompt_made_entirely_of_stopwords_still_searches_for_something():
    """An empty query returns Pexels' unfiltered feed — any clip at all,
    unrelated to the scene. Falling back to the raw prompt at least keeps
    the search on topic."""
    assert stock_search_terms("the of and with") == "the of and with"


class _Settings:
    pexels_api_key = "pexels-key"
    pixabay_api_key = "pixabay-key"


async def test_a_blocked_provider_falls_through_to_the_next(tmp_path, monkeypatch):
    """The regression. A 403 from Pexels used to abort the whole render;
    Pixabay was configured and never got asked."""
    scene = Scene(
        index=0,
        duration_s=3.0,
        visual=SceneVisual(prompt="honey jar"),
        audio=SceneAudio(voiceover_line="line"),
    )

    async def blocked(query, api_key):
        raise httpx.HTTPStatusError(
            "403", request=httpx.Request("GET", "https://api.pexels.com"),
            response=httpx.Response(403),
        )

    calls = []

    async def works(query, api_key):
        calls.append(query)
        from app.engines import visual_engine

        return visual_engine.StockClip(
            url="https://example.test/clip.mp4",
            attribution=None,
        )

    async def fake_download(url, path):
        path.write_bytes(b"")

    monkeypatch.setattr("app.engines.visual_engine._search_pexels", blocked)
    monkeypatch.setattr("app.engines.visual_engine._search_pixabay", works)
    monkeypatch.setattr("app.engines.visual_engine._download", fake_download)

    path = await _fetch_stock_media(scene, tmp_path, _Settings())

    assert path.exists()
    assert calls == ["honey jar"], "Pixabay was never reached after Pexels was blocked"


async def test_every_provider_failing_is_still_an_error(tmp_path, monkeypatch):
    scene = Scene(
        index=0,
        duration_s=3.0,
        visual=SceneVisual(prompt="honey jar"),
        audio=SceneAudio(voiceover_line="line"),
    )

    async def blocked(query, api_key):
        raise httpx.ConnectError("down")

    monkeypatch.setattr("app.engines.visual_engine._search_pexels", blocked)
    monkeypatch.setattr("app.engines.visual_engine._search_pixabay", blocked)

    with pytest.raises(RuntimeError, match="No stock media provider"):
        await _fetch_stock_media(scene, tmp_path, _Settings())
