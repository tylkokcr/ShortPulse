"""What this service will not make a video about.

Refused at the door, not after the render. A topic that is plainly a
request for pornography is turned down before a project row exists and
before a credit is spent, the same way an unavailable visual mode is —
see `projects.create_project`, which was already shaped for exactly this
kind of refusal.

Why it is not a toggle
----------------------

Every other switch in this codebase belongs to the user. This one
belongs to the deployment, because the consequences do. Stripe's rules
prohibit adult content outright and the account behind this service is a
real registered business; a hosted instance generating it risks the
payment processing the whole thing runs on, not the taste of one video.
The platforms the finished videos are published to say the same. So
there is no setting, and the refusal is the same for everyone.

Three layers, cheapest first
----------------------------

1. **This gate.** An unambiguous request is refused before anything is
   spent. It is the only layer the user ever sees.
2. **The script prompt.** `script_engine` tells the model to keep both
   the narration and the visual prompts advertiser-safe, which is what
   stops a borderline topic turning into an explicit `visual_prompt`.
3. **The negative prompt.** `visual_engine` and `art_styles` steer the
   image model away regardless of what it was asked for — the backstop
   for the case where the first two let something through.

Deliberately narrow
-------------------

The list holds explicit pornographic vocabulary, and nothing else. Not
anatomy, not "sex", not "nude" — a video about sex education, breast
cancer screening or Renaissance painting is a legitimate thing to make
and a filter that blocks it is worse than no filter at all, because it
fails silently on exactly the users least likely to complain.

That narrowness is a real limit and the caller should say so rather than
promise safety: this stops someone typing the obvious thing, not someone
determined to get around it.
"""

from __future__ import annotations

import re
import unicodedata

# Unambiguous requests for pornography. Every entry here is a phrase with
# no ordinary use — which is the bar, because the cost of a false
# positive is refusing somebody's legitimate video with a message that
# calls them a pornographer.
_BLOCKED = {
    # English
    "porn", "porno", "pornography", "pornhub", "xxx", "hentai",
    "nsfw", "camgirl", "escort service", "onlyfans",
    "blowjob", "handjob", "creampie", "gangbang", "bukkake",
    "cumshot", "deepthroat", "anal sex", "oral sex scene",
    "sex scene", "sex tape", "explicit sex", "hardcore sex",
    "naked woman", "naked women", "naked man", "naked men",
    "nude model", "nude photoshoot", "topless woman", "topless women",
    "strip club", "stripper pole dance",
    # Turkish. Words already listed above are not repeated — the lists
    # are one set, and several of these terms are the same in every
    # language that borrowed them.
    "pornografi", "seks videosu", "sikiş", "sikis",
    "çıplak kadın", "ciplak kadin", "çıplak erkek", "ciplak erkek",
    "erotik film", "müstehcen",
    # Spanish / Portuguese / Italian / French / German
    "pornografía", "pornografia", "desnuda", "desnudo",
    "film porno", "pornografie", "nacktfoto", "nacktbilder",
}

# The one thing no wording makes acceptable, in any language. Kept apart
# from the list above because it is not a matter of taste or platform
# rules, and because the refusal for it should never be softened into
# "try a different topic".
_CHILD_TERMS = {
    "child", "children", "kid", "kids", "minor", "minors", "teen", "teens",
    "teenage", "underage", "schoolgirl", "schoolboy", "loli", "shota",
    "çocuk", "çocuklar", "ergen", "reşit olmayan",
    "niño", "niña", "criança", "bambino", "enfant", "kind", "kinder",
}
_SEXUAL_TERMS = {
    "sex", "sexual", "sexy", "porn", "porno", "nude", "naked", "erotic",
    "seks", "seksi", "çıplak", "erotik",
    "sexo", "desnudo", "sexuell", "nackt", "sexuel", "nu",
}

# Stems matched at the *start* of a word rather than whole.
#
# Turkish is agglutinative: "porno" becomes "pornosu", "pornoyu",
# "pornodan". Whole-word matching misses every inflected form, and a
# plain substring match is how "seksen" (eighty) gets read as "seks".
# So only stems that no ordinary word begins with go here — "porno" is
# one, "seks" is emphatically not.
_STEMS = {"porno", "pornograf", "hentai", "müstehcen", "mustehcen"}

_WORD_EDGES = re.compile(r"[^\w\s]", re.UNICODE)


class Refused(Exception):
    """The topic will not be made into a video.

    `reason` is written for the person who typed it: it says what was
    refused and what to do, without lecturing and without repeating the
    phrase back at them.
    """

    def __init__(self, reason: str, *, code: str = "content_refused") -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code


def _normalise(text: str) -> str:
    """Lowercased, punctuation-free, one space between words.

    Turkish dotted I is mapped explicitly for the same reason it is in
    `profanity`: casefold turns I into i, which is not what a Turkish
    word does, and the lists here contain Turkish entries.
    """
    text = text.replace("I", "ı").replace("İ", "i")
    text = unicodedata.normalize("NFKC", text.casefold())
    return " ".join(_WORD_EDGES.sub(" ", text).split())


def _contains_word(haystack: str, needle: str) -> bool:
    """Whole words, including multi-word phrases.

    Padding both sides with spaces makes a substring search behave like a
    word-boundary one without a regex per term: " sex " cannot match
    inside "Sussex", and " anal sex " still matches as a phrase.
    """
    return f" {needle} " in f" {haystack} "


def _starts_with_stem(haystack: str) -> bool:
    """Any word beginning with one of the unambiguous stems."""
    return any(word.startswith(stem) for word in haystack.split() for stem in _STEMS)


def check_topic(topic: str, raw_script: str = "") -> None:
    """Raise `Refused` if this must not be generated.

    Both fields, because a raw script bypasses the model that would have
    written one — the narration is spoken by TTS either way.
    """
    text = _normalise(f"{topic} {raw_script}")
    if not text:
        return

    # Checked first and answered differently. A sexualised topic about
    # minors is not a platform-rules problem to be reworded around, and
    # the message must not suggest it is.
    sexual = any(_contains_word(text, term) for term in _SEXUAL_TERMS) or _starts_with_stem(
        text
    )
    if sexual and any(_contains_word(text, term) for term in _CHILD_TERMS):
        raise Refused(
            "This service does not generate sexual content involving minors, "
            "and will not produce a video on this topic.",
            code="content_refused_minors",
        )

    if _starts_with_stem(text):
        raise Refused(
            "This service doesn't generate adult content — the platforms these "
            "videos are published to and the payment provider behind it both "
            "prohibit it. Try a different topic."
        )

    for term in _BLOCKED:
        if _contains_word(text, term):
            raise Refused(
                "This service doesn't generate adult content — the platforms these "
                "videos are published to and the payment provider behind it both "
                "prohibit it. Try a different topic."
            )
