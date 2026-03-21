"""Export detected events as CMX 3600 EDL (Edit Decision List) format."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _seconds_to_smpte(seconds: float, fps: float = 29.97) -> str:
    """Convert seconds to SMPTE timecode HH:MM:SS:FF."""
    total_frames = int(round(seconds * fps))
    frames_per_sec = int(round(fps))
    ff = total_frames % frames_per_sec
    total_secs = total_frames // frames_per_sec
    ss = total_secs % 60
    total_mins = total_secs // 60
    mm = total_mins % 60
    hh = total_mins // 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def write_edl(events_by_file: dict, output_path: Path, fps: float = 29.97) -> Path:
    """Generate a CMX 3600 EDL file from detected events.

    Args:
        events_by_file: Dict mapping source MP4 Path -> list of Event objects.
        output_path: Path to write the EDL file.
        fps: Frame rate for SMPTE timecode conversion. Default 29.97.

    Returns:
        The output path written.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("TITLE: ShredFinder Export")
    lines.append("FCM: DROP FRAME" if abs(fps - 29.97) < 0.1 else "FCM: NON-DROP FRAME")
    lines.append("")

    edit_num = 1
    rec_offset_sec = 0.0

    for mp4_path, events in events_by_file.items():
        # Reel name: filename stem truncated to 8 chars
        reel = Path(mp4_path).stem[:8].upper()

        for event in events:
            src_in = _seconds_to_smpte(event.clip_start, fps)
            src_out = _seconds_to_smpte(event.clip_start + event.clip_duration, fps)
            rec_in = _seconds_to_smpte(rec_offset_sec, fps)
            rec_out = _seconds_to_smpte(rec_offset_sec + event.clip_duration, fps)

            # CMX 3600 format: edit# reel track transition src_in src_out rec_in rec_out
            lines.append(f"{edit_num:03d}  {reel:<8s} V     C        {src_in} {src_out} {rec_in} {rec_out}")
            # Optional comment with event details
            lines.append(f"* EVENT: {event.event_type} at {event.peak_ts}s")
            lines.append("")

            rec_offset_sec += event.clip_duration
            edit_num += 1

    content = "\n".join(lines) + "\n"
    output_path.write_text(content, encoding="utf-8")
    logger.info("EDL written to %s (%d edits)", output_path, edit_num - 1)
    return output_path
