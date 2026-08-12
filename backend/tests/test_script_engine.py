"""Malformed-LLM-output handling for script_engine._to_script_output.

Small local models return structurally invalid JSON often enough that every
one of these shapes has actually occurred during real renders. Each used to
crash the pipeline; the engine now drops the bad scene and keeps going, and
only gives up when nothing usable is left.
"""

import pytest

from app.engines.script_engine import (
    ScriptGenerationError,
    _named_entities,
    _to_script_output,
    visual_prompts_naming,
)


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


# --------------------------------------------------------------------------
# Named entities in visual prompts
#
# What prompted these: a topic about a League of Legends champion produced
# "a close-up shot of Ashe's face", and the image model — which has never
# heard of Ashe — returned an unrelated generic face. The prompt rules ask
# the model to describe things literally and mostly work, but a local model
# obeys for a few scenes and then drifts, so the check can't rely on it.
# --------------------------------------------------------------------------



def test_a_topic_question_word_is_not_treated_as_a_name():
    """Topics are usually questions, so the first word is capitalised
    without naming anything."""
    assert _named_entities("Why honey never spoils") == set()


def test_names_in_a_topic_are_found():
    assert _named_entities("Why Ashe is strong in League of Legends") == {
        "Ashe",
        "League",
        "Legends",
    }


def test_a_brand_that_starts_lowercase_is_still_a_name():
    """Requiring an initial capital let "iPhone" through — plenty of brands
    are deliberately written that way."""
    assert _named_entities("The story behind the iPhone") == {"iPhone"}
    assert _named_entities("A look at eBay and xAI") == {"eBay", "xAI"}


def test_scenes_naming_the_topic_entity_are_flagged():
    scenes = [
        {"visual_prompt": "an archer in blue armour drawing a glowing bow"},
        {"visual_prompt": "Ashe standing on a battlefield"},
        {"visual_prompt": "a snowy mountain pass at dusk"},
    ]
    assert visual_prompts_naming(scenes, "Why Ashe is strong") == [1]


def test_a_topic_with_no_names_flags_nothing():
    """Without this the check would rewrite prompts on every ordinary
    topic, costing an LLM call per render for no reason."""
    scenes = [{"visual_prompt": "Honey dripping from a wooden spoon"}]
    assert visual_prompts_naming(scenes, "Why honey never spoils") == []


def test_a_missing_visual_prompt_does_not_crash_the_check():
    assert visual_prompts_naming([{}, {"visual_prompt": None}], "Why Ashe wins") == []
