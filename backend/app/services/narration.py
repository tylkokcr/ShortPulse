"""How a generated video's narration is voiced.

The voice is decided on the server, like the script model: a request names
a voice from the catalog, and everything else — which engine speaks it and
how it is read — follows from settings and from the script format.
"""

from __future__ import annotations

from app.engines.script_engine import LANGUAGE_NAMES
from app.schemas.project import TTSProvider, VoiceConfig
from app.services import voices as voice_catalog

# How each script format is read. Piper cannot be told any of this; it is
# what OpenAI's speech model is steered with.
_DELIVERY: dict[str, str] = {
    "free": (
        "A lively short-form video narrator, like a curious friend sharing a "
        "surprising fact. Vary pitch and pace, lean on the key word of each "
        "sentence, keep it brisk and warm. Never flat or monotone."
    ),
    "what_if": (
        "A gripping documentary storyteller narrating a thought experiment as it "
        "unfolds. Calm and ominous at the start, building tension with each "
        "consequence; a short pause before the final twist, then land it. Vary "
        "pitch and pace; never flat or monotone."
    ),
}


def instructions(script_format: str, language: str) -> str:
    """The delivery for a format, spoken with a native accent."""
    name = LANGUAGE_NAMES.get(language, language)
    return f"{_DELIVERY.get(script_format, _DELIVERY['free'])} Speak natural {name} with a native accent."


def resolve(voice: VoiceConfig, language: str, script_format: str) -> VoiceConfig:
    """The voice a generated video is rendered with.

    An OpenAI voice is honoured when the server narrates through OpenAI and
    falls back to the default otherwise; a Piper voice from the catalog is
    kept; an empty or unknown id gets the default. The provider and the
    instructions are always the server's — a request cannot route the text
    to another engine or say how it is read."""
    picked = voice_catalog.by_id(voice.voice_id) if voice.voice_id else None
    voice_id = picked.id if picked else voice_catalog.default_voice_id(language)
    provider = provider_for(voice_id)
    return VoiceConfig(
        provider=provider,
        voice_id=voice_id,
        # Only OpenAI's model reads instructions; MiniMax picks the emotion
        # from the text itself.
        instructions=instructions(script_format, language) if provider == TTSProvider.OPENAI else "",
    )


def provider_for(voice_id: str) -> TTSProvider:
    if voice_id.startswith("minimax:"):
        return TTSProvider.MINIMAX
    if voice_id.startswith("openai:"):
        return TTSProvider.OPENAI
    return TTSProvider.PIPER
