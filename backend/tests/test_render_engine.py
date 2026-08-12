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


async def test_a_scene_keeps_its_last_syllable_and_pauses_before_the_next(tmp_path, target):
    """The voiceover sounded like the narrator was interrupting themselves.

    Two causes, both pinned here. `audio.duration_ms` is set from the end of
    the last word Whisper transcribed, and Whisper puts that boundary at the
    final vowel — so cutting the clip there dropped 80-250ms of trailing
    consonant off every scene. And since clips are concatenated back to
    back, the next sentence then began in the very same instant.

    So: the clip must be at least as long as the voiceover file (nothing
    clipped) plus the configured gap (a breath between lines).
    """
    still = tmp_path / "still.png"
    _run(["-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-frames:v", "1", str(still)])
    voice = _audible_voiceover(tmp_path / "voice.wav", seconds=3.0)

    scene = _scene(0, still, voice)
    # What the audio engine really writes: the last word ends before the
    # audio does. Trusting this number is the bug.
    scene.audio.duration_ms = 2800
    scene.audio.words = [Word(text="hello", start_ms=0, end_ms=2800)]

    clip = await render_engine.render_scene_clip(
        scene, target, tmp_path, ffmpeg_binary=FFMPEG, ffprobe_binary=FFPROBE, scene_gap_s=0.35
    )

    clip_s = await render_engine._probe_duration_ms(clip, FFPROBE) / 1000
    assert clip_s >= 3.0, f"clip is {clip_s:.3f}s — shorter than the voiceover, so a word got cut"
    assert clip_s == pytest.approx(3.35, abs=0.05), f"expected ~3.35s with the gap, got {clip_s:.3f}s"


async def test_the_gap_is_silent_not_a_repeated_tail(tmp_path, target):
    """A pause has to be actual silence. Padding with `-t` alone would let
    ffmpeg loop or hold the audio instead, which sounds worse than no gap."""
    still = tmp_path / "still.png"
    _run(["-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-frames:v", "1", str(still)])
    voice = _audible_voiceover(tmp_path / "voice.wav", seconds=3.0)

    clip = await render_engine.render_scene_clip(
        _scene(0, still, voice), target, tmp_path,
        ffmpeg_binary=FFMPEG, ffprobe_binary=FFPROBE, scene_gap_s=1.0,
    )

    tail = tmp_path / "tail.wav"
    # Everything after the voiceover should be silence.
    _run(["-i", str(clip), "-ss", "3.05", "-map", "0:a", str(tail)])
    assert _mean_volume_db(tail) < -60, "the gap is not silent — the voiceover tail was padded out"


async def _dimensions(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(path)],
        capture_output=True, check=True).stdout.decode().strip()
    w, _, h = out.partition("x")
    return int(w), int(h)


async def test_a_split_stacks_both_clips_into_one_frame(tmp_path, target):
    """The split-screen format: narration on top, ambient footage below."""
    voice = _audible_voiceover(tmp_path / "voice.wav")
    still = tmp_path / "still.png"
    _run(["-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-frames:v", "1", str(still)])
    top = await render_engine.render_scene_clip(
        _scene(0, still, voice), target, tmp_path, ffmpeg_binary=FFMPEG, ffprobe_binary=FFPROBE
    )
    bottom = _silent_stock_clip(tmp_path / "bottom.mp4", seconds=1.0)
    captions = build_ass_subtitles([], SubtitleStyle(), tmp_path / "captions.ass")

    final = await render_engine.finalize_render(
        top, captions, MusicConfig(enabled=False), tmp_path / "split.mp4",
        target=target, ffmpeg_binary=FFMPEG, secondary_video=bottom,
    )

    assert await _dimensions(final) == (target.width, target.height)


