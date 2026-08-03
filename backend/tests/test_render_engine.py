"""Render engine tests that actually invoke ffmpeg.

These are slower than the rest of the suite and are skipped when ffmpeg
isn't available. They exist because the bug they pin was invisible to every
test that didn't decode real output: a stock clip carrying its own audio
track silently replaced the voiceover, and the resulting mismatched AAC
parameters corrupted the stream-copy concat. Both failures produced a file
that existed, had the right duration, and was simply wrong.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.engines import render_engine
from app.engines.subtitle_engine import build_ass_subtitles
from app.schemas.project import (
    MusicConfig,
    Scene,
    SceneAudio,
    SceneVisual,
    SubtitleStyle,
    Word,
)

FFMPEG = os.environ.get("FFMPEG_BINARY") or shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = os.environ.get("FFPROBE_BINARY") or shutil.which("ffprobe") or "ffprobe"


def _has_usable_ffmpeg() -> bool:
    """ffmpeg present *and* built with libass.

    The subtitle burn-in step needs the `ass` filter, and Homebrew's default
    formula ships without it (see the README). Checking only for the binary
    turns that into a confusing mid-test ffmpeg error instead of a skip.
    """
    try:
        out = subprocess.run([FFMPEG, "-version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return b"--enable-libass" in out.stdout


pytestmark = pytest.mark.skipif(
    not _has_usable_ffmpeg(),
    reason=f"{FFMPEG} is missing or built without libass; set FFMPEG_BINARY",
)


def _run(args: list[str]) -> None:
    result = subprocess.run([FFMPEG, "-y", "-v", "error", *args], capture_output=True)
    if result.returncode != 0:
        raise AssertionError(result.stderr.decode()[:2000])


def _silent_stock_clip(path: Path, seconds: float = 3.0) -> Path:
    """Stock footage that carries its own (silent) audio track — exactly
    the shape of the Pexels clip that exposed the bug."""
    _run([
        "-f", "lavfi", "-i", f"color=c=blue:s=320x240:d={seconds}:r=30",
        "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={seconds}",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", str(path),
    ])
    return path


def _audible_voiceover(path: Path, seconds: float = 3.0) -> Path:
    """A loud tone standing in for TTS output, at Piper's sample rate."""
    _run([
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=22050:duration={seconds}",
        "-ac", "1", str(path),
    ])
    return path


def _mean_volume_db(path: Path) -> float:
    """Mean volume of a file's audio. Digital silence reads as -91 dB."""
    result = subprocess.run(
        [FFMPEG, "-i", str(path), "-map", "0:a", "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
    )
    for line in result.stderr.decode().splitlines():
        if "mean_volume:" in line:
            return float(line.split("mean_volume:")[1].strip().split()[0])
    raise AssertionError(f"no mean_volume in ffmpeg output for {path}")


def _audio_params(path: Path) -> tuple[str, str]:
    result = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate,channels", "-of", "csv=p=0", str(path)],
        capture_output=True,
        check=True,
    )
    rate, channels = result.stdout.decode().strip().split(",")
    return rate, channels


def _decode_errors(path: Path) -> str:
    result = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(path), "-map", "0:a", "-f", "null", "-"],
        capture_output=True,
    )
    return result.stderr.decode()


def _atom_order(path: Path) -> list[str]:
    """Top-level MP4 atoms in file order, as ffprobe sees them."""
    result = subprocess.run(
        [FFPROBE, "-v", "trace", str(path)],
        capture_output=True,
    )
    order = []
    for line in result.stderr.decode(errors="replace").splitlines():
        if "parent:'root'" not in line:
            continue
        name = line.split("type:'")[1].split("'")[0]
        if name in ("moov", "mdat") and name not in order:
            order.append(name)
    return order


def _scene(index: int, visual: Path, audio: Path, duration: float = 3.0) -> Scene:
    return Scene(
        index=index,
        duration_s=duration,
        visual=SceneVisual(prompt="p", asset_path=str(visual)),
        audio=SceneAudio(voiceover_line="line", audio_path=str(audio), duration_ms=int(duration * 1000)),
    )


@pytest.fixture
def target():
    return render_engine.RenderTarget(width=320, height=240, fps=30)


