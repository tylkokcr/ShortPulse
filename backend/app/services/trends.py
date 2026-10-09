"""What is catching on right now, per region — and what to make of it.

Three steps, each kept apart so each can be tested alone:

1. **Collect** (once a day per region): the platforms' own official data.
   YouTube Data API most-popular charts — overall and for music, sports,
   gaming and entertainment — and Apple's public most-played songs chart.
   Nothing is scraped. TikTok, the one source that would add most, has no
   API open to a product like this, and its terms forbid scraping it.
2. **Measure**: popularity alone says what is big, not what is moving. A
   video's views per hour since it was published says how fast it is
   rising, which is what a trend is.
3. **Analyse** (every other day, per region and language): a model groups
   the fastest risers into a handful of trends — a topic, a format, a
   sound — says why each is working and whether it is rising, at its peak
   or fading, and turns each into ideas for the two places the studio
   makes videos: from a topic, and from the user's own clips.

Trends come and go in days to a few weeks — sounds and memes fastest,
topics and formats a little slower — so the data is refreshed daily and
the analysis every other day, and each trend carries its own status
rather than the whole page carrying one date.

A scheduler in the API process does the collecting. One worker runs the
API, so one loop is enough; a second process would only collect twice.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import httpx

from app.engines import script_engine
from app.schemas.project import LLMConfig, LLMProvider

logger = logging.getLogger(__name__)

# Regions offered. Each is a market both YouTube's charts and Apple's
# cover; the page names them in the reader's language itself.
REGIONS = (
    "TR",
    "US",
    "GB",
    "DE",
    "PL",
    "FR",
    "ES",
    "IT",
    "NL",
    "BR",
    "MX",
    "IN",
    "JP",
    "KR",
    "SA",
    "AE",
)
LANGS = ("en", "tr", "pl", "de")
_LANG_NAMES = {"en": "English", "tr": "Turkish", "pl": "Polish", "de": "German"}

# YouTube video categories charted on top of the overall one.
_CATEGORIES = {"": "all", "10": "music", "17": "sports", "20": "gaming", "24": "entertainment"}
_YOUTUBE = "https://www.googleapis.com/youtube/v3/videos"
_APPLE = "https://rss.marketingtools.apple.com/api/v2/{cc}/music/most-played/25/songs.json"

DATA_MAX_AGE = timedelta(hours=24)
REPORT_MAX_AGE = timedelta(hours=48)
KEEP_SNAPSHOTS = timedelta(days=30)
# How many of the fastest risers the model reads, and how many trends it
# may return.
_ANALYSE_TOP = 60
# Bumped whenever the prompt changes, so reports written by the old one are
# rewritten instead of being served for two more days.
PROMPT_VERSION = 2
_MAX_TRENDS = 8


# ---------------------------------------------------------------------------
# Collect
# ---------------------------------------------------------------------------


def _iso_seconds(duration: str) -> int:
    """'PT1M5S' -> 65."""
    match = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration or "")
    if not match:
        return 0
    d, h, m, s = (int(x) if x else 0 for x in match.groups())
    return ((d * 24 + h) * 60 + m) * 60 + s


def video_from_api(item: dict, category: str, now: datetime) -> dict | None:
    """One video, as the analysis reads it."""
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    try:
        published = datetime.fromisoformat(str(snippet["publishedAt"]).replace("Z", "+00:00"))
        views = int(stats.get("viewCount", 0))
    except (KeyError, ValueError):
        return None
    hours = max((now - published).total_seconds() / 3600, 1.0)
    seconds = _iso_seconds((item.get("contentDetails") or {}).get("duration", ""))
    thumbs = snippet.get("thumbnails") or {}
    thumb = (thumbs.get("medium") or thumbs.get("high") or thumbs.get("default") or {}).get("url")
    return {
        "id": item.get("id"),
        "title": str(snippet.get("title", ""))[:160],
        "channel": str(snippet.get("channelTitle", ""))[:80],
        "tags": [str(t)[:30] for t in (snippet.get("tags") or [])[:8]],
        "category": category,
        "views": views,
        "views_per_hour": round(views / hours),
        "age_hours": round(hours),
        "short": 0 < seconds <= 180,
        "thumbnail": thumb,
    }


async def collect(region: str, api_key: str, client: httpx.AsyncClient | None = None) -> dict:
    """Today's data for one region: YouTube charts and Apple's songs."""
    now = datetime.now(UTC)
    own = client is None
    client = client or httpx.AsyncClient(timeout=20, follow_redirects=True)
    try:
        videos: dict[str, dict] = {}
        for category_id, category in _CATEGORIES.items():
            params: dict[str, str | int] = {
                "part": "snippet,statistics,contentDetails",
                "chart": "mostPopular",
                "regionCode": region,
                "maxResults": 50,
                "key": api_key,
            }
            if category_id:
                params["videoCategoryId"] = category_id
            response = await client.get(_YOUTUBE, params=params)
            if response.status_code == 404:
                # A category with no chart in this region.
                continue
            response.raise_for_status()
            for item in response.json().get("items", []):
                video = video_from_api(item, category, now)
                if video and video["id"] and video["id"] not in videos:
                    videos[video["id"]] = video
        songs: list[dict] = []
        try:
            response = await client.get(_APPLE.format(cc=region.lower()))
            if response.status_code == 200:
                for r in response.json().get("feed", {}).get("results", [])[:25]:
                    songs.append(
                        {
                            "title": str(r.get("name", ""))[:120],
                            "artist": str(r.get("artistName", ""))[:80],
                            "url": r.get("url"),
                            "artwork": r.get("artworkUrl100"),
                        }
                    )
        except (httpx.HTTPError, ValueError):
            logger.warning("Apple chart for %s unavailable", region)
        return {
            "region": region,
            "fetched_at": now.isoformat(),
            "videos": list(videos.values()),
            "songs": songs,
        }
    finally:
        if own:
            await client.aclose()


# ---------------------------------------------------------------------------
# Analyse
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a short-video strategist for a tool that can make exactly two kinds \
of video, and nothing else:

1. "generate": a narrated 30-60 second short from a topic — a voiceover \
over stock footage or AI-made stills, with captions. Good for facts, \
explainers, stories, lists, history, curiosities, "did you know", \
motivation. It cannot show real people, real matches, scenes from a series \
or a film, or anyone's real footage.
2. "edit": the user's own clips cut to music, beat by beat. Good for sports \
moments and players, fan edits, travel, fitness, dance, gaming highlights, \
cars — anything the user can have footage of.

You read what is rising on YouTube in one country right now. Find the \
trends a creator could ride with this tool this week. A trend is a pattern \
shared by several risers — a subject, a person or team, a format, a song — \
not one video.

The rule that matters most: never suggest copying the trending thing \
itself. Turn it into an angle the tool can actually make. A TV series \
trending is not "make a video of the series" — it is a generate idea about \
the real-world subject behind it ("5 facts about the 90s Istanbul \
underworld"). A player trending is an edit idea ("his best skills this \
season, cut to a rising song"). Drop a trend outright when no honest angle \
exists: politics, news about private people, a song's own music video with \
nothing around it, anything only big because the channel is big.

For each trend give: a short name; its kind (topic, format, sound or \
person); its status (rising if young videos are climbing fast, peak if it is \
everywhere, fading if the videos are old and slowing); one sentence on why \
it is working; the ids of up to three example videos from the list; three \
ideas, each one a ready-to-use topic or edit brief for this tool; and \
whether the ideas suit "generate", "edit" or "both".

Return JSON of this exact shape:
{"summary": "<two sentences>", "trends": [{"name": "...", "kind": "...", \
"status": "...", "why": "...", "examples": ["<video id>"], "ideas": ["..."], \
"fits": "generate|edit|both"}]}"""


