"""Timeline renderer service.

Reads the timeline_data JSON from a Project, builds the FFmpeg filter graph,
and renders the final output video.

The frontend stores timeline_data in this format:
{
    "tracks": [
        {
            "id": "...", "name": "Video 1", "type": "video",
            "muted": false, "locked": false, "visible": true,
            "clips": [
                {
                    "id": "...", "mediaId": "uuid-of-media-record",
                    "trackId": "...", "startTime": 0, "duration": 5.5,
                    "trimStart": 1.2, "trimEnd": 0.5,
                    "name": "clip.mp4", "type": "jump", "speed": 1,
                    "volume": 100, "opacity": 100,
                    "transitionIn": { "type": "crossfade", "duration": 0.5 }
                }
            ]
        }
    ],
    "playheadPosition": 0,
    "zoom": 1
}
"""

import json
import logging
import traceback
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.config import settings
from server.models.media import Media
from server.models.project import Project
from server.services import ffmpeg
from server.services.storage import storage

logger = logging.getLogger(__name__)


async def render_timeline(project_id: str, job_id: str, session: AsyncSession,
                          progress_callback=None) -> Path | None:
    """Render a project's timeline into a single output video.

    Parses the frontend timeline_data JSON, resolves media paths from the DB,
    builds FFmpeg segments with trim/speed/volume info and per-clip transitions,
    then calls ffmpeg.render_concat().

    Args:
        project_id: The project to render.
        job_id: Unique job ID for tracking this render.
        session: Async DB session.
        progress_callback: Optional async callable(percent: float).

    Returns:
        Path to the rendered output file, or None on failure.
    """
    # ---- Load project ----
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

    tracks = timeline.get("tracks", [])
    if not tracks:
        logger.error("Project %s timeline has no tracks", project_id)
        return None

    # ---- Collect segments from visible video tracks ----
    segments: list[dict] = []
    has_audio_mute = False

    for track in tracks:
        # Skip invisible tracks
        if not track.get("visible", True):
            continue

        track_type = track.get("type", "video")
        track_muted = track.get("muted", False)

        clips = track.get("clips", [])
        # Sort clips by their position on the timeline
        clips_sorted = sorted(clips, key=lambda c: c.get("startTime", 0))

        for clip in clips_sorted:
            media_id = clip.get("mediaId")
            if not media_id:
                logger.warning("Clip %s has no mediaId, skipping", clip.get("id", "?"))
                continue

            # Resolve media record from DB
            media_result = await session.execute(
                select(Media).where(Media.id == media_id)
            )
            media = media_result.scalar_one_or_none()
            if media is None:
                logger.warning("Media %s not found for clip %s, skipping",
                               media_id, clip.get("id", "?"))
                continue

            abs_path = storage.get_file_path(media.storage_path)
            if not abs_path.is_file():
                logger.warning("Media file not found on disk: %s (media %s)",
                               abs_path, media_id)
                continue

            # Calculate FFmpeg trim points from clip properties
            trim_start = clip.get("trimStart", 0)
            duration = clip.get("duration", 0)
            trim_end = clip.get("trimEnd", 0)
            # The source portion to use: from trimStart to trimStart + duration - trimEnd
            source_start = trim_start
            source_end = trim_start + duration - trim_end

            if source_end <= source_start:
                logger.warning("Clip %s has invalid trim (start=%s end=%s), skipping",
                               clip.get("id", "?"), source_start, source_end)
                continue

            segment = {
                "path": str(abs_path),
                "start": source_start,
                "end": source_end,
            }

            # Speed
            speed = clip.get("speed", 1)
            if speed != 1 and speed > 0:
                segment["speed"] = speed

            # Volume: factor in track mute and clip volume
            clip_volume = clip.get("volume", 100)
            if track_muted or (track_type == "audio" and track_muted):
                segment["volume"] = 0
                has_audio_mute = True
            elif clip_volume != 100:
                segment["volume"] = clip_volume

            # Transition in (between this clip and the previous)
            transition_in = clip.get("transitionIn")
            if transition_in and isinstance(transition_in, dict):
                t_type = transition_in.get("type", "none")
                t_duration = transition_in.get("duration", 0.5)
                if t_type and t_type != "none":
                    segment["transition"] = t_type
                    segment["transition_duration"] = t_duration

            segments.append(segment)

    if not segments:
        logger.error("No valid segments found in project %s timeline", project_id)
        return None

    # ---- Determine global vs per-clip transition mode ----
    # Check if any segment has a per-clip transition
    has_transitions = any("transition" in seg for seg in segments)

    # For the first clip, transition_in doesn't make sense (no preceding clip)
    # Remove transition from the first segment if present
    if segments and "transition" in segments[0]:
        del segments[0]["transition"]
        if "transition_duration" in segments[0]:
            del segments[0]["transition_duration"]

    # Re-check after removing first-clip transition
    has_transitions = any("transition" in seg for seg in segments)

    # Decide transition mode for ffmpeg.render_concat
    if has_transitions:
        # Per-clip transitions: pass "per-clip" mode
        transition_mode = "per-clip"
        transition_duration = 0.5  # default, overridden per-clip
    else:
        transition_mode = "none"
        transition_duration = 0.5

    # ---- Output path ----
    output_path, _ = storage.render_path(project.user_id, job_id)

    try:
        await ffmpeg.render_concat(
            segments, output_path,
            transition=transition_mode,
            transition_duration=transition_duration,
            progress_callback=progress_callback,
        )
        logger.info("Render complete for project %s, job %s: %s",
                     project_id, job_id, output_path)
        return output_path

    except Exception:
        logger.error("Render failed for project %s, job %s:\n%s",
                     project_id, job_id, traceback.format_exc())
        return None
