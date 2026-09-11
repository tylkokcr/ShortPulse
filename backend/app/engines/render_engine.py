"""FFmpeg assembly core: turns per-scene visual + audio assets and a
generated .ass subtitle track into the final vertical .mp4.

Pipeline:
  1. Normalize each scene into its own clip at the target resolution/fps:
       - still image  -> Ken Burns pan/zoom (`zoompan`) for `duration_s`.
       - video asset  -> scale-to-fill + center-crop, looped/trimmed to
                         `duration_s`.
     Each scene clip gets its own voiceover track muxed in.
  2. Concatenate scene clips (concat demuxer — cheap, no re-encode needed
     since every clip is produced with identical codec params).
  3. In a single final pass: burn in the .ass subtitles, mix background
     music under the voice track with sidechain-compression ducking, and
     encode to H.264/AAC.

All ffmpeg invocations run via asyncio subprocesses so the FastAPI event
loop stays responsive; callers should still expect this to be CPU-bound
and slow on the render machine.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from app.core.config import FONTS_DIR
from app.engines.subtitle_engine import build_ass_subtitles
from app.schemas.project import MusicConfig, Scene, SubtitleStyle

logger = logging.getLogger(__name__)

# Every scene clip is encoded with these exact audio parameters. The
# concat step below stream-copies, which produces a corrupt AAC stream if
# clips disagree on sample rate or channel count — and they otherwise would,
# since TTS voices vary (Piper is 22.05kHz mono) and stock footage carries
# 48kHz stereo. Pinning them here is what makes the copy safe.
_CLIP_AUDIO_FORMAT = ("-ar", "48000", "-ac", "1")

# Move the moov atom (the index a player needs to know what's in the file)
# from the end to the front. Without it a browser has to download the whole
# file before it can show a single frame: a <video> element sits at
# readyState 0 with no error, looking like a broken player rather than a
# slow one. Costs one extra pass over the output at write time.
_FASTSTART = ("-movflags", "+faststart")

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class RenderError(RuntimeError):
    pass


@dataclass
class RenderTarget:
    width: int = 1080
    height: int = 1920
    fps: int = 30


# Shared default so it isn't constructed in a function signature, where it
# would be evaluated once at import and shared anyway — just less visibly.
_DEFAULT_TARGET = RenderTarget()


async def _run_ffmpeg(args: list[str], ffmpeg_binary: str = "ffmpeg") -> None:
    cmd = [ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error", *args]
    logger.debug("ffmpeg %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RenderError(f"ffmpeg failed ({' '.join(cmd)}):\n{stderr.decode(errors='ignore')}")


# Silence appended after each scene's voiceover so consecutive sentences
# don't run together. Without it every clip ended on the last syllable and
# the next one started in the same instant, which sounds like the narrator
# is interrupting themselves.
DEFAULT_SCENE_GAP_S = 0.35


async def _scene_duration_s(
    scene: Scene, ffprobe_binary: str = "ffprobe", gap_s: float = DEFAULT_SCENE_GAP_S
) -> float:
    """How long this scene's clip should run: the voiceover's real length
    plus a breath of silence.

    Measured from the audio file rather than `audio.duration_ms`, which at
    this point is the end of the *last transcribed word* — Whisper places
    that boundary at the final vowel, so trusting it cut 80-250ms off every
    scene, clipping trailing consonants and leaving no pause before the
    next line. The probe is the ground truth; the word timings stay useful
    for subtitles, which is what they were measured for.
    """
    if scene.audio.audio_path:
        try:
            return await _probe_duration_ms(Path(scene.audio.audio_path), ffprobe_binary) / 1000 + gap_s
        except RenderError:
            logger.warning(
                "Could not probe audio for scene %s; falling back to script timing",
                scene.index,
            )
    if scene.audio.duration_ms:
        return scene.audio.duration_ms / 1000 + gap_s
    return scene.duration_s


async def _probe_duration_ms(path: Path, ffprobe_binary: str) -> int:
    """Exact container duration, in ms, of a rendered clip or an audio file.

    For clips: frame-rate quantization means one asked for e.g. 4.440s
    can't land there exactly (4.44s * 30fps = 133.2, not a whole frame
    count), so this reads back what actually got encoded and downstream
    timing (subtitles) is based on ground truth rather than the request.

    `format=duration` is a container property, so the `v:0` stream filter
    below doesn't exclude audio-only inputs — the same helper measures a
    voiceover file (see `_scene_duration_s`).
    """
    cmd = [
        ffprobe_binary,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RenderError(f"ffprobe failed ({' '.join(cmd)}):\n{stderr.decode(errors='ignore')}")
    return round(float(stdout.decode().strip()) * 1000)


async def _render_image_scene_clip(
    scene: Scene, target: RenderTarget, output_path: Path, ffmpeg_binary: str, duration: float
) -> None:
    """Ken Burns effect: slow zoom + pan across the still image, cropped to
    the vertical frame. Direction alternates per scene so consecutive
    clips don't all drift the same way."""
    total_frames = max(round(duration * target.fps), 1)
    # The video track can only ever be a whole number of frames long, so
    # pin the audio to that exact same frame-quantized length (via apad +
    # a hard -t cutoff) instead of letting `-shortest` guess — relying on
    # `-shortest` left video and audio inside the same clip a few tens of
    # milliseconds apart, which snowballs into audible drift once several
    # scenes are concatenated (see render_scene_clip's duration probing).
    exact_duration = total_frames / target.fps

    zoom_start, zoom_end = (1.0, 1.15) if scene.index % 2 == 0 else (1.15, 1.0)
    # Oversize the source so zoompan always has room to pan without
    # revealing empty edges, then pan diagonally across the frame.
    pan_x = "iw/2-(iw/zoom/2)" if scene.index % 4 < 2 else "0"
    pan_y = f"'ih/2-(ih/zoom/2)+(on/{total_frames})*50'"

    zoompan = (
        f"scale=8000:-2,"
        f"zoompan=z='if(lte(on,1),{zoom_start},zoom+({zoom_end}-{zoom_start})/{total_frames})'"
        f":d={total_frames}:x={pan_x}:y={pan_y}:s={target.width}x{target.height}:fps={target.fps}"
    )
    video_filter = f"{zoompan},format=yuv420p"

    args = [
        "-loop", "1",
        "-i", str(scene.visual.asset_path),
        "-i", str(scene.audio.audio_path),
        "-t", f"{exact_duration:.6f}",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", video_filter,
        "-af", f"apad=whole_dur={exact_duration:.6f}",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        *_CLIP_AUDIO_FORMAT,
        str(output_path),
    ]
    await _run_ffmpeg(args, ffmpeg_binary)


