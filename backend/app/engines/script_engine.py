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

from app.core.config import get_settings
from app.engines.graphics import ICONS
from app.schemas.project import (
    GraphicCounter,
    LLMConfig,
    LLMProvider,
    PostCopy,
    Scene,
    SceneAudio,
    SceneGraphic,
    SceneVisual,
    ScriptOutput,
    VideoLength,
)

logger = logging.getLogger(__name__)

# (min_scenes, max_scenes) target per preset. Scenes are still individually
# capped at 3-5s each, so these ranges land roughly at ~15-25s / ~30-45s /
# ~60s+ once the hook and call-to-action are included.
# A format whose rhythm is quicker cuts: more, shorter scenes for the same
# length preset. "What if?" videos change picture every two or three
# seconds — one consequence, one image — where a free topic explains.
FORMAT_SCENE_COUNT: dict[str, dict[VideoLength, tuple[int, int]]] = {
    "what_if": {
        VideoLength.SHORT: (9, 11),
        VideoLength.MEDIUM: (14, 17),
        VideoLength.LONG: (20, 24),
    },
}
_SCENE_LENGTH = {
    "free": "3 to 5 seconds of spoken voiceover (roughly 8-14 words)",
    "what_if": "2 to 3 seconds of spoken voiceover (roughly 5-10 words) — one punchy idea",
}


def scene_count(video_length: VideoLength, script_format: str = "free") -> tuple[int, int]:
    return FORMAT_SCENE_COUNT.get(script_format, SCENE_COUNT_BY_LENGTH)[video_length]


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
    "pl": "Polish",
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
reading...").
- When a person is in the shot, name the framing and keep it to a \
close-up, a portrait, or a medium shot from the waist up. At most one \
person in frame — two only where the line makes no sense without both — \
and never a crowd, a group, a team, an audience, or a background filled \
with figures. Do not ask for full-body shots, for hands or feet as the \
subject, or for someone lying down. The model draws one face convincingly \
and a dozen badly: every extra figure is another pair of hands and feet \
to get wrong, and in a crowd they fail in the foreground where they are \
most visible. When the line is about an action rather than a person, \
prefer the setting or the object over a figure performing it."""

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
{scene_length}.
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
- Keep every "voiceover_line" and every "visual_prompt" suitable for a \
general audience and for advertisers: no sexual content, no nudity, no \
graphic violence or gore. This holds even when the topic invites it — a \
topic about relationships, anatomy or crime is written about, not \
depicted. A "visual_prompt" describing a person must describe them \
clothed.
- Keep the tone punchy and conversational. No filler.
- Never include emoji or symbols in "voiceover_line" — it is read aloud by \
a text-to-speech engine, which will speak an emoji's literal name instead \
of skipping it.
- End with a short call to action (follow, comment, etc.) unless the topic \
clearly calls for a cliffhanger instead.
- Also write the text that goes *around* the video when it is posted: a \
"post" object with a "title" (under 100 characters, written to be clicked \
on), a "description" (1-3 sentences), and 3 to 8 "hashtags". Write the \
title and description in {language_name}. Give hashtags without the '#' \
and without spaces. This is what appears on the post itself, not in the \
video, so do not repeat the hook word for word.

- Pick the soundtrack's mood: a top-level "music_mood", exactly one of \
"upbeat" (fun, energetic, positive), "lofi" (calm, cosy, everyday), \
"atmospheric" (wonder, mystery, space, nature, science) or "suspense" \
(tension, danger, disaster, the unknown). Match the topic's feeling, not \
its subject.
{format_rules}
Respond with ONLY valid JSON, no markdown fences, matching this shape:
{{
  "hook": "string",
  "scenes": [
    {{"voiceover_line": "string", "visual_prompt": "string", "duration_s": 4}}
  ],
  "call_to_action": "string or null",
  "post": {{
    "title": "string",
    "description": "string",
    "hashtags": ["string"]
  }}
}}
"""


