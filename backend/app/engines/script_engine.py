"""LLM layer: turns a topic or raw script into a structured, scene-broken
shooting script the rest of the pipeline can consume.

Supports two backends:
  - Ollama (local, free, default) via its HTTP `/api/generate` endpoint.
  - OpenAI (optional, paid) via the official SDK, for users who want higher
    quality output and don't mind the API cost.

The LLM is instructed to return raw JSON matching `ScriptOutput`. Local
models are unreliable about staying in valid JSON, so the response is
repaired defensively before being parsed.
"""

from __future__ import annotations

import json
import logging
import re

import httpx
from pydantic import ValidationError

from app.schemas.project import (
    LLMConfig,
    LLMProvider,
    Scene,
    SceneAudio,
    SceneVisual,
    ScriptOutput,
    VideoLength,
)

logger = logging.getLogger(__name__)

# (min_scenes, max_scenes) target per preset. Scenes are still individually
# capped at 3-5s each, so these ranges land roughly at ~15-25s / ~30-45s /
# ~60s+ once the hook and call-to-action are included.
SCENE_COUNT_BY_LENGTH: dict[VideoLength, tuple[int, int]] = {
    VideoLength.SHORT: (5, 6),
    VideoLength.MEDIUM: (8, 10),
    VideoLength.LONG: (12, 15),
}

# Display names for ProjectConfig.language codes, used in the prompt
# instruction. Matched against real edge-tts locales (see VoiceConfig) —
# extend both together when adding a language.
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "tr": "Turkish",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "ja": "Japanese",
    "ar": "Arabic",
    "ru": "Russian",
    "it": "Italian",
}

# Descriptive: this text is fed to a diffusion model, where subject,
# lighting and mood all change the image.
VISUAL_PROMPT_RULE_GENERATED = """\
- For every scene, write a concrete, visually descriptive image/video \
generation prompt (subject, setting, lighting, camera angle, mood). The \
image model cannot render legible text, so "visual_prompt" must never \
describe labels, signs, jar labels, packaging text, book covers, screens \
with text, infographics, diagrams with captions/arrows, or any other \
readable writing appearing in the shot — describe the physical scene only \
(e.g. "a jar of honey on a wooden table" rather than "a jar with a label \
reading...")."""

# Terse: this text becomes a stock-library search, which matches on
# keywords. The long form was being generated a token at a time and then
# reduced to its nouns before the query was sent (see
# visual_engine.stock_search_terms) — paying for words that were thrown
# away, and at ~21 tokens/sec that is real wall clock.
VISUAL_PROMPT_RULE_STOCK = """\
- For every scene, write "visual_prompt" as 2 to 4 plain search keywords \
naming what should be on screen — the subject and its setting, nothing \
else. No lighting, camera, mood or style words, no articles, no full \
sentences. It is used to search a stock footage library, so it must \
describe a thing that can be filmed (e.g. "honey jar wooden table", \
"volcano eruption night")."""

SYSTEM_PROMPT_TEMPLATE = """\
You are a viral short-form video scriptwriter for TikTok, YouTube Shorts and \
Instagram Reels. Given a topic, produce a tightly paced vertical video script.

Rules:
- The first line (the "hook") must grab attention within 3 seconds. Use a \
question, bold claim, or pattern interrupt. Never start with "Have you ever".
- Break the script into {min_scenes} to {max_scenes} scenes. Each scene is \
3 to 5 seconds of spoken voiceover (roughly 8-14 words).
- Write "hook", every "voiceover_line", and "call_to_action" entirely in \
{language_name}. Always write "visual_prompt" in English regardless of the \
target language — the image-generation model responds best to English \
prompts.
{visual_prompt_rule}
- Whatever draws or finds the footage knows nothing about specific people, \
characters, brands, games or franchises, and cannot look them up. Naming \
one in "visual_prompt" produces an unrelated stand-in — a topic about a \
game character came back as a generic face. So "visual_prompt" must be \
self-contained and literal: describe what a camera would see, using words \
that mean something with no outside context, and never use jargon from a \
game or fandom ("her ultimate", "auto-attacks"). Write "an archer in blue \
armour drawing a glowing bow" rather than "Ashe using her ultimate". The \
"voiceover_line" is free to name whatever it likes — this rule is only \
about the visual.
- "voiceover_line" must NEVER be empty, even for topics about visual or \
non-verbal cues (body language, micro-expressions, etc.) — the narrator \
always explains the point out loud in words; the visual is a separate, \
complementary illustration, not a substitute for narration.
- Keep the tone punchy and conversational. No filler.
- Never include emoji or symbols in "voiceover_line" — it is read aloud by \
a text-to-speech engine, which will speak an emoji's literal name instead \
of skipping it.
- End with a short call to action (follow, comment, etc.) unless the topic \
clearly calls for a cliffhanger instead.

Respond with ONLY valid JSON, no markdown fences, matching this shape:
{{
  "hook": "string",
  "scenes": [
    {{"voiceover_line": "string", "visual_prompt": "string", "duration_s": 4}}
  ],
  "call_to_action": "string or null"
}}
"""


