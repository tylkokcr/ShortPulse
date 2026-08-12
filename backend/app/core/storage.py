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
_INTERMEDIATE_DIRS = ("visuals", "audio")
_INTERMEDIATE_OUTPUT_GLOBS = ("clip_*.mp4", "concat_list.txt")


def discard_intermediates(project_id: str) -> int:
    """Remove a finished project's working files. Returns bytes reclaimed.

    Only ever called once `final.mp4` exists. The scene assets and per-scene
    clips are inputs to a render that has already happened, and nothing
    reads them afterwards — `scene.visual.asset_path` and
    `audio.audio_path` survive in the stored script but are consulted only
    while rendering.

    That does mean a project cannot be re-rendered from scratch after this
    runs. Nothing offers to, and editing deliberately works from
    `concatenated.mp4` instead, which is why that file is kept.

    Best-effort: a render that succeeded must not be reported as failed
    because cleanup hit a permissions error.
    """
    root = get_settings().storage_root / project_id
    if not (root / "output" / "final.mp4").is_file():
        return 0

    targets: list[Path] = []
    for name in _INTERMEDIATE_DIRS:
        directory = root / name
        if directory.is_dir():
            targets.append(directory)
    for pattern in _INTERMEDIATE_OUTPUT_GLOBS:
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