# Extra rules per ScriptFormat, added to the system prompt. "free" has
# none: the rules above are already that format.
FORMAT_RULES: dict[str, str] = {
    "what_if": """\
This video is a "what would happen if" thought experiment, told as a story \
to the viewer rather than a list of facts. Follow these:
- The topic is a hypothetical ("What if the Moon disappeared?", "What if \
Poland vanished from the map?"). If it is not phrased as one, treat it as \
"what would happen if <topic>".
- The hook is the first thing the viewer hears: the hypothetical asked \
as a mysterious question straight to them, the kind they have never \
thought to ask — "Have you ever wondered what would happen if Poland \
vanished from the map overnight?" It is the FIRST scene's \
"voiceover_line", word for word, and the second scene is where it has \
happened ("This morning, it's gone.").
- Talk TO the viewer, in the second person, and put the consequences in \
their own day: what they notice first at breakfast, in their kitchen, on \
their phone, at the beach, on holiday. "Look at your kitchen" beats "the \
appliance industry is affected".
- Prefer things people know and touch — a food, a spread, a fruit, a \
show, a holiday spot, a festival, an animal — over sectors and statistics. \
Each consequence is a specific thing most viewers do not know comes from \
there (or depends on it). Never write that something "is disrupted", \
"falls into chaos", "is affected", "struggles" or "changes completely". \
Weak: "Agriculture would suffer." Strong: "Your morning hazelnut spread \
just got very expensive."
- Early on, one striking image in a single line — a poetic picture of \
what THIS change looks like, true to its geography or physics.
- Every example in these rules shows a style, never content to reuse: \
copying an example sentence into a script about something else is a \
failure.
- Short lines: one idea each, rhythm varied, as if spoken to camera. \
Cliffhangers are their own short lines ("But there is a problem.", "And \
then it starts.") and end on "…" — that is where the narrator holds a \
breath; use it two to four times a script. \
Time markers are welcome where the order matters ("By morning", "Ten years \
on") and must match when the effect really arrives — tides in hours, \
climate in decades, a planet's tilt over millions of years; a long scale \
is part of the surprise.
- Two thirds of the way through, a turn: "But..." — a twist that changes \
how the whole thing feels (something that once vanished and came back, a \
hidden upside, the thing nobody would expect to miss). Then the most \
surprising fact as the payoff. Never end on a summary.
- Close on a question that turns the video into a series and invites a \
comment: for a place, "Which country should vanish next? Tell me below"; \
otherwise "What would you miss first?".
- Numbers: only well-established, stable ones — a population, an area, a \
distance, a famous record, a share an encyclopedia would state ("about \
two thirds of the world's hazelnuts") — rounded and said with "about". \
Never a percentage of damage, loss or decline: nobody has measured a \
hypothetical, so any such figure is invented. A line without a number is \
fine; a made-up number ruins the video.
- Stay consistent with the premise: whatever vanishes takes everything \
inside it with it (its rivers, cities, people), so a consequence is about \
what the REST of the world loses or how it changes.
- About countries, peoples or groups: geography, food, culture, economy, \
history — never whether a people deserves to exist. No mockery, no \
stereotypes, no wishing harm. Warmth is welcome: these videos are loved \
by the country's own people.
- Disasters are told through their effects on the world (lights going \
out, tides stopping, prices jumping), never through injured or dead \
people.
- Keep it light and curious: no wars, genocide, memorials or disasters \
with victims as content, not even as the twist.
- "visual_prompt": an illustrated scene showing that one consequence \
through objects, places and people doing things, framed close and simple \
enough to read in two seconds. Never a map, a globe with borders, a chart \
or anything with words or numbers in it: the image model cannot draw \
geography or text.
- The image model adds whatever usually belongs in a scene: describe a \
night sky and it draws a Moon, even in a video about the Moon being gone. \
So add a top-level "keep_out" string to the JSON: the thing that vanished, \
in a few plain English words an image model knows, comma-separated \
("moon, full moon, crescent moon"). Empty when nothing visible vanished.
- On-screen graphics: every scene object also carries
  "tally": 1-3 words in the script's language naming what this line is \
about, as a row on a growing on-screen list ("Apples", "The Witcher", \
"Gdańsk port"); the hook scene and the closing question have none;
  "icon": exactly one word from this list, the closest match: {icons};
  "stamp": only on the two or three biggest moments of the whole script, \
1-2 punchy words in the script's language that land the line (otherwise \
leave it out).
Add a top-level "tally_title": a short heading for that list in the \
script's language ("The world without Poland"). And a top-level \
"counter": when a country, city or people vanishes, ALWAYS its \
population, rounded and well established, as {"label": "...", "start": \
N, "end": 0} with the label in the script's language ("Population of \
Türkiye", 85000000); for other premises only if one well-established \
number fits, otherwise leave it out. Every scene with a tally gets an \
icon — pick the nearest one rather than none.
""",
}