def _build_system_prompt(
    video_length: VideoLength, language: str, visual_mode: str = "fast_hybrid"
) -> str:
    min_scenes, max_scenes = SCENE_COUNT_BY_LENGTH[video_length]
    language_name = LANGUAGE_NAMES.get(language, language)
    visual_prompt_rule = (
        VISUAL_PROMPT_RULE_STOCK
        if visual_mode == "stock_media"
        else VISUAL_PROMPT_RULE_GENERATED
    )
    return SYSTEM_PROMPT_TEMPLATE.format(
        visual_prompt_rule=visual_prompt_rule,
        min_scenes=min_scenes, max_scenes=max_scenes, language_name=language_name
    )


class ScriptGenerationError(RuntimeError):
    pass


def _build_user_prompt(topic: str, raw_script: str | None) -> str:
    if raw_script:
        return (
            f"The user already wrote this script — segment it into scenes "
            f"and generate a visual prompt per scene, but do not rewrite "
            f"the voiceover lines:\n\n{raw_script}"
        )
    return f"Topic: {topic}"


def _extract_json(text: str) -> dict:
    """Local models frequently wrap JSON in prose or markdown fences.
    Pull out the first top-level {...} block and parse it."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1:
            text = text[first_brace : last_brace + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScriptGenerationError(f"Model did not return valid JSON: {exc}") from exc


async def _call_ollama(config: LLMConfig, system_prompt: str, prompt: str) -> str:
    payload = {
        "model": config.model,
        "system": system_prompt,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": config.temperature},
    }
    async with httpx.AsyncClient(base_url=config.base_url, timeout=120.0) as client:
        response = await client.post("/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()
        return data["response"]


async def _call_openai(config: LLMConfig, system_prompt: str, prompt: str) -> str:
    from openai import AsyncOpenAI  # local import: optional dependency

    client = AsyncOpenAI(api_key=config.api_key)
    response = await client.chat.completions.create(
        model=config.model or "gpt-4o-mini",
        temperature=config.temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content or "{}"


async def generate_script(
    topic: str,
    config: LLMConfig,
    raw_script: str | None = None,
    video_length: VideoLength = VideoLength.SHORT,
    language: str = "en",
    visual_mode: str = "fast_hybrid",
    max_attempts: int = 3,
) -> ScriptOutput:
    """Run the LLM and convert its response into a validated ScriptOutput.

    Local models occasionally produce a response where every scene is
    malformed in the same way for a given topic (e.g. leaving
    "voiceover_line" blank) — since generation is sampled with temperature
    > 0, a retry is often enough to get a usable script, so failures are
    retried a few times before giving up.
    """
    last_error: ScriptGenerationError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await _generate_script_once(
                topic, config, raw_script, video_length, language, visual_mode
            )
        except ScriptGenerationError as exc:
            last_error = exc
            logger.warning("Script generation attempt %d/%d failed: %s", attempt, max_attempts, exc)
    assert last_error is not None
    raise last_error


async def _generate_script_once(
    topic: str,
    config: LLMConfig,
    raw_script: str | None,
    video_length: VideoLength,
    language: str,
    visual_mode: str = "fast_hybrid",
) -> ScriptOutput:
    system_prompt = _build_system_prompt(video_length, language, visual_mode)
    user_prompt = _build_user_prompt(topic, raw_script)

    raw_text = await _call_llm(config, system_prompt, user_prompt)
    parsed = _extract_json(raw_text)
    await _rewrite_named_prompts(parsed, topic, config)
    return _to_script_output(topic, parsed)


async def _call_llm(config: LLMConfig, system_prompt: str, prompt: str) -> str:
    if config.provider == LLMProvider.OLLAMA:
        return await _call_ollama(config, system_prompt, prompt)
    if config.provider == LLMProvider.OPENAI:
        return await _call_openai(config, system_prompt, prompt)
    raise ScriptGenerationError(f"Unsupported LLM provider: {config.provider}")


def _first_present(d: dict, keys: list[str]) -> str | None:
    for key in keys:
        value = d.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


# Words that start a sentence or a stock phrase and happen to be
# capitalised — not names, and not worth rewriting a prompt over.
_NOT_A_NAME = {
    "a", "an", "the", "close", "closeup", "close-up", "wide", "aerial", "macro",
    "split", "slow", "time", "first", "second", "third", "new", "old", "young",
    # Topics are usually written as a question or a statement, so the first
    # word is capitalised without being a name.
    "why", "what", "when", "where", "how", "who", "which", "this", "that",
    "does", "did", "can", "could", "should", "are", "is", "was", "were",
    "your", "you", "my", "our", "their", "some", "every", "all", "most",
}


def _named_entities(topic: str) -> set[str]:
    """Capitalised words in the topic that a generator won't recognise.

    Deliberately drawn from the topic rather than from a dictionary: the
    thing the user asked about is exactly the thing the model will name in
    its visual prompts, and it needs no list of every character and brand
    in the world to spot it.
    """
    # Any token carrying an uppercase letter, not just one starting with
    # it — brand names routinely start lowercase (iPhone, eBay, xAI), and
    # requiring an initial capital let "iPhone" through unnoticed.
    words = re.findall(r"\b[\w'-]*[A-Z][\w'-]*\b", topic)
    return {w for w in words if w.lower() not in _NOT_A_NAME and len(w) > 2}


def visual_prompts_naming(scenes: list[dict], topic: str) -> list[int]:
    """Indices of scenes whose visual prompt names something from the topic.

    Whatever draws or searches for the footage has no idea who "Ashe" is,
    so a prompt containing it comes back as an unrelated stand-in — in the
    case that prompted this, a generic face for a game character. The
    prompt rules ask the model to avoid it and mostly work, but a local
    model applies the rule for a few scenes and then drifts, so this is the
    check that doesn't rely on it remembering.
    """
    entities = _named_entities(topic)
    if not entities:
        return []
    hits = []
    for i, scene in enumerate(scenes):
        prompt = (scene.get("visual_prompt") or "").lower()
        if any(e.lower() in prompt for e in entities):
            hits.append(i)
    return hits


REWRITE_SYSTEM_PROMPT = """\
You rewrite image-generation prompts so they describe only what a camera \
would see.

