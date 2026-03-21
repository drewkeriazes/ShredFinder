"""Scan a directory for GoPro MP4 files."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def scan_footage(input_dir: str | Path) -> list[dict]:
    """Find all MP4 files in input_dir and return metadata about each.

    Returns list of dicts with keys: path, filename, size_bytes, size_human.
    Skips LRV, THM, JPG, and other non-MP4 files.
    """
    input_path = Path(input_dir)
    if not input_path.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    mp4_files = sorted(
        [f for f in input_path.iterdir() if f.suffix.upper() == ".MP4" and f.stat().st_size > 0],
        key=lambda f: f.name,
    )

    if not mp4_files:
        raise FileNotFoundError(f"No MP4 files found in {input_dir}")

    results = []
    for f in mp4_files:
        size = f.stat().st_size
        results.append({
            "path": f,
            "filename": f.name,
            "size_bytes": size,
            "size_human": _format_size(size),
        })

    # Check for GoPro naming convention
    gopro_prefixes = ("GH", "GX", "GP")
    has_gopro_names = any(r["filename"][:2].upper() in gopro_prefixes for r in results)
    if not has_gopro_names:
        logger.warning(
            "No standard GoPro naming (GH/GX prefix) detected. "
            "Files may have been renamed — this is fine, telemetry is embedded in the file."
        )

    logger.info("Found %d MP4 files in %s", len(results), input_dir)
    return results


def _format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
