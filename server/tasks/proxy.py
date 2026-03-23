"""Background tasks for proxy generation and thumbnail extraction."""

import json
import logging

from server.models.base import async_session_factory
from server.services.proxy import generate_proxy, extract_thumbnail

logger = logging.getLogger(__name__)


async def generate_proxy_task(media_id: str, ws_manager=None) -> None:
    """Background task: generate a 720p proxy video for the given media.

    Args:
        media_id: UUID of the Media record.
        ws_manager: Optional WebSocketManager for progress broadcasts.
    """
    async with async_session_factory() as session:
        async def _progress(percent: float):
            if ws_manager:
                await ws_manager.broadcast(json.dumps({
                    "type": "proxy_progress",
                    "media_id": media_id,
                    "percent": round(percent, 1),
                }))

        result = await generate_proxy(media_id, session, progress_callback=_progress)

        if ws_manager:
            await ws_manager.broadcast(json.dumps({
                "type": "proxy_complete" if result else "proxy_error",
                "media_id": media_id,
            }))


async def extract_thumbnails_task(media_id: str, ws_manager=None) -> None:
    """Background task: extract a poster-frame thumbnail for the given media.

    Args:
        media_id: UUID of the Media record.
        ws_manager: Optional WebSocketManager for progress broadcasts.
    """
    async with async_session_factory() as session:
        result = await extract_thumbnail(media_id, session)

        if ws_manager:
            await ws_manager.broadcast(json.dumps({
                "type": "thumbnail_complete" if result else "thumbnail_error",
                "media_id": media_id,
            }))