async def _render_video_scene_clip(
    scene: Scene, target: RenderTarget, output_path: Path, ffmpeg_binary: str, duration: float
) -> None:
    """Scale-to-fill + center-crop a stock/AI video clip to the target
    aspect ratio, looping it if it's shorter than the scene's voiceover."""
    # Same reasoning as _render_image_scene_clip: pin both streams to the
    # same frame-quantized length explicitly instead of trusting
    # `-shortest`, which left video and audio a few tens of ms apart.
    total_frames = max(round(duration * target.fps), 1)
    exact_duration = total_frames / target.fps

    video_filter = (
        f"scale={target.width}:{target.height}:force_original_aspect_ratio=increase,"
        f"crop={target.width}:{target.height},fps={target.fps},format=yuv420p"
    )

    args = [
        "-stream_loop", "-1",
        "-i", str(scene.visual.asset_path),
        "-i", str(scene.audio.audio_path),
        "-t", f"{exact_duration:.6f}",
        # Stock footage often carries its own audio track. Without an
        # explicit map, ffmpeg's default stream selection prefers it over
        # the voiceover (it picks the "best" audio stream, and a 48kHz
        # stereo camera track beats 22kHz mono TTS), silently dropping the
        # narration for that scene.
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", video_filter,
        "-af", f"apad=whole_dur={exact_duration:.6f}",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        *_CLIP_AUDIO_FORMAT,
        str(output_path),
    ]
    await _run_ffmpeg(args, ffmpeg_binary)


