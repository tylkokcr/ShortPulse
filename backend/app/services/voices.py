"""The selectable Piper voice catalog.

Every key here was checked against `rhasspy/piper-voices` rather than
guessed — a key that doesn't exist fails at render time, after the user has
already been charged, with a HuggingFace 404 that means nothing to them.
`tests/test_voice_catalog.py` re-checks them against the published index.

Voices are described by region and quality because that is what the
upstream catalog actually records. It carries no gender field, so none is
claimed here; the two `hfc_*` models are the exception, and only because
the model name itself states it. To hear the difference, use the preview
endpoint — that beats any adjective we could invent.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.engines.audio_engine import PIPER_VOICE_BY_LANGUAGE


@dataclass(frozen=True)
class Voice:
    """`id` is the Piper repo path, which is exactly what
    `VoiceConfig.voice_id` expects."""

    id: str
    name: str
    language: str
    region: str
    quality: str

    @property
    def is_default(self) -> bool:
        return PIPER_VOICE_BY_LANGUAGE.get(self.language) == self.id


def _v(id: str, name: str, language: str, region: str, quality: str) -> Voice:
    return Voice(id=id, name=name, language=language, region=region, quality=quality)


# Curated rather than exhaustive: the repo ships 173 voices, many at
# "x_low"/"low" quality that sound noticeably worse than the medium models
# and would only make the picker harder to choose from.
VOICES: tuple[Voice, ...] = (
    # English
    _v("en/en_US/ryan/medium/en_US-ryan-medium", "Ryan", "en", "US", "medium"),
    _v("en/en_US/amy/medium/en_US-amy-medium", "Amy", "en", "US", "medium"),
    _v("en/en_US/lessac/medium/en_US-lessac-medium", "Lessac", "en", "US", "medium"),
    _v("en/en_US/hfc_female/medium/en_US-hfc_female-medium", "HFC Female", "en", "US", "medium"),
    _v("en/en_US/hfc_male/medium/en_US-hfc_male-medium", "HFC Male", "en", "US", "medium"),
    _v("en/en_GB/alan/medium/en_GB-alan-medium", "Alan", "en", "UK", "medium"),
    _v("en/en_GB/cori/medium/en_GB-cori-medium", "Cori", "en", "UK", "medium"),
    # Turkish — the repo ships exactly one Turkish voice.
    _v("tr/tr_TR/dfki/medium/tr_TR-dfki-medium", "DFKI", "tr", "TR", "medium"),
    # Spanish
    _v("es/es_ES/davefx/medium/es_ES-davefx-medium", "DaveFX", "es", "Spain", "medium"),
    _v("es/es_ES/sharvard/medium/es_ES-sharvard-medium", "Sharvard", "es", "Spain", "medium"),
    _v("es/es_MX/ald/medium/es_MX-ald-medium", "Ald", "es", "Mexico", "medium"),
    _v("es/es_AR/daniela/high/es_AR-daniela-high", "Daniela", "es", "Argentina", "high"),
    # French
    _v("fr/fr_FR/tom/medium/fr_FR-tom-medium", "Tom", "fr", "France", "medium"),
    _v("fr/fr_FR/siwis/medium/fr_FR-siwis-medium", "Siwis", "fr", "France", "medium"),
    _v("fr/fr_FR/upmc/medium/fr_FR-upmc-medium", "UPMC", "fr", "France", "medium"),
    # German
    _v("de/de_DE/thorsten/medium/de_DE-thorsten-medium", "Thorsten", "de", "Germany", "medium"),
    _v("de/de_DE/thorsten/high/de_DE-thorsten-high", "Thorsten HQ", "de", "Germany", "high"),
    _v("de/de_DE/mls/medium/de_DE-mls-medium", "MLS", "de", "Germany", "medium"),
    # Portuguese
    _v("pt/pt_BR/faber/medium/pt_BR-faber-medium", "Faber", "pt", "Brazil", "medium"),
    _v("pt/pt_BR/cadu/medium/pt_BR-cadu-medium", "Cadu", "pt", "Brazil", "medium"),
    _v("pt/pt_BR/jeff/medium/pt_BR-jeff-medium", "Jeff", "pt", "Brazil", "medium"),
    # Arabic — one speaker, medium is the better of its two qualities.
    _v("ar/ar_JO/kareem/medium/ar_JO-kareem-medium", "Kareem", "ar", "Jordan", "medium"),
    # Russian
    _v("ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium", "Dmitri", "ru", "Russia", "medium"),
    _v("ru/ru_RU/denis/medium/ru_RU-denis-medium", "Denis", "ru", "Russia", "medium"),
    _v("ru/ru_RU/irina/medium/ru_RU-irina-medium", "Irina", "ru", "Russia", "medium"),
    _v("ru/ru_RU/ruslan/medium/ru_RU-ruslan-medium", "Ruslan", "ru", "Russia", "medium"),
    # Italian
    _v("it/it_IT/paola/medium/it_IT-paola-medium", "Paola", "it", "Italy", "medium"),
    _v("it/it_IT/serena/medium/it_IT-serena-medium", "Serena", "it", "Italy", "medium"),
    # Polish
    _v("pl/pl_PL/darkman/medium/pl_PL-darkman-medium", "Darkman", "pl", "Poland", "medium"),
    _v("pl/pl_PL/gosia/medium/pl_PL-gosia-medium", "Gosia", "pl", "Poland", "medium"),
)

# A short, neutral line per language for the preview endpoint. Written in
# the target language so the sample demonstrates the voice's own accent
# rather than its attempt at a foreign one.
PREVIEW_LINE: dict[str, str] = {
    "en": "This is how your video will sound.",
    "tr": "Videonuz bu sesle anlatılacak.",
    "es": "Así sonará tu vídeo.",
    "fr": "Voici à quoi ressemblera votre vidéo.",
    "de": "So wird dein Video klingen.",
    "pt": "É assim que o seu vídeo vai soar.",
    "ar": "هكذا سيبدو صوت الفيديو الخاص بك.",
    "ru": "Вот как будет звучать ваше видео.",
    "it": "Ecco come suonerà il tuo video.",
    "pl": "Tak będzie brzmiał twój film.",
}


# OpenAI's voices speak every language, so they are offered for each one,
# ahead of Piper's, when the server narrates through OpenAI (see
# openai_enabled). Named as OpenAI names them; "*" for the language.
OPENAI_VOICE_NAMES = ("ash", "coral", "sage", "ballad", "verse", "onyx", "nova", "shimmer")
OPENAI_VOICES: tuple[Voice, ...] = tuple(
    _v(f"openai:{name}", name.capitalize(), "*", "AI", "studio") for name in OPENAI_VOICE_NAMES
)


# MiniMax's system voices, also every language (language_boost sets the
# accent). Few on purpose: these were heard in Turkish before being listed.
MINIMAX_VOICES: tuple[Voice, ...] = (
    _v("minimax:English_CaptivatingStoryteller", "Storyteller", "*", "AI", "studio"),
    _v("minimax:English_Deep-VoicedGentleman", "Deep Voice", "*", "AI", "studio"),
    _v("minimax:English_Wiselady", "Wise Lady", "*", "AI", "studio"),
    # Native voices, offered in their own language only and ahead of the
    # rest there: heard against the English ones reading Turkish, they say
    # it the way a Turkish narrator would.
    _v("minimax:Turkish_Trustworthyman", "Güven Veren", "tr", "AI", "studio"),
    _v("minimax:Turkish_CalmWoman", "Sakin", "tr", "AI", "studio"),
    _v("minimax:German_FriendlyMan", "Freundlich", "de", "AI", "studio"),
)


def openai_enabled() -> bool:
    from app.core.config import get_settings

    settings = get_settings()
    return bool(settings.openai_tts and settings.openai_api_key)


def minimax_enabled() -> bool:
    from app.core.config import get_settings

    settings = get_settings()
    return bool(settings.minimax_tts and settings.replicate_api_token)


def _hosted(language: str | None = None) -> tuple[Voice, ...]:
    minimax = [
        v for v in (MINIMAX_VOICES if minimax_enabled() else ())
        if language is None or v.language in ("*", language)
    ]
    # A language's own voices first.
    minimax.sort(key=lambda v: v.language == "*")
    return (*minimax, *(OPENAI_VOICES if openai_enabled() else ()))


def default_voice_id(language: str) -> str:
    """The voice a video in `language` gets when nobody picked one."""
    from app.core.config import get_settings

    if minimax_enabled():
        settings = get_settings()
        native = settings.minimax_voice_by_language.get(language)
        return f"minimax:{native or settings.minimax_tts_voice}"
    if openai_enabled():
        return f"openai:{get_settings().openai_tts_voice}"
    return PIPER_VOICE_BY_LANGUAGE.get(language, "")


def by_id(voice_id: str) -> Voice | None:
    return next((voice for voice in (*_hosted(), *VOICES) if voice.id == voice_id), None)


def for_language(language: str) -> list[Voice]:
    return [*_hosted(language), *(voice for voice in VOICES if voice.language == language)]


# The voices a story series' cast is given, by who they are. Heard on one
# Turkish line each (2026-11-07, ~/Downloads/shortpulse-ses-4): all of them
# distinct, men 90-110 Hz, women 155-230, girls 290-330. A language's own
# voices come first; the rest speak it through MiniMax's language boost.
_CAST_POOL: dict[str, tuple[str, ...]] = {
    "woman": ("Wise_Woman", "Calm_Woman", "Inspirational_girl", "Lovely_Girl"),
    "man": ("Deep_Voice_Man", "Elegant_Man", "Casual_Guy", "Determined_Man"),
    "girl": ("Lively_Girl", "Sweet_Girl_2", "Exuberant_Girl"),
    "boy": ("Decent_Boy", "Young_Knight"),
    "older_woman": ("Abbess", "Wise_Woman"),
    "older_man": ("Patient_Man", "Deep_Voice_Man"),
}
_NATIVE_CAST: dict[str, dict[str, tuple[str, ...]]] = {
    "tr": {"woman": ("Turkish_CalmWoman",), "man": ("Turkish_Trustworthyman",)},
    "de": {"man": ("German_FriendlyMan",), "woman": ("German_SweetLady",)},
}


def _cast_kind(gender: str, age: int | None) -> str:
    g = (gender or "").strip().lower()
    if g in ("girl", "boy"):
        return g
    child = age is not None and age < 14
    older = age is not None and age >= 60
    if g in ("woman", "female", "f"):
        return "girl" if child else "older_woman" if older else "woman"
    if g in ("man", "male", "m"):
        return "boy" if child else "older_man" if older else "man"
    return "woman"


def assign_cast_voices(cast, language: str) -> None:
    """Give every cast member without one a MiniMax voice, each a different
    one where the pool allows: the first member (the narrator) gets the
    language's own voice of their kind when there is one."""
    used = {m.voice_id for m in cast if m.voice_id}
    lang = (language or "en").split("-")[0]
    for member in cast:
        if member.voice_id:
            continue
        kind = _cast_kind(member.gender, member.age)
        base = kind.removeprefix("older_")
        pool = (*_NATIVE_CAST.get(lang, {}).get(base, ()), *_CAST_POOL[kind])
        choice = next((f"minimax:{v}" for v in pool if f"minimax:{v}" not in used), None)
        member.voice_id = choice or f"minimax:{pool[0]}"
        used.add(member.voice_id)
