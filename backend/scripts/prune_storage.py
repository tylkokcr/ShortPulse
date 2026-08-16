"""Report — and optionally remove — rendered files nothing needs any more.

Storage grows without bound otherwise. Every render leaves its stills,
audio, subtitles and final .mp4 on disk; nothing removed them until a
project was explicitly deleted, and renders from crashed or abandoned
sessions were never cleaned at all.

Two kinds of waste, and they are not the same kind:

  * **Orphans** — directories with no project row behind them. Nothing
    will ever read these again, so removing them is pure reclamation.
  * **Expired re-roll inputs** — the per-scene voiceover and clips a
    finished project keeps so one of its scenes can be re-drawn. Those
    are useful for a while and then are not; the window is
    REGENERATION_RETENTION_DAYS. Sweeping them leaves the video, the
    poster and the editable cut untouched, and only costs the project its
    ability to be re-rolled.

Read-only by default. Deleting someone's videos is not something a script
should do because it was run without arguments:

    python scripts/prune_storage.py                    # report both
    python scripts/prune_storage.py --delete           # act on both
    python scripts/prune_storage.py --only-orphans     # ignore the window
    python scripts/prune_storage.py --only-expired     # ignore orphans
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.storage import discard_intermediates, discard_project_files  # noqa: E402
from app.services import db  # noqa: E402


def _size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _reroll_input_size(root: Path, project_id: str) -> int:
    """Bytes a project is holding purely so a scene can be re-rolled."""
    directory = root / project_id
    audio = directory / "audio"
    freed = _size(audio) if audio.is_dir() else 0
    freed += sum(f.stat().st_size for f in (directory / "output").glob("clip_*.mp4"))
    return freed


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delete", action="store_true", help="remove what it finds")
    parser.add_argument(
        "--only-orphans", action="store_true", help="skip the retention sweep"
    )
    parser.add_argument(
        "--only-expired", action="store_true", help="skip the orphan sweep"
    )
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

    if not settings.database_url:
        # Without a database there is no record of what a project is, so
        # there is no safe way to call anything an orphan — or to know how
        # old anything is.
        print("DATABASE_URL is not set — cannot tell which directories are orphaned.")
        return 1

    pool = await db.connect(settings.database_url)
    try:
        known = {str(r["id"]) for r in await pool.fetch("select id from projects")}
        expired = [
            str(r["id"])
            for r in await pool.fetch(
                """
                select id from projects
                where status = 'complete'
                  and updated_at < now() - ($1 || ' days')::interval
                """,
                str(settings.regeneration_retention_days),
            )
        ]
    finally:
        await db.disconnect()

    total = sum(_size(p) for p in on_disk.values())
    print(f"{len(on_disk)} project directories, {total / 1e9:.2f} GB total")

    orphans: dict[str, Path] = {}
    if not args.only_expired:
        orphans = {name: path for name, path in on_disk.items() if name not in known}
        reclaimable = sum(_size(p) for p in orphans.values())
        print(f"{len(orphans)} with no project row, {reclaimable / 1e9:.2f} GB reclaimable")

    # An orphan is about to lose its whole directory, so don't count its
    # re-roll inputs twice.
    stale: list[str] = []
    if not args.only_orphans:
        stale = [p for p in expired if p in on_disk and p not in orphans]
        stale_bytes = sum(_reroll_input_size(root, p) for p in stale)
        print(
            f"{len(stale)} past the {settings.regeneration_retention_days}-day re-roll "
            f"window, {stale_bytes / 1e9:.2f} GB reclaimable"
        )

    if not orphans and not stale:
        return 0
    if not args.delete:
        print("\nRe-run with --delete to remove them.")
        return 0

    if orphans:
        freed = sum(discard_project_files(name) for name in orphans)
        print(f"Removed {len(orphans)} directories, reclaimed {freed / 1e9:.2f} GB")
    if stale:
        freed = sum(
            discard_intermediates(p, keep_reassembly_inputs=False) for p in stale
        )
        print(f"Expired re-roll inputs on {len(stale)} projects, reclaimed {freed / 1e9:.2f} GB")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
