"""Render API: submit timeline renders, check progress, download output."""

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.auth import get_current_user
from server.models.base import get_session
from server.models.project import Project
from server.models.user import User
from server.tasks.render import render_jobs, render_project_task

router = APIRouter(prefix="/api/render", tags=["render"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class RenderRequest(BaseModel):
    project_id: str


class RenderSubmitResponse(BaseModel):
    job_id: str
    status: str


class RenderStatusResponse(BaseModel):
    job_id: str
    status: str
    percent: float
    error: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("", response_model=RenderSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_render(
    body: RenderRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Submit a project timeline for rendering.

    Returns a job_id that can be used to poll status and download the result.
    """
    # Verify project ownership
    result = await session.execute(
        select(Project).where(
            Project.id == body.project_id,
            Project.user_id == current_user.id,
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if not project.timeline_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no timeline data to render",
        )

    job_id = str(uuid.uuid4())
    ws_manager = request.app.state.ws_manager
    background_tasks.add_task(render_project_task, body.project_id, job_id, ws_manager)

    return RenderSubmitResponse(job_id=job_id, status="queued")


@router.get("/{job_id}/status", response_model=RenderStatusResponse)
async def get_render_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get the progress of a render job."""
    job = render_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Render job not found")

    return RenderStatusResponse(
        job_id=job_id,
        status=job["status"],
        percent=job["percent"],
        error=job.get("error"),
    )


@router.get("/{job_id}/download")
async def download_render(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Download the rendered video file."""
    job = render_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Render job not found")

    if job["status"] != "complete":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Render not complete (status: {job['status']})",
        )

    output_path = Path(job["output_path"])
    if not output_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rendered file not found")

    return FileResponse(
        path=str(output_path),
        media_type="video/mp4",
        filename=f"render_{job_id}.mp4",
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_render(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Cancel a render job and clean up.

    Note: This removes the job from tracking. If the FFmpeg process is still
    running, it will complete but the output will not be served.
    """
    job = render_jobs.pop(job_id, None)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Render job not found")

    # Clean up output file if it exists
    output_path = job.get("output_path")
    if output_path:
        p = Path(output_path)
        if p.is_file():
            p.unlink()
