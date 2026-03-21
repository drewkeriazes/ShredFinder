"""Season statistics aggregation across all sessions."""

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

from .session import Session
from .telemetry import Telemetry

logger = logging.getLogger(__name__)


@dataclass
class SeasonStats:
    """Aggregated stats across all sessions."""
    total_sessions: int = 0
    total_files: int = 0
    total_events: int = 0
    total_jumps: int = 0
    total_spins: int = 0
    total_crashes: int = 0
    total_speed_events: int = 0
    top_speed_mph: float = 0.0
    best_airtime_sec: float = 0.0
    biggest_spin_degrees: float = 0.0
    total_clip_duration_sec: float = 0.0
    vertical_feet: float = 0.0
    distance_miles: float = 0.0
    riding_time_sec: float = 0.0
    chairlift_time_sec: float = 0.0


def compute_season_stats(
    sessions: list[Session],
    telemetry_by_file: dict[Path, Telemetry] | None = None,
) -> SeasonStats:
    """Compute aggregate statistics across all sessions."""
    stats = SeasonStats()
    stats.total_sessions = len(sessions)

    for session in sessions:
        stats.total_files += len(session.files)
        stats.total_events += session.total_events

        for event in session.events:
            primary = event.event_type.split("+")[0]
            if primary == "jump":
                stats.total_jumps += 1
            elif primary == "spin":
                stats.total_spins += 1
            elif primary == "crash":
                stats.total_crashes += 1
            elif primary == "speed":
                stats.total_speed_events += 1

            stats.total_clip_duration_sec += event.clip_duration

            if event.peak_speed_mph > stats.top_speed_mph:
                stats.top_speed_mph = event.peak_speed_mph
            if event.airtime_sec > stats.best_airtime_sec:
                stats.best_airtime_sec = event.airtime_sec
            if event.spin_degrees > stats.biggest_spin_degrees:
                stats.biggest_spin_degrees = event.spin_degrees

    # Compute GPS-derived stats from telemetry
    if telemetry_by_file:
        for path, telemetry in telemetry_by_file.items():
            if telemetry.has_gps and not telemetry.gps_df.empty:
                vert, dist = _compute_gps_stats(telemetry)
                stats.vertical_feet += vert
                stats.distance_miles += dist

            # Segment-based time breakdown
            for seg in telemetry.segments:
                duration = seg.end_ts - seg.start_ts
                if seg.activity == "riding":
                    stats.riding_time_sec += duration
                elif seg.activity == "chairlift":
                    stats.chairlift_time_sec += duration

    logger.info("Season stats: %d sessions, %d events, top speed %.1f mph",
                stats.total_sessions, stats.total_events, stats.top_speed_mph)
    return stats


def _compute_gps_stats(telemetry: Telemetry) -> tuple[float, float]:
    """Compute vertical feet descended and distance traveled from GPS data.

    Returns (vertical_feet, distance_miles).
    """
    gps_df = telemetry.gps_df
    if len(gps_df) < 2:
        return 0.0, 0.0

    alt = gps_df["alt_m"].values
    lat = gps_df["lat"].values
    lon = gps_df["lon"].values

    # Smooth altitude to reduce GPS noise
    if len(alt) > 20:
        kernel_size = min(20, len(alt) // 5)
        if kernel_size > 1:
            kernel = np.ones(kernel_size) / kernel_size
            alt_smooth = np.convolve(alt, kernel, mode="valid")
        else:
            alt_smooth = alt
    else:
        alt_smooth = alt

    # Vertical descent: sum only negative altitude changes (going downhill)
    alt_diffs = np.diff(alt_smooth)
    descent_m = float(np.sum(alt_diffs[alt_diffs < 0]))
    vertical_feet = abs(descent_m) * 3.28084  # meters to feet

    # Distance: approximate using lat/lon differences
    R_miles = 3958.8  # Earth radius in miles
    total_dist = 0.0
    for i in range(1, len(lat)):
        dlat = np.radians(lat[i] - lat[i-1])
        dlon = np.radians(lon[i] - lon[i-1])
        a = (np.sin(dlat/2)**2 +
             np.cos(np.radians(lat[i-1])) * np.cos(np.radians(lat[i])) *
             np.sin(dlon/2)**2)
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
        total_dist += R_miles * c

    return vertical_feet, total_dist


def write_stats_text(stats: SeasonStats, output_path: Path) -> str:
    """Write human-readable stats summary. Returns the text."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "=" * 50,
        "SHREDFINDER — SEASON STATS",
        "=" * 50,
        "",
        f"Sessions:           {stats.total_sessions}",
        f"Files processed:    {stats.total_files}",
        f"Total events:       {stats.total_events}",
        f"  Jumps:            {stats.total_jumps}",
        f"  Spins:            {stats.total_spins}",
        f"  Crashes:          {stats.total_crashes}",
        f"  Speed events:     {stats.total_speed_events}",
        "",
        "HIGHLIGHTS:",
        f"  Top speed:        {stats.top_speed_mph:.1f} mph",
        f"  Best airtime:     {stats.best_airtime_sec:.2f}s",
    ]

    if stats.biggest_spin_degrees > 0:
        lines.append(f"  Biggest spin:     {stats.biggest_spin_degrees:.0f} degrees")

    lines.append("")

    if stats.vertical_feet > 0:
        lines += [
            "GPS STATS:",
            f"  Vertical feet:    {stats.vertical_feet:,.0f} ft",
            f"  Distance:         {stats.distance_miles:.1f} miles",
        ]
        if stats.riding_time_sec > 0:
            ride_min = stats.riding_time_sec / 60
            lift_min = stats.chairlift_time_sec / 60
            lines += [
                f"  Riding time:      {ride_min:.0f} min",
                f"  Chairlift time:   {lift_min:.0f} min",
            ]
        lines.append("")

    lines += [
        f"Total clip footage: {stats.total_clip_duration_sec:.0f}s "
        f"({stats.total_clip_duration_sec / 60:.1f} min)",
        "",
    ]

    text = "\n".join(lines)
    output_path.write_text(text)
    return text


def write_stats_json(stats: SeasonStats, output_path: Path) -> Path:
    """Write stats as JSON for programmatic consumption."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(stats)
    output_path.write_text(json.dumps(data, indent=2))
    return output_path
