"""REST endpoints for project creation, listing, and video download."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.schemas.project import Project, ProjectConfig
from app.services import project_store

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=Project, status_code=201)
async def create_project(config: ProjectConfig, request: Request) -> Project:
    """Create a project and enqueue it for rendering immediately."""
    project = await project_store.create_project(config)
    await request.app.state.render_queue.submit(project)
    return project


@router.get("", response_model=list[Project])
async def list_projects() -> list[Project]:
    return await project_store.list_projects()


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str) -> Project:
    project = await project_store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str) -> None:
    if await project_store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await project_store.delete_project(project_id)


@router.get("/{project_id}/download")
async def download_project_video(project_id: str) -> FileResponse:
    project = await project_store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.output_path:
        raise HTTPException(status_code=409, detail="Render is not complete yet")
    return FileResponse(
        project.output_path,
        media_type="video/mp4",
        filename=f"{project.config.topic[:40].strip().replace(' ', '_') or project_id}.mp4",
    )