async def test_voiceover_survives_stock_footage_that_has_its_own_audio(tmp_path, target):
    """The regression: ffmpeg's default stream selection prefers a 48kHz
    stereo camera track over 22kHz mono TTS, so the scene rendered silent
    and nobody noticed until a whole video came back with no narration."""
    stock = _silent_stock_clip(tmp_path / "stock.mp4")
    voice = _audible_voiceover(tmp_path / "voice.wav")

    clip = await render_engine.render_scene_clip(
        _scene(0, stock, voice), target, tmp_path,
        ffmpeg_binary=FFMPEG, ffprobe_binary=FFPROBE,
    )

    # The stock track is digital silence; the voiceover is a loud tone.
    # Anything near -91 dB means the wrong stream was kept.
    assert _mean_volume_db(clip) > -40, "scene rendered silent — stock audio won over the voiceover"


async def test_every_clip_gets_identical_audio_parameters(tmp_path, target):
    """Concat stream-copies, which silently corrupts the output if clips
    disagree on sample rate or channel count."""
    voice = _audible_voiceover(tmp_path / "voice.wav")
    stock = _silent_stock_clip(tmp_path / "stock.mp4")     # 48kHz stereo source
    still = tmp_path / "still.png"
    _run(["-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-frames:v", "1", str(still)])

    from_video = await render_engine.render_scene_clip(
        _scene(0, stock, voice), target, tmp_path, ffmpeg_binary=FFMPEG, ffprobe_binary=FFPROBE
    )
    from_image = await render_engine.render_scene_clip(
        _scene(1, still, voice), target, tmp_path, ffmpeg_binary=FFMPEG, ffprobe_binary=FFPROBE
    )

    assert _audio_params(from_video) == _audio_params(from_image) == ("48000", "1")


async def test_concatenating_mixed_source_clips_decodes_cleanly(tmp_path, target):
    """End of the chain: the corrupt concat is what actually broke the
    render, and it only shows up when you decode the result."""
    voice = _audible_voiceover(tmp_path / "voice.wav")
    stock = _silent_stock_clip(tmp_path / "stock.mp4")
    still = tmp_path / "still.png"
    _run(["-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-frames:v", "1", str(still)])

    clips = [
        await render_engine.render_scene_clip(
            _scene(0, stock, voice), target, tmp_path, ffmpeg_binary=FFMPEG, ffprobe_binary=FFPROBE
        ),
        await render_engine.render_scene_clip(
            _scene(1, still, voice), target, tmp_path, ffmpeg_binary=FFMPEG, ffprobe_binary=FFPROBE
        ),
    ]
    concatenated = await render_engine.concat_scene_clips(clips, tmp_path, ffmpeg_binary=FFMPEG)

    errors = _decode_errors(concatenated)
    assert errors.strip() == "", f"concatenated audio does not decode cleanly:\n{errors[:1000]}"
    # And the narration is still there afterwards.
    assert _mean_volume_db(concatenated) > -40


async def test_the_final_video_starts_playing_before_it_finishes_downloading(tmp_path, target):
    """The moov atom must come before mdat.

    It's the index a player needs to know what's in the file. At the end,
    a browser has to fetch the whole thing before it can show one frame —
    a <video> element sits at readyState 0 with no error, which looks like
    a broken player rather than a slow one. Caught exactly that way: the
    preview spun forever while the URL itself served fine over curl.
    """
    voice = _audible_voiceover(tmp_path / "voice.wav")
    still = tmp_path / "still.png"
    _run(["-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-frames:v", "1", str(still)])
    scene = _scene(0, still, voice)
    scene.audio.words = [Word(text="hello", start_ms=0, end_ms=800)]
    clip = await render_engine.render_scene_clip(
        scene, target, tmp_path, ffmpeg_binary=FFMPEG, ffprobe_binary=FFPROBE
    )
    concatenated = await render_engine.concat_scene_clips([clip], tmp_path, ffmpeg_binary=FFMPEG)
    captions = build_ass_subtitles([scene], SubtitleStyle(), tmp_path / "captions.ass")

    final = await render_engine.finalize_render(
        concatenated,
        captions,
        MusicConfig(enabled=False),
        tmp_path / "final.mp4",
        target=target,
        ffmpeg_binary=FFMPEG,
    )

    assert _atom_order(final) == ["moov", "mdat"], (
        "moov is not first — the browser must download the whole file before playback"
    )