def _risers(snapshot: dict) -> list[dict]:
    videos = sorted(snapshot.get("videos", []), key=lambda v: -v.get("views_per_hour", 0))
    return videos[:_ANALYSE_TOP]


def analysis_prompt(snapshot: dict, lang: str, previous: list[str]) -> str:
    lines = [
        f"[{v['id']}] {v['title']} — {v['channel']} | {v['category']}"
        f"{' | Short' if v.get('short') else ''} | {v['views_per_hour']}/h over {v['age_hours']}h"
        f"{' | tags: ' + ', '.join(v['tags'][:5]) if v.get('tags') else ''}"
        for v in _risers(snapshot)
    ]
    songs = [f"{i + 1}. {s['title']} — {s['artist']}" for i, s in enumerate(snapshot.get("songs", [])[:15])]
    seen = (
        "\n\nLast time the trends were: "
        + "; ".join(previous[:_MAX_TRENDS])
        + ". Use them to judge whether each is rising, at its peak or fading."
        if previous
        else ""
    )
    return (
        f"Country: {snapshot['region']}. Write every name, sentence and idea in "
        f"{_LANG_NAMES.get(lang, 'English')}. At most {_MAX_TRENDS} trends.{seen}\n\n"
        "Fastest-rising videos (views per hour since published):\n"
        + "\n".join(lines)
        + ("\n\nMost-played songs:\n" + "\n".join(songs) if songs else "")
    )


