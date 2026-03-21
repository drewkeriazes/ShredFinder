"""ShredFinder CLI — detect and cut highlight clips from GoPro footage."""

import logging
import sys
from pathlib import Path

import click

from .clipper import cut_all_clips
from .config import load_config
from .detector import detect_events
from .report import write_manifest, write_summary
from .scanner import scan_footage
from .telemetry import Telemetry, extract_telemetry


def _setup_logging(verbose: bool) -> None:
    """Configure structured logging for ShredFinder."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%H:%M:%S"
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, stream=sys.stderr)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


@click.command()
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False))
@click.option("-o", "--output-dir", default=None, help="Output directory for clips. Default: ./clips")
@click.option("--min-speed-mph", default=None, type=float, help="Speed threshold for speed events (mph).")
@click.option("--min-airtime-sec", default=None, type=float, help="Minimum airtime for jump detection (seconds).")
@click.option("--g-threshold", default=None, type=float,
              help="Freefall threshold (m/s²). Lower = stricter. Default 4.0.")
@click.option("--min-landing-g", default=None, type=float,
              help="Minimum landing spike to confirm a jump (m/s²). Default 15.0.")
@click.option("--min-spin-degrees", default=None, type=float,
              help="Minimum rotation to detect a spin (degrees). Default 180.")
@click.option("--spin-axis", default=None, type=click.Choice(["x", "y", "z"]),
              help="Gyro axis for yaw/spin detection. Default z.")
@click.option("--crash-g-threshold", default=None, type=float,
              help="G-force spike threshold for crash detection (m/s²). Default 25.0.")
@click.option("--clip-pad-sec", default=None, type=float, help="Seconds of padding before/after each event.")
@click.option("--clip-max-sec", default=None, type=float, help="Maximum clip duration (seconds).")
@click.option("--max-workers", default=None, type=int, help="Parallel FFmpeg processes. Default: min(cpus, 4).")
@click.option("--no-organize", is_flag=True, help="Don't organize clips into subfolders by type.")
@click.option("--no-chairlift-filter", is_flag=True, help="Disable chairlift/stationary segment filtering.")
@click.option("--export-edl", is_flag=True, help="Export events as CMX 3600 EDL file.")
@click.option("--export-gpx", is_flag=True, help="Export GPS tracks and events as GPX file.")
@click.option("--reel", is_flag=True, help="Generate auto-highlight reel from top events.")
@click.option("--top-n", default=10, type=int, help="Number of clips in highlight reel. Default 10.")
@click.option("--stats", is_flag=True, help="Generate season stats summary.")
@click.option("--trail-map", is_flag=True, help="Generate interactive HTML trail map.")
@click.option("--dry-run", is_flag=True, help="Detect events but don't cut clips.")
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
def cli(
    input_dir: str,
    output_dir: str | None,
    min_speed_mph: float | None,
    min_airtime_sec: float | None,
    g_threshold: float | None,
    min_landing_g: float | None,
    min_spin_degrees: float | None,
    spin_axis: str | None,
    crash_g_threshold: float | None,
    clip_pad_sec: float | None,
    clip_max_sec: float | None,
    max_workers: int | None,
    no_organize: bool,
    no_chairlift_filter: bool,
    export_edl: bool,
    export_gpx: bool,
    reel: bool,
    top_n: int,
    stats: bool,
    trail_map: bool,
    dry_run: bool,
    verbose: bool,
):
    """Detect highlight moments in GoPro snowboard footage and cut clips.

    INPUT_DIR is the folder containing raw GoPro .MP4 files.

    Output clips are organized into subfolders by event type:

    \b
      clips/
        jumps/       Jump events (with landing quality labels)
        speed/       Speed peak events
        spins/       Spin/rotation events (with degree labels)
        crashes/     Crash/bail events
        by_source/   Clips grouped by source MP4 file
    """
    _setup_logging(verbose)
    logger = logging.getLogger("shredfinder")

    # Load config file defaults, then override with CLI flags
    config = load_config()
    det = config["detection"]
    out = config["output"]

    g_threshold = g_threshold if g_threshold is not None else det["g_threshold"]
    min_airtime_sec = min_airtime_sec if min_airtime_sec is not None else det["min_airtime_sec"]
    min_landing_g = min_landing_g if min_landing_g is not None else det["min_landing_g"]
    min_speed_mph = min_speed_mph if min_speed_mph is not None else det["min_speed_mph"]
    min_spin_degrees = min_spin_degrees if min_spin_degrees is not None else det["min_spin_degrees"]
    spin_axis = spin_axis if spin_axis is not None else det["spin_axis"]
    crash_g_threshold = crash_g_threshold if crash_g_threshold is not None else det["crash_g_threshold"]
    clip_pad_sec = clip_pad_sec if clip_pad_sec is not None else det["clip_pad_sec"]
    clip_max_sec = clip_max_sec if clip_max_sec is not None else det["clip_max_sec"]
    max_workers = max_workers if max_workers is not None else out["max_workers"]
    filter_chairlift = (not no_chairlift_filter) and det.get("filter_chairlift", True)
    organize = not no_organize and out.get("organize", True)
    output_dir = output_dir if output_dir is not None else out["output_dir"]
    output_path = Path(output_dir)

    # --- Scan footage ---
    click.echo(f"Scanning {input_dir} for MP4 files...")
    try:
        files = scan_footage(input_dir)
    except FileNotFoundError as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)

    click.echo(f"Found {len(files)} MP4 files:")
    for f in files:
        click.echo(f"  {f['filename']}  ({f['size_human']})")

    click.echo(f"\nDetection: g={g_threshold}, airtime={min_airtime_sec}s, "
               f"landing_g={min_landing_g}, speed={min_speed_mph}mph, "
               f"spin={min_spin_degrees}deg/{spin_axis}, crash_g={crash_g_threshold}")

    # --- Extract telemetry and detect events ---
    events_by_file: dict[Path, list] = {}
    telemetry_by_file: dict[Path, object] = {}
    no_telemetry: list[Path] = []
    total_events = 0

    with click.progressbar(files, label="Processing files", item_show_func=lambda f: f["filename"] if f else "") as bar:
        for f in bar:
            mp4_path = f["path"]

            try:
                telemetry = extract_telemetry(mp4_path)
            except Exception as e:
                logger.error("Error extracting telemetry from %s: %s", f["filename"], e)
                no_telemetry.append(mp4_path)
                continue

            if not telemetry.has_accl and not telemetry.has_gps:
                logger.debug("No telemetry in %s", f["filename"])
                no_telemetry.append(mp4_path)
                continue

            telemetry_by_file[mp4_path] = telemetry

            events = detect_events(
                telemetry,
                min_airtime_sec=min_airtime_sec,
                g_threshold=g_threshold,
                min_speed_mph=min_speed_mph,
                clip_pad_sec=clip_pad_sec,
                clip_max_sec=clip_max_sec,
                min_landing_g=min_landing_g,
                min_spin_degrees=min_spin_degrees,
                spin_axis=spin_axis,
                crash_g_threshold=crash_g_threshold,
                filter_chairlift=filter_chairlift,
            )

            if events:
                events_by_file[mp4_path] = events
                total_events += len(events)

    # --- Print detected events ---
    click.echo("")
    for mp4_path, events in events_by_file.items():
        click.echo(f"\n{mp4_path.name}:")
        for e in events:
            _print_event(e)

    # --- Summary of detection ---
    click.echo(f"\n{'=' * 40}")
    click.echo(f"Detection complete: {total_events} events across {len(events_by_file)} files")

    if no_telemetry:
        click.echo(f"Files with no telemetry: {len(no_telemetry)}")
        for p in no_telemetry:
            click.echo(f"  {p.name}")

    if total_events == 0:
        click.echo(
            "\nNo events detected. Try:\n"
            "  --g-threshold 6.0  (less strict freefall detection)\n"
            "  --min-landing-g 10  (lower landing impact threshold)\n"
            "  --min-speed-mph 10  (lower speed threshold)\n"
            "  --min-airtime-sec 0.2  (shorter jumps)\n"
            "  --min-spin-degrees 90  (detect smaller rotations)"
        )
        if not dry_run:
            write_summary([], output_path / "summary.txt", no_telemetry)
        sys.exit(0)

    # --- Exports available even in dry-run ---
    if export_edl:
        from .edl_export import write_edl
        edl_path = write_edl(events_by_file, output_path / "timeline.edl")
        click.echo(f"EDL: {edl_path}")

    if export_gpx:
        from .gpx_export import write_gpx
        all_telemetry = list(telemetry_by_file.values())
        all_events = [e for evts in events_by_file.values() for e in evts]
        gpx_path = write_gpx(all_telemetry, all_events, output_path / "tracks.gpx")
        click.echo(f"GPX: {gpx_path}")

    if trail_map:
        from .trail_map import write_trail_map
        map_path = write_trail_map(telemetry_by_file, events_by_file, output_path / "trail_map.html")
        if map_path:
            click.echo(f"Trail map: {map_path}")

    if stats:
        from .session import group_into_sessions
        from .stats import compute_season_stats, write_stats_text, write_stats_json

        gps_centroids = {}
        for path, tel in telemetry_by_file.items():
            if tel.has_gps and not tel.gps_df.empty:
                valid = tel.gps_df[(tel.gps_df["lat"].abs() > 0.001)]
                if not valid.empty:
                    gps_centroids[path] = (float(valid["lat"].mean()), float(valid["lon"].mean()))

        sessions = group_into_sessions(events_by_file, gps_centroids)
        season = compute_season_stats(sessions, telemetry_by_file)
        stats_text = write_stats_text(season, output_path / "stats.txt")
        write_stats_json(season, output_path / "stats.json")
        click.echo(f"\n{stats_text}")

    if dry_run:
        click.echo("\n--dry-run: skipping clip cutting.")
        return

    # --- Cut clips ---
    org_label = ", organized by type" if organize else ""
    click.echo(f"\nCutting {total_events} clips to {output_dir}/ (workers={max_workers}{org_label}) ...")
    results = cut_all_clips(events_by_file, output_path, max_workers=max_workers, organize=organize)

    success_count = sum(1 for r in results if r.success)
    fail_count = sum(1 for r in results if not r.success)
    click.echo(f"Done: {success_count} clips cut, {fail_count} failed.")

    for r in results:
        if not r.success:
            click.echo(f"  FAILED: {r.clip_path.name} — {r.error}", err=True)

    # --- Highlight reel ---
    if reel:
        from .reel import generate_highlight_reel
        reel_path = generate_highlight_reel(events_by_file, output_path, top_n=top_n)
        if reel_path:
            click.echo(f"\nHighlight reel: {reel_path}")

    # --- Reports ---
    manifest_path = write_manifest(results, output_path / "manifest.csv")
    click.echo(f"\nManifest: {manifest_path}")

    summary = write_summary(results, output_path / "summary.txt", no_telemetry)
    click.echo(f"\n{summary}")


def _print_event(e) -> None:
    """Print a single detected event to stdout."""
    if "jump" in e.event_type:
        quality = f"  landing={e.landing_quality}" if e.landing_quality else ""
        click.echo(f"  JUMP at {e.peak_ts}s  airtime={e.airtime_sec}s  "
                   f"landing_G={e.landing_magnitude}  conf={e.confidence}{quality}")
    if "speed" in e.event_type:
        click.echo(f"  SPEED at {e.peak_ts}s  peak={e.peak_speed_mph} mph")
    if "spin" in e.event_type:
        click.echo(f"  SPIN at {e.peak_ts}s  {e.spin_degrees:.0f}deg on {e.spin_axis}-axis  "
                   f"conf={e.confidence}")
    if "crash" in e.event_type:
        click.echo(f"  CRASH at {e.peak_ts}s  G={e.landing_magnitude}  severity={e.crash_severity}")
