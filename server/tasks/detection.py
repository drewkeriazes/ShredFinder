"""Background task: run ShredFinder detection pipeline on an uploaded media file."""

import json
import logging

from server.models.base import async_session_factory
from server.models.media import Media
from server.models.project import Clip
from server.services.storage import storage

from sqlalchemy import select

logger = logging.getLogger(__name__)


async def run_detection(media_id: str, project_id: str, ws_manager=None) -> None:
    """Run the ShredFinder telemetry extraction and event detection pipeline.

    1. Resolves the media file path from the database.
    2. Extracts GPMF telemetry using the shredfinder package.
    3. Runs the detector to find jumps, spins, speed events, and crashes.
    4. Creates Clip records for each detected event.
    5. Updates the media status.

    Args:
        media_id: UUID of the Media record.
        project_id: UUID of the Project to attach detected clips to.
        ws_manager: Optional WebSocketManager for broadcasting progress.
    """
    async with async_session_factory() as session:
        try:
            result = await session.execute(select(Media).where(Media.id == media_id))
            media = result.scalar_one_or_none()
            if media is None:
                logger.error("Detection: media %s not found", media_id)
                return

            source_path = storage.get_file_path(media.storage_path)
            if not source_path.is_file():
                logger.error("Detection: source file missing: %s", source_path)
                media.status = "error"
                await session.commit()
                return

            if ws_manager:
                await ws_manager.broadcast(json.dumps({
                    "type": "detection_progress",
                    "media_id": media_id,
                    "status": "extracting_telemetry",
                    "percent": 10,
                }))

            # Import the shredfinder package
            from shredfinder.telemetry import extract_telemetry
            from shredfinder.detector import detect_events

            telemetry = extract_telemetry(source_path)

            if not telemetry.has_accl and not telemetry.has_gps:
                logger.warning("No telemetry data found in %s", source_path.name)
                media.status = "ready"
                await session.commit()
                if ws_manager:
                    await ws_manager.broadcast(json.dumps({
                        "type": "detection_complete",
                        "media_id": media_id,
                        "events_found": 0,
                    }))
                return

            if ws_manager:
                await ws_manager.broadcast(json.dumps({
                    "type": "detection_progress",
                    "media_id": media_id,
                    "status": "detecting_events",
                    "percent": 50,
                }))

            events = detect_events(telemetry)

            # Create Clip records for each detected event
            clips_created = 0
            for event in events:
                clip_end = event.clip_start + event.clip_duration

                # Build metadata JSON from event attributes
                meta = {
                    "airtime_sec": event.airtime_sec,
                    "peak_speed_mph": event.peak_speed_mph,
                    "spin_degrees": event.spin_degrees,
                    "spin_axis": event.spin_axis,
                    "crash_severity": event.crash_severity,
                    "landing_quality": event.landing_quality,
                    "landing_score": event.landing_score,
                    "landing_magnitude": event.landing_magnitude,
                    "confidence": event.confidence,
                    "peak_ts": event.peak_ts,
                }

                # Determine the primary event type (handle merged types like "jump+spin")
                primary_type = event.event_type.split("+")[0]

                # Build a descriptive name
                name = _build_clip_name(event)

                clip = Clip(
                    project_id=project_id,
                    media_id=media_id,
                    name=name,
                    clip_type=primary_type,
                    start_time=event.clip_start,
                    end_time=clip_end,
                    metadata_json=json.dumps(meta),
                )
                session.add(clip)
                clips_created += 1

            media.status = "ready"
            await session.commit()

            logger.info(
                "Detection complete for media %s: %d events, %d clips created",
                media_id, len(events), clips_created,
            )

            if ws_manager:
                await ws_manager.broadcast(json.dumps({
                    "type": "detection_complete",
                    "media_id": media_id,
                    "events_found": len(events),
                    "clips_created": clips_created,
                }))

        except Exception as e:
            logger.exception("Detection failed for media %s: %s", media_id, e)
            try:
                result = await session.execute(select(Media).where(Media.id == media_id))
                media = result.scalar_one_or_none()
                if media:
                    media.status = "error"
                    await session.commit()
            except Exception:
                pass

            if ws_manager:
                await ws_manager.broadcast(json.dumps({
                    "type": "detection_error",
                    "media_id": media_id,
                    "error": str(e),
                }))


def _build_clip_name(event) -> str:
    """Build a human-readable name for a clip from its event data."""
    etype = event.event_type

    if "jump" in etype:
        quality = f" ({event.landing_quality})" if event.landing_quality else ""
        return f"Jump {event.airtime_sec:.1f}s{quality}"
    elif "spin" in etype:
        return f"Spin {event.spin_degrees:.0f}deg"
    elif "speed" in etype:
        return f"Speed {event.peak_speed_mph:.0f}mph"
    elif "crash" in etype:
        return f"Crash (severity {event.crash_severity:.0f})"
    else:
        return f"Event at {event.peak_ts:.1f}s"
