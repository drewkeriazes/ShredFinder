"""Cut video clips from source MP4 files using FFmpeg."""

import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .detector import Event
from .telemetry import find_ffmpeg

logger = logging.getLogger(__name__)


@dataclass
class ClipResult:
    """Result of a single clip cut operation."""
    clip_path: Path
    source_file: Path
    event: Event
    success: bool
    error: str = ""


def cut_clip(
    source_file: str | Path,
    event: Event,
    output_dir: str | Path,
    clip_index: int,
    organize: bool = True,
) -> ClipResult:
    """Cut a single clip from source video around a detected event.

    Uses FFmpeg stream copy (no re-encoding) for speed.

    When organize=True, clips are placed into subfolders:
      output_dir/
        jumps/
        speed/
        spins/
        crashes/
        by_source/
          GX010185/
    """
    source_file = Path(source_file)
    output_dir = Path(output_dir)

    # Format timestamp for filename: 01m23s
    total_sec = int(event.clip_start)
    minutes = total_sec // 60
    seconds = total_sec % 60
    ts_fmt = f"{minutes:02d}m{seconds:02d}s"

    base = source_file.stem

    # Build descriptive filename
    name_parts = [event.event_type, f"{clip_index:03d}", base, ts_fmt]
    if event.spin_degrees > 0:
        name_parts.insert(1, f"{int(event.spin_degrees)}deg")
    if event.landing_quality:
        name_parts.insert(1, event.landing_quality)
    clip_name = f"{'_'.join(name_parts)}.mp4"

    # Determine output subdirectory based on event type
    if organize:
        # Primary type folder (use base type, not compound like "jump+speed")
        primary_type = event.event_type.split("+")[0]
        type_folder_map = {
            "jump": "jumps", "speed": "speed", "spin": "spins", "crash": "crashes",
        }
        type_folder = type_folder_map.get(primary_type, "other")
        type_dir = output_dir / type_folder
        type_dir.mkdir(parents=True, exist_ok=True)

        # Also create a symlink/copy in by_source/<source_stem>/
        source_dir = output_dir / "by_source" / base
        source_dir.mkdir(parents=True, exist_ok=True)

        clip_path = type_dir / clip_name

        # We'll create a relative symlink from by_source to the type folder
        # (done after cutting below)
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        clip_path = output_dir / clip_name

    ffmpeg = find_ffmpeg()

    try:
        result = subprocess.run(
            [
                ffmpeg, "-y",
                "-ss", str(event.clip_start),
                "-i", str(source_file),
                "-t", str(event.clip_duration),
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                str(clip_path),
            ],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            logger.error("FFmpeg failed for %s: %s", clip_name, result.stderr[:200])
            return ClipResult(
                clip_path=clip_path,
                source_file=source_file,
                event=event,
                success=False,
                error=result.stderr[:500],
            )

        # Verify output exists and is non-empty
        if not clip_path.exists() or clip_path.stat().st_size == 0:
            logger.error("Output file is empty or missing: %s", clip_path)
            return ClipResult(
                clip_path=clip_path,
                source_file=source_file,
                event=event,
                success=False,
                error="Output file is empty or missing",
            )

        logger.info("Cut clip %s (%.1fs)", clip_name, event.clip_duration)

        # Create a reference in by_source/ folder
        if organize:
            source_ref = source_dir / clip_name
            if not source_ref.exists():
                try:
                    # Use relative symlink if possible, otherwise copy reference
                    rel_target = os.path.relpath(clip_path, source_ref.parent)
                    source_ref.symlink_to(rel_target)
                except OSError:
                    # Symlinks may fail on Windows without admin — just skip
                    pass

        return ClipResult(
            clip_path=clip_path,
            source_file=source_file,
            event=event,
            success=True,
        )

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timed out for %s", clip_name)
        return ClipResult(
            clip_path=clip_path,
            source_file=source_file,
            event=event,
            success=False,
            error="FFmpeg timed out after 120s",
        )
    except FileNotFoundError:
        logger.error("FFmpeg not found")
        return ClipResult(
            clip_path=clip_path,
            source_file=source_file,
            event=event,
            success=False,
            error="FFmpeg not found",
        )


def cut_all_clips(
    events_by_file: dict[Path, list[Event]],
    output_dir: str | Path,
    max_workers: int | None = None,
    organize: bool = True,
) -> list[ClipResult]:
    """Cut clips for all detected events across all files.

    Uses ThreadPoolExecutor for parallel clip cutting. Each clip reads from
    a different time offset (or different source file), so parallel ffmpeg
    processes don't contend on the same I/O.

    Args:
        events_by_file: Dict mapping source MP4 path to its detected events.
        output_dir: Directory to write clips into.
        max_workers: Max parallel ffmpeg processes. Defaults to min(cpu_count, 4).

    Returns:
        List of ClipResult objects in submission order.
    """
    output_dir = Path(output_dir)

    if max_workers is None:
        max_workers = min(os.cpu_count() or 2, 4)

    # Build work items with stable indices
    work_items = []
    clip_index = 1
    for source_file, events in sorted(events_by_file.items()):
        for event in events:
            work_items.append((source_file, event, output_dir, clip_index, organize))
            clip_index += 1

    if not work_items:
        return []

    logger.info("Cutting %d clips with %d workers", len(work_items), max_workers)

    results: list[ClipResult | None] = [None] * len(work_items)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {}
        for idx, (source, event, out_dir, ci, org) in enumerate(work_items):
            future = executor.submit(cut_clip, source, event, out_dir, ci, org)
            future_to_idx[future] = idx

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                source, event, _, ci, _ = work_items[idx]
                logger.error("Unexpected error cutting clip %d: %s", ci, e)
                results[idx] = ClipResult(
                    clip_path=Path(output_dir) / f"error_{ci:03d}.mp4",
                    source_file=source,
                    event=event,
                    success=False,
                    error=str(e),
                )

    return [r for r in results if r is not None]
