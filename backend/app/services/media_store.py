"""A user's own files: kept once, used by as many projects as they like.

Postgres when there is a database, memory otherwise — the same split as
`project_store`, for the same reason: a self-hosted install with no
database still works, it just forgets on restart.

Files live at `<media_root>/<id><ext>`, with a poster at `<id>.jpg` for a
video. The id is a server-made UUID and the extension comes from a short
whitelist, so the path is never anything a request chose. A project uses
a file by hard-linking it into its own directory (`link_into`): deleting
the file later leaves the project's copy, and deleting the project leaves
the file.
"""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import asyncpg

from app.core.config import media_root

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


@dataclass
class MediaFile:
    id: str
    user_id: str | None
    kind: str  # "video" | "audio"
    name: str
    ext: str
    size_bytes: int
    duration_s: float | None = None
    width: int | None = None
    height: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # "upload", "link" (fetched from a link the user gave) or "youtube".
    origin: str = "upload"
    # When the file is deleted by itself; None keeps it. Set on YouTube
    # imports (see migration 0013).
    expires_at: datetime | None = None

    @property
    def expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= datetime.now(UTC)

    @property
    def path(self) -> Path:
        return media_root() / f"{self.id}{self.ext}"

    @property
    def poster(self) -> Path:
        return media_root() / f"{self.id}.jpg"


def new_id() -> str:
    return str(uuid.uuid4())


def safe_ext(filename: str, kind: str) -> str:
    ext = Path(filename).suffix.lower()
    allowed = VIDEO_EXTS if kind == "video" else AUDIO_EXTS
    return ext if ext in allowed else (".mp4" if kind == "video" else ".mp3")


def link_into(media: MediaFile, destination: Path) -> None:
    """Put a file into a project without copying it, where the disk allows."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    try:
        os.link(media.path, destination)
    except OSError:
        shutil.copy2(media.path, destination)


def adopt(source: Path, media: MediaFile) -> None:
    """Keep a file a project already has as a media file — the reverse of
    `link_into`, used when someone uploads and asks to keep it."""
    media.path.unlink(missing_ok=True)
    try:
        os.link(source, media.path)
    except OSError:
        shutil.copy2(source, media.path)


def remove_files(media: MediaFile) -> None:
    media.path.unlink(missing_ok=True)
    media.poster.unlink(missing_ok=True)


class _Memory:
    def __init__(self) -> None:
        self.rows: dict[str, MediaFile] = {}

    async def add(self, media: MediaFile) -> None:
        self.rows[media.id] = media

    async def get(self, media_id: str) -> MediaFile | None:
        return self.rows.get(media_id)

    async def list(self, user_id: str | None) -> list[MediaFile]:
        rows = [m for m in self.rows.values() if m.user_id == user_id and not m.expired]
        return sorted(rows, key=lambda m: m.created_at, reverse=True)

    async def expired(self) -> Sequence[MediaFile]:
        return [m for m in self.rows.values() if m.expired]

    async def used_bytes(self, user_id: str | None) -> int:
        return sum(m.size_bytes for m in self.rows.values() if m.user_id == user_id)

    async def delete(self, media_id: str) -> None:
        self.rows.pop(media_id, None)


class _Postgres:
    _COLUMNS = (
        "id, user_id, kind, name, ext, size_bytes, duration_s, width, height, created_at, "
        "origin, expires_at"
    )

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @staticmethod
    def _row(row: asyncpg.Record) -> MediaFile:
        return MediaFile(
            id=str(row["id"]),
            user_id=str(row["user_id"]) if row["user_id"] else None,
            kind=row["kind"],
            name=row["name"],
            ext=row["ext"],
            size_bytes=row["size_bytes"],
            duration_s=row["duration_s"],
            width=row["width"],
            height=row["height"],
            created_at=row["created_at"],
            origin=row["origin"],
            expires_at=row["expires_at"],
        )

    async def add(self, media: MediaFile) -> None:
        await self._pool.execute(
            """
            insert into media_files (id, user_id, kind, name, ext, size_bytes,
                                     duration_s, width, height, origin, expires_at)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            media.id, media.user_id, media.kind, media.name, media.ext,
            media.size_bytes, media.duration_s, media.width, media.height,
            media.origin, media.expires_at,
        )

    async def get(self, media_id: str) -> MediaFile | None:
        try:
            uuid.UUID(media_id)
        except ValueError:
            return None
        row = await self._pool.fetchrow(
            f"select {self._COLUMNS} from media_files where id = $1", media_id
        )
        return self._row(row) if row else None

    async def list(self, user_id: str | None) -> list[MediaFile]:
        rows = await self._pool.fetch(
            f"""
            select {self._COLUMNS} from media_files
            where user_id is not distinct from $1
              and (expires_at is null or expires_at > now())
            order by created_at desc
            """,
            user_id,
        )
        return [self._row(r) for r in rows]

    async def used_bytes(self, user_id: str | None) -> int:
        value = await self._pool.fetchval(
            "select coalesce(sum(size_bytes), 0) from media_files "
            "where user_id is not distinct from $1",
            user_id,
        )
        return int(value or 0)

    async def delete(self, media_id: str) -> None:
        await self._pool.execute("delete from media_files where id = $1", media_id)

    async def expired(self) -> Sequence[MediaFile]:
        rows = await self._pool.fetch(
            f"select {self._COLUMNS} from media_files where expires_at <= now()"
        )
        return [self._row(r) for r in rows]


_store: _Memory | _Postgres = _Memory()


def configure(pool: asyncpg.Pool | None) -> None:
    global _store
    _store = _Postgres(pool) if pool is not None else _Memory()


async def add(media: MediaFile) -> None:
    await _store.add(media)


async def get_owned(media_id: str, user_id: str | None) -> MediaFile | None:
    """The file, if it exists and belongs to this user — None otherwise,
    for either reason, so a caller cannot probe someone else's ids."""
    media = await _store.get(media_id)
    if media is None or media.user_id != user_id or media.expired:
        return None
    return media


async def list_for(user_id: str | None) -> list[MediaFile]:
    return await _store.list(user_id)


async def used_bytes(user_id: str | None) -> int:
    return await _store.used_bytes(user_id)


async def delete(media: MediaFile) -> None:
    await _store.delete(media.id)
    remove_files(media)


async def prune_expired() -> int:
    """Delete every file past its `expires_at`, row and disk both. Cheap
    when there are none, so it is called on the paths that list or add
    files rather than from a timer that would need a home of its own.
    Projects already made from one keep their own linked copy."""
    gone = await _store.expired()
    for media in gone:
        await delete(media)
    return len(gone)
