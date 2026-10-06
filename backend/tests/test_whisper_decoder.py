"""faster-whisper's audio decoder still works with the installed PyAV.

PyAV 19 dropped an argument faster-whisper passes to av.open, and an image
rebuild picked it up: every transcription in production failed at once.
This decodes a second of real audio through faster-whisper's own decoder,
so a resolver that drifts onto an incompatible pair fails here, in CI,
rather than on the first upload after a deploy.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

faster_whisper_audio = pytest.importorskip("faster_whisper.audio")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg to make the clip")
def test_decode_audio_runs_on_the_installed_pyav(tmp_path: Path) -> None:
    clip = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=d=1", str(clip)],
        check=True,
    )
    samples = faster_whisper_audio.decode_audio(str(clip), sampling_rate=16000)
    assert 15000 < len(samples) < 17000
