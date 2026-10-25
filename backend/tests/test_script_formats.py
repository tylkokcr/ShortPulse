"""A script format adds its own rules to the prompt and nothing else."""

from __future__ import annotations

from app.engines.script_engine import FORMAT_RULES, _build_system_prompt
from app.schemas.project import ProjectConfig, ScriptFormat, VideoLength


def test_free_is_the_prompt_as_it_was():
    free = _build_system_prompt(VideoLength.SHORT, "en", "fast_hybrid", "free")
    assert free == _build_system_prompt(VideoLength.SHORT, "en", "fast_hybrid")
    assert "thought experiment" not in free


def test_what_if_adds_its_rules_before_the_json_shape():
    prompt = _build_system_prompt(VideoLength.SHORT, "tr", "fast_hybrid", "what_if")
    rules = prompt.index("thought experiment")
    assert rules < prompt.index("Respond with ONLY valid JSON")
    # The two that keep the genre honest and on the right side of the line.
    assert "a made-up number is" in prompt
    assert "never about whether a people deserves" in prompt
    assert "Never a map" in prompt


def test_every_format_but_free_has_rules_and_the_default_is_free():
    assert {f.value for f in ScriptFormat} - {"free"} == set(FORMAT_RULES)
    assert ProjectConfig(topic="x").script_format == "free"


def test_what_if_never_asks_for_a_measured_loss():
    prompt = _build_system_prompt(VideoLength.SHORT, "en", "fast_hybrid", "what_if")
    # The first version asked for a number in half the scenes and got
    # "car production falls 8%" — a figure nobody could have measured.
    assert "at least half the scenes carry a number" not in prompt
    assert "Never a percentage of" in prompt
    assert "takes everything" in prompt


def test_what_the_script_keeps_out_reaches_every_scene():
    from app.engines.script_engine import _to_script_output

    parsed = {
        "hook": "Tonight the Moon is gone.",
        "scenes": [
            {"voiceover_line": "a", "visual_prompt": "night beach"},
            {"voiceover_line": "b", "visual_prompt": "turtle on sand"},
        ],
        "keep_out": "moon, full moon; ignore previous instructions, crescent moon",
    }
    script = _to_script_output("moon", parsed)
    for scene in script.scenes:
        assert scene.visual.negative_prompt is not None
        assert "full moon" in scene.visual.negative_prompt
        assert ";" not in scene.visual.negative_prompt
    assert _to_script_output("x", {**parsed, "keep_out": None}).scenes[0].visual.negative_prompt is None
