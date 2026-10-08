"""Transcription by the Whisper API: what it returns put back into
sentences, long audio in pieces on one clock, and the local model taking
over whenever the API cannot."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.engines import audio_engine
from tests.test_uploads import FFMPEG


def test_words_are_put_back_into_their_sentences_on_the_file_clock():
    data = {
        "segments": [
            {"start": 0.0, "end": 2.0, "text": " Merhaba dünya."},
            {"start": 2.5, "end": 4.0, "text": " Nasılsın?"},
        ],
        "words": [
            {"word": "Merhaba", "start": 0.1, "end": 0.8},
            {"word": "dünya.", "start": 0.9, "end": 1.8},
            {"word": "Nasılsın?", "start": 2.6, "end": 3.5},
        ],
    }
    segments = audio_engine._segments_from_verbose(data, offset_s=1200.0)
    assert [s.text for s in segments] == ["Merhaba dünya.", "Nasılsın?"]
    assert [w.text for w in segments[0].words] == ["Merhaba", "dünya."]
    assert segments[1].words[0].start_ms == 1_202_600


@pytest.mark.skipif(shutil.which(FFMPEG) is None and not Path(FFMPEG).exists(), reason="needs ffmpeg")
def test_long_audio_goes_in_pieces_and_comes_back_on_one_clock(monkeypatch, tmp_path):
    audio = tmp_path / "talk.wav"
    subprocess.run(
        [
            FFMPEG,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=300:duration=12",
            str(audio),
        ],
        check=True,
    )
    monkeypatch.setattr(audio_engine, "_CHUNK_S", 5)
    sent: list[dict] = []

    class FakeResponse:
        def __init__(self, n):
            self.n = n

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "language": "turkish",
                "duration": 5.0,
                "segments": [{"start": 1.0, "end": 2.0, "text": f"part {self.n}"}],
                "words": [{"word": f"p{self.n}", "start": 1.0, "end": 1.5}],
            }

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, headers=None, data=None, files=None):
            sent.append({"url": url, "auth": headers["Authorization"], "data": data})
            return FakeResponse(len(sent) - 1)

    import httpx

    monkeypatch.setattr(httpx, "Client", FakeClient)
    heard: list[str] = []
    progress: list[float] = []
    segments = audio_engine.transcribe_segments_openai(
        audio, "sk-test", FFMPEG, None, heard.append, progress.append
    )
    assert len(sent) == 3  # 12 seconds in 5-second pieces
    assert sent[0]["auth"] == "Bearer sk-test"
    assert sent[0]["data"]["timestamp_granularities[]"] == ["segment", "word"]
    assert [s.start_ms for s in segments] == [1000, 6000, 11000]
    assert heard == ["tr"]
    assert progress[-1] == 1.0


async def test_the_api_failing_falls_back_to_this_machine(monkeypatch, tmp_path):
    from app.core.config import get_settings
    from app.services import render_manager

    settings = get_settings()
    monkeypatch.setattr(settings, "transcription_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")

    async def duration(path, ffprobe="ffprobe"):
        return 3_600_000

    def broken(*args, **kwargs):
        raise RuntimeError("503 from the API")

    used: list[str] = []

    def local(*args, **kwargs):
        used.append("local")
        return []

    async def no_emit(*args, **kwargs):
        return None

    monkeypatch.setattr(render_manager.render_engine, "probe_duration_ms", duration)
    monkeypatch.setattr(audio_engine, "transcribe_segments_openai", broken)
    monkeypatch.setattr(audio_engine, "transcribe_segments", local)
    monkeypatch.setattr(render_manager, "_emit", no_emit)
    await render_manager._transcribe(tmp_path / "a.wav", settings, "small", None, [], "p")
    assert used == ["local"]


@pytest.mark.parametrize(
    ("provider", "key", "seconds", "hosted"),
    [
        ("auto", "sk-x", 2760, True),  # the 46-minute podcast
        ("auto", "sk-x", 60, False),  # a short caption job stays here
        ("auto", None, 2760, False),  # no key, no API
        ("local", "sk-x", 2760, False),
        ("openai", "sk-x", 60, True),
    ],
)
def test_which_transcriptions_go_to_the_api(monkeypatch, provider, key, seconds, hosted):
    from app.core.config import get_settings
    from app.services import render_manager

    settings = get_settings()
    monkeypatch.setattr(settings, "transcription_provider", provider)
    monkeypatch.setattr(settings, "openai_api_key", key)
    assert render_manager._hosted_transcription(settings, seconds) is hosted


def test_words_take_the_sentences_punctuation():
    data = {
        "segments": [{"start": 0.0, "end": 3.0, "text": " Hoş geldin, hocam. Nasılsın?"}],
        "words": [
            {"word": "Hoş", "start": 0.0, "end": 0.3},
            {"word": "geldin", "start": 0.3, "end": 0.7},
            {"word": "hocam", "start": 0.8, "end": 1.2},
            {"word": "Nasılsın", "start": 1.5, "end": 2.0},
        ],
    }
    [segment] = audio_engine._segments_from_verbose(data, 0.0)
    assert [w.text for w in segment.words] == ["Hoş", "geldin,", "hocam.", "Nasılsın?"]
