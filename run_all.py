"""Batch-process all known GoPro footage directories."""

import logging
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path

from shredfinder.config import get_footage_dirs, load_config
from shredfinder.scanner import scan_footage
from shredfinder.telemetry import extract_telemetry
from shredfinder.detector import detect_events
from shredfinder.clipper import cut_all_clips
from shredfinder.report import write_manifest, write_summary

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger("shredfinder")

# Load config
config = load_config()
det = config["detection"]
output_dir = Path(config["output"]["output_dir"])
max_workers = config["output"]["max_workers"]

# Get footage dirs from config
footage_dirs = get_footage_dirs(config)

if not footage_dirs:
    print("No footage directories available. Create a shredfinder.toml config file.")
    sys.exit(1)

all_events_by_file: dict[Path, list] = {}
all_no_telemetry: list[Path] = []

for folder in footage_dirs:
    try:
        files = scan_footage(folder)
    except FileNotFoundError:
        print(f"SKIP: {folder} (no MP4 files)")
        continue

    print(f"\n{'=' * 60}")
    print(f"PROCESSING: {folder} ({len(files)} files)")
    print(f"{'=' * 60}")

    for f in files:
        mp4_path = f["path"]
        print(f"\n  {f['filename']}  ({f['size_human']})")

        try:
            telemetry = extract_telemetry(mp4_path)
        except Exception as e:
            print(f"    ERROR: {e}")
            all_no_telemetry.append(mp4_path)
            continue

        if not telemetry.has_accl and not telemetry.has_gps:
            print("    No telemetry data.")
            all_no_telemetry.append(mp4_path)
            continue

        parts = []
        if telemetry.has_accl:
            parts.append(f"{len(telemetry.accl_df)} ACCL")
        if telemetry.has_gps:
            parts.append(f"{len(telemetry.gps_df)} GPS")
        print(f"    Telemetry: {', '.join(parts)}")

        events = detect_events(
            telemetry,
            min_airtime_sec=det["min_airtime_sec"],
            g_threshold=det["g_threshold"],
            min_speed_mph=det["min_speed_mph"],
            clip_pad_sec=det["clip_pad_sec"],
            clip_max_sec=det["clip_max_sec"],
            min_landing_g=det["min_landing_g"],
        )

        if events:
            all_events_by_file[mp4_path] = events
            for e in events:
                if "jump" in e.event_type:
                    print(f"    -> JUMP at {e.peak_ts}s  airtime={e.airtime_sec}s  "
                          f"landing_G={e.landing_magnitude}  confidence={e.confidence}")
                if "speed" in e.event_type:
                    print(f"    -> SPEED at {e.peak_ts}s  peak={e.peak_speed_mph} mph")
        else:
            print("    No events.")

# --- Cut all clips ---
total = sum(len(v) for v in all_events_by_file.values())
print(f"\n{'=' * 60}")
print(f"TOTAL: {total} events across {len(all_events_by_file)} files")
print(f"{'=' * 60}")

if total > 0:
    print(f"\nCutting {total} clips to {output_dir}/ (workers={max_workers}) ...")
    results = cut_all_clips(all_events_by_file, output_dir, max_workers=max_workers)

    success = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    print(f"Done: {success} clips cut, {failed} failed.")

    for r in results:
        if not r.success:
            print(f"  FAILED: {r.clip_path.name} -- {r.error}")

    manifest_path = write_manifest(results, output_dir / "manifest.csv")
    print(f"\nManifest: {manifest_path}")

    report = write_summary(results, output_dir / "summary.txt", all_no_telemetry)
    print(f"\n{report}")
else:
    print("\nNo events detected across any folder.")
