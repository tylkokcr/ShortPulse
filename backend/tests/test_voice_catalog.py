"""The voice catalog.

A voice id is a path inside `rhasspy/piper-voices`. Get one wrong and
nothing complains until render time — after the user has been charged —
when huggingface_hub raises a 404 that means nothing to them. The network
test below is the only way to catch that, so it runs whenever the repo is
reachable and skips when it isn't.
"""

from __future__ import annotations

import pytest

from app.engines.audio_engine import PIPER_VOICE_BY_LANGUAGE
from app.services import voices as catalog


def test_every_language_the_pipeline_supports_has_at_least_one_voice():
    offered = {voice.language for voice in catalog.VOICES}
    assert offered == set(PIPER_VOICE_BY_LANGUAGE)


def test_every_language_default_is_offered_in_the_picker():
    """Otherwise the pre-selected voice wouldn't appear in its own list."""
    for language, default_id in PIPER_VOICE_BY_LANGUAGE.items():
        ids = {voice.id for voice in catalog.for_language(language)}
        assert default_id in ids, f"{language} default {default_id} missing from catalog"


def test_exactly_one_default_per_language():
    for language in PIPER_VOICE_BY_LANGUAGE:
        defaults = [v for v in catalog.for_language(language) if v.is_default]
        assert len(defaults) == 1


def test_ids_are_unique():
    ids = [voice.id for voice in catalog.VOICES]
    assert len(ids) == len(set(ids))


def test_every_language_has_a_preview_line():
    for language in PIPER_VOICE_BY_LANGUAGE:
        assert catalog.PREVIEW_LINE.get(language)


def test_ids_follow_the_repo_layout():
    """`<lang>/<locale>/<speaker>/<quality>/<file>`, and the filename stem
    is what Piper names the model."""
    for voice in catalog.VOICES:
        parts = voice.id.split("/")
        assert len(parts) == 5, voice.id
        assert parts[0] == voice.language, voice.id
        assert parts[3] == voice.quality, voice.id
        assert parts[4].endswith(voice.quality), voice.id


@pytest.mark.network
def test_every_voice_exists_upstream():
    hub = pytest.importorskip("huggingface_hub")
    try:
        published = set(hub.list_repo_files("rhasspy/piper-voices"))
    except Exception as exc:  # noqa: BLE001 - offline or rate-limited
        pytest.skip(f"piper-voices repo unreachable: {exc}")

    missing = [v.id for v in catalog.VOICES if f"{v.id}.onnx" not in published]
    assert not missing, f"Voices not published upstream: {missing}"
