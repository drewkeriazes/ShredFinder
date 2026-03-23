"""Proxy and thumbnail generation service.

Wraps the lower-level ffmpeg module to operate on Media records, updating
their status and paths in the database.
"""

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.config import settings
from server.models.media import Media
from server.services import ffmpeg
from server.services.storage import storage

logger = logging.getLogger(__name__)


async def generate_proxy(media_id: str, session: AsyncSession,
                         progress_callback=None) -> str | None:
    """Create a 720p proxy video for the given media record.

    Updates the Media record's proxy_path and status on completion.
    Returns the proxy relative path, or None on failure.
    """
    result = await session.execute(select(Media).where(Media.id == media_id))
    media = result.scalar_one_or_none()
    if media is None:
        logger.error("Media %s not found", media_id)
        return None

    source_path = storage.get_file_path(media.storage_path)
    if not source_path.is_file():
        logger.error("Source file missing: %s", source_path)
        media.status = "error"
        await session.commit()
        return None

    # Build proxy output path
    proxy_filename = f"{media_id}_proxy.mp4"
    proxy_rel = f"{media.user_id}/proxies/{proxy_filename}"
    proxy_abs = settings.PROXY_DIR / media.user_id / proxy_filename
    proxy_abs.parent.mkdir(parents=True, exist_ok=True)

    try:
        media.status = "processing"
        await session.commit()

        await ffmpeg.generate_proxy(
            source_path, proxy_abs,
            height=settings.PROXY_HEIGHT,
            crf=settings.PROXY_CRF,
            progress_callback=progress_callback,
        )

        media.proxy_path = proxy_rel
        await session.commit()
        logger.info("Proxy generated for media %s: %s", media_id, proxy_rel)
        return proxy_rel

    except Exception as e:
        logger.error("Proxy generation failed for %s: %s", media_id, e)
        media.status = "error"
        await session.commit()
        return None


async def extract_thumbnail(media_id: str, session: AsyncSession) -> str | None:
    """Extract a poster-frame thumbnail from the video.

    Updates the Media record's thumbnail_path on success.
    Returns the thumbnail relative path, or None on failure.
    """
    result = await session.execute(select(Media).where(Media.id == media_id))
    media = result.scalar_one_or_none()
    if media is None:
        logger.error("Media %s not found", media_id)
        return None

    source_path = storage.get_file_path(media.storage_path)
    if not source_path.is_file():
        logger.error("Source file missing: %s", source_path)
        return None

    thumb_filename = f"{media_id}_thumb.jpg"
    thumb_rel = f"{media.user_id}/thumbnails/{thumb_filename}"
    thumb_abs = settings.THUMBNAIL_DIR / media.user_id / thumb_filename
    thumb_abs.parent.mkdir(parents=True, exist_ok=True)

    try:
        await ffmpeg.extract_thumbnail(source_path, thumb_abs, timestamp=2.0)
        media.thumbnail_path = thumb_rel
        await session.commit()
        logger.info("Thumbnail extracted for media %s: %s", media_id, thumb_rel)
        return thumb_rel

    except Exception as e:
        logger.error("Thumbnail extraction failed for %s: %s", media_id, e)
        return None


async def get_video_info(file_path: Path) -> dict:
    """Return video metadata dict (duration, width, height, fps, codec)."""
    return await ffmpeg.get_video_info(file_path)
