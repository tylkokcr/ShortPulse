"""Which words to bleep, and where they are.

Whisper times every word individually — that is what makes the caption
highlight follow the speech — so censoring is not a transcription
problem here. It is a lookup: decide which of the timed words to hide,
and hand their spans to the two places that can act on them. The audio
is silenced and a tone put in its place; the caption shows `***`.

Both halves matter. Bleeping the audio and leaving the word written
across the screen censors nothing, and masking only the caption leaves
it audible — either one alone is theatre.

What this is not
----------------

It is not a safety system and must not be described as one. The list is
finite, spelling is infinite, and no list survives someone who wants
past it. This exists so that a video meant for a platform with
advertiser rules does not need re-recording over one word — a
convenience for the person who made it, not a guarantee to anyone else.

Matching is deliberately conservative
-------------------------------------

Whole words only, never substrings. Substring matching is how "Scunthorpe"
becomes unpublishable, and a caption that bleeps a syllable out of an
innocent word is a worse failure than missing a real one: the first is
visibly broken, the second is what the user already had.

The lists are short on purpose — the handful of words a platform's
automated review actually acts on, per language, rather than an
exhaustive catalogue of insults. `PROFANITY_EXTRA` is there because no
fixed list fits everyone's channel.
"""

from __future__ import annotations

import re
import unicodedata

from app.schemas.project import Word

# The strong words each language's platforms actually demonetise for,
# stems included where the language inflects them. Kept deliberately
# small: every entry is a word this will silence in someone's video, so
# the bar for adding one is "a platform acts on it", not "it is rude".
_LISTS: dict[str, set[str]] = {
    "en": {
        "fuck", "fucks", "fucked", "fucking", "fucker", "fuckers",
        "shit", "shits", "shitty", "bullshit",
        "bitch", "bitches", "cunt", "cunts",
        "asshole", "assholes", "dick", "dickhead", "motherfucker", "motherfuckers",
    },
    "tr": {
        "sik", "siker", "sikik", "sikim", "siktir", "sikeyim", "siktir et",
        "amk", "aq", "amina", "amına", "amcık", "amcik",
        "orospu", "piç", "pic", "yarrak", "göt", "got veren", "gavat",
        "pezevenk", "kahpe",
    },
    "es": {
        "joder", "jodido", "mierda", "puta", "putas", "puto", "putos",
        "coño", "gilipollas", "cabrón", "cabron", "hijoputa",
    },
    "fr": {
        "putain", "merde", "connard", "connards", "connasse",
        "salope", "enculé", "encule", "bordel", "foutre",
    },
    "de": {
        "scheiße", "scheisse", "scheiß", "scheiss", "ficken", "fick",
        "fotze", "wichser", "arschloch", "hurensohn",
    },
    "pt": {
        "foda", "foder", "fodido", "merda", "caralho", "porra",
        "puta", "putas", "cabrão", "cabrao", "filho da puta",
    },
    "it": {
        "cazzo", "merda", "stronzo", "stronza", "vaffanculo",
        "puttana", "troia", "coglione",
    },
    "ru": {
        "блядь", "бля", "хуй", "хуя", "пизда", "пиздец", "ебать", "ёбаный",
        "ебаный", "сука", "мудак",
    },
    "ar": {
        "كس", "خرا", "عرص", "شرموط", "شرموطة", "زبي", "منيك",
    },
}

# What replaces the word on screen. Three asterisks rather than one per
# letter: a mask that spells out the length is a puzzle, and a caption
# that changes width mid-line reflows the one after it.
MASK = "***"

# Padding around the silence, in milliseconds. Whisper's boundaries land
# on the vowel, not on the plosive that starts the word, so a bleep cut
# exactly to the timestamps leaves the first consonant audible — which is
# usually the recognisable part.
PAD_MS = 60


# Everything that is not a letter, for the language's own alphabet. Used
# to strip the punctuation Whisper attaches to a word — "shit," and
# "shit" are the same word and only one of them would match.
_EDGES = re.compile(r"^\W+|\W+$", re.UNICODE)


def _normalise(text: str, language: str) -> str:
    """A word, reduced to what is worth comparing.

    `casefold` rather than `lower`: it folds the German ß to ss and the
    Cyrillic and Greek cases the way a lookup needs. Turkish is the one
    language where that is not enough — casefold maps I to i, but Turkish
    I lowercases to ı, so "SIK" would fold to "sik" and match a word the
    speaker did not say. Mapping the dotless pair explicitly first is
    what keeps that apart.
    """
    text = _EDGES.sub("", text)
    if language == "tr":
        text = text.replace("I", "ı").replace("İ", "i")
    # NFKC so a composed and a decomposed form of the same accented word
    # compare equal — Whisper is not consistent about which it emits.
    return unicodedata.normalize("NFKC", text.casefold())


def word_list(language: str, extra: str = "") -> set[str]:
    """The words to censor for one language.

    An unknown language gets the English list rather than nothing: a
    video in a language with no list of its own is more likely to contain
    English swearing than none at all, and returning an empty set would
    make the toggle silently do nothing.
    """
    base = _LISTS.get(language, _LISTS["en"])
    added = {
        _normalise(part, language)
        for part in extra.split(",")
        if _normalise(part, language)
    }
    return {_normalise(w, language) for w in base} | added


def is_profane(text: str, language: str, extra: str = "") -> bool:
    return _normalise(text, language) in word_list(language, extra)


def censor_words(words: list[Word], language: str, extra: str = "") -> list[Word]:
    """The same words, with the ones to hide replaced by the mask.

    A new list rather than a mutation: the uncensored transcript is what
    the editor shows and what a re-render without the toggle has to be
    able to produce again. Overwriting it here would make the choice
    permanent the first time it was made.
    """
    listed = word_list(language, extra)
    return [
        word.model_copy(update={"text": MASK})
        if _normalise(word.text, language) in listed
        else word
        for word in words
    ]


def spans(words: list[Word], language: str, extra: str = "") -> list[tuple[float, float]]:
    """When to silence the audio, in seconds, merged and padded.

    Merged because two swear words in a row produce two spans a few
    milliseconds apart, and a tone that stops and restarts in that gap
    sounds like a fault rather than a bleep.
    """
    listed = word_list(language, extra)
    hits = [
        (max(word.start_ms - PAD_MS, 0), word.end_ms + PAD_MS)
        for word in words
        if _normalise(word.text, language) in listed
    ]
    if not hits:
        return []

    hits.sort()
    merged = [hits[0]]
    for start, end in hits[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return [(start / 1000, end / 1000) for start, end in merged]
