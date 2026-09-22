"""Orchestrates the full pipeline for a single project: script -> audio ->
visuals -> subtitles -> render, pushing RenderProgress updates over the
project's WebSocket channel at every stage.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from pathlib import Path

from app.core import monitoring
from app.core.config import Settings, project_dir
from app.core.storage import discard_intermediates
from app.engines import (
    audio_engine,
    render_engine,
    script_engine,
    subtitle_engine,
    visual_engine,
)
from app.schemas.project import (
    AspectRatio,
    CaptionTrack,
    Project,
    ProjectSource,
    ProjectStatus,
    RenderProgress,
    RenderStage,
    Scene,
    SceneAudio,
    SceneVisual,
    VideoLength,
    VisualMode,
)
from app.services import (
    art_styles,
    clipping,
    credits,
    db,
    dubbing,
    project_store,
    publish_manager,
    uploads,
)
from app.services.connection_manager import connection_manager

logger = logging.getLogger(__name__)


async def _emit(project_id: str, **kwargs) -> None:
    progress = RenderProgress(project_id=project_id, **kwargs)
    await connection_manager.broadcast(progress)


def resolution_for(
    aspect_ratio: str, default: tuple[int, int]
) -> tuple[int, int]:
    """Pixel dimensions for an aspect ratio.

    `aspect_ratio` was accepted by the API and stored on every project long
    before anything read it — renders were hardcoded to the vertical
    default, so asking for 1:1 silently produced a 9:16 video.

    The short edge is pinned to the vertical default's width (1080 by
    default), which lands on the sizes these platforms actually expect —
    1080x1920, 1080x1080, 1920x1080 — rather than inflating the square case
    to 1920x1920. Both dimensions are forced even: H.264 with yuv420p
    cannot encode odd ones.
    """
    short_edge = min(default)
    wide = round(short_edge * 16 / 9)
    by_ratio = {
        AspectRatio.VERTICAL_9_16: (short_edge, wide),
        AspectRatio.SQUARE_1_1: (short_edge, short_edge),
        AspectRatio.HORIZONTAL_16_9: (wide, short_edge),
    }
    try:
        width, height = by_ratio[AspectRatio(aspect_ratio)]
    except ValueError:
        logger.warning("Unknown aspect ratio %r; falling back to %r", aspect_ratio, default)
        width, height = default
    return width - (width % 2), height - (height % 2)


class StageTimings:
    """Wall-clock seconds per pipeline stage.

    Compute time is the dominant cost of running this pipeline as a hosted
    service, and it is very unevenly distributed across stages (image
    generation dwarfs everything else). Capacity planning and any per-video
    pricing needs the breakdown, not just the total, so record it per
    project and persist it next to the render output.
    """

    def __init__(self) -> None:
        self._stages: dict[str, float] = {}
        self._t0 = time.perf_counter()

    @contextmanager
    def stage(self, name: str):
        started = time.perf_counter()
        try:
            yield
        finally:
            self._stages[name] = round(time.perf_counter() - started, 2)

    def as_dict(self) -> dict:
        total = round(time.perf_counter() - self._t0, 2)
        return {
            "stages_s": dict(self._stages),
            "total_s": total,
            # Share of wall clock per stage — this is what tells you which
            # stage to optimize or price around.
            "stage_share_pct": {
                k: round(v / total * 100, 1) for k, v in self._stages.items()
            }
            if total > 0
            else {},
        }

    def write(self, path: Path, extra: dict | None = None) -> dict:
        payload = {**(extra or {}), **self.as_dict()}
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload


async def run_pipeline(project: Project, settings: Settings) -> None:
    config = project.config
    project_id = config.id
    paths = project_dir(project_id)
    # Every stage that produces pixels — outro card, scene clips, subtitle
    # canvas — has to agree on this, so it is resolved once here rather
    # than read from settings at each call site.
    render_width, render_height = resolution_for(
        config.aspect_ratio, settings.default_resolution
    )

    timings = StageTimings()

    try:
        await project_store.update_project(project_id, status=ProjectStatus.RENDERING)

        # 1. Script generation -------------------------------------------------
        await _emit(
            project_id,
            stage=RenderStage.SCRIPT_GENERATION,
            progress_pct=5,
            message="Generating scene breakdown with the LLM...",
        )
        with timings.stage("script"):
            script = await script_engine.generate_script(
                topic=config.topic,
                config=config.llm,
                raw_script=config.raw_script,
                video_length=config.video_length,
                language=config.language,
                # Stock mode turns this into a keyword search, so asking
                # for prose here would be generated and then discarded.
                visual_mode=str(config.visual_mode),
            )
        # What the whole render should keep out of frame, stamped onto
        # every scene the LLM just wrote. Per scene rather than read from
        # the config at generation time, so a scene re-rolled later starts
        # from what the project asked for and can add to it — and so the
        # stored script says what each picture was actually generated
        # against, which is the only record after the fact.
        if config.negative_prompt:
            for scene in script.scenes:
                scene.visual.negative_prompt = config.negative_prompt

        if config.outro.enabled:
            outro_text = config.outro.text or script.call_to_action or "Thanks for watching!"
            script.scenes.append(
                Scene(
                    index=len(script.scenes),
                    duration_s=3,
                    is_outro=True,
                    visual=SceneVisual(prompt="Branded outro card (drawn locally, not AI-generated)"),
                    audio=SceneAudio(voiceover_line=outro_text),
                )
            )

        # Saved early so the UI can show the scene breakdown while the slow
        # stages run. Note this snapshot is incomplete — everything below
        # mutates the scenes further, and the final save at the end of the
        # pipeline is what persists that.
        await project_store.update_project(project_id, script=script)
        total_scenes = len(script.scenes)

        # 2. Audio synthesis + transcription per scene --------------------------
        with timings.stage("audio_and_transcription"):
            for i, scene in enumerate(script.scenes):
                await _emit(
                    project_id,
                    stage=RenderStage.AUDIO_SYNTHESIS,
                    progress_pct=10 + (i / total_scenes) * 20,
                    message=f"Synthesizing voiceover for scene {i + 1}/{total_scenes}...",
                    current_scene=i + 1,
                    total_scenes=total_scenes,
                )
                await audio_engine.process_scene_audio(
                    scene,
                    config.voice,
                    paths / "audio",
                    whisper_model_size=settings.whisper_model_size,
                    whisper_device=settings.whisper_device,
                    whisper_compute_type=settings.whisper_compute_type,
                    language=config.language,
                )

        # 3. Visual generation per scene -----------------------------------------
        if config.visual_mode == VisualMode.AI_VIDEO and not visual_engine.is_model_fully_cached(
            settings.ltx_video_model_id
        ):
            await _emit(
                project_id,
                stage=RenderStage.VISUAL_GENERATION,
                progress_pct=30,
                message=(
                    "First-time AI Video model download (tens of GB) is starting — this can take "
                    "a long time on a slow connection. It's a one-time download; later renders on "
                    "this machine won't need it again."
                ),
            )

        # How many scenes may be worked on at once. The reasoning lives
        # with the generators, because it depends on which implementation
        # of a mode is going to run — see visual_engine.scene_concurrency.
        visual_concurrency = visual_engine.scene_concurrency(
            VisualMode(config.visual_mode), settings
        )
        limit = asyncio.Semaphore(visual_concurrency)
        completed = 0

        async def build_visual(scene: Scene) -> None:
            nonlocal completed
            async with limit:
                if scene.is_outro:
                    outro_path = paths / "visuals" / f"scene_{scene.index:02d}_outro.png"
                    visual_engine.generate_outro_card(
                        scene.audio.voiceover_line,
                        outro_path,
                        logo_path=config.outro.logo_path,
                        background_color=config.outro.background_color,
                        accent_color=config.outro.accent_color,
                        width=render_width,
                        height=render_height,
                    )
                    scene.visual.asset_path = str(outro_path)
                else:
                    await visual_engine.generate_scene_visual(
                        scene,
                        config.visual_mode,
                        paths / "visuals",
                        settings,
                        art_style=art_styles.by_id(config.art_style),
                        size=visual_engine.sdxl_size_for(render_width, render_height),
                        render_size=(render_width, render_height),
                    )
            # Reported on completion rather than on start: with several in
            # flight, "scene 3 of 5" as a starting announcement would jump
            # around and go backwards.
            completed += 1
            await _emit(
                project_id,
                stage=RenderStage.VISUAL_GENERATION,
                progress_pct=30 + (completed / total_scenes) * 35,
                message=f"Visuals: {completed}/{total_scenes} scenes ({config.visual_mode})...",
                current_scene=completed,
                total_scenes=total_scenes,
            )

        with timings.stage("visuals"):
            await _emit(
                project_id,
                stage=RenderStage.VISUAL_GENERATION,
                progress_pct=30,
                message=f"Generating visuals for {total_scenes} scenes ({config.visual_mode})...",
                total_scenes=total_scenes,
            )
            await asyncio.gather(*(build_visual(scene) for scene in script.scenes))

        # The buyer paid for the mode they asked for. If generation fell
        # back to stock footage anyway — a model that won't load, a GPU
        # that disappeared mid-render — they received the cheaper product
        # and should be charged the cheaper price.
        #
        # The API refuses modes this install can't run, so reaching here
        # means something broke rather than something was misconfigured.
        # Belt and braces, because the failure is invisible in the output:
        # a stock-footage video looks like a finished video.
        await _refund_mode_downgrade(project_id, config, script.scenes)

        # 4. Render scene clips, then build subtitles from each clip's real,
        # frame-quantized duration (not the pre-render estimate), then
        # concat + finalize with music. -----------------------------------
        await _emit(
            project_id,
            stage=RenderStage.SUBTITLE_GENERATION,
            progress_pct=68,
            message="Rendering scene clips and timing subtitles to them...",
        )

        async def on_scene_rendered(done: int, total: int) -> None:
            await _emit(
                project_id,
                stage=RenderStage.ASSEMBLY,
                progress_pct=70 + (done / total) * 25,
                message=f"Rendering scene clip {done}/{total}...",
                current_scene=done,
                total_scenes=total,
            )

        target = render_engine.RenderTarget(
            width=render_width, height=render_height, fps=config.fps
        )
        output_path = paths / "output" / "final.mp4"

        if (
            config.music.enabled
            and not config.music.track_path
            and settings.default_music_track_path.exists()
        ):
            config.music.track_path = str(settings.default_music_track_path)

        with timings.stage("ffmpeg_assembly"):
            final_path = await render_engine.render_project(
                script.scenes,
                config.subtitles,
                paths / "subtitles" / "captions.ass",
                config.music,
                paths / "output",
                output_path,
                target=target,
                ffmpeg_binary=settings.ffmpeg_binary,
                ffprobe_binary=settings.ffprobe_binary,
                scene_gap_s=settings.scene_gap_s,
                on_scene_rendered=on_scene_rendered,
                language=config.language,
            )

        video_s = sum(
            (s.audio.duration_ms or int(s.duration_s * 1000)) for s in script.scenes
        ) / 1000
        summary = timings.write(
            paths / "timings.json",
            extra={
                "project_id": project_id,
                "visual_mode": str(config.visual_mode),
                "video_length_preset": str(config.video_length),
                "language": config.language,
                "scene_count": total_scenes,
                "video_duration_s": round(video_s, 2),
                "image_model": settings.sdxl_model_id,
                "diffusion_device": settings.diffusion_device,
                # Which implementation of fast_hybrid ran, and what the
                # provider says it will bill for. This is the only place
                # the two costs of a render — our wall clock and someone
                # else's invoice — can be compared against one price.
                "image_backend": str(visual_engine.image_backend(settings) or "none"),
                "remote_predict_s": round(
                    sum(s.visual.predict_time_s or 0.0 for s in script.scenes), 2
                ),
            },
        )
        logger.info(
            "Render finished for %s in %.1fs (%s, %d scenes, %.1fs video): %s",
            project_id,
            summary["total_s"],
            config.visual_mode,
            total_scenes,
            video_s,
            summary["stages_s"],
        )

        # The scene assets and per-scene clips were inputs to a render
        # that has now happened. Editing works from concatenated.mp4, so
        # nothing reads them again.
        discard_intermediates(project_id)

        # Thumbnail for the library grid. Best-effort: a project without
        # one still plays.
        await render_engine.extract_poster(
            final_path,
            paths / "output" / "poster.jpg",
            ffmpeg_binary=settings.ffmpeg_binary,
            ffprobe_binary=settings.ffprobe_binary,
        )

        # Save the script again, not just the status. Every stage above
        # mutated the scenes in place — audio paths and word timings,
        # visual asset paths, and the stock-footage attribution that
        # Pexels' terms require us to display. The snapshot taken right
        # after script generation has none of it, so without this the
        # finished project reads back missing everything the render
        # actually produced.
        finished = await project_store.update_project(
            project_id,
            status=ProjectStatus.COMPLETE,
            output_path=str(final_path),
            script=script,
            # Flatten the per-scene word timings onto the finished
            # timeline. The scenes keep their own relative timings (that's
            # what they were measured against), but corrections have to be
            # made against the video the user is actually watching — and
            # reburning from this costs one ffmpeg pass instead of the
            # whole pipeline.
            captions=CaptionTrack(
                words=subtitle_engine.absolute_words(script.scenes),
                style=config.subtitles,
            ),
            # Clear any error left by a reconciler that raced this render.
            error=None,
        )
        await _emit(
            project_id,
            stage=RenderStage.DONE,
            progress_pct=100,
            message="Render complete.",
            output_path=str(final_path),
        )

        # Anything the user asked to be posted without being asked. Comes
        # after the DONE event on purpose: the render is finished and paid
        # for either way, and the page should say so before anything
        # starts talking to YouTube.
        #
        # Guarded because this is inside the pipeline's own try block — an
        # exception escaping here would be caught below as a render
        # failure and refund a video that rendered perfectly.
        try:
            await publish_manager.queue_automatic_posts(finished)
        except Exception:  # noqa: BLE001 - publishing must not fail a render
            logger.exception("Could not queue automatic posts for %s", project_id)

    except Exception as exc:  # noqa: BLE001 - surface any pipeline failure to the client
        logger.exception("Render pipeline failed for project %s", project_id)
        monitoring.report_render_failure(exc, project_id=project_id, stage="render")
        await project_store.update_project(project_id, status=ProjectStatus.FAILED, error=str(exc))
        await _refund_failed_render(project_id, reason=str(exc))
        await _emit(
            project_id,
            stage=RenderStage.FAILED,
            progress_pct=0,
            message="Render failed.",
            error=str(exc),
        )


async def run_upload_pipeline(
    project: Project,
    settings: Settings,
    submit: "Callable[[Project], Awaitable[None]] | None" = None,
) -> None:
    """Caption a video the user already has.

    Everything the generate path does before the burn-in — writing a
    script, speaking it, finding footage — has already happened offline,
    in whatever the user shot. So this runs the tail of the pipeline only:
    transcribe the speech, build the caption track, burn it in.

    It reports over the same WebSocket channel and moves through the same
    RenderStage values as `run_pipeline`, because to the client this is the
    same thing: a project that is rendering and then isn't.
    """
    config = project.config
    project_id = config.id
    paths = project_dir(project_id)
    source = Path(project.source_path or "")
    timings = StageTimings()

    try:
        await project_store.update_project(project_id, status=ProjectStatus.RENDERING)

        if not source.is_file():
            raise RuntimeError("The uploaded video is missing from storage.")

        # 1. Transcription -----------------------------------------------------
        await _emit(
            project_id,
            stage=RenderStage.TRANSCRIPTION,
            progress_pct=10,
            message="Listening to the video and timing every word...",
        )
        dubbing_to = config.dub_language
        segments: list = []
        with timings.stage("transcription"):
            # faster-whisper decodes the container itself, so the mp4 goes
            # in directly — no separate audio extraction step.
            #
            # A dub needs the sentences, not just the words: a sentence is
            # what gets translated, and its start and end are the slot the
            # replacement speech has to land in. Same model, same single
            # pass either way.
            # Sentences, not just words. A dub translates one at a time and
            # an extraction cuts on their boundaries; captions alone are
            # chunked by word count and never need them. Same model and the
            # same single pass in either branch.
            if dubbing_to or config.clip_count:
                segments = await asyncio.to_thread(
                    audio_engine.transcribe_segments,
                    source,
                    settings.whisper_model_size,
                    settings.whisper_device,
                    settings.whisper_compute_type,
                    config.language,
                )
                words = [word for segment in segments for word in segment.words]
            else:
                words = await asyncio.to_thread(
                    audio_engine.transcribe_word_timestamps,
                    source,
                    settings.whisper_model_size,
                    settings.whisper_device,
                    settings.whisper_compute_type,
                    config.language,
                )

        if not words:
            raise RuntimeError(
                "No speech was found in that video, so there is nothing to caption."
            )

        # 1a. Clips ------------------------------------------------------------
        #
        # An extraction never gets past here: it has no video of its own to
        # render. It cuts, hands each cut to this same function as an
        # ordinary upload, and finishes holding nothing but their ids.
        if config.clip_count:
            await _extract_clips(project, segments, settings, timings, submit)
            return

        # 1b. Dub -------------------------------------------------------------
        voice_track: Path | None = None
        if dubbing_to:
            await _emit(
                project_id,
                stage=RenderStage.AUDIO_SYNTHESIS,
                progress_pct=30,
                message=f"Translating {len(segments)} lines and speaking them...",
            )
            with timings.stage("dubbing"):
                translations = await dubbing.translate_segments(
                    segments, config.language, dubbing_to, config.llm
                )
                source_ms = await render_engine.probe_duration_ms(
                    source, settings.ffprobe_binary
                )
                voice_track, spoken = await dubbing.build_dub_track(
                    segments,
                    translations,
                    config.voice,
                    dubbing_to,
                    source_ms,
                    paths / "audio",
                    ffmpeg_binary=settings.ffmpeg_binary,
                    ffprobe_binary=settings.ffprobe_binary,
                )
            # Caption what is now being said, not what was said before.
            words = dubbing.words_from_segments(spoken)

        # 2. Subtitles ---------------------------------------------------------
        await _emit(
            project_id,
            stage=RenderStage.SUBTITLE_GENERATION,
            progress_pct=55,
            message=f"Building captions from {len(words)} words...",
        )
        probed = await uploads.probe(source, settings.ffprobe_binary)
        with timings.stage("subtitles"):
            ass_path = subtitle_engine.build_ass_from_words(
                words,
                config.subtitles,
                paths / "subtitles" / "captions.ass",
                # The caption canvas has to match the video it is drawn
                # over, not our vertical default — burning a 1080x1920
                # layout onto landscape footage puts the text off-screen.
                play_res=(probed.width, probed.height),
                # Casing follows the language on screen, which after a dub
                # is the language spoken into it (see subtitle_engine's
                # Turkish dotted-i handling for why this matters).
                language=dubbing_to or config.language,
            )

        # 3. Burn in -----------------------------------------------------------
        await _emit(
            project_id,
            stage=RenderStage.ASSEMBLY,
            progress_pct=70,
            message="Burning the captions into the video...",
        )
        output_path = paths / "output" / "final.mp4"
        with timings.stage("ffmpeg_assembly"):
            final_path = await render_engine.finalize_render(
                source,
                ass_path,
                config.music,
                output_path,
                target=render_engine.RenderTarget(probed.width, probed.height, config.fps),
                ffmpeg_binary=settings.ffmpeg_binary,
                voice_track=voice_track,
            )

        timings.write(
            paths / "timings.json",
            extra={
                "project_id": project_id,
                "source": "upload",
                "language": config.language,
                "word_count": len(words),
                "video_duration_s": round(probed.duration_s, 2),
            },
        )

        # The scene assets and per-scene clips were inputs to a render
        # that has now happened. Editing works from concatenated.mp4, so
        # nothing reads them again.
        discard_intermediates(project_id)

        # Thumbnail for the library grid. Best-effort: a project without
        # one still plays.
        await render_engine.extract_poster(
            final_path,
            paths / "output" / "poster.jpg",
            ffmpeg_binary=settings.ffmpeg_binary,
            ffprobe_binary=settings.ffprobe_binary,
        )

        await project_store.update_project(
            project_id,
            status=ProjectStatus.COMPLETE,
            output_path=str(final_path),
            captions=CaptionTrack(words=words, style=config.subtitles),
            error=None,
        )
        await _emit(
            project_id,
            stage=RenderStage.DONE,
            progress_pct=100,
            message="Captions ready.",
            output_path=str(final_path),
        )

    except Exception as exc:  # noqa: BLE001 - surface any failure to the client
        logger.exception("Upload pipeline failed for project %s", project_id)
        monitoring.report_render_failure(exc, project_id=project_id, stage="upload")
        await project_store.update_project(project_id, status=ProjectStatus.FAILED, error=str(exc))
        await _refund_failed_render(project_id, reason=str(exc))
        await _emit(
            project_id,
            stage=RenderStage.FAILED,
            progress_pct=0,
            message="Captioning failed.",
            error=str(exc),
        )


async def _extract_clips(
    project: Project,
    segments: list,
    settings: Settings,
    timings: "StageTimings",
    submit: "Callable[[Project], Awaitable[None]] | None" = None,
) -> None:
    """Cut the moments worth keeping out of a long upload.

    Each cut becomes an ordinary upload project and goes back on the
    render queue. That is the whole reason the feature is small: a clip is
    not a new kind of thing, it is a short video somebody uploaded, and
    everything downstream — captions, editing, publishing, the library
    card — already knows what to do with one.

    Back on the queue rather than rendered here. This runs inside a worker
    slot, and doing the children inline would hold that slot for five
    Whisper passes and five encodes — on a box configured for two
    concurrent renders, one extraction would be most of the machine for as
    long as it took. Queued, the cutting finishes in seconds, the clips
    appear immediately with their own progress, and they compete for the
    machine on the same terms as everything else.

    The parent keeps only their ids. It is the record of the extraction,
    not a video, and the project page reads `clip_project_ids` to know to
    show a list instead of a player.
    """
    config = project.config
    project_id = config.id
    source = Path(project.source_path or "")

    await _emit(
        project_id,
        stage=RenderStage.SCRIPT_GENERATION,
        progress_pct=25,
        message="Reading the transcript for the moments worth posting...",
    )

    with timings.stage("clip_selection"):
        moments = await clipping.pick_moments(segments, config.llm, config.clip_count or 3)

    if not moments:
        # Not an error. The transcript was read and nothing in it stood up
        # on its own, which is a finding about the video rather than a
        # failure of the run — and it is refunded, because the user asked
        # for clips and got none.
        await _refund_failed_render(project_id, reason="no_clips_found")
        raise RuntimeError(
            "Nothing in that video held together as a clip on its own. "
            "Your credits have been returned."
        )

    paths = project_dir(project_id)
    child_ids: list[str] = []

    for index, moment in enumerate(moments):
        await _emit(
            project_id,
            stage=RenderStage.ASSEMBLY,
            progress_pct=30 + (index / len(moments)) * 60,
            message=f"Cutting clip {index + 1} of {len(moments)}...",
        )

        cut = paths / f"clip_{index}.mp4"
        with timings.stage(f"clip_{index}_cut"):
            await render_engine.cut_clip(
                source, cut, moment.start_s, moment.end_s, settings.ffmpeg_binary
            )

        # A copy of the parent's settings with the clip's own identity: same
        # caption style, same language, same aspect ratio, and none of the
        # extraction — a child that inherited clip_count would try to cut
        # itself apart again.
        child_config = config.model_copy(
            update={
                "id": str(uuid.uuid4()),
                "clip_count": None,
                "topic": moment.title,
            }
        )
        child = await project_store.create_project(child_config, user_id=project.user_id)
        child_source = project_dir(child_config.id) / "source.mp4"
        child_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cut, child_source)
        child = await project_store.update_project(
            child_config.id, source_path=str(child_source)
        )
        child_ids.append(child_config.id)

        if submit is not None:
            await submit(child)
        else:
            # No queue to put it on: a self-hosted script or a test calling
            # the pipeline directly. Sequential rather than gathered, for
            # the reason the queue exists.
            await run_upload_pipeline(child, settings)

    await project_store.update_project(
        project_id,
        status=ProjectStatus.COMPLETE,
        clip_project_ids=child_ids,
    )
    await _emit(
        project_id,
        stage=RenderStage.DONE,
        progress_pct=100,
        # "Cut", not "ready": the clips are queued behind whatever else is
        # rendering, and each carries its own progress from here.
        message=f"{len(child_ids)} clips cut — each is rendering on its own now.",
    )


async def _refund_failed_render(project_id: str, *, reason: str) -> None:
    """Give the credits back when a render doesn't produce a video.

    Deliberately swallows its own errors: a ledger problem must not replace
    the pipeline error the user actually needs to see, and the refund is
    idempotent, so the startup reconciler will pick up anything missed here.
    """
    pool = db.optional_pool()
    if pool is None:
        return
    try:
        await credits.refund_project(pool, project_id, note=f"render failed: {reason}"[:200])
    except Exception:  # noqa: BLE001
        logger.exception(
            "Could not refund project %s after a failed render; the startup "
            "reconciler will retry",
            project_id,
        )


async def _refund_mode_downgrade(project_id: str, config, scenes) -> None:
    """Charge the cheaper price when the visuals came out cheaper.

    generate_scene_visual falls back to stock footage rather than losing a
    render, and records what actually produced each asset. What was
    delivered is then priced by how much of it fell back, and the
    difference is paid back.

    This used to correct only a wholesale downgrade, which was right when
    the generation happened locally: the pipeline either loaded or it
    didn't, so the outcome was all or nothing. Serving fast_hybrid from an
    API made per-scene failure the ordinary case instead — one rate-limited
    request, one gateway error, one prompt the safety checker rejects — and
    under the old rule a video with half its scenes downgraded was billed
    in full and said nothing about it.

    Rounding keeps the old behaviour at the bottom end without a special
    case: the gap on a short fast_hybrid render is 2 credits, so one scene
    in twelve still pays back nothing. That is the fallback doing its job
    on a video that is otherwise what was ordered.

    Swallows its own errors like the other ledger paths here: a billing
    problem must not fail a render that produced a working video.
    """
    requested = VisualMode(config.visual_mode)
    if requested == VisualMode.STOCK_MEDIA:
        return

    generated = [s for s in scenes if not s.is_outro]
    if not generated:
        return
    downgraded = [s for s in generated if s.visual.mode == VisualMode.STOCK_MEDIA]
    if not downgraded:
        return

    delivered = config.model_copy(update={"visual_mode": VisualMode.STOCK_MEDIA})
    gap = credits.cost_for(config) - credits.cost_for(delivered)
    owed = round(gap * len(downgraded) / len(generated))
    if owed <= 0:
        return

    pool = db.optional_pool()
    if pool is None:
        return
    try:
        await credits.correct_charge(
            pool,
            project_id,
            owed,
            note=(
                f"{len(downgraded)}/{len(generated)} scenes fell back from "
                f"{requested} to stock media"
            ),
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Could not correct the charge for project %s after a mode downgrade",
            project_id,
        )


async def reconcile_interrupted_renders() -> int:
    """Clean up renders that were in flight when the process died.

    A project only sits in `rendering` while a worker is driving it, and
    workers don't survive a restart — so anything found in that state at
    startup is abandoned. Left alone it would show as an eternally
    in-progress render that the user had already paid for. Refund it and
    mark it failed so they can retry.

    Returns how many were recovered.
    """
    stale = await project_store.list_interrupted()
    if not stale:
        return 0

    pool = db.optional_pool()
    recovered = 0
    for project_id in stale:
        # Claim it first. The write only lands while the project is still
        # `rendering`, so a pipeline that finished in the meantime keeps
        # its result — and we don't refund a video the user received.
        if not await project_store.fail_if_rendering(
            project_id, "Render was interrupted by a server restart. Please try again."
        ):
            logger.info("Project %s finished before it could be recovered", project_id)
            continue

        recovered += 1
        if pool is not None:
            try:
                await credits.refund_project(
                    pool, project_id, note="render interrupted by a server restart"
                )
            except Exception:  # noqa: BLE001
                logger.exception("Could not refund interrupted project %s", project_id)

    if recovered:
        logger.warning("Recovered %d render(s) interrupted by a restart", recovered)
    return recovered


# Roughly how long a render takes on the machine that serves them, per
# unit of length. Measured across twelve real renders on the 4-vCPU
# production host: stock_media came in at 22-92s, fast_hybrid at 242-362s
# with a median of 319s for a medium. Only ~43s of that waits on
# Replicate; the rest is local TTS, Whisper and ffmpeg, which is why the
# concurrency limit is a CPU limit and not an I/O one.
#
# Used only to turn a queue position into a sentence. It is an estimate
# shown as "about", never a promise, and being 20% out is fine — the
# alternative it replaces is an unlabelled spinner.
_TYPICAL_RENDER_S = {
    # Per length unit, so a medium is twice these and a long three times.
    # Fitted to the measured totals rather than guessed: fast_hybrid
    # mediums came in at 242-251s (125 x 2 = 250) and longs at 319-362s
    # (125 x 3 = 375, deliberately the pessimistic end). stock_media ran
    # 38s for five scenes and 92s for twelve.
    VisualMode.STOCK_MEDIA: 32,
    VisualMode.FAST_HYBRID: 125,
    VisualMode.AI_VIDEO: 600,
}

# Longer presets mean more scenes, and the measured totals scale with
# scene count rather than with anything else. Same shape as the price
# multiplier in credits._LENGTH_MULTIPLIER, and for the same reason.
_LENGTH_UNITS = {
    VideoLength.SHORT: 1,
    VideoLength.MEDIUM: 2,
    VideoLength.LONG: 3,
}


class RenderTaskQueue:
    """Bounded async worker pool so heavy renders don't all fight for the
    same GPU/CPU at once. Projects submitted beyond `max_concurrent`
    simply wait in the asyncio.Queue until a worker frees up.

    It also remembers the order it is holding them in. A queued render is
    indistinguishable from a stuck one from the outside — the project sits
    at `draft`, no progress event is emitted because no worker has picked
    it up, and the page shows the same waiting state whether the answer is
    "ten seconds" or "ninety minutes". At two concurrent renders and ~5.5
    minutes each, the tenth person in line waits half an hour, so this is
    the difference between a queue and an outage as far as they can tell.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._queue: asyncio.Queue[Project] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        # Ids in the order they will be started. asyncio.Queue exposes no
        # way to ask where something is, and reaching into its internal
        # deque would break the moment it changed.
        self._waiting: list[str] = []
        self._running: set[str] = set()

    def waiting_ahead_of(self, project_id: str) -> int | None:
        """How many renders will start before this one, or None.

        None means the question does not apply: the project is already
        running, has finished, or was never queued here. Zero means it is
        next, which is worth saying out loud and is not the same as None.
        """
        try:
            return self._waiting.index(project_id)
        except ValueError:
            return None

    def estimated_wait_s(self, project: Project) -> int | None:
        """A rough seconds-until-started for a queued project."""
        ahead = self.waiting_ahead_of(project.config.id)
        if ahead is None:
            return None
        per_render = _TYPICAL_RENDER_S.get(project.config.visual_mode, 180)
        length = _LENGTH_UNITS.get(project.config.video_length, 1)
        workers = max(1, self._settings.max_concurrent_renders)
        # The renders currently running have to finish first, so on
        # average half of one of them is still ahead of the queue.
        return int((ahead // workers) * per_render * length + per_render * length / 2)

    def start(self) -> None:
        for _ in range(self._settings.max_concurrent_renders):
            self._workers.append(asyncio.create_task(self._worker_loop()))

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        self._workers.clear()

    async def submit(self, project: Project) -> None:
        # Recorded before the put, so a position is available from the
        # moment the request that queued it returns. The other order leaves
        # a window where the project exists, the page is already polling,
        # and the queue says it has never heard of it.
        self._waiting.append(project.config.id)
        await self._queue.put(project)

    async def _worker_loop(self) -> None:
        while True:
            project = await self._queue.get()
            project_id = project.config.id
            # No longer waiting: it is being rendered, and a position of
            # "0 ahead" would be a different and wrong statement.
            try:
                self._waiting.remove(project_id)
            except ValueError:  # pragma: no cover - defensive
                pass
            self._running.add(project_id)
            try:
                # Uploads and generated projects share this queue on
                # purpose: both are ffmpeg- and Whisper-bound, so they
                # compete for the same machine and should respect the same
                # concurrency limit.
                if project.config.source == ProjectSource.UPLOAD:
                    # The queue passes itself in so an extraction can put
                    # its clips back on it rather than rendering them
                    # inside this worker's slot.
                    await run_upload_pipeline(project, self._settings, self.submit)
                else:
                    await run_pipeline(project, self._settings)
            finally:
                self._running.discard(project_id)
                self._queue.task_done()
