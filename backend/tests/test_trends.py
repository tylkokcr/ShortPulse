"""The trends section: what is collected, what the analysis may say, and
when it is written again."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from app.services import trends

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)


def _item(vid, title, hours_old, views, seconds=45, tags=None):
    return {
        "id": vid,
        "snippet": {
            "title": title,
            "channelTitle": "ch",
            "tags": tags or [],
            "publishedAt": (NOW - timedelta(hours=hours_old)).isoformat().replace("+00:00", "Z"),
            "thumbnails": {"medium": {"url": f"https://i.ytimg.com/{vid}.jpg"}},
        },
        "statistics": {"viewCount": str(views)},
        "contentDetails": {"duration": f"PT{seconds // 60}M{seconds % 60}S"},
    }


def test_rising_is_measured_by_views_per_hour_not_views():
    old_giant = trends.video_from_api(_item("a", "Old", 24 * 30, 10_000_000, 600), "all", NOW)
    young = trends.video_from_api(_item("b", "Young", 5, 500_000), "all", NOW)
    assert young["views_per_hour"] > old_giant["views_per_hour"]
    assert young["short"] and not old_giant["short"]


async def test_collect_reads_every_chart_once_and_the_songs():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if "marketingtools.apple.com" in str(request.url):
            return httpx.Response(200, json={"feed": {"results": [{"name": "Song", "artistName": "Artist"}]}})
        category = request.url.params.get("videoCategoryId", "")
        if category == "20":
            return httpx.Response(404, json={})
        return httpx.Response(
            200, json={"items": [_item("same", "Twice", 3, 3000), _item(f"v{category}", "x", 2, 10)]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        data = await trends.collect("TR", "key", client)
    assert sum("youtube" in u for u in seen) == 5
    assert [v["id"] for v in data["videos"]].count("same") == 1
    assert data["songs"] == [{"title": "Song", "artist": "Artist", "url": None, "artwork": None}]


def test_the_analysis_cannot_point_at_videos_that_are_not_there():
    snapshot = {"videos": [trends.video_from_api(_item("real", "Real", 3, 3000), "all", NOW)]}
    raw = {
        "summary": "s",
        "trends": [
            {
                "name": "T",
                "kind": "nonsense",
                "status": "exploding",
                "why": "w",
                "examples": ["real", "invented"],
                "ideas": ["i1", "i2", "i3", "i4"],
                "fits": "?",
            },
            {"name": "", "why": "no name"},
            "not a dict",
        ],
    }
    report = trends.validate_report(raw, snapshot)
    [t] = report["trends"]
    assert [e["id"] for e in t["examples"]] == ["real"]
    assert (t["kind"], t["status"], t["fits"]) == ("topic", "rising", "both")
    assert len(t["ideas"]) == 3


async def test_a_report_is_written_once_and_reused_until_it_is_stale(monkeypatch):
    from types import SimpleNamespace

    trends.configure(None)
    calls = {"collect": 0, "analyse": 0}

    async def collect(region, key, client=None):
        calls["collect"] += 1
        return {"region": region, "videos": [], "songs": []}

    async def analyse(snapshot, lang, llm, previous):
        calls["analyse"] += 1
        return {"summary": "s", "trends": [], "version": trends.PROMPT_VERSION}

    monkeypatch.setattr(trends, "collect", collect)
    monkeypatch.setattr(trends, "analyse", analyse)
    settings = SimpleNamespace(
        youtube_api_key="k",
        llm_provider="ollama",
        llm_model="m",
        ollama_base_url="http://x",
        openai_api_key=None,
    )
    await trends.get_report("TR", "tr", settings)
    await trends.get_report("TR", "tr", settings)
    assert calls == {"collect": 1, "analyse": 1}
    await trends.get_report("TR", "en", settings)  # another language: another analysis
    assert calls == {"collect": 1, "analyse": 2}
    # A report written by an older prompt is rewritten, fresh or not.
    monkeypatch.setattr(trends, "PROMPT_VERSION", trends.PROMPT_VERSION + 1)
    await trends.get_report("TR", "en", settings)
    assert calls == {"collect": 1, "analyse": 3}


async def test_the_api_offers_only_its_regions(monkeypatch):
    from fastapi import FastAPI

    from app.api.routes import trends as route
    from app.core.config import get_settings
    from tests.test_uploads import _client

    app = FastAPI()
    app.include_router(route.router)
    monkeypatch.setattr(get_settings(), "youtube_api_key", None)
    async with _client(app) as client:
        assert (await client.get("/api/trends/regions")).json()["enabled"] is False
        assert (await client.get("/api/trends?region=TR")).status_code == 404
        monkeypatch.setattr(get_settings(), "youtube_api_key", "k")
        assert (await client.get("/api/trends?region=ZZ")).status_code == 422