def _build_system_prompt(
    video_length: VideoLength,
    language: str,
    visual_mode: str = "fast_hybrid",
    script_format: str = "free",
) -> str:
    min_scenes, max_scenes = scene_count(video_length, script_format)
    language_name = LANGUAGE_NAMES.get(language, language)
    visual_prompt_rule = (
        VISUAL_PROMPT_RULE_STOCK
        if visual_mode == "stock_media"
        else VISUAL_PROMPT_RULE_GENERATED
    )
    return SYSTEM_PROMPT_TEMPLATE.format(
        visual_prompt_rule=visual_prompt_rule,
        min_scenes=min_scenes, max_scenes=max_scenes, language_name=language_name,
        scene_length=_SCENE_LENGTH.get(script_format, _SCENE_LENGTH["free"]),
        # The icon list is the renderer's (graphics.ICONS), so a word the
        # model is offered is always one that can be drawn.
        format_rules=FORMAT_RULES.get(script_format, "").replace("{icons}", ", ".join(ICONS)),
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


class ScriptProviderError(RuntimeError):
    """The provider cannot serve this request, and asking again won't help.

    Deliberately not a ScriptGenerationError. That one means the model
    returned something unusable, which is worth another sample — and
    generate_script takes three of them. An account with no quota is not a
    bad sample, and three more of those is exactly the waste this exists
    to stop.
    """


# Waits before each retry. Only a genuine rate limit gets here: the SDK's
# own retries are off, see _call_openai.
_OPENAI_RETRY_BACKOFF_S = (1.0, 3.0, 8.0)


def _is_out_of_quota(exc: object) -> bool:
    """Whether a 429 means "no money" rather than "too fast".

    Duck-typed on purpose: openai is an optional dependency here, so this
    must be readable — and testable — on an install that has never had it.
    The code is on the exception in current SDKs and in the response body
    in older ones, so both are checked rather than trusting either.
    """
    if getattr(exc, "code", None) == "insufficient_quota":
        return True
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("code") == "insufficient_quota":
            return True
        return body.get("code") == "insufficient_quota"
    return False


def is_reasoning_model(model: str) -> bool:
    """gpt-5 and later, and the o-series: no temperature, an effort instead."""
    name = model.lower()
    return name.startswith("gpt-5") or bool(re.match(r"o\d", name))


_fact_model_cache: tuple[float, str] | None = None


async def resolve_fact_model(settings) -> str:
    """The model that writes fact-bound scripts. `fact_llm_model` may name
    one; "auto" asks OpenAI which of `fact_llm_candidates` this account can
    use and takes the first, rechecking hourly — model names change faster
    than deploys, and a name that has been retired fails every render."""
    import time

    global _fact_model_cache
    if settings.fact_llm_model and settings.fact_llm_model != "auto":
        return settings.fact_llm_model
    if _fact_model_cache and time.monotonic() - _fact_model_cache[0] < 3600:
        return _fact_model_cache[1]
    chosen = settings.llm_model
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            )
            response.raise_for_status()
            have = {m.get("id") for m in response.json().get("data", [])}
        chosen = next((m for m in settings.fact_llm_candidates if m in have), settings.llm_model)
    except Exception:  # noqa: BLE001 - the everyday model still writes a script
        logger.warning("Could not list OpenAI models; using %s", chosen, exc_info=True)
    _fact_model_cache = (time.monotonic(), chosen)
    logger.info("Fact-bound scripts are written by %s", chosen)
    return chosen


async def _call_openai(config: LLMConfig, system_prompt: str, prompt: str) -> str:
    import asyncio

    from openai import (  # local import: optional dependency
        APIConnectionError,
        AsyncOpenAI,
        InternalServerError,
        RateLimitError,
    )

    # max_retries=0, against the SDK's default of two.
    #
    # A 429 from OpenAI means one of two opposite things. A rate limit is
    # worth waiting out. `insufficient_quota` — an account with no billing
    # or no credit — is not: it will not have money on the third attempt
    # either, and retrying only made the real error take three round trips
    # to surface, on an account that had already spent credits on the
    # render. The SDK cannot tell them apart, so it is left to do neither
    # and the distinction is made here.
    client = AsyncOpenAI(api_key=config.api_key or get_settings().openai_api_key, max_retries=0)

    # A backoff per retry, then None for the final attempt, which must not
    # sleep and must not swallow. Same shape as the Replicate retry in
    # visual_engine, for the same reason.
    for backoff in (*_OPENAI_RETRY_BACKOFF_S, None):
        try:
            model = config.model or "gpt-4o-mini"
            # Reasoning models refuse any temperature but their own and take
            # an effort instead.
            tuning: dict = (
                {"reasoning_effort": "medium"}
                if is_reasoning_model(model)
                else {"temperature": config.temperature}
            )
            response = await client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                **tuning,
            )
            return response.choices[0].message.content or "{}"
        except RateLimitError as exc:
            if _is_out_of_quota(exc):
                raise ScriptProviderError(
                    "The OpenAI account this deployment uses is out of quota. "
                    "Add billing or credit at platform.openai.com — no amount of "
                    "retrying will change it."
                ) from exc
            if backoff is None:
                raise
            logger.warning("OpenAI rate limited the request; retrying in %.1fs", backoff)
            await asyncio.sleep(backoff)
        except (APIConnectionError, InternalServerError) as exc:
            if backoff is None:
                raise
            logger.warning("OpenAI call failed (%s); retrying in %.1fs", exc, backoff)
            await asyncio.sleep(backoff)

    raise ScriptProviderError("OpenAI did not answer")  # unreachable, for the type checker