async def render_scene_clip(
    scene: Scene,
    target: RenderTarget,
    output_dir: Path,
    ffmpeg_binary: str = "ffmpeg",
    ffprobe_binary: str = "ffprobe",
    scene_gap_s: float = DEFAULT_SCENE_GAP_S,
    duration_override_s: float | None = None,
) -> Path:
    """Encode one scene into a clip the concat step can stream-copy.

    `duration_override_s` re-encodes a scene to a length that was already
    decided, which is what makes replacing one scene of a finished video
    safe. The frame count is round(duration * fps), so pinning the
    duration makes the new clip frame-identical to the one it replaces —
    the concatenated timeline does not move and no subtitle word has to be
    re-timed. Without it the same audio would be re-probed and almost
    certainly give the same answer, but "almost" is not a property you can
    build a caption track on.
    """
    if not scene.visual.asset_path or not scene.audio.audio_path:
        raise RenderError(f"Scene {scene.index} is missing visual or audio assets")

    ext = Path(scene.visual.asset_path).suffix.lower()
    output_path = output_dir / f"clip_{scene.index:02d}.mp4"

    # Probed once here rather than inside each renderer: the two paths must
    # agree on the clip length, and this keeps it to a single ffprobe call.
    duration = (
        duration_override_s
        if duration_override_s is not None
        else await _scene_duration_s(scene, ffprobe_binary, scene_gap_s)
    )

    if ext in _IMAGE_EXTENSIONS:
        await _render_image_scene_clip(scene, target, output_path, ffmpeg_binary, duration)
    elif ext in _VIDEO_EXTENSIONS:
        await _render_video_scene_clip(scene, target, output_path, ffmpeg_binary, duration)
    else:
        raise RenderError(f"Unrecognized visual asset type: {ext}")

    # Correct the bookkept duration to what actually got encoded so
    # subtitle timing (computed from cumulative scene durations) doesn't
    # drift out of sync with the real, frame-quantized clip lengths.
    scene.audio.duration_ms = await _probe_duration_ms(output_path, ffprobe_binary)

    return output_path


async def concat_scene_clips(clip_paths: list[Path], output_dir: Path, ffmpeg_binary: str = "ffmpeg") -> Path:
    """Stream-copy concat.

    Safe only because every clip above is produced with identical codec,
    resolution, fps, pix_fmt *and* audio parameters (see
    _CLIP_AUDIO_FORMAT). Copying mismatched AAC streams doesn't error — it
    silently emits a stream whose later packets decode as garbage.
    """
    concat_list_path = output_dir / "concat_list.txt"
    concat_list_path.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in clip_paths), encoding="utf-8"
    )
    output_path = output_dir / "concatenated.mp4"
    args = ["-f", "concat", "-safe", "0", "-i", str(concat_list_path), "-c", "copy", str(output_path)]
    await _run_ffmpeg(args, ffmpeg_binary)
    return output_path


