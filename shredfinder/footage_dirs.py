"""Known GoPro footage directories.

Configure your footage locations in shredfinder.toml instead of editing this file.
See README.md for config file format.
"""

from pathlib import Path

# Add your directories to shredfinder.toml — see config.py and README for format.
# This module is kept for backwards compatibility only.
GOPRO_DIRS: list[dict] = []
EXTERNAL_DIRS: list[dict] = []


def get_available_dirs() -> list[Path]:
    """Return only the footage directories that are currently accessible."""
    return [d["path"] for d in GOPRO_DIRS if d["path"].is_dir()]


def get_all_dirs() -> list[dict]:
    """Return all known directories with an 'available' flag."""
    results = []
    for d in GOPRO_DIRS + EXTERNAL_DIRS:
        results.append({**d, "available": d["path"].is_dir()})
    return results
