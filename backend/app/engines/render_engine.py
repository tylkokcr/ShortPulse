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

from app.engines.subtitle_engine import build_ass_subtitles
from app.schemas.project import MusicConfig, Scene, SubtitleStyle

logger = logging.getLogger(__name__)

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class RenderError(RuntimeError):
    pass


@dataclass
class RenderTarget:
    width: int = 1080
    height: int = 1920
    fps: int = 30


async def _run_ffmpeg(args: list[str], ffmpeg_binary: str = "ffmpeg") -> None:
    cmd = [ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error", *args]
    logger.debug("ffmpeg %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RenderError(f"ffmpeg failed ({' '.join(cmd)}):\n{stderr.decode(errors='ignore')}")


def _scene_duration_s(scene: Scene) -> float:
    if scene.audio.duration_ms:
        return scene.audio.duration_ms / 1000
    return scene.duration_s


async def _probe_duration_ms(path: Path, ffprobe_binary: str) -> int:
    """Exact rendered duration, in ms, of a clip's video stream. Frame-rate
    quantization means a clip asked for e.g. 4.440s can't land on that
    exactly (4.44s * 30fps = 133.2, not a whole frame count) — this reads
    back what actually got encoded so downstream timing (subtitles) can be
    based on ground truth instead of the pre-render request.
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
    scene: Scene, target: RenderTarget, output_path: Path, ffmpeg_binary: str
) -> None:
    """Ken Burns effect: slow zoom + pan across the still image, cropped to
    the vertical frame. Direction alternates per scene so consecutive
    clips don't all drift the same way."""
    duration = _scene_duration_s(scene)
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
    pan_y = "'ih/2-(ih/zoom/2)+(on/{tf})*50'".format(tf=total_frames)

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
        "-vf", video_filter,
        "-af", f"apad=whole_dur={exact_duration:.6f}",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path),
    ]
    await _run_ffmpeg(args, ffmpeg_binary)


async def _render_video_scene_clip(
    scene: Scene, target: RenderTarget, output_path: Path, ffmpeg_binary: str
) -> None:
    """Scale-to-fill + center-crop a stock/AI video clip to the target
    aspect ratio, looping it if it's shorter than the scene's voiceover."""
    duration = _scene_duration_s(scene)
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
        "-vf", video_filter,
        "-af", f"apad=whole_dur={exact_duration:.6f}",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path),
    ]
    await _run_ffmpeg(args, ffmpeg_binary)


async def render_scene_clip(
    scene: Scene,
    target: RenderTarget,
    output_dir: Path,
    ffmpeg_binary: str = "ffmpeg",
    ffprobe_binary: str = "ffprobe",
) -> Path:
    if not scene.visual.asset_path or not scene.audio.audio_path:
        raise RenderError(f"Scene {scene.index} is missing visual or audio assets")

    ext = Path(scene.visual.asset_path).suffix.lower()
    output_path = output_dir / f"clip_{scene.index:02d}.mp4"

    if ext in _IMAGE_EXTENSIONS:
        await _render_image_scene_clip(scene, target, output_path, ffmpeg_binary)
    elif ext in _VIDEO_EXTENSIONS:
        await _render_video_scene_clip(scene, target, output_path, ffmpeg_binary)
    else:
        raise RenderError(f"Unrecognized visual asset type: {ext}")

    # Correct the bookkept duration to what actually got encoded so
    # subtitle timing (computed from cumulative scene durations) doesn't
    # drift out of sync with the real, frame-quantized clip lengths.
    scene.audio.duration_ms = await _probe_duration_ms(output_path, ffprobe_binary)

    return output_path


async def concat_scene_clips(clip_paths: list[Path], output_dir: Path, ffmpeg_binary: str = "ffmpeg") -> Path:
    """Stream-copy concat. Safe because every clip was produced with
    identical codec/resolution/fps/pix_fmt above."""
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
) -> Path:
    """Burn in subtitles and, if enabled, mix background music under the
    voiceover with sidechain-compression ducking (music volume drops
    automatically whenever the voice track is speaking).
    """
    # ass filter paths must have colons/backslashes escaped for the ffmpeg
    # filtergraph parser, particularly on Windows-style paths.
    escaped_ass_path = str(subtitle_ass_path).replace("\\", "/").replace(":", "\\:")
    subtitles_filter = f"ass='{escaped_ass_path}'"

    if music.enabled and music.track_path:
        filter_complex = (
            f"[0:v]{subtitles_filter}[vout];"
            f"[1:a]volume={music.volume_db}dB,aloop=loop=-1:size=2e9[music];"
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
        args = [
            "-i", str(concatenated_video),
            "-i", str(music.track_path),
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-r", str(target.fps),
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(output_path),
        ]
    else:
        args = [
            "-i", str(concatenated_video),
            "-vf", subtitles_filter,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-r", str(target.fps),
            "-c:a", "aac",
            "-b:a", "192k",
            str(output_path),
        ]

    await _run_ffmpeg(args, ffmpeg_binary)
    return output_path


async def render_project(
    scenes: list[Scene],
    subtitle_style: SubtitleStyle,
    subtitle_output_path: Path,
    music: MusicConfig,
    output_dir: Path,
    final_output_path: Path,
    target: RenderTarget = RenderTarget(),
    ffmpeg_binary: str = "ffmpeg",
    ffprobe_binary: str = "ffprobe",
    on_scene_rendered=None,
) -> Path:
    """Full assembly: render each scene clip, THEN build subtitles (using
    each clip's real, frame-quantized duration rather than the pre-render
    estimate — see render_scene_clip), then concat and finalize with
    subtitles and music. `on_scene_rendered(index, total)` is an optional
    async callback for progress reporting (see render_manager.py)."""
    clip_paths: list[Path] = []
    for scene in scenes:
        clip_path = await render_scene_clip(scene, target, output_dir, ffmpeg_binary, ffprobe_binary)
        clip_paths.append(clip_path)
        if on_scene_rendered:
            await on_scene_rendered(scene.index + 1, len(scenes))

    subtitle_ass_path = build_ass_subtitles(
        scenes, subtitle_style, subtitle_output_path, play_res=(target.width, target.height)
    )

    concatenated = await concat_scene_clips(clip_paths, output_dir, ffmpeg_binary)
    return await finalize_render(
        concatenated, subtitle_ass_path, music, final_output_path, target, ffmpeg_binary
    )
