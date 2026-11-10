"""Native voices for a story's cast, from the ElevenLabs account itself.

Over Replicate, ElevenLabs offers 26 preset voices, all English speakers:
reading Turkish they stayed flat however the lines were tagged. The
account's own API reaches the Voice Library, where voice actors publish
voices in their own language. So a story's cast is voiced from those:
the account's voices first, and when it has too few in the story's
language, the most-used library voices in that language are added to it
(Starter allows ten; a pool takes at most eight).

Every voice is labelled by who it sounds like — a kind, as
voices._cast_kind names them — and the cast is matched to those.
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

API = "https://api.elevenlabs.io/v1"

# Who a library voice sounds like, from its own labels.
_KINDS = ("woman", "man", "older_woman", "older_man", "girl", "boy")
# The ones a pool tries to have, and how many of each.
_WANTED = {"woman": 3, "man": 3, "older_woman": 1, "older_man": 1}

_pool_cache: dict[str, tuple[float, dict[str, list[str]]]] = {}


def enabled() -> bool:
    from app.core.config import get_settings

    return bool(get_settings().elevenlabs_api_key)


def _kind(gender: str, age: str) -> str | None:
    gender, age = (gender or "").lower(), (age or "").lower().replace("-", "_")
    if gender not in ("female", "male"):
        return None
    old = age in ("old", "senior")
    if gender == "female":
        return "older_woman" if old else "woman"
    return "older_man" if old else "man"


def _speaks(voice: dict, language: str) -> bool:
    labels = voice.get("labels") or {}
    if (labels.get("language") or "").lower().startswith(language):
        return True
    return any(
        (v.get("language") or "").lower().startswith(language)
        for v in voice.get("verified_languages") or []
    )


async def _account_pool(client: httpx.AsyncClient, language: str) -> dict[str, list[str]]:
    response = await client.get(f"{API}/voices")
    if response.status_code >= 400:
        # Say why — a key without Voices permission answers 401 and the
        # body names the missing permission.
        raise RuntimeError(
            f"ElevenLabs refused the voice list ({response.status_code}): {response.text[:300]}"
        )
    pool: dict[str, list[str]] = {k: [] for k in _KINDS}
    for voice in response.json().get("voices", []):
        if not _speaks(voice, language):
            continue
        labels = voice.get("labels") or {}
        kind = _kind(labels.get("gender", ""), labels.get("age", ""))
        if kind:
            pool[kind].append(voice["voice_id"])
    return pool


async def _add_from_library(
    client: httpx.AsyncClient, language: str, kind: str, count: int
) -> list[str]:
    """The library's most-used voices of this kind in this language, added
    to the account. Voices the account cannot use on its plan are skipped."""
    gender = "female" if kind.endswith("woman") else "male"
    params: dict[str, str | int] = {
        "language": language,
        "gender": gender,
        "page_size": 20,
        "sort": "cloned_by_count",
    }
    if kind.startswith("older_"):
        params["age"] = "old"
    response = await client.get(f"{API}/shared-voices", params=params)
    if response.status_code >= 400:
        raise RuntimeError(
            f"ElevenLabs refused the library search ({response.status_code}): "
            f"{response.text[:300]}"
        )
    added: list[str] = []
    for voice in response.json().get("voices", []):
        if len(added) == count:
            break
        if not kind.startswith("older_") and (voice.get("age") or "") == "old":
            continue
        try:
            made = await client.post(
                f"{API}/voices/add/{voice['public_owner_id']}/{voice['voice_id']}",
                json={"new_name": f"ShortPulse {language} {kind} {len(added) + 1}"},
            )
            made.raise_for_status()
            added.append(made.json()["voice_id"])
        except (httpx.HTTPError, KeyError):
            logger.warning("Could not add library voice %s", voice.get("voice_id"), exc_info=True)
    return added


async def voice_pool(language: str) -> dict[str, list[str]]:
    """Voice ids by kind for this language: the account's own, topped up
    from the library. Kept for an hour; an account change shows up then."""
    from app.core.config import get_settings

    language = (language or "en").split("-")[0]
    cached = _pool_cache.get(language)
    if cached and time.monotonic() < cached[0]:
        return cached[1]
    key = get_settings().elevenlabs_api_key
    async with httpx.AsyncClient(timeout=30, headers={"xi-api-key": key or ""}) as client:
        pool = await _account_pool(client, language)
        for kind, wanted in _WANTED.items():
            missing = wanted - len(pool[kind])
            if missing > 0:
                pool[kind] += await _add_from_library(client, language, kind, missing)
    # A child is voiced by the youngest-sounding adult voice of their sex,
    # acted down by the line's tags; the library has very few children.
    pool["girl"] = pool["girl"] or pool["woman"][-1:]
    pool["boy"] = pool["boy"] or pool["man"][-1:]
    _pool_cache[language] = (time.monotonic() + 3600, pool)
    return pool


def assign(cast, pool: dict[str, list[str]]) -> None:
    """Give every cast member without one an account voice of their kind,
    each a different one where the pool allows."""
    from app.services.voices import _cast_kind

    used = {m.voice_id for m in cast if m.voice_id}
    for member in cast:
        if member.voice_id:
            continue
        kind = _cast_kind(member.gender, member.age)
        choices = pool.get(kind) or pool.get(kind.removeprefix("older_")) or []
        fresh = [v for v in choices if f"elevenlabs:{v}" not in used]
        picks = fresh or choices
        if picks:
            member.voice_id = f"elevenlabs:{picks[0]}"
            used.add(member.voice_id)
