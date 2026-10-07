"""Where caption lines break, and that a chosen break is kept."""

from app.engines.subtitle_engine import plan_lines, with_line_starts
from app.schemas.project import Word


def _words(text: str, gap_after: dict[int, int] | None = None) -> list[Word]:
    out, t = [], 0
    for i, token in enumerate(text.split()):
        out.append(Word(text=token, start_ms=t, end_ms=t + 300))
        t += 300 + (gap_after or {}).get(i, 0)
    return out


def _texts(lines: list[list[Word]]) -> list[str]:
    return [" ".join(w.text for w in line) for line in lines]


def test_a_line_does_not_end_on_a_weak_word() -> None:
    lines = plan_lines(_words("This model is specially made"), 4, "en")
    assert _texts(lines) == ["This model", "is specially made"]


def test_lines_are_balanced_rather_than_full_then_a_lone_word() -> None:
    lines = plan_lines(_words("one two three four five"), 4, "en")
    assert [len(line) for line in lines] in ([3, 2], [2, 3])


def test_a_sentence_ends_a_line() -> None:
    lines = plan_lines(_words("They are in stock. You can order"), 4, "en")
    assert _texts(lines)[0] == "They are in stock."


def test_a_comma_is_preferred_as_a_break() -> None:
    lines = plan_lines(_words("Thanks to the collar, it offers more"), 4, "en")
    assert _texts(lines)[0].endswith("collar,")


def test_a_long_pause_ends_a_line() -> None:
    lines = plan_lines(_words("first second third fourth", gap_after={1: 1500}), 4, "en")
    assert _texts(lines) == ["first second", "third fourth"]


def test_marked_line_starts_are_kept_exactly() -> None:
    words = _words("one two three four five six")
    words[0] = words[0].model_copy(update={"starts_line": True})
    words[1] = words[1].model_copy(update={"starts_line": True})
    lines = plan_lines(words, 4, "en")
    assert _texts(lines) == ["one", "two three four five six"]


def test_a_marked_line_that_runs_far_past_the_limit_is_split() -> None:
    words = _words(" ".join(f"w{i}" for i in range(12)))
    words[0] = words[0].model_copy(update={"starts_line": True})
    assert all(len(line) <= 4 for line in plan_lines(words, 4, "en"))


def test_marks_round_trip_through_planning() -> None:
    marked = with_line_starts(_words("This model is specially made. It is warm"), 4, "en")
    assert _texts(plan_lines(marked, 4, "en")) == _texts(
        plan_lines(_words("This model is specially made. It is warm"), 4, "en")
    )
    assert marked[0].starts_line


def test_three_word_lines_still_avoid_a_weak_ending() -> None:
    """Full three-word lines leave no slack to nudge a break, which is where
    'THANKS TO THE' / 'REMOVABLE FUR COLLAR' survived."""
    sentence = "Thanks to the removable fur collar, it offers a different use alternative."
    for line in plan_lines(_words(sentence), 3, "en")[:-1]:
        assert line[-1].text.lower() not in {"the", "a", "to", "of", "with"}