async def generate_script(
    topic: str,
    config: LLMConfig,
    raw_script: str | None = None,
    video_length: VideoLength = VideoLength.SHORT,
    language: str = "en",
    visual_mode: str = "fast_hybrid",
    max_attempts: int = 3,
    script_format: str = "free",
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
                topic, config, raw_script, video_length, language, visual_mode, script_format
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
    script_format: str = "free",
) -> ScriptOutput:
    system_prompt = _build_system_prompt(video_length, language, visual_mode, script_format)
    user_prompt = _build_user_prompt(topic, raw_script)
    facts: list[str] = []
    if script_format == "what_if" and not raw_script:
        # Facts first, then the story: a model asked to be vivid and correct
        # in one go was vivid. Collected on their own, with the instruction
        # to leave out anything uncertain, they are the only claims the
        # script may make.
        facts = await _collect_facts(topic, config)
        if facts:
            user_prompt += (
                "\n\nVerified facts — the only factual claims the script may make; "
                "pick the most surprising, everyday ones and tell them in the viewer's "
                "own day:\n" + "\n".join(f"- {f}" for f in facts)
            )

    raw_text = await _call_llm(config, system_prompt, user_prompt)
    parsed = _extract_json(raw_text)
    await _rewrite_named_prompts(parsed, topic, config)
    # Only for the generated modes: a stock search is keywords, and
    # "close-up of feet" is a perfectly good thing to look for in a
    # library of real footage — somebody filmed it properly.
    if script_format == "what_if" and not raw_script:
        parsed = await _review_what_if(parsed, topic, language, video_length, config, facts)
    if visual_mode != "stock_media":
        await _rewrite_badly_framed_prompts(parsed, config)
    return _to_script_output(topic, parsed, video_length, script_format)


WHAT_IF_REVIEW_PROMPT = """\
You are the fact-checker and editor of a "what would happen if" short-video \
script, written in {language_name}. You get the script as JSON and return \
the SAME JSON shape with every problem fixed. Check each "voiceover_line":

0. When a list of verified facts is given, every factual claim must come \
from it; replace any other claim with one from the list.
1. Is the fact true of THIS subject specifically? A food, product, record \
or tradition that belongs to another country or thing must go. A \
superlative must be literally true ("Europe's largest" is not "the \
world's largest").
2. Is it consistent with the premise? Whatever vanished takes everything \
inside it with it — its rivers, forests, cities, people — so a line about \
one of those still existing, or about something that would not change, \
must go.
3. Does it make literal sense? Remove non-sequiturs and lines that sound \
nice but mean nothing.
4. Is it concrete? Replace vague lines ("things change", "everyone looks \
for something") with a specific, true, everyday consequence.
5. Is the "But..." turn a real twist grounded in fact? If not, rewrite it \
into one.
6. The last line before the closing question must be a surprising fact, \
never a summary.

7. Tone: light and curious. Remove any war, genocide, memorial or \
disaster with victims, whatever its place in history.
8. Voice: you fix facts, never the storytelling. Keep it told to the \
viewer in the second person, inside their own day (breakfast, kitchen, \
phone, holiday). No sentence pattern ("X disappears", "X is gone") more \
than twice — rewrite the rest as what the viewer notices.
9. The first scene's line IS the hook: a mysterious question to the \
viewer about the hypothetical. Keep it first; never drop it.
10. The last scene asks the viewer a question that invites a comment \
("Which country should vanish next?").

When a fact is doubtful, replace it with one you are certain of rather \
than softening it. Keep the hook, keep the scene count within one, keep \
lines short (5-10 words) and in the second person where they were. When \
you change a line, rewrite its "visual_prompt" to match (an illustrated \
scene, no maps, no text). Keep "keep_out", "music_mood", "post", \
"call_to_action", "counter", "tally_title" and every scene's "tally", \
"icon" and "stamp" unless they are wrong; when you change a line, change \
its tally and icon to match.

Respond with ONLY the corrected JSON object.
"""


