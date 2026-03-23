"""Timeline renderer service.

Reads the timeline_data JSON from a Project, builds the FFmpeg filter graph,
and renders the final output video.
"""

import json
import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.config import settings
from server.models.project import Project
from server.services import ffmpeg
from server.services.storage import storage

logger = logging.getLogger(__name__)


async def render_timeline(project_id: str, job_id: str, session: AsyncSession,
                          progress_callback=None) -> Path | None:
    """Render a project's timeline into a single output video.

    The timeline_data JSON is expected to have the structure:
    {
        "tracks": [
            {
                "clips": [
                    {
                        "media_path": "relative/path.mp4",
                        "start": 10.5,
                        "end": 22.3
                    },
                    ...
                ]
            }
        ],
        "transition": "crossfade",       # optional, default "none"
        "transition_duration": 0.5        # optional, default 0.5
    }

    Args:
        project_id: The project to render.
        job_id: Unique job ID for tracking this render.
        session: Async DB session.
        progress_callback: Optional async callable(percent: float).

    Returns:
        Path to the rendered output file, or None on failure.
    """
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        logger.error("Project %s not found", project_id)
        return None

    if not project.timeline_data:
        logger.error("Project %s has no timeline data", project_id)
        return None

    try:
        timeline = json.loads(project.timeline_data)
    except json.JSONDecodeError as e:
        logger.error("Invalid timeline JSON for project %s: %s", project_id, e)
        return None

    # Flatten all clips from all tracks into a single ordered list of segments
    segments = []
    for track in timeline.get("tracks", []):
        for clip in track.get("clips", []):
            media_path = clip.get("media_path", "")
            abs_path = storage.get_file_path(media_path)
            if not abs_path.is_file():
                logger.warning("Clip source not found: %s", abs_path)
                continue
            segments.append({
                "path": str(abs_path),
                "start": clip.get("start", 0),
                "end": clip.get("end", 0),
            })

    if not segments:
        logger.error("No valid segments found in project %s timeline", project_id)
        return None

    transition = timeline.get("transition", "none")
    transition_duration = timeline.get("transition_duration", 0.5)

    # Output path
    output_dir = settings.RENDER_DIR / project.user_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{job_id}.mp4"

    try:
        await ffmpeg.render_concat(
            segments, output_path,
            transition=transition,
            transition_duration=transition_duration,
            progress_callback=progress_callback,
        )
        logger.info("Render complete for project %s, job %s: %s", project_id, job_id, output_path)
        return output_path

    except Exception as e:
        logger.error("Render failed for project %s, job %s: %s", project_id, job_id, e)
        return None
