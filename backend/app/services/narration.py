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
    "story": (
        "An intimate first-person storyteller recalling what happened to them, "
        "like telling a close friend late at night: quiet, personal, a catch in the "
        "voice at the turns, unhurried. Never flat or monotone."
    ),
    "outbreak": (
        "A tense thriller narrator telling a survival story as it happens. Low and "
        "urgent, quickening as the danger grows, a held breath before each reveal, "
        "and a quiet, ominous final line. Never flat or monotone."
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
        # A story told slower: the "what if?" narrators the format is
        # modelled on take their time and let lines land.
        rate=(
            "-6%"
            if script_format in ("what_if", "outbreak", "story") and provider == TTSProvider.MINIMAX
            else "+0%"
        ),
        # Only OpenAI's model reads instructions; MiniMax picks the emotion
        # from the text itself.
        instructions=instructions(script_format, language) if provider == TTSProvider.OPENAI else "",
    )


def provider_for(voice_id: str) -> TTSProvider:
    if voice_id.startswith("elevenlabs:"):
        return TTSProvider.ELEVENLABS
    if voice_id.startswith("minimax:"):
        return TTSProvider.MINIMAX
    if voice_id.startswith("openai:"):
        return TTSProvider.OPENAI
    return TTSProvider.PIPER


# How a story line's tone tags are acted, as directions for OpenAI's model.
_TONE_DIRECTION = {
    "whispers": "in a trembling whisper", "softly": "softly and warmly",
    "tense": "tense and low, holding something back", "nervous": "nervous and hesitant",
    "scared": "frightened, the breath catching", "sad": "sad and heavy",
    "crying": "through tears, the voice breaking", "sighs": "with a long sigh",
    "angry": "angry and sharp", "shouting": "shouting, loud and raw",
    "laughs": "laughing", "excited": "excited and quick", "curious": "curious",
    "surprised": "surprised", "shocked": "shocked, gasping", "firm": "firm and controlled",
    "tired": "tired", "sarcastic": "sarcastic",
}


def acting_instructions(member, tone: str | None, narrating: bool, language: str) -> str:
    """Direction for one line of a story, for a model that takes it (OpenAI):
    who is speaking, how they feel saying it, and the language."""
    gender = (member.gender or "").lower()
    who = f"{member.name}, a {member.age}-year-old {gender}" if member.age else member.name
    if gender in ("girl", "boy") or (member.age and member.age < 14):
        who += " — a real child's voice, small and high"
    how = ", ".join(
        _TONE_DIRECTION[t.strip()] for t in (tone or "").split(",") if t.strip() in _TONE_DIRECTION
    )
    role = (
        "telling their own story in the first person, intimate, as if confessing to a close "
        "friend late at night"
        if narrating
        else "saying this line in a scene of a gripping audio drama"
    )
    name = LANGUAGE_NAMES.get(language, language)
    return (
        f"You are voicing {who}, {role}. Say it {how or 'as the moment calls for'}. "
        "Act it with real emotion like a voice actor: vary pitch, pace and volume, "
        f"never flat, never robotic. Speak natural {name} with a native accent."
    )
