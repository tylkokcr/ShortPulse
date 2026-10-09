"""Title, description and hashtags for a video that has none.

A generated video gets its post copy from the call that writes its script
(PostCopy). An uploaded video, a clip cut from one and a beat edit never
had a script, so the publish panel opened empty and every post was typed
by hand. This writes the same three fields from what the video does have:
what was said in it, and what it was called.
"""

from __future__ import annotations

import re

from app.engines import script_engine
from app.schemas.project import LLMConfig, PostCopy, Project, ProjectSource

_NAMES = {
    "en": "English",
    "tr": "Turkish",
    "pl": "Polish",
    "de": "German",
    "es": "Spanish",
    "fr": "French",
    "pt": "Portuguese",
    "it": "Italian",
    "ar": "Arabic",
    "ru": "Russian",
}
# Names a project gets when nobody named it — no help to a copywriter.
_GENERIC = {"beat edit", "uploaded video", ""}

SYSTEM_PROMPT = """\
You write the post that goes with a short vertical video on TikTok, YouTube \
Shorts and Instagram Reels: a title that makes someone stop scrolling, a \
description of one or two short sentences, and up to eight hashtags that \
people actually search. No clickbait the video does not deliver, no emoji \
spam (one or two at most), hashtags without the '#'.

Return JSON of this exact shape:
{"title": "<at most 90 characters>", "description": "<at most 300 characters>", \
"hashtags": ["..."]}"""


def _readable(name: str) -> str:
    """A file name as words: 'Neymar_100+_WOW_Skills.mp4' -> 'Neymar 100+ WOW Skills'."""
    name = re.sub(r"\.(mp4|mov|m4v|webm|mkv)$", "", name.strip(), flags=re.I)
    name = re.sub(r"\s*\(\d+\)$", "", name)
    return re.sub(r"[_]+", " ", name).strip()


def prompt_for(project: Project, lang: str) -> str:
    config = project.config
    words = " ".join(w.text for w in (project.captions.words if project.captions else []))[:2500]
    topic = _readable(config.topic)
    kind = {
        ProjectSource.BEAT_EDIT: "an edit of the creator's own clips cut to music"
        + (f", {config.beat_edit.style.value} style" if config.beat_edit else ""),
        ProjectSource.UPLOAD: "the creator's own video"
        + (", a clip cut from a longer one" if not words else ""),
    }.get(config.source, "a short video")
    parts = [f"Write it in {_NAMES.get(lang, 'English')}.", f"The video is {kind}."]
    if topic.lower() not in _GENERIC:
        parts.append(f"Its name: {topic}")
    if words:
        parts.append(f"What is said in it:\n{words}")
    return "\n".join(parts)


def validate(raw: object) -> PostCopy:
    data = raw if isinstance(raw, dict) else {}
    tags = [
        re.sub(r"[^\w]", "", str(t).lstrip("#"))[:30] for t in (data.get("hashtags") or []) if str(t).strip()
    ]
    return PostCopy(
        title=str(data.get("title", "")).strip().strip('"')[:100],
        description=str(data.get("description", "")).strip()[:2200],
        hashtags=[t for t in tags if t][:8],
    )


async def suggest(project: Project, lang: str, llm: LLMConfig) -> PostCopy:
    raw = await script_engine.complete_json(llm, SYSTEM_PROMPT, prompt_for(project, lang))
    return validate(raw)