FACTS_PROMPT = """\
You research a "what would happen if" short video. For the hypothetical you \
are given, list what the REST of the world concretely depends on from the \
thing that vanished, or what physically changes — the facts such a video \
is built from.

Rules:
- 10 to 14 facts, each one sentence in English, specific (a named product, \
food, place, industry, species, route, record) and checkable in an \
encyclopedia.
- Numbers only when well established; round them and say "about". Never a \
percentage of damage, loss or decline.
- Only facts you are certain of. Leave out anything you would hesitate \
over; ten certain facts beat fourteen with one wrong.
- Consistent with the premise: whatever vanishes takes everything inside \
it (its rivers, cities, people). Facts are about the rest of the world.
- Prefer things an ordinary person has touched, eaten, watched or used.
- Mind borders: a forest, river, mountain or sea shared with a neighbour \
loses only the part inside.
- Light and curious, never grim: no wars, genocide, memorials or \
disasters with victims, however well known. These videos are watched for \
fun and by the country's own people.

Respond with ONLY JSON: {"facts": ["...", "..."]}
"""


async def _collect_facts(topic: str, config: LLMConfig) -> list[str]:
    """The checked facts a "what if?" script is written from. Empty when the
    model does not answer usably — the script is then written as before."""
    try:
        parsed = _extract_json(await _call_llm(config, FACTS_PROMPT, f"Hypothetical: {topic}"))
    except Exception:  # noqa: BLE001 - facts are an aid, not a requirement
        logger.warning("Collecting facts failed; writing without them", exc_info=True)
        return []
    facts = parsed.get("facts") if isinstance(parsed, dict) else None
    if not isinstance(facts, list):
        return []
    return [f.strip()[:240] for f in facts if isinstance(f, str) and f.strip()][:14]


async def _review_what_if(
    parsed: dict,
    topic: str,
    language: str,
    video_length: VideoLength,
    config: LLMConfig,
    facts: list[str] | None = None,
) -> dict:
    """A second pass over a "what if?" script, as a fact-checker.

    The first pass follows the shape well and invents freely: on gpt-4.1 a
    Poland script had fish and chips for breakfast, "the world's largest"
    apple orchards and a "two seas meet" line copied from the prompt's own
    example. Reviewing a finished script against a checklist is a much
    easier task than writing one under twenty rules, and catches those.

    Never makes things worse than it found them: if the reply does not parse
    or has lost scenes, the original is kept.
    """
    import json as _json

    try:
        raw = await _call_llm(
            config,
            WHAT_IF_REVIEW_PROMPT.format(language_name=LANGUAGE_NAMES.get(language, language)),
            f"Topic: {topic}\n\n"
            + (
                "Facts the script was written from (verified):\n"
                + "\n".join(f"- {f}" for f in facts)
                + "\n\n"
                if facts
                else ""
            )
            + f"Script:\n{_json.dumps(parsed, ensure_ascii=False)}",
        )
        reviewed = _extract_json(raw)
    except Exception:  # noqa: BLE001 - the unreviewed script is still a script
        logger.warning("What-if review failed; keeping the first draft", exc_info=True)
        return parsed
    scenes = reviewed.get("scenes") if isinstance(reviewed, dict) else None
    floor = scene_count(video_length, "what_if")[0] - 1
    if not isinstance(scenes, list) or len(scenes) < floor:
        logger.warning("What-if review returned an unusable script; keeping the first draft")
        return parsed
    return reviewed


async def _call_llm(config: LLMConfig, system_prompt: str, prompt: str) -> str:
    if config.provider == LLMProvider.OLLAMA:
        return await _call_ollama(config, system_prompt, prompt)
    if config.provider == LLMProvider.OPENAI:
        return await _call_openai(config, system_prompt, prompt)
    raise ScriptGenerationError(f"Unsupported LLM provider: {config.provider}")


async def complete_json(config: LLMConfig, system_prompt: str, prompt: str) -> dict:
    """Ask the configured model for JSON and hand back the parsed object.

    The same provider dispatch and the same forgiving parser the script
    generator uses — local models wrap JSON in prose often enough that
    anything calling a model needs `_extract_json`, not `json.loads`.
    Exposed so other services (dubbing) get that behaviour without
    reaching into this module's privates or building a second LLM client.
    """
    raw = await _call_llm(config, system_prompt, prompt)
    return _extract_json(raw)


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


