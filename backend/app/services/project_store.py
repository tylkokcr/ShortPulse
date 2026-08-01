"""Project persistence, with two interchangeable backends.

Postgres when a database is configured (the hosted product needs projects
and credits to survive a restart), and an in-memory dict otherwise, so the
self-hosted path still runs with zero infrastructure. Both implement the
same async interface, chosen once at startup by `configure()`.

The API is async because the Postgres backend is; the in-memory one just
doesn't await anything.
"""

from __future__ import annotations

import json
import logging
from typing import Protocol

import asyncpg

from app.schemas.project import Project, ProjectConfig, ProjectStatus

logger = logging.getLogger(__name__)


class ProjectStore(Protocol):
    async def create_project(self, config: ProjectConfig, user_id: str | None = ...) -> Project: ...
    async def get_project(self, project_id: str) -> Project | None: ...
    async def list_projects(self, user_id: str | None = ...) -> list[Project]: ...
    async def update_project(self, project_id: str, **updates) -> Project: ...
    async def delete_project(self, project_id: str) -> None: ...
    async def list_interrupted(self) -> list[str]: ...
    async def owner_of(self, project_id: str) -> str | None: ...


class InMemoryProjectStore:
    """Single-process store. Everything is lost on restart, including the
    record of any render that was in flight."""

    def __init__(self) -> None:
        self._projects: dict[str, Project] = {}

    async def create_project(self, config: ProjectConfig, user_id: str | None = None) -> Project:
        project = Project(config=config, status=ProjectStatus.DRAFT)
        self._projects[config.id] = project
        return project

    async def get_project(self, project_id: str) -> Project | None:
        return self._projects.get(project_id)

    async def list_projects(self, user_id: str | None = None) -> list[Project]:
        return list(self._projects.values())

    async def update_project(self, project_id: str, **updates) -> Project:
        project = self._projects[project_id]
        updated = project.model_copy(update=updates)
        self._projects[project_id] = updated
        return updated

    async def delete_project(self, project_id: str) -> None:
        self._projects.pop(project_id, None)

    async def list_interrupted(self) -> list[str]:
        # Nothing survives a restart here, so there is never anything left
        # over to recover.
        return []

    async def owner_of(self, project_id: str) -> str | None:
        # This backend only runs where there are no accounts.
        return None


class PostgresProjectStore:
    """Durable store. Survives restarts, and lets a reconciler find renders
    that were interrupted mid-flight (see the projects_rendering_idx)."""

    # Columns that live in their own SQL column rather than inside `config`.
    _COLUMNS = {"status", "script", "output_path", "error", "credits_cost"}

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @staticmethod
    def _row_to_project(row: asyncpg.Record) -> Project:
        return Project(
            config=ProjectConfig.model_validate_json(row["config"]),
            status=ProjectStatus(row["status"]),
            script=json.loads(row["script"]) if row["script"] else None,
            output_path=row["output_path"],
            error=row["error"],
            credits_cost=row["credits_cost"],
        )

    async def create_project(self, config: ProjectConfig, user_id: str | None = None) -> Project:
        await self._pool.execute(
            """
            insert into projects (id, user_id, status, config)
            values ($1, $2, 'draft', $3::jsonb)
            """,
            config.id,
            user_id,
            config.model_dump_json(),
        )
        return Project(config=config, status=ProjectStatus.DRAFT)

    async def get_project(self, project_id: str) -> Project | None:
        row = await self._pool.fetchrow(
            """
            select config, status, script, output_path, error, credits_cost
            from projects where id = $1
            """,
            project_id,
        )
        return self._row_to_project(row) if row else None

    async def list_projects(self, user_id: str | None = None) -> list[Project]:
        if user_id is None:
            rows = await self._pool.fetch(
                """
                select config, status, script, output_path, error, credits_cost
                from projects order by created_at desc limit 100
                """
            )
        else:
            rows = await self._pool.fetch(
                """
                select config, status, script, output_path, error, credits_cost
                from projects where user_id = $1 order by created_at desc limit 100
                """,
                user_id,
            )
        return [self._row_to_project(r) for r in rows]

    async def update_project(self, project_id: str, **updates) -> Project:
        unknown = set(updates) - self._COLUMNS
        if unknown:
            raise ValueError(f"Cannot persist unknown project fields: {sorted(unknown)}")

        sets, values = [], []
        for i, (key, value) in enumerate(updates.items(), start=2):
            sets.append(f"{key} = ${i}")
            if key == "script" and value is not None:
                # Pydantic model -> JSONB
                value = value.model_dump_json() if hasattr(value, "model_dump_json") else json.dumps(value)
                sets[-1] = f"{key} = ${i}::jsonb"
            elif key == "status":
                value = value.value if hasattr(value, "value") else str(value)
            values.append(value)

        row = await self._pool.fetchrow(
            f"""
            update projects set {', '.join(sets)}, updated_at = now()
            where id = $1
            returning config, status, script, output_path, error, credits_cost
            """,
            project_id,
            *values,
        )
        if row is None:
            raise KeyError(f"No such project: {project_id}")
        return self._row_to_project(row)

    async def delete_project(self, project_id: str) -> None:
        await self._pool.execute("delete from projects where id = $1", project_id)

    async def list_interrupted(self) -> list[str]:
        """Projects still marked `rendering`.

        Nothing but a crashed or restarted process can leave a project in
        that state: the pipeline always moves it to complete or failed.
        Called once at startup so those renders get refunded instead of
        being silently kept, and reported as failed instead of spinning
        forever in the UI.
        """
        rows = await self._pool.fetch(
            "select id from projects where status = 'rendering'"
        )
        return [str(r["id"]) for r in rows]

    async def owner_of(self, project_id: str) -> str | None:
        owner = await self._pool.fetchval(
            "select user_id from projects where id = $1", project_id
        )
        return str(owner) if owner else None


# --------------------------------------------------------------------------
# Module-level facade, so callers don't care which backend is active.
# --------------------------------------------------------------------------

_store: ProjectStore = InMemoryProjectStore()


def configure(pool: asyncpg.Pool | None) -> None:
    """Select the backend. Called once during application startup."""
    global _store
    if pool is None:
        _store = InMemoryProjectStore()
        logger.warning(
            "No database configured — projects are in memory and will be lost on restart"
        )
    else:
        _store = PostgresProjectStore(pool)
        logger.info("Projects persisted to Postgres")


def active_backend() -> str:
    return type(_store).__name__


async def create_project(config: ProjectConfig, user_id: str | None = None) -> Project:
    return await _store.create_project(config, user_id)


async def get_project(project_id: str) -> Project | None:
    return await _store.get_project(project_id)


async def list_projects(user_id: str | None = None) -> list[Project]:
    return await _store.list_projects(user_id)


async def update_project(project_id: str, **updates) -> Project:
    return await _store.update_project(project_id, **updates)


async def delete_project(project_id: str) -> None:
    await _store.delete_project(project_id)


async def list_interrupted() -> list[str]:
    return await _store.list_interrupted()


async def owner_of(project_id: str) -> str | None:
    return await _store.owner_of(project_id)
