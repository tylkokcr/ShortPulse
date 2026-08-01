"""Malformed-LLM-output handling for script_engine._to_script_output.

Small local models return structurally invalid JSON often enough that every
one of these shapes has actually occurred during real renders. Each used to
crash the pipeline; the engine now drops the bad scene and keeps going, and
only gives up when nothing usable is left.
"""

import pytest

from app.engines.script_engine import ScriptGenerationError, _to_script_output


def _scene(**overrides) -> dict:
    scene = {"voiceover_line": "a line", "visual_prompt": "a prompt", "duration_s": 4}
    scene.update(overrides)
    return scene


def test_null_duration_falls_back_to_default():
    script = _to_script_output("t", {"hook": "h", "scenes": [_scene(duration_s=None)]})
    assert script.scenes[0].duration_s == 4.0


def test_duration_is_clamped_to_supported_range():
    parsed = {"hook": "h", "scenes": [_scene(duration_s=99), _scene(duration_s=0.1)]}
    script = _to_script_output("t", parsed)
    assert [s.duration_s for s in script.scenes] == [5.0, 3.0]


def test_alternate_key_names_are_accepted():
    # Models drift off the exact key names the prompt asks for.
    parsed = {"hook": "h", "scenes": [{"text": "spoken", "image_prompt": "visual"}]}
    script = _to_script_output("t", parsed)
    assert script.scenes[0].audio.voiceover_line == "spoken"
    assert script.scenes[0].visual.prompt == "visual"


def test_scene_that_is_a_bare_string_is_skipped_not_fatal():
    parsed = {"hook": "h", "scenes": ["just a sentence", _scene()]}
    script = _to_script_output("t", parsed)
    assert len(script.scenes) == 1


def test_scene_missing_required_fields_is_skipped():
    parsed = {"hook": "h", "scenes": [_scene(voiceover_line=""), _scene()]}
    script = _to_script_output("t", parsed)
    assert len(script.scenes) == 1


def test_surviving_scenes_are_reindexed_contiguously():
    # Downstream code (subtitle offsets, clip filenames) assumes 0..n-1.
    parsed = {"hook": "h", "scenes": ["bad", _scene(), "bad", _scene()]}
    script = _to_script_output("t", parsed)
    assert [s.index for s in script.scenes] == [0, 1]


def test_top_level_array_raises_retryable_error():
    with pytest.raises(ScriptGenerationError):
        _to_script_output("t", [_scene()])


def test_zero_usable_scenes_raises_retryable_error():
    with pytest.raises(ScriptGenerationError):
        _to_script_output("t", {"hook": "h", "scenes": ["bad", {"nope": 1}]})


def test_hook_falls_back_to_first_line_when_absent():
    script = _to_script_output("t", {"scenes": [_scene(voiceover_line="opening")]})
    assert script.hook == "opening"
