"""Re-drawing one scene of a finished video.

Every scene is an independent sample from a model that gets it right most
of the time. At the measured per-scene failure rate a ten-scene video is
flawless about a third of the time, and the only cure on offer used to be
rendering the whole thing again — which resamples the nine scenes that
were fine and costs the full price to fix one frame. Whole-video re-rolls
do not converge; they are a fresh lottery each time. Replacing one scene
does converge: keep what worked, resample what did not.

What makes it affordable is that almost nothing has to be redone. The
script is unchanged, so the voiceover is unchanged, so the transcript and
its word timings are unchanged. Only the picture is new. So: draw one
image, re-encode that one scene's clip against its existing audio,
stream-copy the clips back together, and hand the tail to `editing`, which
already knows how to burn captions over a concatenated cut.

The one thing to be careful about is length. A clip's duration comes from
its audio (render_engine._scene_duration_s), not from its picture, so a
re-drawn scene is the same length as the one it replaces — but "should be"
is not good enough for a timeline every caption is pinned to, so the
duration is passed in explicitly and the result is checked.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path

from app.core.config import Settings, project_dir
from app.engines import render_engine, subtitle_engine, visual_engine
from app.schemas.project import EditSpec, Layout, Project, Scene, VisualMode
from app.services import art_styles, editing
from app.services.render_manager import resolution_for

logger = logging.getLogger(__name__)

# Everything else is either unavailable here (ai_video needs a GPU this
# service does not rent) or has nothing to re-roll (an outro card is drawn
# locally from the operator's own text and comes back identical).
REGENERABLE_MODES = frozenset({VisualMode.FAST_HYBRID, VisualMode.STOCK_MEDIA})

_MAX_PROMPT_CHARS = 400
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class NotRegenerable(RuntimeError):
    """This project or scene cannot have its visual re-drawn."""


# --------------------------------------------------------------------------
# Can this be done at all
# --------------------------------------------------------------------------


def _reassembly_inputs(project: Project) -> tuple[Path, list[Path]]:
    """The audio directory and the per-scene clips a re-roll needs."""
    paths = project_dir(project.config.id)
    return paths / "audio", sorted((paths / "output").glob("clip_*.mp4"))


def availability(project: Project) -> tuple[bool, str | None]:
    """Whether a scene of this project could be re-drawn, and why not.

    Answered for the whole project rather than per scene because that is
    what the UI needs to decide between showing a control and explaining
    its absence. The reason is written for the person reading it in the
    app, not for a log.
    """
    if project.status != "complete":
        return False, "This video hasn't finished rendering yet."
    if project.source_path or not project.script:
        return False, "Uploaded videos have no scenes to re-draw."
    if project.config.visual_mode not in REGENERABLE_MODES:
        return False, f"{project.config.visual_mode} scenes can't be re-drawn on this service."

    audio_dir, clips = _reassembly_inputs(project)
    scenes = project.script.scenes
    if not clips or len(clips) != len(scenes) or not audio_dir.is_dir():
        # The retention window closed, or the video predates re-rolling.
        return False, (
            "The working files for this video have been cleaned up, so its "
            "scenes can no longer be re-drawn. Rendering it again would."
        )
    return True, None


def sanitise_prompt(raw: str) -> str:
    """Trim a client-supplied prompt to something worth sending on.

    This ends up in a JSON body to Replicate and in a URL query to a stock
    search — neither a shell nor an ffmpeg filtergraph — so the point is
    hygiene and cost, not injection. A newline-laden 8KB paste is a slower
    generation and a worse picture, not a vulnerability.
    """
    cleaned = _CONTROL_CHARS.sub(" ", raw)
    cleaned = " ".join(cleaned.split())[:_MAX_PROMPT_CHARS].strip()
    if not cleaned:
        raise NotRegenerable("A visual prompt can't be empty.")
    return cleaned


# --------------------------------------------------------------------------
# Doing it
# --------------------------------------------------------------------------


def _audio_for(audio_dir: Path, scene: Scene) -> Path:
    """This scene's voiceover, found by name rather than by stored path.

    `scene.audio.audio_path` is an absolute path recorded during the
    render and goes stale the moment storage moves — a container rebuild,
    a volume remount. The layout is stable where the path is not, so the
    directory is the authority and the stored value is the fallback. Same
    defensiveness as editing.burn_source_for.
    """
    for candidate in sorted(audio_dir.glob(f"scene_{scene.index:02d}.*")):
        return candidate
    stored = Path(scene.audio.audio_path) if scene.audio.audio_path else None
    if stored and stored.is_file():
        return stored
    raise NotRegenerable(f"Scene {scene.index + 1}'s voiceover is no longer on disk.")


async def _refuse_on_geometry_drift(clip: Path, target, ffprobe_binary: str) -> None:
    """A re-encoded clip has to match the ones it will be concatenated with.

    concat -c copy does not validate: given a clip of a different size it
    emits a file that plays and then decodes as garbage (see the note on
    render_engine.concat_scene_clips). If the deployment's resolution,
    aspect ratio or fps changed since this project was rendered, the safe
    answer is to refuse rather than to hand back a broken video.
    """
    probed = await render_engine.probe_dimensions(clip, ffprobe_binary)
    if tuple(probed) != (target.width, target.height):
        raise NotRegenerable(
            "This video was rendered at a different size than the current "
            "settings produce, so a re-drawn scene wouldn't line up with the rest."
        )


async def regenerate_scene(
    project: Project,
    scene_index: int,
    settings: Settings,
    *,
    revision: int,
    prompt: str | None = None,
    negative_prompt: str | None = None,
) -> Path:
    """Re-draw one scene and rebuild the video around it.

    Mutates `project.script` in place — the new prompt, asset path and
    revision — and returns the path to the rebuilt final video. The caller
    persists; this does not, so a failure leaves the stored project
    describing the video that is still on disk.

    `revision` is supplied rather than derived because it keys the charge,
    and the counter therefore has to advance whether or not the picture
    arrives. A revision that only moved on success would make the retry
    after a refunded failure reuse the same idempotency key — and a
    replayed key is not a second charge, so the retry would be free.
    """
    ok, reason = availability(project)
    if not ok:
        raise NotRegenerable(reason or "This video can't be re-drawn.")

    assert project.script is not None  # availability() established this
    scenes = project.script.scenes
    if not 0 <= scene_index < len(scenes):
        raise NotRegenerable(f"This video has {len(scenes)} scenes.")
    scene = scenes[scene_index]
    if scene.is_outro:
        raise NotRegenerable("The closing card is drawn from your own text, not generated.")

    config = project.config
    paths = project_dir(config.id)
    audio_dir, clips = _reassembly_inputs(project)
    width, height = resolution_for(config.aspect_ratio, settings.default_resolution)
    target = render_engine.RenderTarget(width, height, config.fps)

    await _refuse_on_geometry_drift(clips[0], target, settings.ffprobe_binary)

    # Point the scene at the assets that actually exist now, so
    # render_scene_clip resolves them and the stored script stops carrying
    # a stale absolute path.
    scene.audio.audio_path = str(_audio_for(audio_dir, scene))
    if prompt is not None:
        scene.visual.prompt = sanitise_prompt(prompt)
    if negative_prompt is not None:
        # Empty is meaningful: it clears a scene-specific negative and
        # falls back to the art style's own, which is what the generator
        # does with None.
        cleaned = " ".join(_CONTROL_CHARS.sub(" ", negative_prompt).split())
        scene.visual.negative_prompt = cleaned[:_MAX_PROMPT_CHARS] or None
    scene.visual.revision = revision

    scratch = paths / "output" / f".regen_{scene_index:02d}"
    if scratch.exists():
        shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True)

    previous_duration_ms = scene.audio.duration_ms
    try:
        await visual_engine.generate_scene_visual(
            scene,
            config.visual_mode,
            paths / "visuals",
            settings,
            art_style=art_styles.by_id(config.art_style),
            size=visual_engine.sdxl_size_for(width, height),
            render_size=(width, height),
            variant=scene.visual.revision,
        )

        # Pinned to the length it already had, so the timeline cannot move.
        new_clip = await render_engine.render_scene_clip(
            scene,
            target,
            scratch,
            ffmpeg_binary=settings.ffmpeg_binary,
            ffprobe_binary=settings.ffprobe_binary,
            duration_override_s=(previous_duration_ms or 0) / 1000 or None,
        )
        # render_scene_clip re-probes and rewrites duration_ms; keep that,
        # it is the ground truth, but notice if it disagreed.
        delta_ms = (scene.audio.duration_ms or 0) - (previous_duration_ms or 0)
        if delta_ms:
            logger.warning(
                "Re-drawn scene %s of %s came back %+dms; shifting the captions after it",
                scene_index,
                config.id,
                delta_ms,
            )

        os.replace(new_clip, paths / "output" / f"clip_{scene_index:02d}.mp4")

        # Re-read the directory: the clip just replaced is in it, and the
        # sort is what puts scene 10 after scene 9 rather than after 1.
        _, refreshed = _reassembly_inputs(project)
        concatenated = await render_engine.concat_scene_clips(
            refreshed, scratch, settings.ffmpeg_binary
        )
        os.replace(concatenated, paths / "output" / "concatenated.mp4")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        # The picture is inside the clip now, and keeping it would put
        # back the directory that was 91% of what cleanup reclaims.
        shutil.rmtree(paths / "visuals", ignore_errors=True)

    # `edit.captions` is the authority once a project has been edited, and
    # it holds text the user typed. Rebuilding the track from the scenes
    # would silently replace it with the transcript.
    current = (project.edit.captions if project.edit else None) or project.captions
    if current and delta_ms:
        # Where the *next* scene started before this one changed length.
        # Not scene_start_ms(scenes, scene_index + 1): this scene's
        # duration has already been rewritten to the new value, so that
        # would compute the new boundary and leave a word sitting in the
        # gap between them unmoved.
        at_ms = subtitle_engine.scene_start_ms(scenes, scene_index) + (previous_duration_ms or 0)
        current = current.model_copy(
            update={"words": subtitle_engine.shift_words_from(current.words, at_ms, delta_ms)}
        )

    edit = EditSpec(
        layout=project.edit.layout if project.edit else Layout.FULL,
        secondary_path=project.edit.secondary_path if project.edit else None,
        captions=current,
        overlays=project.edit.overlays if project.edit else [],
        music=config.music,
    )
    final_path = await editing.apply_edit(project, edit, settings)
    project.edit = edit
    project.captions = current
    return final_path