# Compositions the image model reliably fails at, detected in the prompt
# rather than trusted to the rule that already forbids them.
#
# The rule is in SYSTEM_PROMPT_TEMPLATE and it is followed most of the
# time. Three paid renders say what "most" means: a crowd of six
# photographers with twelve unusable feet, a table of interlocking hands,
# and a close-up of feet on a dance floor — each after the rule was
# written, each a scene the customer had to look at. Writing it more
# firmly a fourth time is not a plan.
#
# So this is the same shape as visual_prompts_naming: a check that does
# not rely on the model remembering. Deliberately narrow — these match a
# subject, not a mention. "a woman walking, hands in her pockets" is a
# portrait with hands in it and comes out fine; "a close-up of hands" is
# the failure.
_SUBJECT_LEAD = (
    r"(?:close[-\s]?up|closeup|shot|view|image|photo|macro)\s+of\s+"
    r"(?:a|an|the|some|someone'?s?|a\s+person'?s?|two)?\s*"
)
_EXTREMITIES = r"(?:hands?|feet|foot|fingers?|toes?|palms?)"

# Objects whose whole point is the writing on them. The existing text rule
# forbids describing legible text, which does not help when the *object*
# carries it: "a metronome ticking on a table" names no text and came back
# with a dial reading 70, 20, 480, 1955.
# Objects that carry writing whether or not the prompt asks for any.
#
# Maps were added after a paid "world war 2" render came back with two of
# its nine scenes showing Europe labelled ZAIIRA, PICHISITALLA and KOBGAN.
# They are the worst case of the whole category — a map is nothing but
# text on colour — and the model will always attempt the labels.
#
# "globe" is deliberately absent despite being a map wrapped round a ball:
# it is also a lamp, and "a globe of warm light from a paper lantern" is a
# prompt that works and must not be rewritten. Matching anywhere in the
# sentence (below) means an ambiguous word costs more than a missed one.
_TEXT_BEARING = (
    r"(?:metronome|clock|wall\s+clock|watch|gauge|dial|speedometer|thermometer|"
    r"calendar|newspaper|magazine|book\s+cover|poster|billboard|license\s+plate|"
    r"scoreboard|price\s+tag|map|atlas|chart|graph|diagram|blueprint|"
    r"schematic|document|certificate|menu|signpost|banner|"
    r"(?:street|road|neon|shop)\s+sign)"
)

_BAD_FRAMING = [
    re.compile(_SUBJECT_LEAD + _EXTREMITIES, re.I),
    re.compile(r"^\s*(?:a\s+|an\s+|the\s+)?(?:pair\s+of\s+)?" + _EXTREMITIES + r"\b", re.I),
    re.compile(r"\b(?:crowd|crowds|audience|group\s+of|groups\s+of|team\s+of|"
               r"several\s+people|many\s+people|bunch\s+of\s+people)\b", re.I),
    re.compile(r"\bfull[-\s]body\b", re.I),
    re.compile(r"\b(?:lying\s+down|lying\s+on|laying\s+down|lies\s+on)\b", re.I),
    # Anywhere in the prompt, not only as the lead subject. The two that
    # shipped were "A vintage world map showing Europe" and "A map of
    # Europe being redrawn" — the first slipped past a lead-anchored
    # pattern because two adjectives sat between the article and the noun,
    # and a map in the background is unreadable in exactly the same way as
    # one in the foreground. Unlike the framing rules above, this failure
    # is about the object being in frame at all, not about how it is shot.
    re.compile(r"\b" + _TEXT_BEARING + r"s?\b", re.I),
]


def visual_prompts_framing(scenes: list[dict]) -> list[int]:
    """Indices whose visual prompt asks for a shot that reliably fails.

    Pure and keyword-based on purpose. A second LLM deciding whether a
    prompt is well framed would have the same failure mode as the first
    one — it would agree most of the time — and the whole reason this
    exists is that "most of the time" already happened three times.
    """
    hits = []
    for i, scene in enumerate(scenes):
        prompt = scene.get("visual_prompt") or ""
        if any(pattern.search(prompt) for pattern in _BAD_FRAMING):
            hits.append(i)
    return hits


FRAMING_REWRITE_SYSTEM_PROMPT = """\
You rewrite image-generation prompts that ask for shots a diffusion model
cannot draw.

Each prompt you are given asks for one of: hands or feet as the subject, a
crowd or group of people, a full-body shot, someone lying down, or an
object covered in numbers or writing such as a clock, a metronome or a
map. Every one of those comes back deformed or unreadable.

Rewrite each to describe the same moment with a shot that works: one
person at most, framed as a close-up, a portrait or a medium shot from the
waist up — or, where the line is about an action or a thing, the setting
or the object itself with no figure and no dial.

Examples:
"a close-up of feet performing a dance step on a wooden floor" becomes
"a dancer's face lit from the side, mid-movement, wooden studio floor behind".
"a group of photographers at a shoot" becomes
"a single photographer raising a camera, studio lights soft behind him".
"a metronome ticking on a table" becomes
"a wooden table in warm side light, a brass pendulum blurred mid-swing".
"a vintage map of Europe with borders and labels" becomes
"a candlelit desk, dividers and a curled parchment edge, no lettering".

Keep each rewrite under 20 words. Respond with ONLY valid JSON:
{"prompts": ["rewritten prompt", "rewritten prompt"]}
"""


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


