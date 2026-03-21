"""Configuration management for ShredFinder.

Loads footage directories and settings from a TOML config file instead of
hard-coding paths. Falls back to defaults if no config exists.

Config file locations (checked in order):
  1. ./shredfinder.toml  (project-local)
  2. ~/.config/shredfinder/config.toml  (user-level, Unix)
  3. ~/shredfinder.toml  (user-level, any OS)
"""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Default config written when `shredfinder init` creates a new file
_DEFAULT_CONFIG = """\
# ShredFinder configuration
# Add your GoPro footage directories below.

[detection]
g_threshold = 4.0         # Freefall threshold (m/s²). Lower = stricter. Gravity ≈ 9.8.
min_airtime_sec = 0.3     # Minimum airtime to count as a jump (seconds).
min_landing_g = 15.0      # Minimum landing spike to confirm a jump (m/s²).
min_speed_mph = 20.0      # Speed threshold for speed events (mph).
clip_pad_sec = 3.0        # Padding before/after each event (seconds).
clip_max_sec = 12.0       # Maximum clip duration (seconds).

[output]
output_dir = "./clips"
max_workers = 4           # Parallel FFmpeg processes for clip cutting.

[[footage]]
path = "."
label = "Current directory"
"""


def _find_config_path() -> Path | None:
    """Find the first existing config file."""
    candidates = [
        Path("./shredfinder.toml"),
        Path.home() / ".config" / "shredfinder" / "config.toml",
        Path.home() / "shredfinder.toml",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def _parse_toml(path: Path) -> dict:
    """Parse a TOML file, using tomllib (3.11+) or falling back to tomli."""
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        try:
            import tomli as tomllib
        except ImportError:
            logger.warning("tomli not installed and Python < 3.11 — using defaults")
            return {}

    with open(path, "rb") as f:
        return tomllib.load(f)


def load_config() -> dict:
    """Load and return the merged configuration.

    Returns a dict with keys: detection, output, footage.
    Missing sections are filled with defaults.
    """
    defaults = {
        "detection": {
            "g_threshold": 4.0,
            "min_airtime_sec": 0.3,
            "min_landing_g": 15.0,
            "min_speed_mph": 20.0,
            "clip_pad_sec": 3.0,
            "clip_max_sec": 12.0,
            "min_spin_degrees": 180.0,
            "spin_axis": "z",
            "crash_g_threshold": 25.0,
            "filter_chairlift": True,
        },
        "output": {
            "output_dir": "./clips",
            "max_workers": 4,
            "organize": True,
        },
        "footage": [],
    }

    config_path = _find_config_path()
    if config_path is None:
        logger.debug("No config file found, using defaults")
        return defaults

    logger.info("Loading config from %s", config_path)
    data = _parse_toml(config_path)

    # Merge detection settings
    if "detection" in data:
        defaults["detection"].update(data["detection"])

    # Merge output settings
    if "output" in data:
        defaults["output"].update(data["output"])

    # Footage dirs from config
    if "footage" in data:
        defaults["footage"] = data["footage"]

    return defaults


def get_footage_dirs(config: dict | None = None) -> list[Path]:
    """Return available footage directories from config.

    Falls back to the legacy footage_dirs module if no config file exists.
    """
    if config is None:
        config = load_config()

    dirs = []
    for entry in config.get("footage", []):
        p = Path(entry["path"])
        if p.is_dir():
            dirs.append(p)
        else:
            logger.debug("Footage dir not available: %s", p)

    return dirs


def init_config(path: Path | None = None) -> Path:
    """Create a default config file. Returns the path written."""
    if path is None:
        path = Path("./shredfinder.toml")

    path.write_text(_DEFAULT_CONFIG)
    logger.info("Created config file: %s", path)
    return path
