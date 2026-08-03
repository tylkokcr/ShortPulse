"""Report — and optionally remove — rendered files with no project behind them.

Storage grows without bound otherwise. Every render leaves its stills,
audio, subtitles and final .mp4 on disk; nothing removed them until a
project was explicitly deleted, and renders from crashed or abandoned
sessions were never cleaned at all.

Read-only by default. Deleting someone's videos is not something a script
should do because it was run without arguments:

    python scripts/prune_storage.py            # report
    python scripts/prune_storage.py --delete   # actually remove orphans
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.storage import discard_project_files  # noqa: E402
from app.services import db  # noqa: E402


def _size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delete", action="store_true", help="remove the orphans it finds")
    args = parser.parse_args()

    settings = get_settings()
    root = settings.storage_root
    if not root.exists():
        print(f"No storage directory at {root}")
        return 0

    on_disk = {d.name: d for d in root.iterdir() if d.is_dir()}
    if not on_disk:
        print("Nothing on disk.")
        return 0

    if settings.database_url:
        pool = await db.connect(settings.database_url)
        rows = await pool.fetch("select id from projects")
        known = {str(r["id"]) for r in rows}
        await db.disconnect()
    else:
        # Without a database there is no record of what a project is, so
        # there is no safe way to call anything an orphan.
        print("DATABASE_URL is not set — cannot tell which directories are orphaned.")
        return 1

    orphans = {name: path for name, path in on_disk.items() if name not in known}
    total = sum(_size(p) for p in on_disk.values())
    reclaimable = sum(_size(p) for p in orphans.values())

    print(f"{len(on_disk)} project directories, {total / 1e9:.2f} GB total")
    print(f"{len(orphans)} with no project row, {reclaimable / 1e9:.2f} GB reclaimable")

    if not orphans:
        return 0
    if not args.delete:
        print("\nRe-run with --delete to remove them.")
        return 0

    freed = sum(discard_project_files(name) for name in orphans)
    print(f"Removed {len(orphans)} directories, reclaimed {freed / 1e9:.2f} GB")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
