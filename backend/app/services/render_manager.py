"""Orchestrates the full pipeline for a single project: script -> audio ->
visuals -> subtitles -> render, pushing RenderProgress updates over the
project's WebSocket channel at every stage.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import contextmanager
from pathlib import Path

from app.core.config import Settings, project_dir
from app.engines import audio_engine, render_engine, script_engine, visual_engine
from app.schemas.project import (
    Project,
    ProjectStatus,
    RenderProgress,
    RenderStage,
    Scene,
    SceneAudio,
    SceneVisual,
    VisualMode,
)
from app.services import credits, db, project_store
from app.services.connection_manager import connection_manager

logger = logging.getLogger(__name__)


async def _emit(project_id: str, **kwargs) -> None:
    progress = RenderProgress(project_id=project_id, **kwargs)
    await connection_manager.broadcast(progress)


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
            )
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

        with timings.stage("visuals"):
            for i, scene in enumerate(script.scenes):
                await _emit(
                    project_id,
                    stage=RenderStage.VISUAL_GENERATION,
                    progress_pct=30 + (i / total_scenes) * 35,
                    message=f"Generating visuals for scene {i + 1}/{total_scenes} ({config.visual_mode})...",
                    current_scene=i + 1,
                    total_scenes=total_scenes,
                )
                if scene.is_outro:
                    outro_path = paths / "visuals" / f"scene_{scene.index:02d}_outro.png"
                    visual_engine.generate_outro_card(
                        scene.audio.voiceover_line,
                        outro_path,
                        logo_path=config.outro.logo_path,
                        background_color=config.outro.background_color,
                        accent_color=config.outro.accent_color,
                        width=settings.default_resolution[0],
                        height=settings.default_resolution[1],
                    )
                    scene.visual.asset_path = str(outro_path)
                else:
                    await visual_engine.generate_scene_visual(
                        scene, config.visual_mode, paths / "visuals", settings
                    )

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

        width, height = settings.default_resolution
        target = render_engine.RenderTarget(width=width, height=height, fps=config.fps)
        output_path = paths / "output" / "final.mp4"

        if config.music.enabled and not config.music.track_path and settings.default_music_track_path.exists():
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
                on_scene_rendered=on_scene_rendered,
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

        # Save the script again, not just the status. Every stage above
        # mutated the scenes in place — audio paths and word timings,
        # visual asset paths, and the stock-footage attribution that
        # Pexels' terms require us to display. The snapshot taken right
        # after script generation has none of it, so without this the
        # finished project reads back missing everything the render
        # actually produced.
        await project_store.update_project(
            project_id,
            status=ProjectStatus.COMPLETE,
            output_path=str(final_path),
            script=script,
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

    except Exception as exc:  # noqa: BLE001 - surface any pipeline failure to the client
        logger.exception("Render pipeline failed for project %s", project_id)
        await project_store.update_project(project_id, status=ProjectStatus.FAILED, error=str(exc))
        await _refund_failed_render(project_id, reason=str(exc))
        await _emit(
            project_id,
            stage=RenderStage.FAILED,
            progress_pct=0,
            message="Render failed.",
            error=str(exc),
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


class RenderTaskQueue:
    """Bounded async worker pool so heavy renders don't all fight for the
    same GPU/CPU at once. Projects submitted beyond `max_concurrent`
    simply wait in the asyncio.Queue until a worker frees up."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._queue: asyncio.Queue[Project] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []

    def start(self) -> None:
        for _ in range(self._settings.max_concurrent_renders):
            self._workers.append(asyncio.create_task(self._worker_loop()))

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        self._workers.clear()

    async def submit(self, project: Project) -> None:
        await self._queue.put(project)

    async def _worker_loop(self) -> None:
        while True:
            project = await self._queue.get()
            try:
                await run_pipeline(project, self._settings)
            finally:
                self._queue.task_done()