The prompts you are given name a specific person, character, brand or \
franchise. Whatever draws the image has never heard of it and will invent \
an unrelated substitute, so each prompt must be rewritten to describe the \
same shot literally — appearance, setting, action — with the name and any \
fandom jargon removed.

Example: "Ashe standing behind enemies with her ultimate" becomes "an \
archer in blue armour drawing a glowing bow, enemies scattered behind her".

Keep each rewrite under 15 words. Respond with ONLY valid JSON:
{"prompts": ["rewritten prompt", "rewritten prompt"]}
"""


async def _rewrite_named_prompts(
    parsed: dict, topic: str, config: LLMConfig
) -> None:
    """Replace visual prompts that name topic entities, in place.

    One extra call for the whole batch rather than one per scene, and a
    failure leaves the originals untouched — a literal-but-generic image is
    the improvement here, and an unrelated one is what we already had.
    """
    scenes = parsed.get("scenes")
    if not isinstance(scenes, list):
        return
    hits = visual_prompts_naming(scenes, topic)
    if not hits:
        return

    numbered = "\n".join(f"{n + 1}. {scenes[i].get('visual_prompt')}" for n, i in enumerate(hits))
    try:
        raw = await _call_llm(config, REWRITE_SYSTEM_PROMPT, numbered)
        rewritten = _extract_json(raw).get("prompts")
        if not isinstance(rewritten, list) or len(rewritten) != len(hits):
            raise ScriptGenerationError("rewrite returned the wrong number of prompts")
    except Exception as exc:  # noqa: BLE001 - a failed rewrite is not a failed render
        logger.warning("Could not rewrite %d named visual prompt(s): %s", len(hits), exc)
        return

    for index, prompt in zip(hits, rewritten, strict=True):
        if isinstance(prompt, str) and prompt.strip():
            logger.info(
                "Rewrote visual prompt naming a topic entity: %r -> %r",
                scenes[index].get("visual_prompt"),
                prompt,
            )
            scenes[index]["visual_prompt"] = prompt.strip()


def _to_script_output(topic: str, parsed: dict) -> ScriptOutput:
    # The model is asked for a top-level object, but occasionally returns a
    # bare array of scenes (or something else entirely). Raise the engine's
    # own error type so generate_script's retry loop can catch it.
    if not isinstance(parsed, dict):
        raise ScriptGenerationError(
            f"Model returned {type(parsed).__name__}, expected a JSON object"
        )

    scenes: list[Scene] = []
    for raw_index, raw_scene in enumerate(parsed.get("scenes", [])):
        # One malformed scene shouldn't sink an otherwise-good script (and
        # shouldn't crash out of generate_script's retry loop, which only
        # catches ScriptGenerationError) — so any parsing failure here,
        # not just missing keys, results in skipping the scene.
        try:
            # Models occasionally emit a bare string (or a list) where a
            # scene object belongs, which would otherwise AttributeError on
            # the .get() below and escape the retry loop entirely.
            if not isinstance(raw_scene, dict):
                raise TypeError(f"expected a scene object, got {type(raw_scene).__name__}")

            # `.get(..., 4)` alone isn't enough: models sometimes emit an
            # explicit `"duration_s": null`, which .get() happily returns
            # instead of falling back to the default.
            raw_duration = raw_scene.get("duration_s")
            duration_s = float(raw_duration) if raw_duration is not None else 4.0
            duration_s = min(max(duration_s, 3), 5)

            # Local models don't reliably stick to the exact key names
            # requested in the prompt, so accept the variants they drift to.
            voiceover_line = _first_present(raw_scene, ["voiceover_line", "voiceover", "line", "text"])
            visual_prompt = _first_present(raw_scene, ["visual_prompt", "image_prompt", "visual", "prompt"])
            if voiceover_line is None or visual_prompt is None:
                raise ValueError("missing voiceover line or visual prompt")

            scene = Scene(
                index=len(scenes),
                duration_s=duration_s,
                visual=SceneVisual(prompt=visual_prompt),
                audio=SceneAudio(voiceover_line=voiceover_line),
            )
        except (ValueError, TypeError, AttributeError, ValidationError) as exc:
            logger.warning("Skipping scene %d (%s): %r", raw_index, exc, raw_scene)
            continue

        scenes.append(scene)

    if not scenes:
        raise ScriptGenerationError("Model returned zero usable scenes")

    try:
        return ScriptOutput(
            topic=topic,
            hook=parsed.get("hook", scenes[0].audio.voiceover_line),
            scenes=scenes,
            total_duration_s=sum(s.duration_s for s in scenes),
            call_to_action=parsed.get("call_to_action"),
        )
    except ValidationError as exc:
        raise ScriptGenerationError(f"Malformed script structure: {exc}") from exc
