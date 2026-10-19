"""Audio engine helpers: script-aligned captions and joined numbers."""
from __future__ import annotations

# --- captions from the script, timing from Whisper -----------------------


def _heard(*items):
    from app.schemas.project import Word

    return [Word(text=t, start_ms=s, end_ms=e) for t, s, e in items]


def test_a_generated_caption_says_what_the_script_says():
    from app.engines.audio_engine import align_to_script

    heard = _heard(("Honey", 0, 300), ("is", 300, 400), ("as", 420, 520), ("sick,", 520, 800),
                   ("around", 820, 1100), ("3", 1100, 1300), (".2", 1300, 1500), ("to", 1500, 1600),
                   ("4", 1600, 1800), (".5.", 1800, 2000))
    words = align_to_script(heard, "Honey is acidic, around 3.2 to 4.5.")
    assert [w.text for w in words] == ["Honey", "is", "acidic,", "around", "3.2", "to", "4.5."]
    acidic = words[2]
    assert 400 <= acidic.start_ms <= 520 and acidic.end_ms <= 820
    assert words[4].start_ms == 1100 and words[4].end_ms == 1500


def test_a_word_whisper_never_heard_sits_between_its_neighbours():
    from app.engines.audio_engine import align_to_script

    heard = _heard(("It", 0, 200), ("rains", 200, 500), ("three", 600, 800), ("hundred", 800, 1100),
                   ("days.", 1100, 1500))
    words = align_to_script(heard, "It rains 300 days.")
    assert [w.text for w in words] == ["It", "rains", "300", "days."]
    assert words[1].end_ms <= words[2].start_ms <= words[3].start_ms
    assert all(w.end_ms > w.start_ms for w in words)


def test_nothing_heard_or_no_script_leaves_the_words_alone():
    from app.engines.audio_engine import align_to_script

    heard = _heard(("hi", 0, 100))
    assert align_to_script(heard, "") == heard
    assert align_to_script([], "hello") == []


def test_numbers_whisper_split_are_put_back_together():
    from app.engines.audio_engine import join_split_numbers

    words = join_split_numbers(_heard(("about", 0, 100), ("10", 100, 300), (",000", 300, 500),
                                      ("meters,", 500, 800), ("50", 800, 900), ("%", 900, 1000),
                                      ("and", 1000, 1100), (".", 1100, 1150)))
    assert [w.text for w in words] == ["about", "10,000", "meters,", "50%", "and", "."]
    assert words[1].start_ms == 100 and words[1].end_ms == 500
