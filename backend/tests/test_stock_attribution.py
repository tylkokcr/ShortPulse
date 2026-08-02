"""Stock footage attribution.

Pexels' API terms require a prominent link back to Pexels from any
application using the API, and crediting the photographer where possible.
That makes attribution a licence condition, not a nicety — shipping stock
footage without it is using the clips outside their terms.

The failure mode these tests guard is quiet: the pipeline works perfectly,
the video renders, and the only thing missing is the credit. Nothing
downstream breaks, so nothing else would notice.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.engines import visual_engine
from app.schemas.project import Scene, SceneAudio, SceneVisual, StockAttribution

# Trimmed to the fields we read, but with the nesting and key names of a
# real response — the point is to fail if the provider's shape assumptions
# are wrong.
PEXELS_RESPONSE = {
    "videos": [
        {
            "id": 3571264,
            "url": "https://www.pexels.com/video/waves-crashing-3571264/",
            "user": {
                "id": 1437723,
                "name": "Ruvim Miksanskiy",
                "url": "https://www.pexels.com/@digitech",
            },
            "video_files": [
                {"link": "https://player.pexels.com/…/hd.mp4", "width": 1080, "height": 1920},
                {"link": "https://player.pexels.com/…/sd.mp4", "width": 640, "height": 360},
            ],
        }
    ]
}

PIXABAY_RESPONSE = {
    "hits": [
        {
            "id": 125,
            "pageURL": "https://pixabay.com/videos/id-125/",
            "user": "CoverrFreeFootage",
            "user_id": 1234,
            "videos": {"medium": {"url": "https://cdn.pixabay.com/video/…/medium.mp4"}},
        }
    ]
}


def _stub(payload: dict) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(200, content=json.dumps(payload)))


@pytest.fixture
def scene() -> Scene:
    return Scene(
        index=0,
        duration_s=4,
        visual=SceneVisual(prompt="ocean waves"),
        audio=SceneAudio(voiceover_line="the sea is vast"),
    )


class Settings:
    def __init__(self, pexels=None, pixabay=None):
        self.pexels_api_key = pexels
        self.pixabay_api_key = pixabay


@pytest.fixture(autouse=True)
def _no_real_downloads(monkeypatch, tmp_path):
    async def fake_download(url: str, output_path: Path) -> None:
        output_path.write_bytes(b"fake mp4")

    monkeypatch.setattr(visual_engine, "_download", fake_download)


def _serve(monkeypatch, payload: dict) -> None:
    """Make visual_engine's httpx.AsyncClient() return a client backed by a
    canned response. The real class is captured first, or the replacement
    would construct itself."""
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(transport=_stub(payload))
    )


@pytest.fixture
def pexels(monkeypatch):
    _serve(monkeypatch, PEXELS_RESPONSE)


@pytest.fixture
def pixabay(monkeypatch):
    _serve(monkeypatch, PIXABAY_RESPONSE)


async def test_a_pexels_clip_records_who_to_credit(scene, tmp_path, pexels):
    await visual_engine._fetch_stock_media(scene, tmp_path, Settings(pexels="key"))

    credit = scene.visual.attribution
    assert credit is not None, "clip downloaded with no attribution — licence violation"
    assert credit.provider == "Pexels"
    assert credit.provider_url == "https://www.pexels.com"
    assert credit.author == "Ruvim Miksanskiy"
    assert credit.author_url == "https://www.pexels.com/@digitech"
    assert credit.source_url == "https://www.pexels.com/video/waves-crashing-3571264/"


async def test_a_pixabay_clip_records_who_to_credit(scene, tmp_path, pixabay):
    await visual_engine._fetch_stock_media(scene, tmp_path, Settings(pixabay="key"))

    credit = scene.visual.attribution
    assert credit is not None
    assert credit.provider == "Pixabay"
    assert credit.author == "CoverrFreeFootage"
    assert credit.source_url == "https://pixabay.com/videos/id-125/"


async def test_the_portrait_file_is_still_chosen(scene, tmp_path, pexels, monkeypatch):
    """Attribution must not have changed which file gets picked — these
    are vertical videos."""
    captured = {}

    async def capture(url: str, output_path: Path) -> None:
        captured["url"] = url
        output_path.write_bytes(b"x")

    monkeypatch.setattr(visual_engine, "_download", capture)
    await visual_engine._fetch_stock_media(scene, tmp_path, Settings(pexels="key"))

    assert captured["url"].endswith("hd.mp4")  # the 1080x1920 one


async def test_a_provider_with_no_author_still_credits_the_provider():
    """Pexels' link requirement stands even when the photographer field is
    missing, so attribution must never be dropped wholesale."""
    credit = StockAttribution(provider="Pexels", provider_url="https://www.pexels.com")
    assert credit.as_text() == "Video from Pexels"


async def test_credit_line_is_pasteable():
    credit = StockAttribution(
        provider="Pexels", provider_url="https://www.pexels.com", author="Ruvim Miksanskiy"
    )
    assert credit.as_text() == "Video by Ruvim Miksanskiy on Pexels"


async def test_ai_generated_visuals_have_nothing_to_credit(scene):
    """Only stock scenes carry attribution; a credit on an AI-generated
    frame would be a false claim about where it came from."""
    assert scene.visual.attribution is None