async def _rewrite_badly_framed_prompts(parsed: dict, config: LLMConfig) -> None:
    """Replace visual prompts asking for shots the model cannot draw.

    Same shape as _rewrite_named_prompts and for the same reason: the rule
    is in the system prompt, it is followed most of the time, and "most"
    has now cost three paid renders a scene each. One extra call for the
    whole batch, and a failure leaves the originals — a badly framed
    prompt is what we already had.
    """
    scenes = parsed.get("scenes")
    if not isinstance(scenes, list):
        return
    hits = visual_prompts_framing(scenes)
    if not hits:
        return

    numbered = "\n".join(f"{n + 1}. {scenes[i].get('visual_prompt')}" for n, i in enumerate(hits))
    try:
        raw = await _call_llm(config, FRAMING_REWRITE_SYSTEM_PROMPT, numbered)
        rewritten = _extract_json(raw).get("prompts")
        if not isinstance(rewritten, list) or len(rewritten) != len(hits):
            raise ScriptGenerationError("framing rewrite returned the wrong number of prompts")
    except Exception as exc:  # noqa: BLE001 - a failed rewrite is not a failed render
        logger.warning("Could not reframe %d visual prompt(s): %s", len(hits), exc)
        return

    for index, prompt in zip(hits, rewritten, strict=True):
        if isinstance(prompt, str) and prompt.strip():
            logger.info(
                "Reframed a visual prompt the model draws badly: %r -> %r",
                scenes[index].get("visual_prompt"),
                prompt,
            )
            scenes[index]["visual_prompt"] = prompt.strip()


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


_HASHTAG_STRIP = re.compile(r"[^0-9A-Za-z_À-ɏͰ-῿]+")


def _to_post_copy(parsed: dict, topic: str, hook: str, call_to_action: str | None) -> PostCopy:
    """The caption, title and tags the video is published under.

    Never raises and never returns None. That is the point of it: the
    automatic publish path runs when nobody is watching, and a model that
    dropped the "post" key — which local ones do — must not be the reason
    a finished render cannot be posted. So everything here degrades to
    something derived from the script, which is always present.

    The derived version is not as good as the written one. It is better
    than a title of "" , which YouTube rejects outright.
    """
    raw = parsed.get("post")
    if not isinstance(raw, dict):
        raw = {}

    title = _first_present(raw, ["title", "post_title", "headline"]) or hook or topic
    description = (
        _first_present(raw, ["description", "caption", "post_description", "body"])
        or " ".join(part for part in (hook, call_to_action) if part)
        or topic
    )

    tags: list[str] = []
    raw_tags = raw.get("hashtags") or raw.get("tags") or []
    # Models sometimes hand back "#one #two #three" as a single string
    # instead of a list.
    if isinstance(raw_tags, str):
        raw_tags = raw_tags.split()
    if isinstance(raw_tags, list):
        for tag in raw_tags:
            if not isinstance(tag, str):
                continue
            # Stored bare: the '#' is punctuation each platform applies
            # itself, and a stored one would have to be stripped before
            # any of them could use it. Spaces and emoji go too — a
            # hashtag containing either is not a hashtag anywhere.
            cleaned = _HASHTAG_STRIP.sub("", tag)
            if cleaned and cleaned.lower() not in {t.lower() for t in tags}:
                tags.append(cleaned)

    try:
        # Truncated rather than rejected. A model that wrote 140 characters
        # of title produced usable copy and one unusable field, and losing
        # the whole post over it would be the wrong trade.
        return PostCopy(
            title=title.strip()[:100],
            description=description.strip()[:2200],
            hashtags=tags[:15],
        )
    except ValidationError as exc:  # pragma: no cover - defensive
        logger.warning("Unusable post copy (%s); falling back to the topic", exc)
        return PostCopy(title=topic[:100], description=topic[:2200])


def _bare_line(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.casefold()).strip()


def _short(raw: object, limit: int) -> str | None:
    text = " ".join(raw.split()) if isinstance(raw, str) else ""
    return text[:limit] or None