def validate_report(raw: Any, snapshot: dict) -> dict:
    """Keep what is well-formed and points at videos that exist."""
    by_id = {v["id"]: v for v in snapshot.get("videos", [])}
    trends = []
    for t in (raw.get("trends") if isinstance(raw, dict) else None) or []:
        if not isinstance(t, dict) or not str(t.get("name", "")).strip():
            continue
        examples = [
            {k: by_id[i][k] for k in ("id", "title", "channel", "thumbnail", "views", "views_per_hour")}
            for i in (t.get("examples") or [])
            if isinstance(i, str) and i in by_id
        ][:3]
        status = str(t.get("status", "")).lower()
        kind = str(t.get("kind", "")).lower()
        fits = str(t.get("fits", "")).lower()
        trends.append(
            {
                "name": str(t["name"]).strip()[:80],
                "kind": kind if kind in ("topic", "format", "sound", "person") else "topic",
                "status": status if status in ("rising", "peak", "fading") else "rising",
                "why": str(t.get("why", "")).strip()[:400],
                "ideas": [str(i).strip()[:200] for i in (t.get("ideas") or []) if str(i).strip()][:3],
                "fits": fits if fits in ("generate", "edit", "both") else "both",
                "examples": examples,
            }
        )
        if len(trends) >= _MAX_TRENDS:
            break
    summary = str(raw.get("summary", "")).strip()[:500] if isinstance(raw, dict) else ""
    return {"summary": summary, "trends": trends, "version": PROMPT_VERSION}


async def analyse(snapshot: dict, lang: str, llm: LLMConfig, previous: list[str]) -> dict:
    raw = await script_engine.complete_json(llm, SYSTEM_PROMPT, analysis_prompt(snapshot, lang, previous))
    return validate_report(raw, snapshot)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


@dataclass
class Report:
    region: str
    lang: str
    generated_at: datetime
    fetched_at: datetime
    report: dict
    songs: list[dict]


class _Memory:
    def __init__(self) -> None:
        self.snapshots: dict[str, tuple[int, datetime, dict]] = {}
        self.reports: dict[tuple[str, str], tuple[datetime, int, dict]] = {}
        self._next = 1

    async def latest_snapshot(self, region):
        return self.snapshots.get(region)

    async def add_snapshot(self, region, data):
        sid, self._next = self._next, self._next + 1
        self.snapshots[region] = (sid, datetime.now(UTC), data)
        return sid

    async def report(self, region, lang):
        return self.reports.get((region, lang))

    async def save_report(self, region, lang, snapshot_id, report):
        self.reports[(region, lang)] = (datetime.now(UTC), snapshot_id, report)

    async def prune(self):
        return None


