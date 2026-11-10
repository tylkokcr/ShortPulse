"""A story's cast voiced from the ElevenLabs account: the account's voices in
the story's language first, topped up from the Voice Library."""

from __future__ import annotations

import json

import httpx
import pytest

from app.core import config as core_config
from app.engines import audio_engine
from app.schemas.project import CastMember, TTSProvider, VoiceConfig
from app.services import elevenlabs_voices


class FakeEleven:
    def __init__(self):
        self.added: list[str] = []
        self.spoken: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["xi-api-key"] == "xi-test"
        path = request.url.path
        if path == "/v1/voices":
            return httpx.Response(200, json={"voices": [
                {"voice_id": "TrWoman0000000000001", "labels": {"gender": "female", "age": "young",
                                                                 "language": "tr"}},
                {"voice_id": "EnMan000000000000001", "labels": {"gender": "male", "language": "en"}},
            ]})
        if path == "/v1/shared-voices":
            gender = request.url.params["gender"]
            old = request.url.params.get("age") == "old"
            return httpx.Response(200, json={"voices": [
                {"public_owner_id": f"owner{i}", "voice_id": f"{gender}{'old' if old else ''}{i}",
                 "age": "old" if old else "middle_aged"}
                for i in range(4)
            ]})
        if path.startswith("/v1/voices/add/"):
            new = "Added" + str(len(self.added)).zfill(15)
            self.added.append(path)
            return httpx.Response(200, json={"voice_id": new})
        if path.startswith("/v1/text-to-speech/"):
            self.spoken.append({"voice": path.rsplit("/", 1)[1], **json.loads(request.content)})
            return httpx.Response(200, content=b"ID3 mp3")
        return httpx.Response(404)


@pytest.fixture
def eleven(monkeypatch):
    settings = core_config.get_settings()
    monkeypatch.setattr(settings, "elevenlabs_api_key", "xi-test")
    fake = FakeEleven()
    real = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(fake), **{k: v for k, v in kw.items()
                                                                   if k == "headers"}),
    )
    elevenlabs_voices._pool_cache.clear()
    return fake


async def test_the_pool_is_the_accounts_turkish_voices_topped_up_from_the_library(eleven):
    pool = await elevenlabs_voices.voice_pool("tr")
    # The account's one Turkish woman, then two more women and three men
    # from the library, one older of each; the English man is not used.
    assert pool["woman"][0] == "TrWoman0000000000001" and len(pool["woman"]) == 3
    assert len(pool["man"]) == 3 and "EnMan000000000000001" not in pool["man"]
    assert len(pool["older_woman"]) == 1 and len(pool["older_man"]) == 1
    assert len(eleven.added) == 7
    # Asked again within the hour: nothing more is added.
    await elevenlabs_voices.voice_pool("tr")
    assert len(eleven.added) == 7


async def test_every_cast_member_gets_a_different_account_voice(eleven):
    pool = await elevenlabs_voices.voice_pool("tr")
    cast = [
        CastMember(name="Elif", gender="woman", age=32, look="x"),
        CastMember(name="Mert", gender="man", age=35, look="x"),
        CastMember(name="Suna", gender="woman", age=64, look="x"),
        CastMember(name="Ada", gender="girl", age=7, look="x"),
    ]
    elevenlabs_voices.assign(cast, pool)
    ids = [m.voice_id for m in cast]
    assert all(i and i.startswith("elevenlabs:") for i in ids)
    assert ids[0] == "elevenlabs:TrWoman0000000000001"
    assert len(set(ids)) == 4


async def test_an_account_voice_is_spoken_through_the_elevenlabs_api(eleven, tmp_path):
    voice = VoiceConfig(provider=TTSProvider.ELEVENLABS, voice_id="elevenlabs:TrWoman0000000000001")
    out = tmp_path / "line.mp3"
    await audio_engine.synthesize_line("[whispers] Kapıyı açma…", voice, out, "tr")
    assert out.read_bytes() == b"ID3 mp3"
    sent = eleven.spoken[0]
    assert sent["voice"] == "TrWoman0000000000001" and sent["model_id"] == "eleven_v3"
    assert sent["language_code"] == "tr" and sent["text"].startswith("[whispers]")


async def test_the_acting_tags_survive_the_cleaning_but_asides_do_not(eleven, tmp_path):
    voice = VoiceConfig(provider=TTSProvider.ELEVENLABS, voice_id="elevenlabs:TrWoman0000000000001")
    await audio_engine.synthesize_line(
        "[whispers] [scared] Kapıyı (gülümseyerek) açma.", voice, tmp_path / "a.mp3", "tr"
    )
    assert eleven.spoken[0]["text"] == "[whispers] [scared] Kapıyı açma."
