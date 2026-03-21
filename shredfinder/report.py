"""Generate manifest CSV and summary report from clip results."""

import csv
import logging
from datetime import datetime
from pathlib import Path

from .clipper import ClipResult

logger = logging.getLogger(__name__)


def write_manifest(results: list[ClipResult], output_path: str | Path) -> Path:
    """Write a CSV manifest of all cut clips."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "clip_path", "source_file", "event_type", "peak_ts",
            "clip_start", "clip_duration", "peak_value",
            "confidence", "landing_quality", "spin_degrees", "crash_severity", "success",
        ])
        for r in results:
            peak_value = _format_peak_value(r.event)
            writer.writerow([
                r.clip_path,
                r.source_file,
                r.event.event_type,
                r.event.peak_ts,
                r.event.clip_start,
                r.event.clip_duration,
                peak_value,
                r.event.confidence,
                r.event.landing_quality,
                r.event.spin_degrees if r.event.spin_degrees > 0 else "",
                r.event.crash_severity if r.event.crash_severity > 0 else "",
                r.success,
            ])

    return output_path


def _format_peak_value(event) -> str:
    """Format the primary metric for an event."""
    if event.spin_degrees > 0:
        return f"{event.spin_degrees:.0f}° spin"
    if event.peak_speed_mph > 0:
        return f"{event.peak_speed_mph} mph"
    if event.airtime_sec > 0:
        return f"{event.airtime_sec}s airtime"
    if event.crash_severity > 0:
        return f"severity {event.crash_severity}"
    return ""


def write_summary(
    results: list[ClipResult],
    output_path: str | Path,
    no_telemetry_files: list[Path] | None = None,
) -> str:
    """Generate a human-readable summary report. Returns the report text."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    jump_clips = [r for r in successful if "jump" in r.event.event_type]
    speed_clips = [r for r in successful if "speed" in r.event.event_type]
    spin_clips = [r for r in successful if "spin" in r.event.event_type]
    crash_clips = [r for r in successful if "crash" in r.event.event_type]

    stomped = [r for r in jump_clips if r.event.landing_quality == "stomped"]
    sketchy = [r for r in jump_clips if r.event.landing_quality == "sketchy"]

    total_duration = sum(r.event.clip_duration for r in successful)

    lines = [
        "=" * 50,
        "SHREDFINDER — HIGHLIGHT CLIP REPORT",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "=" * 50,
        "",
        f"Total clips cut:    {len(successful)}",
        f"  Jumps:            {len(jump_clips)}  (stomped: {len(stomped)}, sketchy: {len(sketchy)})",
        f"  Speed:            {len(speed_clips)}",
        f"  Spins:            {len(spin_clips)}",
        f"  Crashes:          {len(crash_clips)}",
        f"Total clip footage: {total_duration:.0f}s ({total_duration / 60:.1f} min)",
        "",
    ]

    # Best moments
    if jump_clips:
        best_jump = max(jump_clips, key=lambda r: r.event.airtime_sec)
        lines.append(f"Longest airtime:    {best_jump.event.airtime_sec}s "
                     f"({best_jump.source_file.name} at {best_jump.event.peak_ts}s)")
    if speed_clips:
        best_speed = max(speed_clips, key=lambda r: r.event.peak_speed_mph)
        lines.append(f"Top speed:          {best_speed.event.peak_speed_mph} mph "
                     f"({best_speed.source_file.name} at {best_speed.event.peak_ts}s)")
    if spin_clips:
        best_spin = max(spin_clips, key=lambda r: r.event.spin_degrees)
        lines.append(f"Biggest spin:       {best_spin.event.spin_degrees:.0f}° "
                     f"({best_spin.source_file.name} at {best_spin.event.peak_ts}s)")
    if jump_clips or speed_clips or spin_clips:
        lines.append("")

    if failed:
        lines.append(f"FAILED clips:       {len(failed)}")
        for r in failed:
            lines.append(f"  {r.source_file.name} at {r.event.clip_start}s: {r.error}")
        lines.append("")

    if no_telemetry_files:
        lines.append(f"Files with no telemetry: {len(no_telemetry_files)}")
        for f in no_telemetry_files:
            lines.append(f"  {f.name}")
        lines.append("")

    if successful:
        lines.append("CLIPS (sorted by type then timestamp):")
        lines.append("")
        for r in sorted(successful, key=lambda x: (x.event.event_type, x.event.clip_start)):
            detail = _format_clip_detail(r.event)
            lines.append(f"  {r.clip_path.name}{detail}")
        lines.append("")

    lines += [
        "OUTPUT FOLDER STRUCTURE:",
        "  clips/jumps/     — Jump events",
        "  clips/speed/     — Speed peak events",
        "  clips/spins/     — Spin/rotation events",
        "  clips/crashes/   — Crash/bail events",
        "  clips/by_source/ — Clips grouped by source MP4",
        "",
        "NEXT STEPS:",
        "  1. Import the clips/ folder into DaVinci Resolve",
        "  2. Start with your best clip — don't save it for the end",
        "  3. Add music from YouTube Audio Library (free, no copyright issues)",
        "  4. In the Color tab, apply a snow LUT for a cinematic grade",
        "  5. Deliver at 1080p or 4K",
        "",
    ]

    if not successful:
        lines += [
            "WARNING: No clips were produced. Check that:",
            "  - GoPro GPS was enabled during recording",
            "  - Accelerometer data is present (it usually is)",
            "  - Try lowering thresholds (--g-threshold 6, --min-speed-mph 10)",
            "",
        ]

    report = "\n".join(lines)
    output_path.write_text(report)
    return report


def _format_clip_detail(event) -> str:
    """Format event details for the clip listing."""
    if event.spin_degrees > 0:
        return f"  [{event.spin_degrees:.0f}° spin, conf={event.confidence}]"
    if event.crash_severity > 0:
        return f"  [crash, G={event.landing_magnitude}, severity={event.crash_severity}]"
    if event.peak_speed_mph > 0:
        return f"  [peak: {event.peak_speed_mph} mph]"
    if event.airtime_sec > 0:
        quality = f", {event.landing_quality}" if event.landing_quality else ""
        return (f"  [airtime: {event.airtime_sec}s, landing G: {event.landing_magnitude}, "
                f"conf={event.confidence}{quality}]")
    return ""
