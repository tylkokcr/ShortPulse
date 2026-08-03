"""Where a project's generated files live, and how they're cleaned up."""

from __future__ import annotations

import logging
import shutil

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
