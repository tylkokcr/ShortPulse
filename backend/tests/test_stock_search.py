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
    ffmpeg_binary = "ffmpeg"


async def test_a_blocked_provider_falls_through_to_the_next(tmp_path, monkeypatch):
    """The regression. A 403 from Pexels used to abort the whole render;
    Pixabay was configured and never got asked."""
    scene = Scene(
        index=0,
        duration_s=3.0,
        visual=SceneVisual(prompt="honey jar"),
        audio=SceneAudio(voiceover_line="line"),
    )

    async def blocked(query, api_key, target_height=1920, variant=0):
        raise httpx.HTTPStatusError(
            "403", request=httpx.Request("GET", "https://api.pexels.com"),
            response=httpx.Response(403),
        )

    calls = []

    async def works(query, api_key, target_height=1920, variant=0):
        calls.append(query)
        from app.engines import visual_engine

        return visual_engine.StockClip(
            url="https://example.test/clip.mp4",
            attribution=None,
        )

    async def fake_download(url, path, seconds=0, ffmpeg_binary="ffmpeg"):
        path.write_bytes(b"")

    monkeypatch.setattr("app.engines.visual_engine._search_pexels", blocked)
    monkeypatch.setattr("app.engines.visual_engine._search_pixabay", works)
    monkeypatch.setattr("app.engines.visual_engine._download_head", fake_download)

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

    async def blocked(query, api_key, target_height=1920, variant=0):
        raise httpx.ConnectError("down")

    monkeypatch.setattr("app.engines.visual_engine._search_pexels", blocked)
    monkeypatch.setattr("app.engines.visual_engine._search_pixabay", blocked)

    with pytest.raises(RuntimeError, match="No stock media provider"):
        await _fetch_stock_media(scene, tmp_path, _Settings())


# --------------------------------------------------------------------------
# Rendition choice — the single biggest lever on how long a stock render takes
# --------------------------------------------------------------------------


def _file(width: int, height: int) -> dict:
    return {"width": width, "height": height, "link": f"https://x/{width}x{height}.mp4"}


LADDER = [
    _file(2160, 3840),
    _file(1440, 2560),
    _file(1080, 1920),
    _file(720, 1280),
    _file(360, 640),
]


def test_the_smallest_rendition_that_covers_the_render_is_chosen():
    """Measured on a real clip: the 4K master is 33MB and 26s to fetch,
    the 1080 rendition 7MB and 3s — and ffmpeg scales the 4K back down to
    1080 anyway."""
    from app.engines.visual_engine import _pick_rendition

    assert _pick_rendition(LADDER, 1920)["height"] == 1920


def test_a_smaller_render_takes_a_smaller_rendition():
    from app.engines.visual_engine import _pick_rendition

    assert _pick_rendition(LADDER, 1080)["height"] == 1280


def test_nothing_tall_enough_falls_back_to_the_largest_available():
    from app.engines.visual_engine import _pick_rendition

    assert _pick_rendition([_file(360, 640), _file(540, 960)], 1920)["height"] == 960


def test_portrait_renditions_win_over_bigger_landscape_ones():
    """A landscape source is centre-cropped to a vertical frame and loses
    most of its width, so a smaller portrait file is the better source."""
    from app.engines.visual_engine import _pick_rendition

    mixed = [_file(3840, 2160), _file(1080, 1920)]
    chosen = _pick_rendition(mixed, 1920)

    assert (chosen["width"], chosen["height"]) == (1080, 1920)


# --------------------------------------------------------------------------
# Variants — what makes re-rolling a stock scene worth a credit
#
# The search is a deterministic function of its query, so without this a
# re-roll re-downloads the identical clip and the customer pays for a
# byte-identical result. That failure is invisible from the outside: the
# request succeeds, the video is unchanged.
# --------------------------------------------------------------------------


def _pexels_page(count: int) -> dict:
    return {
        "videos": [
            {
                "url": f"https://www.pexels.com/video/{i}/",
                "user": {"name": f"author {i}", "url": f"https://x/{i}"},
                "video_files": [{"width": 1080, "height": 1920, "link": f"https://x/{i}.mp4"}],
            }
            for i in range(count)
        ]
    }


def _pixabay_page(count: int) -> dict:
    return {
        "hits": [
            {
                "pageURL": f"https://pixabay.com/videos/{i}/",
                "user": f"author {i}",
                "user_id": i,
                "videos": {"medium": {"url": f"https://x/{i}.mp4"}},
            }
            for i in range(count)
        ]
    }


async def _pexels(monkeypatch, page: dict, variant: int):
    from app.engines import visual_engine

    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=page)

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def client(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr(visual_engine.httpx, "AsyncClient", client)
    clip = await visual_engine._search_pexels("honey jar", "key", 1920, variant)
    return clip, captured


async def test_two_variants_return_two_different_clips(monkeypatch):
    """The property the whole feature rests on."""
    first, _ = await _pexels(monkeypatch, _pexels_page(5), 0)
    second, _ = await _pexels(monkeypatch, _pexels_page(5), 1)

    assert first.attribution.source_url != second.attribution.source_url


async def test_the_search_asks_for_a_page_deep_enough_to_have_variants(monkeypatch):
    """One request either way — the variant indexes into results already
    paid for, rather than costing an extra round trip."""
    from app.engines import visual_engine

    _, captured = await _pexels(monkeypatch, _pexels_page(5), 0)

    assert int(captured["params"]["per_page"]) == visual_engine._STOCK_VARIANTS


async def test_a_variant_past_the_end_wraps_instead_of_failing(monkeypatch):
    """A niche query with two matches, asked for the fifth. A second-best
    clip beats no clip, and beats an exception in the middle of a paid
    re-roll."""
    clip, _ = await _pexels(monkeypatch, _pexels_page(2), 4)

    assert clip is not None
    assert clip.attribution.source_url == "https://www.pexels.com/video/0/"


async def test_an_empty_result_is_still_none(monkeypatch):
    """So _fetch_stock_media falls through to the next provider rather
    than dividing by zero on the wrap."""
    clip, _ = await _pexels(monkeypatch, {"videos": []}, 3)

    assert clip is None


async def test_pixabay_varies_too(monkeypatch):
    """Both providers, or a re-roll behaves differently depending on which
    one happens to answer."""
    from app.engines import visual_engine

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_pixabay_page(4))

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def client(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr(visual_engine.httpx, "AsyncClient", client)

    first = await visual_engine._search_pixabay("honey jar", "key", 1920, 0)
    second = await visual_engine._search_pixabay("honey jar", "key", 1920, 1)

    assert first.attribution.source_url != second.attribution.source_url