class _Postgres:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def latest_snapshot(self, region):
        row = await self.pool.fetchrow(
            "select id, fetched_at, data from trend_snapshots where region = $1 "
            "order by fetched_at desc limit 1",
            region,
        )
        return (row["id"], row["fetched_at"], json.loads(row["data"])) if row else None

    async def add_snapshot(self, region, data):
        return await self.pool.fetchval(
            "insert into trend_snapshots (region, data) values ($1, $2::jsonb) returning id",
            region,
            json.dumps(data),
        )

    async def report(self, region, lang):
        row = await self.pool.fetchrow(
            "select generated_at, snapshot_id, report from trend_reports where region = $1 and lang = $2",
            region,
            lang,
        )
        return (row["generated_at"], row["snapshot_id"], json.loads(row["report"])) if row else None

    async def save_report(self, region, lang, snapshot_id, report):
        await self.pool.execute(
            """
            insert into trend_reports (region, lang, snapshot_id, report) values ($1, $2, $3, $4::jsonb)
            on conflict (region, lang) do update
               set generated_at = now(), snapshot_id = excluded.snapshot_id, report = excluded.report
            """,
            region,
            lang,
            snapshot_id,
            json.dumps(report),
        )

    async def prune(self):
        await self.pool.execute("delete from trend_snapshots where fetched_at < now() - interval '30 days'")


_store: _Memory | _Postgres = _Memory()
# Regions somebody asked for lately, kept fresh by the scheduler.
_asked: dict[str, datetime] = {}
_locks: dict[tuple[str, str], asyncio.Lock] = {}


def configure(pool: asyncpg.Pool | None) -> None:
    global _store
    _store = _Postgres(pool) if pool is not None else _Memory()


def _llm(settings) -> LLMConfig:
    return LLMConfig(
        provider=LLMProvider(settings.llm_provider),
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        api_key=settings.openai_api_key,
        temperature=0.4,
    )


async def refresh_region(region: str, settings) -> int | None:
    """Collect a region if its data is older than a day; the snapshot id."""
    latest = await _store.latest_snapshot(region)
    if latest and datetime.now(UTC) - latest[1] < DATA_MAX_AGE:
        return latest[0]
    data = await collect(region, settings.youtube_api_key)
    return await _store.add_snapshot(region, data)


async def get_report(region: str, lang: str, settings) -> Report | None:
    """The analysis for a region in a language, written if it is missing
    or stale. One writer per (region, language) at a time."""
    _asked[region] = datetime.now(UTC)
    lock = _locks.setdefault((region, lang), asyncio.Lock())
    async with lock:
        snapshot_id = await refresh_region(region, settings)
        latest = await _store.latest_snapshot(region)
        if latest is None:
            return None
        _, fetched_at, snapshot = latest
        existing = await _store.report(region, lang)
        fresh = (
            existing is not None
            and existing[2].get("version") == PROMPT_VERSION
            and datetime.now(UTC) - existing[0] < REPORT_MAX_AGE
            and (existing[1] == snapshot_id or datetime.now(UTC) - existing[0] < DATA_MAX_AGE)
        )
        if fresh and existing is not None:
            generated_at, report = existing[0], existing[2]
        else:
            previous = [t["name"] for t in (existing[2]["trends"] if existing else [])]
            report = await analyse(snapshot, lang, _llm(settings), previous)
            await _store.save_report(region, lang, snapshot_id, report)
            generated_at = datetime.now(UTC)
        return Report(region, lang, generated_at, fetched_at, report, snapshot.get("songs", []))


async def run_scheduler(settings, every_s: float = 3 * 3600) -> None:
    """Keep the regions people use fresh. Runs for the life of the API."""
    while True:
        try:
            cutoff = datetime.now(UTC) - timedelta(days=7)
            regions = set(settings.trends_default_regions) | {r for r, t in _asked.items() if t > cutoff}
            for region in sorted(regions):
                if region in REGIONS:
                    await refresh_region(region, settings)
            await _store.prune()
        except Exception:  # noqa: BLE001 - a bad day of collecting must not stop the loop
            logger.exception("Trend collection failed")
        await asyncio.sleep(every_s)