async def test_a_short_bottom_clip_is_looped_not_frozen(tmp_path, target):
    """A 1s clip under a 3s narration must keep moving. Without the loop
    the output either ends early or holds the last frame."""
    voice = _audible_voiceover(tmp_path / "voice.wav", seconds=3.0)
    still = tmp_path / "still.png"
    _run(["-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-frames:v", "1", str(still)])
    top = await render_engine.render_scene_clip(
        _scene(0, still, voice), target, tmp_path, ffmpeg_binary=FFMPEG, ffprobe_binary=FFPROBE
    )
    bottom = _silent_stock_clip(tmp_path / "bottom.mp4", seconds=1.0)
    captions = build_ass_subtitles([], SubtitleStyle(), tmp_path / "captions.ass")

    final = await render_engine.finalize_render(
        top, captions, MusicConfig(enabled=False), tmp_path / "split.mp4",
        target=target, ffmpeg_binary=FFMPEG, secondary_video=bottom,
    )

    top_s = await render_engine._probe_duration_ms(top, FFPROBE) / 1000
    final_s = await render_engine._probe_duration_ms(final, FFPROBE) / 1000
    assert final_s == pytest.approx(top_s, abs=0.2), (
        f"split is {final_s:.2f}s but the narration is {top_s:.2f}s"
    )


async def test_the_bottom_clip_never_takes_over_the_soundtrack(tmp_path, target):
    """Same trap as scene clips: ffmpeg's default stream selection prefers
    a 48kHz stereo track over 22kHz mono TTS, which would silence the
    narration in favour of whatever the bottom clip was recorded with."""
    voice = _audible_voiceover(tmp_path / "voice.wav")
    still = tmp_path / "still.png"
    _run(["-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-frames:v", "1", str(still)])
    top = await render_engine.render_scene_clip(
        _scene(0, still, voice), target, tmp_path, ffmpeg_binary=FFMPEG, ffprobe_binary=FFPROBE
    )
    # Carries its own (silent) 48kHz stereo track, like real stock footage.
    bottom = _silent_stock_clip(tmp_path / "bottom.mp4", seconds=3.0)
    captions = build_ass_subtitles([], SubtitleStyle(), tmp_path / "captions.ass")

    final = await render_engine.finalize_render(
        top, captions, MusicConfig(enabled=False), tmp_path / "split.mp4",
        target=target, ffmpeg_binary=FFMPEG, secondary_video=bottom,
    )

    assert _mean_volume_db(final) > -40, "the narration was replaced by the bottom clip's audio"


def test_the_caption_font_ships_with_the_app():
    """Captions default to Montserrat, which is not installed on a typical
    machine — including every container. Without the bundled file libass
    substitutes silently, so the same project renders in one typeface on a
    laptop and another in production.

    The legacy family name matters as much as the file: the variable font
    Google publishes reports itself as "Montserrat Thin", so a style asking
    for "Montserrat" does not match it, and if it did every caption would
    be hairline. The bundled file is pinned to weight 700 and renamed.
    """
    import struct

    from app.core.config import FONTS_DIR

    fonts = list(FONTS_DIR.glob("*.ttf"))
    assert fonts, f"no caption font shipped in {FONTS_DIR}"

    data = fonts[0].read_bytes()
    table_count = struct.unpack(">H", data[4:6])[0]
    name_table = next(
        struct.unpack(">I", data[12 + i * 16 + 8 : 12 + i * 16 + 12])[0]
        for i in range(table_count)
        if data[12 + i * 16 : 12 + i * 16 + 4] == b"name"
    )
    count, strings = struct.unpack(">HH", data[name_table + 2 : name_table + 6])
    families = set()
    for i in range(count):
        record = name_table + 6 + i * 12
        platform, _, _, name_id, length, offset = struct.unpack(
            ">HHHHHH", data[record : record + 12]
        )
        if name_id == 1 and platform == 3:
            start = name_table + strings + offset
            families.add(data[start : start + length].decode("utf-16-be", "ignore"))

    assert "Montserrat" in families, f"font family is {families}, not what SubtitleStyle asks for"


async def test_the_burn_in_points_libass_at_the_bundled_font(tmp_path, target):
    """Pinned because the failure is invisible: drop `fontsdir` and the
    render still succeeds, just in a different typeface."""
    from app.core.config import FONTS_DIR

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

    result = subprocess.run(
        [
            FFMPEG, "-v", "info", "-i", str(concatenated),
            "-vf", f"ass='{captions}':fontsdir='{FONTS_DIR}'",
            "-frames:v", "1", "-y", str(tmp_path / "frame.png"),
        ],
        capture_output=True,
    )
    log = result.stderr.decode(errors="ignore")

    assert "Montserrat" in log, "libass never loaded the bundled font"
