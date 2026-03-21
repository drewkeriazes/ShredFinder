"""Group MP4 files into sessions by date and GPS proximity."""

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from .detector import Event
from .telemetry import find_ffprobe

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """A group of related footage files (same day/location)."""
    session_id: str
    date: str  # YYYY-MM-DD
    location_label: str  # lat/lon centroid or resort name
    files: list[Path] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)

    @property
    def total_events(self) -> int:
        return len(self.events)

    @property
    def jump_count(self) -> int:
        return sum(1 for e in self.events if "jump" in e.event_type)

    @property
    def spin_count(self) -> int:
        return sum(1 for e in self.events if "spin" in e.event_type)

    @property
    def crash_count(self) -> int:
        return sum(1 for e in self.events if "crash" in e.event_type)

    @property
    def top_speed(self) -> float:
        speeds = [e.peak_speed_mph for e in self.events if e.peak_speed_mph > 0]
        return max(speeds) if speeds else 0.0

    @property
    def best_airtime(self) -> float:
        airtimes = [e.airtime_sec for e in self.events if e.airtime_sec > 0]
        return max(airtimes) if airtimes else 0.0


def get_file_creation_date(mp4_path: Path) -> str | None:
    """Extract creation date from MP4 metadata via ffprobe.

    Returns date string like '2024-02-15' or None.
    """
    try:
        ffprobe = find_ffprobe()
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json",
             "-show_format", str(mp4_path)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        tags = data.get("format", {}).get("tags", {})
        creation_time = tags.get("creation_time", "")
        if creation_time:
            # Parse ISO format: "2024-02-15T10:30:00.000000Z"
            dt = datetime.fromisoformat(creation_time.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
    except Exception as e:
        logger.debug("Could not read creation date from %s: %s", mp4_path.name, e)

    # Fallback to filesystem modification time
    try:
        mtime = mp4_path.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except Exception:
        return None


def group_into_sessions(
    events_by_file: dict[Path, list[Event]],
    gps_centroids: dict[Path, tuple[float, float]] | None = None,
    time_gap_hours: float = 4.0,
) -> list[Session]:
    """Group files into sessions by date and GPS proximity.

    Args:
        events_by_file: Map of source file -> detected events.
        gps_centroids: Optional map of source file -> (mean_lat, mean_lon).
        time_gap_hours: Max hours gap to consider same session.

    Returns:
        List of Session objects sorted by date.
    """
    # Get dates for all files
    file_dates: dict[Path, str] = {}
    for mp4_path in events_by_file:
        date = get_file_creation_date(mp4_path)
        file_dates[mp4_path] = date or "unknown"

    # Group by date
    date_groups: dict[str, list[Path]] = {}
    for path, date in sorted(file_dates.items(), key=lambda x: x[1]):
        date_groups.setdefault(date, []).append(path)

    # Within each date, split by GPS proximity if available
    sessions = []
    for date, files in sorted(date_groups.items()):
        if gps_centroids and len(files) > 1:
            sub_groups = _split_by_location(files, gps_centroids)
        else:
            sub_groups = [files]

        for group_idx, group_files in enumerate(sub_groups):
            location = _format_location(group_files, gps_centroids)
            session_id = f"{date}_{group_idx + 1}" if len(sub_groups) > 1 else date

            all_events = []
            for f in group_files:
                all_events.extend(events_by_file.get(f, []))

            sessions.append(Session(
                session_id=session_id,
                date=date,
                location_label=location,
                files=group_files,
                events=all_events,
            ))

    logger.info("Grouped %d files into %d sessions", len(events_by_file), len(sessions))
    return sessions


def _split_by_location(
    files: list[Path],
    centroids: dict[Path, tuple[float, float]],
    max_distance_km: float = 5.0,
) -> list[list[Path]]:
    """Split files into sub-groups by GPS proximity."""
    groups: list[list[Path]] = []

    for f in files:
        if f not in centroids:
            # No GPS — add to first group or create new one
            if groups:
                groups[0].append(f)
            else:
                groups.append([f])
            continue

        lat, lon = centroids[f]
        placed = False
        for group in groups:
            # Check distance to any file in the group
            for gf in group:
                if gf in centroids:
                    glat, glon = centroids[gf]
                    dist = _haversine_km(lat, lon, glat, glon)
                    if dist <= max_distance_km:
                        group.append(f)
                        placed = True
                        break
            if placed:
                break

        if not placed:
            groups.append([f])

    return groups


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance between two GPS coordinates in km."""
    R = 6371.0
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = (np.sin(dlat / 2) ** 2 +
         np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2) ** 2)
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def _format_location(
    files: list[Path],
    centroids: dict[Path, tuple[float, float]] | None,
) -> str:
    """Format a location label from GPS centroids."""
    if not centroids:
        return ""

    lats, lons = [], []
    for f in files:
        if f in centroids:
            lat, lon = centroids[f]
            lats.append(lat)
            lons.append(lon)

    if not lats:
        return ""

    mean_lat = sum(lats) / len(lats)
    mean_lon = sum(lons) / len(lons)
    return f"{mean_lat:.4f}, {mean_lon:.4f}"
