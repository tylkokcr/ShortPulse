"""Who reads a generated video, and how, is the server's decision."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.engines.script_engine import _music_mood
from app.schemas.project import TTSProvider, VoiceConfig
from app.services import narration
from app.services import voices as voice_catalog


@pytest.fixture
def hosted(monkeypatch):
    """OpenAI only — the shape these first tests were written for."""
    settings = get_settings()
    monkeypatch.setattr(settings, "openai_tts", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "openai_tts_voice", "ash")
    monkeypatch.setattr(settings, "replicate_api_token", None)


@pytest.fixture
def both(hosted, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "replicate_api_token", "r8_test")
    monkeypatch.setattr(settings, "minimax_tts", True)
    monkeypatch.setattr(settings, "minimax_tts_voice", "English_CaptivatingStoryteller")


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setattr(get_settings(), "openai_api_key", None)
    monkeypatch.setattr(get_settings(), "replicate_api_token", None)


def test_with_a_key_an_unpicked_voice_is_openai_and_read_for_its_format(hosted):
    voice = narration.resolve(VoiceConfig(), "tr", "what_if")
    assert voice.provider == TTSProvider.OPENAI and voice.voice_id == "openai:ash"
    assert "thought experiment" in voice.instructions and "Turkish" in voice.instructions


def test_a_picked_piper_voice_is_kept_and_gets_no_instructions(hosted):
    piper = "tr/tr_TR/dfki/medium/tr_TR-dfki-medium"
    voice = narration.resolve(VoiceConfig(voice_id=piper), "tr", "free")
    assert voice.provider == TTSProvider.PIPER and voice.voice_id == piper and not voice.instructions


def test_a_request_cannot_choose_the_engine_or_the_delivery(hosted):
    asked = VoiceConfig(provider=TTSProvider.EDGE_TTS, voice_id="openai:../../x", instructions="shout")
    voice = narration.resolve(asked, "en", "free")
    assert voice.provider == TTSProvider.OPENAI and voice.voice_id == "openai:ash"
    assert voice.instructions != "shout"


def test_without_a_key_everything_stays_on_piper(local):
    voice = narration.resolve(VoiceConfig(voice_id="openai:coral"), "pl", "free")
    assert voice.provider == TTSProvider.PIPER
    assert voice.voice_id == "pl/pl_PL/darkman/medium/pl_PL-darkman-medium"
    assert not any(v.id.startswith("openai:") for v in voice_catalog.for_language("pl"))


def test_openai_voices_are_offered_in_every_language_when_hosted(hosted):
    for language in ("tr", "pl", "en"):
        ids = [v.id for v in voice_catalog.for_language(language)]
        assert ids[0].startswith("openai:") and any(not i.startswith("openai:") for i in ids)


def test_only_known_moods_choose_the_soundtrack():
    assert _music_mood(" Suspense ") == "suspense"
    assert _music_mood("../../etc") is None and _music_mood(None) is None


def test_with_both_minimax_is_the_default_and_takes_no_instructions(both):
    voice = narration.resolve(VoiceConfig(), "tr", "what_if")
    assert voice.provider == TTSProvider.MINIMAX
    assert voice.voice_id == "minimax:English_CaptivatingStoryteller"
    assert voice.instructions == ""
    # OpenAI's voices stay pickable beside it.
    picked = narration.resolve(VoiceConfig(voice_id="openai:coral"), "tr", "free")
    assert picked.provider == TTSProvider.OPENAI and picked.instructions


def test_minimax_voices_lead_the_picker(both):
    ids = [v.id for v in voice_catalog.for_language("pl")]
    assert ids[0].startswith("minimax:")
    assert any(i.startswith("openai:") for i in ids) and any("/" in i for i in ids)
