"""In-memory project store.

Good enough for a single-user local tool. Swap for SQLite/Postgres if you
need multi-user persistence across restarts; the interface here is small
enough to reimplement behind the same functions.
"""

from __future__ import annotations

from app.schemas.project import Project, ProjectConfig, ProjectStatus

_projects: dict[str, Project] = {}


def create_project(config: ProjectConfig) -> Project:
    project = Project(config=config, status=ProjectStatus.DRAFT)
    _projects[config.id] = project
    return project


def get_project(project_id: str) -> Project | None:
    return _projects.get(project_id)


def list_projects() -> list[Project]:
    return list(_projects.values())


def update_project(project_id: str, **updates) -> Project:
    project = _projects[project_id]
    updated = project.model_copy(update=updates)
    _projects[project_id] = updated
    return updated


def delete_project(project_id: str) -> None:
    _projects.pop(project_id, None)