def _scene_graphic(raw_scene: dict) -> SceneGraphic | None:
    """A scene's graphic fields, when the model wrote any. An icon outside
    graphics.ICONS is dropped rather than drawn as a box."""
    icon = _short(raw_scene.get("icon"), 24)
    graphic = SceneGraphic(
        tally=_short(raw_scene.get("tally"), 40),
        icon=icon.lower() if icon and icon.lower() in ICONS else None,
        stamp=_short(raw_scene.get("stamp"), 24),
    )
    return graphic if (graphic.tally or graphic.stamp) else None


def _counter(raw: object) -> GraphicCounter | None:
    if not isinstance(raw, dict):
        return None
    try:
        label = _short(raw.get("label"), 40)
        start, end = int(raw.get("start")), int(raw.get("end", 0))  # type: ignore[arg-type]
        if not label or start <= end:
            return None
        return GraphicCounter(label=label, start=start, end=end)
    except (TypeError, ValueError, ValidationError):
        return None


MUSIC_MOODS = ("upbeat", "lofi", "atmospheric", "suspense")


def _music_mood(raw: object) -> str | None:
    mood = raw.strip().lower() if isinstance(raw, str) else ""
    return mood if mood in MUSIC_MOODS else None


def _keep_out(raw: object) -> str:
    """The model's "keep_out" as negative-prompt terms: words and commas
    only, a handful of terms, so a stray sentence cannot become one."""
    if not isinstance(raw, str):
        return ""
    terms = [re.sub(r"[^\w\s-]", "", t).strip() for t in raw.split(",")]
    return ", ".join(t for t in terms if t and len(t) <= 40)[:160]


def _to_script_output(
    topic: str,
    parsed: dict,
    video_length: VideoLength = VideoLength.SHORT,
    script_format: str = "free",
) -> ScriptOutput:
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
                graphic=_scene_graphic(raw_scene),
            )
        except (ValueError, TypeError, AttributeError, ValidationError) as exc:
            logger.warning("Skipping scene %d (%s): %r", raw_index, exc, raw_scene)
            continue

        scenes.append(scene)

    if not scenes:
        raise ScriptGenerationError("Model returned zero usable scenes")

    # "hook" is metadata; only scenes are spoken. A Poland script came back
    # with its hook in the field and not in the voiceover, and the video
    # opened mid-story — so a "what if?" hook missing from the first scene
    # is put back as one, over the first scene's picture.
    hook_text = _first_present(parsed, ["hook"])
    if script_format == "what_if" and hook_text and _bare_line(hook_text) not in _bare_line(
        scenes[0].audio.voiceover_line
    ):
        scenes.insert(
            0,
            Scene(
                index=0,
                duration_s=scenes[0].duration_s,
                visual=SceneVisual(prompt=scenes[0].visual.prompt),
                audio=SceneAudio(voiceover_line=hook_text),
            ),
        )
        for i, scene in enumerate(scenes):
            scene.index = i

    # What must not be drawn in any scene (the "what if?" format asks for
    # it: the Moon kept turning up in a video about the Moon being gone).
    keep_out = _keep_out(parsed.get("keep_out"))
    if keep_out:
        for scene in scenes:
            scene.visual.negative_prompt = keep_out

    # SCENE_COUNT_BY_LENGTH is an instruction in the prompt, and a model
    # that ignores it used to cost nothing but local CPU. It is now the
    # only unbounded term in the price of a render: one image is generated
    # per scene, billed per image, against a charge fixed by the length
    # preset the buyer picked. Thirty scenes on a three-credit short is a
    # three-minute "short" as well, so the cap is right on its own terms.
    max_scenes = scene_count(video_length, script_format)[1]
    if len(scenes) > max_scenes:
        logger.warning(
            "Model returned %d scenes for a %s video; keeping the first %d",
            len(scenes),
            video_length,
            max_scenes,
        )
        # The last scene is kept: it is the closing line or question, and
        # the one a video can least do without.
        scenes = [*scenes[: max_scenes - 1], scenes[-1]]
        for i, scene in enumerate(scenes):
            scene.index = i

    hook = parsed.get("hook", scenes[0].audio.voiceover_line)
    call_to_action = parsed.get("call_to_action")

    try:
        return ScriptOutput(
            topic=topic,
            hook=hook,
            scenes=scenes,
            total_duration_s=sum(s.duration_s for s in scenes),
            call_to_action=call_to_action,
            post=_to_post_copy(parsed, topic, hook, call_to_action),
            music_mood=_music_mood(parsed.get("music_mood")),
            counter=_counter(parsed.get("counter")),
            tally_title=_short(parsed.get("tally_title"), 40),
        )
    except ValidationError as exc:
        raise ScriptGenerationError(f"Malformed script structure: {exc}") from exc
