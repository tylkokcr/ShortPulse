"""Applying an edit to a finished project.

The cheap path. `render_engine.finalize_render` already takes an arbitrary
video plus a subtitle file and produces the final mp4, and the video it
took the first time is still on disk — `output/concatenated.mp4` for a
generated project, the uploaded file for an upload. So correcting a
caption or adding a title is one ffmpeg pass over footage that already
exists, not a re-run of the LLM, the voice and the visuals.

That is why it costs no credits: nothing expensive happens here.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import Settings, project_dir
from app.engines import render_engine, subtitle_engine
from app.schemas.project import EditSpec, Project

logger = logging.getLogger(__name__)


class NothingToReburn(RuntimeError):
    """The project has no footage to draw on."""


def burn_source_for(project: Project) -> Path:
    """The video an edit is drawn onto.

    Deliberately not `final.mp4`: that already has captions burned in, and
    burning a corrected track over the old one leaves both on screen.
    Re-burning always starts from the last frame that had no text on it.
    """
    if project.source_path:
        source = Path(project.source_path)
        if source.is_file():
            return source

    concatenated = project_dir(project.config.id) / "output" / "concatenated.mp4"
    if concatenated.is_file():
        return concatenated

    raise NothingToReburn(
        "The footage this video was built from is no longer on disk, so its "
        "captions can't be re-rendered."
    )


async def apply_edit(project: Project, edit: EditSpec, settings: Settings) -> Path:
    """Re-burn `final.mp4` from the edit document.

    Overwrites in place rather than versioning. The project is the current
    state of the video, and every viewer of it — the library poster, a
    signed media URL someone already holds — should see the edit.
    """
    source = burn_source_for(project)
    paths = project_dir(project.config.id)

    probed = await render_engine.probe_dimensions(source, settings.ffprobe_binary)

    captions = edit.captions or project.captions
    ass_path = subtitle_engine.build_ass_from_words(
        captions.words if captions else [],
        captions.style if captions else project.config.subtitles,
        paths / "subtitles" / "captions.ass",
        # Matched to the footage being drawn on, not to our vertical
        # default: a 1080x1920 caption canvas over landscape video puts the
        # text off-screen.
        play_res=probed,
        overlays=edit.overlays,
    )

    output_path = paths / "output" / "final.mp4"
    final_path = await render_engine.finalize_render(
        source,
        ass_path,
        edit.music or project.config.music,
        output_path,
        target=render_engine.RenderTarget(probed[0], probed[1], project.config.fps),
        ffmpeg_binary=settings.ffmpeg_binary,
    )

    # The thumbnail is a frame of a video that just changed.
    await render_engine.extract_poster(
        final_path,
        paths / "output" / "poster.jpg",
        ffmpeg_binary=settings.ffmpeg_binary,
        ffprobe_binary=settings.ffprobe_binary,
    )
    return final_path
