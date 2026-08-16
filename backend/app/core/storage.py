"""Where a project's generated files live, and how they're cleaned up."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def discard_project_files(project_id: str) -> int:
    """Delete everything a project generated. Returns bytes reclaimed.

    Deliberately forgiving: a project whose files are already gone is not
    an error, and a failure here must not turn a successful delete into a
    500 for the user. The row is the source of truth, so the worst case is
    orphaned bytes rather than a broken record.
    """
    root = get_settings().storage_root / project_id
    if not root.exists():
        return 0

    freed = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
    try:
        shutil.rmtree(root)
    except OSError:
        logger.exception("Could not remove storage for project %s", project_id)
        return 0

    logger.info("Reclaimed %.1f MB from project %s", freed / 1e6, project_id)
    return freed


# What a finished project still needs, and why. Everything else under its
# directory is scaffolding from the render and is never read again.
#
#   output/final.mp4         the product
#   output/poster.jpg        library thumbnail
#   output/concatenated.mp4  the pre-subtitle cut an edit is re-burned from
#   source/                  an upload's original, same role for uploads
#   subtitles/               tiny, and rewritten on every edit anyway
#
# Measured on a real install before this existed: 8.4GB across 196
# projects, of which 6.8GB — 81% — was intermediate. `visuals/` alone was
# 6.2GB of downloaded stock clips that had already been encoded into the
# scene clips that were themselves already concatenated.
#
# Two of them came back, for a while. Re-rolling one scene of a finished
# video needs that scene's voiceover and every other scene's clip — the
# visuals do not come back, because the picture is already inside the clip
# and a re-roll draws a new one. That split is why this is two tiers
# rather than a flag on the whole thing: `visuals/` was 91% of the win, so
# keeping the other 9% for a month costs little and buys the feature.
_ALWAYS_DISCARDED_DIRS = ("visuals",)
_ALWAYS_DISCARDED_OUTPUT_GLOBS = ("concat_list.txt",)

# Kept until the retention window closes, then swept by
# scripts/prune_storage.py. Without both of these a project can never be
# re-rolled — see services/regeneration.availability.
_REASSEMBLY_DIRS = ("audio",)
_REASSEMBLY_OUTPUT_GLOBS = ("clip_*.mp4",)


def discard_intermediates(project_id: str, *, keep_reassembly_inputs: bool = True) -> int:
    """Remove a finished project's working files. Returns bytes reclaimed.

    Only ever called once `final.mp4` exists. The scene assets are inputs
    to a render that has already happened — `scene.visual.asset_path`
    survives in the stored script but is consulted only while rendering.

    By default this keeps what a scene re-roll needs: the per-scene
    voiceover and every scene's finished clip. Re-rolling scene 4 draws a
    new picture for it, re-encodes that one clip against its unchanged
    audio, and concatenates it with the others — so the audio and the
    clips are the inputs, and the visuals genuinely are not.

    Call it with `keep_reassembly_inputs=False` once the retention window
    has passed. That is the sweeper's job (scripts/prune_storage.py) and
    it takes the project past the point of re-rolling for good; editing
    still works either way, because that re-burns from
    `concatenated.mp4`.

    Best-effort: a render that succeeded must not be reported as failed
    because cleanup hit a permissions error.
    """
    root = get_settings().storage_root / project_id
    if not (root / "output" / "final.mp4").is_file():
        return 0

    dirs = list(_ALWAYS_DISCARDED_DIRS)
    globs = list(_ALWAYS_DISCARDED_OUTPUT_GLOBS)
    if not keep_reassembly_inputs:
        dirs += list(_REASSEMBLY_DIRS)
        globs += list(_REASSEMBLY_OUTPUT_GLOBS)

    targets: list[Path] = []
    for name in dirs:
        directory = root / name
        if directory.is_dir():
            targets.append(directory)
    for pattern in globs:
        targets.extend((root / "output").glob(pattern))

    freed = 0
    for target in targets:
        try:
            if target.is_dir():
                freed += sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
                shutil.rmtree(target)
            else:
                freed += target.stat().st_size
                target.unlink()
        except OSError:
            logger.warning("Could not remove %s while cleaning up %s", target, project_id)

    if freed:
        logger.info("Reclaimed %.1f MB of intermediates from %s", freed / 1e6, project_id)
    return freed