async def finalize_render(
    concatenated_video: Path,
    subtitle_ass_path: Path,
    music: MusicConfig,
    output_path: Path,
    target: RenderTarget,
    ffmpeg_binary: str = "ffmpeg",
    secondary_video: Path | None = None,
) -> Path:
    """The single composite pass: lay out the frame, burn in the text, mix
    the audio, encode.

    Everything that changes what the finished file looks like happens here,
    in one ffmpeg invocation, which is what makes an edit cheap enough to
    be free — see services/editing.py.

    With `secondary_video`, the frame becomes the split-screen format: this
    video on top, that one underneath, each scaled to fill its half and
    centre-cropped. The soundtrack stays the top one's. Silencing the
    bottom clip is not a stylistic choice — the format exists to put
    ambient footage under narration, and two voices at once is unwatchable.
    """
    # ass filter paths must have colons/backslashes escaped for the ffmpeg
    # filtergraph parser, particularly on Windows-style paths.
    def _escape(path: Path) -> str:
        return str(path).replace("\\", "/").replace(":", "\\:")

    # `fontsdir` points libass at the font shipped with the app. Without it
    # the caption typeface is whatever the host happens to have installed,
    # which on a machine with no Montserrat — including every container —
    # is a silent substitution rather than an error.
    subtitles_filter = (
        f"ass='{_escape(subtitle_ass_path)}':fontsdir='{_escape(FONTS_DIR)}'"
    )

    inputs: list[str] = []
    if secondary_video is not None:
        # Looped so a short clip underneath still covers the whole
        # narration rather than freezing on its last frame. `-shortest`
        # below is what stops the output being infinite.
        inputs += ["-stream_loop", "-1", "-i", str(secondary_video)]
    music_enabled = bool(music.enabled and music.track_path)
    if music_enabled:
        inputs += ["-i", str(music.track_path)]

    if secondary_video is not None:
        half = target.height // 2
        # setsar=1 on both: vstack refuses inputs whose sample aspect
        # ratios disagree, and stock footage frequently carries a
        # non-square one.
        video_chain = (
            f"[0:v]scale={target.width}:{half}:force_original_aspect_ratio=increase,"
            f"crop={target.width}:{half},setsar=1[top];"
            f"[1:v]scale={target.width}:{half}:force_original_aspect_ratio=increase,"
            f"crop={target.width}:{half},setsar=1[bot];"
            f"[top][bot]vstack=inputs=2[stacked];"
            f"[stacked]{subtitles_filter}[vout]"
        )
    else:
        video_chain = f"[0:v]{subtitles_filter}[vout]"

    if music_enabled:
        music_index = 2 if secondary_video is not None else 1
        audio_chain = (
            f";[{music_index}:a]volume={music.volume_db}dB,aloop=loop=-1:size=2e9[music];"
            + (
                "[music][0:a]sidechaincompress=threshold=0.05:ratio=8:attack=5:release=300[ducked];"
                if music.duck_on_voice
                else "[music]anull[ducked];"
            )
            # normalize=0 is essential: amix defaults to normalize=1, which
            # auto-attenuates every input by 1/n_inputs (here, ~halves both
            # the voice and the already-ducked music) to guard against
            # clipping — that's what made the mixed music barely audible
            # and the voice noticeably quieter than the no-music path.
            + "[0:a][ducked]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
        )
        audio_map = ["-map", "[aout]"]
    else:
        audio_chain = ""
        # Explicit, not default: with a second video input ffmpeg's stream
        # selection would be free to prefer the bottom clip's audio track
        # over the narration (see _render_video_scene_clip for the same
        # trap costing a whole scene's voiceover).
        audio_map = ["-map", "0:a?"]

    args = [
        "-i", str(concatenated_video),
        *inputs,
        "-filter_complex", video_chain + audio_chain,
        "-map", "[vout]",
        *audio_map,
        "-c:v", "libx264",
        # veryfast, matching the scene clips above rather than out-ranking
        # them. This pass burns captions over material that has already
        # been through a veryfast encode, so `medium` here was polishing
        # detail that was spent two steps earlier — it bought 0.28% SSIM
        # for 2.4x the encode time, measured at this same CRF.
        #
        # It is the single largest CPU stage in a render (ffmpeg_assembly
        # is 35.5% of wall clock across the twelve renders in the timings
        # files), and it scales with video length rather than scene count,
        # so a long video paid the most for the least.
        "-preset", "veryfast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-r", str(target.fps),
        "-c:a", "aac",
        "-b:a", "192k",
        *_FASTSTART,
    ]
    if music_enabled or secondary_video is not None:
        # Both add an input that outlasts the video on purpose (music
        # loops, the bottom clip loops), so the output needs an end.
        args.append("-shortest")
    args.append(str(output_path))

    await _run_ffmpeg(args, ffmpeg_binary)
    return output_path


