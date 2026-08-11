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
}


def by_id(voice_id: str) -> Voice | None:
    return next((voice for voice in VOICES if voice.id == voice_id), None)


def for_language(language: str) -> list[Voice]:
    return [voice for voice in VOICES if voice.language == language]
