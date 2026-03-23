"""Detection API: trigger and query ShredFinder detection on uploaded media."""

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.auth import get_current_user
from server.models.base import get_session
from server.models.media import Media
from server.models.project import Clip
from server.models.user import User
from server.tasks.detection import run_detection

router = APIRouter(prefix="/api/detection", tags=["detection"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class DetectionRunRequest(BaseModel):
    project_id: str | None = None


class DetectionStatusResponse(BaseModel):
    media_id: str
    status: str  # uploading | processing | ready | error


class DetectedClipResponse(BaseModel):
    id: str
    type: str
    startTime: float
    endTime: float
    confidence: float | None = None
    metadata: dict | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/run/{media_id}", status_code=status.HTTP_202_ACCEPTED)
async def run_detection_endpoint(
    media_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    body: DetectionRunRequest | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Trigger ShredFinder detection on an uploaded media file.

    Runs as a background task. Poll /status/{media_id} or listen on the
    WebSocket for progress updates.
    """
    # Verify ownership
    result = await session.execute(
        select(Media).where(Media.id == media_id, Media.user_id == current_user.id)
    )
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")

    project_id = body.project_id if body else None
    ws_manager = request.app.state.ws_manager
    background_tasks.add_task(run_detection, media_id, project_id, ws_manager)

    return {"status": "started", "media_id": media_id}


@router.get("/status/{media_id}", response_model=DetectionStatusResponse)
async def get_detection_status(
    media_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get the current detection/processing status of a media file."""
    result = await session.execute(
        select(Media).where(Media.id == media_id, Media.user_id == current_user.id)
    )
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")

    return DetectionStatusResponse(media_id=media.id, status=media.status)


@router.get("/results/{media_id}", response_model=list[DetectedClipResponse])
async def get_detection_results(
    media_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get all detected events/clips for a media file.

    Returns clips from all projects that reference this media.
    Only returns clips belonging to the current user's projects.
    """
    # Verify media ownership
    result = await session.execute(
        select(Media).where(Media.id == media_id, Media.user_id == current_user.id)
    )
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")

    result = await session.execute(
        select(Clip).where(Clip.media_id == media_id)
    )
    clips = result.scalars().all()

    events = []
    for clip in clips:
        meta = None
        confidence = None
        if clip.metadata_json:
            try:
                meta = json.loads(clip.metadata_json)
                confidence = meta.get("confidence") if meta else None
            except json.JSONDecodeError:
                pass

        events.append(DetectedClipResponse(
            id=clip.id,
            type=clip.clip_type,
            startTime=clip.start_time,
            endTime=clip.end_time,
            confidence=confidence,
            metadata=meta,
        ))

    return events