async def render_project(
    scenes: list[Scene],
    subtitle_style: SubtitleStyle,
    subtitle_output_path: Path,
    music: MusicConfig,
    output_dir: Path,
    final_output_path: Path,
    target: RenderTarget = _DEFAULT_TARGET,
    ffmpeg_binary: str = "ffmpeg",
    ffprobe_binary: str = "ffprobe",
    scene_gap_s: float = DEFAULT_SCENE_GAP_S,
    on_scene_rendered=None,
    language: str = "en",
) -> Path:
    """Full assembly: render each scene clip, THEN build subtitles (using
    each clip's real, frame-quantized duration rather than the pre-render
    estimate — see render_scene_clip), then concat and finalize with
    subtitles and music. `on_scene_rendered(index, total)` is an optional
    async callback for progress reporting (see render_manager.py)."""
    clip_paths: list[Path] = []
    for scene in scenes:
        clip_path = await render_scene_clip(
            scene, target, output_dir, ffmpeg_binary, ffprobe_binary, scene_gap_s
        )
        clip_paths.append(clip_path)
        if on_scene_rendered:
            await on_scene_rendered(scene.index + 1, len(scenes))

    subtitle_ass_path = build_ass_subtitles(
        scenes,
        subtitle_style,
        subtitle_output_path,
        play_res=(target.width, target.height),
        # Casing rules differ by language — see subtitle_engine._uppercase.
        language=language,
    )

    concatenated = await concat_scene_clips(clip_paths, output_dir, ffmpeg_binary)
    return await finalize_render(
        concatenated, subtitle_ass_path, music, final_output_path, target, ffmpeg_binary
    )


async def extract_poster(
    video_path: Path,
    output_path: Path,
    at_s: float = 1.5,
    width: int = 360,
    ffmpeg_binary: str = "ffmpeg",
    ffprobe_binary: str = "ffprobe",
) -> Path | None:
    """Still frame for the library grid and the <video> poster attribute.

    Seeks a little way in rather than to frame zero: the first frame of a
    Ken Burns pan is often the least representative one, and a stock clip
    frequently opens on a fade. `at_s` is clamped so a clip shorter than
    the seek point still yields a frame instead of an empty file.

    Returns None rather than raising. A project with no thumbnail is a
    cosmetic problem; a render that reports failure because a thumbnail
    didn't encode is a real one.
    """
    try:
        duration_ms = await _probe_duration_ms(video_path, ffprobe_binary)
        seek = min(at_s, max(duration_ms / 1000 - 0.1, 0))
        await _run_ffmpeg(
            [
                "-ss", f"{seek:.3f}",
                "-i", str(video_path),
                "-frames:v", "1",
                "-vf", f"scale={width}:-2:flags=lanczos",
                "-q:v", "4",
                str(output_path),
            ],
            ffmpeg_binary,
        )
        return output_path
    except (RenderError, OSError) as exc:
        logger.warning("Could not extract a poster frame from %s: %s", video_path, exc)
        return None


async def probe_dimensions(path: Path, ffprobe_binary: str = "ffprobe") -> tuple[int, int]:
    """Pixel dimensions of a video's first video stream.

    Needed wherever something is drawn *onto* existing footage rather than
    produced at a size we chose — a subtitle canvas has to match the frame
    it is composited over, or the text lands off-screen.
    """
    cmd = [
        ffprobe_binary,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0:s=x",
        str(path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RenderError(f"ffprobe failed ({' '.join(cmd)}):\n{stderr.decode(errors='ignore')}")
    width, _, height = stdout.decode().strip().partition("x")
    return int(width), int(height)
