"""Generate auto-highlight reels from ranked events."""

import logging
import subprocess
import tempfile
from pathlib import Path

from .clipper import ClipResult, cut_clip
from .detector import Event
from .telemetry import find_ffmpeg

logger = logging.getLogger(__name__)


def rank_events(events_by_file: dict[Path, list[Event]]) -> list[tuple[Path, Event]]:
    """Rank all events across all files by quality/interest.

    Returns a list of (source_file, event) tuples sorted by rank score (best first).

    Scoring:
      - Base: event confidence score
      - Spin bonus: +0.3 for spins (rarer, more interesting)
      - Spin degree bonus: +0.1 per 180 degrees beyond 180
      - Airtime bonus: +0.2 for >0.5s airtime
      - Stomped bonus: +0.15 for clean landings
      - Crash penalty: -0.1 (still interesting, but lower priority)
      - Variety: handled by caller (select mix of types)
    """
    scored = []

    for source_file, events in events_by_file.items():
        for event in events:
            score = event.confidence

            # Spin bonus
            if event.spin_degrees >= 180:
                score += 0.3
                score += 0.1 * ((event.spin_degrees - 180) / 180)

            # Airtime bonus
            if event.airtime_sec > 0.5:
                score += 0.2

            # Landing quality
            if event.landing_quality == "stomped":
                score += 0.15
            elif event.landing_quality == "crash":
                score -= 0.1

            # Speed bonus for very fast moments
            if event.peak_speed_mph > 30:
                score += 0.1

            scored.append((source_file, event, score))

    # Sort by score descending
    scored.sort(key=lambda x: x[2], reverse=True)

    return [(src, evt) for src, evt, _ in scored]


def select_top_n(
    ranked: list[tuple[Path, Event]],
    top_n: int = 10,
    variety: bool = True,
) -> list[tuple[Path, Event]]:
    """Select top N events with variety (mix of event types).

    When variety=True, ensures no more than 60% of clips are the same type.
    """
    if not variety or len(ranked) <= top_n:
        return ranked[:top_n]

    selected = []
    type_counts: dict[str, int] = {}
    max_per_type = max(2, int(top_n * 0.6))

    for src, evt in ranked:
        if len(selected) >= top_n:
            break

        primary_type = evt.event_type.split("+")[0]
        if type_counts.get(primary_type, 0) >= max_per_type:
            continue

        selected.append((src, evt))
        type_counts[primary_type] = type_counts.get(primary_type, 0) + 1

    # If we didn't fill top_n (due to variety constraint), add more from the ranked list
    if len(selected) < top_n:
        for src, evt in ranked:
            if len(selected) >= top_n:
                break
            if (src, evt) not in selected:
                selected.append((src, evt))

    return selected


def generate_highlight_reel(
    events_by_file: dict[Path, list[Event]],
    output_dir: Path,
    top_n: int = 10,
    reel_name: str = "highlight_reel.mp4",
) -> Path | None:
    """Generate a highlight reel from the top-ranked events.

    Cuts individual clips then concatenates them via FFmpeg concat demuxer
    (stream copy, no re-encoding if all clips share codec/resolution).

    Returns the path to the reel, or None if generation failed.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ranked = rank_events(events_by_file)
    selected = select_top_n(ranked, top_n)

    if not selected:
        logger.warning("No events to build highlight reel")
        return None

    logger.info("Building highlight reel from top %d events", len(selected))

    # Cut individual clips to a temp directory
    reel_clips_dir = output_dir / "_reel_clips"
    reel_clips_dir.mkdir(parents=True, exist_ok=True)

    clip_paths = []
    for i, (source, event) in enumerate(selected):
        result = cut_clip(source, event, reel_clips_dir, i + 1, organize=False)
        if result.success:
            clip_paths.append(result.clip_path)
        else:
            logger.warning("Failed to cut reel clip %d: %s", i + 1, result.error)

    if not clip_paths:
        logger.error("No clips were cut for the highlight reel")
        return None

    # Create concat list file
    reel_path = output_dir / reel_name
    concat_file = reel_clips_dir / "concat.txt"
    with open(concat_file, "w") as f:
        for clip in clip_paths:
            # FFmpeg concat requires forward slashes and escaped single quotes
            safe_path = str(clip.resolve()).replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

    # Concatenate via FFmpeg
    ffmpeg = find_ffmpeg()
    try:
        result = subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0",
             "-i", str(concat_file), "-c", "copy", str(reel_path)],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            logger.error("FFmpeg concat failed: %s", result.stderr[:500])
            return None

        if reel_path.exists() and reel_path.stat().st_size > 0:
            logger.info("Highlight reel generated: %s (%d clips)", reel_path, len(clip_paths))

            # Clean up temp clips
            for clip in clip_paths:
                clip.unlink(missing_ok=True)
            concat_file.unlink(missing_ok=True)
            try:
                reel_clips_dir.rmdir()
            except OSError:
                pass  # Not empty, leave it

            return reel_path

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg concat timed out")
    except Exception as e:
        logger.error("Reel generation failed: %s", e)

    return None
