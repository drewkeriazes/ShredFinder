"""Media API: upload, list, stream, and serve video files."""

import json
import mimetypes
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.datastructures import UploadFile as StarletteUploadFile

from server.api.auth import get_current_user
from server.models.base import get_session
from server.models.media import Media
from server.models.user import User
from server.services.proxy import get_video_info
from server.services.storage import storage
from server.tasks.proxy import extract_thumbnails_task, generate_proxy_task

router = APIRouter(prefix="/api/media", tags=["media"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ClipResponse(BaseModel):
    id: str
    name: str
    clip_type: str
    start_time: float
    end_time: float
    metadata: dict | None = None

    model_config = {"from_attributes": True}


class MediaResponse(BaseModel):
    id: str
    user_id: str
    original_filename: str
    storage_path: str
    proxy_path: str | None = None
    thumbnail_path: str | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    codec: str | None = None
    file_size: int | None = None
    status: str
    clips: list[ClipResponse] = []

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/upload", response_model=MediaResponse, status_code=status.HTTP_201_CREATED)
async def upload_media(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Upload a video file via multipart form data.

    Saves the file to storage, creates a Media record, and kicks off
    background tasks for proxy generation and thumbnail extraction.
    """
    form = await request.form()
    upload_file = form.get("file")
    if upload_file is None or not isinstance(upload_file, StarletteUploadFile):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file uploaded")

    filename = upload_file.filename or "video.mp4"

    # Save to storage
    rel_path = await storage.save_upload(upload_file, current_user.id, filename)
    abs_path = storage.get_file_path(rel_path)
    file_size = abs_path.stat().st_size

    # Extract video info
    try:
        info = await get_video_info(abs_path)
    except Exception:
        info = {}

    media = Media(
        user_id=current_user.id,
        original_filename=filename,
        storage_path=rel_path,
        duration=info.get("duration"),
        width=info.get("width"),
        height=info.get("height"),
        fps=info.get("fps"),
        codec=info.get("codec"),
        file_size=file_size,
        status="processing",
    )
    session.add(media)
    await session.commit()
    await session.refresh(media)

    # Kick off background processing
    ws_manager = request.app.state.ws_manager
    background_tasks.add_task(generate_proxy_task, media.id, ws_manager)
    background_tasks.add_task(extract_thumbnails_task, media.id, ws_manager)

    # Return response directly — new upload has no clips yet, avoid lazy-load issue
    return MediaResponse(
        id=media.id,
        user_id=media.user_id,
        original_filename=media.original_filename,
        storage_path=media.storage_path,
        proxy_path=media.proxy_path,
        thumbnail_path=media.thumbnail_path,
        duration=media.duration,
        width=media.width,
        height=media.height,
        fps=media.fps,
        codec=media.codec,
        file_size=media.file_size,
        status=media.status,
        clips=[],
    )


@router.get("", response_model=list[MediaResponse])
async def list_media(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List all media files belonging to the current user."""
    result = await session.execute(
        select(Media)
        .where(Media.user_id == current_user.id)
        .options(selectinload(Media.clips))
        .order_by(Media.created_at.desc())
    )
    media_list = result.scalars().all()
    return [_media_with_clips(m) for m in media_list]


@router.get("/{media_id}", response_model=MediaResponse)
async def get_media(
    media_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get details for a single media file."""
    result = await session.execute(
        select(Media)
        .where(Media.id == media_id, Media.user_id == current_user.id)
        .options(selectinload(Media.clips))
    )
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    return _media_with_clips(media)


def _media_with_clips(media: Media) -> MediaResponse:
    """Convert a Media ORM object to a MediaResponse, parsing clip metadata."""
    clips = []
    for clip in media.clips:
        meta = None
        if clip.metadata_json:
            try:
                meta = json.loads(clip.metadata_json)
            except json.JSONDecodeError:
                pass
        clips.append(ClipResponse(
            id=clip.id,
            name=clip.name,
            clip_type=clip.clip_type,
            start_time=clip.start_time,
            end_time=clip.end_time,
            metadata=meta,
        ))
    return MediaResponse.model_validate(media, from_attributes=True).model_copy(
        update={"clips": clips}
    )


@router.get("/{media_id}/stream")
async def stream_media(
    media_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Stream the original video file with support for HTTP range requests (seeking)."""
    result = await session.execute(
        select(Media).where(Media.id == media_id, Media.user_id == current_user.id)
    )
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")

    file_path = storage.get_file_path(media.storage_path)
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found on disk")

    file_size = file_path.stat().st_size
    content_type = mimetypes.guess_type(str(file_path))[0] or "video/mp4"

    range_header = request.headers.get("range")
    if range_header:
        return _range_response(file_path, file_size, content_type, range_header)

    return FileResponse(
        path=str(file_path),
        media_type=content_type,
        filename=media.original_filename,
    )


@router.get("/{media_id}/thumbnail")
async def serve_thumbnail(
    media_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Serve the thumbnail image for a media file."""
    result = await session.execute(
        select(Media).where(Media.id == media_id, Media.user_id == current_user.id)
    )
    media = result.scalar_one_or_none()
    if media is None or not media.thumbnail_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not available")

    thumb_path = storage.get_file_path(media.thumbnail_path)
    if not thumb_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail file not found")

    return FileResponse(path=str(thumb_path), media_type="image/jpeg")


@router.get("/{media_id}/proxy")
async def serve_proxy(
    media_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Serve the proxy video for a media file."""
    result = await session.execute(
        select(Media).where(Media.id == media_id, Media.user_id == current_user.id)
    )
    media = result.scalar_one_or_none()
    if media is None or not media.proxy_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proxy not available")

    proxy_path = storage.get_file_path(media.proxy_path)
    if not proxy_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proxy file not found")

    return FileResponse(path=str(proxy_path), media_type="video/mp4")


# ---------------------------------------------------------------------------
# Range request helper
# ---------------------------------------------------------------------------

def _range_response(file_path: Path, file_size: int, content_type: str,
                    range_header: str) -> StreamingResponse:
    """Build a 206 Partial Content response for video seeking."""
    # Parse "bytes=start-end"
    try:
        range_spec = range_header.replace("bytes=", "")
        parts = range_spec.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
    except (ValueError, IndexError):
        start = 0
        end = file_size - 1

    end = min(end, file_size - 1)
    chunk_size = end - start + 1

    def _iter_file():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = chunk_size
            while remaining > 0:
                read_size = min(1024 * 1024, remaining)
                data = f.read(read_size)
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_size),
    }

    return StreamingResponse(
        _iter_file(),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=content_type,
        headers=headers,
    )
