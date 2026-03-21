"""Extract GPMF telemetry from GoPro MP4 files using ffprobe/ffmpeg."""

import functools
import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .gpmf_parser import parse_gpmf

logger = logging.getLogger(__name__)


@dataclass
class Segment:
    """A classified time segment of activity."""
    start_ts: float
    end_ts: float
    activity: str  # "riding", "chairlift", "stationary"


@dataclass
class Telemetry:
    """Extracted telemetry data from one MP4 file."""
    source_file: Path
    accl_df: pd.DataFrame  # columns: ts_sec, x, y, z, magnitude
    gps_df: pd.DataFrame   # columns: ts_sec, lat, lon, alt_m, speed_2d_ms, speed_mph
    gyro_df: pd.DataFrame = None  # columns: ts_sec, x, y, z, magnitude (deg/s)
    device_name: str = ""
    has_accl: bool = False
    has_gps: bool = False
    has_gyro: bool = False
    segments: list = None

    def __post_init__(self):
        if self.gyro_df is None:
            self.gyro_df = pd.DataFrame()
        if self.segments is None:
            self.segments = []


@functools.lru_cache(maxsize=1)
def find_ffmpeg() -> str:
    """Find ffmpeg executable, checking common Windows install locations.

    Result is cached after the first successful lookup.
    """
    # Check PATH first
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        logger.debug("Found ffmpeg in PATH: %s", ffmpeg)
        return ffmpeg

    # Check winget install location
    winget_path = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    if winget_path.exists():
        for d in winget_path.iterdir():
            if "FFmpeg" in d.name:
                candidate = d / "ffmpeg-8.1-full_build" / "bin" / "ffmpeg.exe"
                if candidate.exists():
                    logger.debug("Found ffmpeg via WinGet: %s", candidate)
                    return str(candidate)
                # Try any version
                for sub in d.iterdir():
                    candidate = sub / "bin" / "ffmpeg.exe"
                    if candidate.exists():
                        logger.debug("Found ffmpeg via WinGet: %s", candidate)
                        return str(candidate)

    raise FileNotFoundError(
        "ffmpeg not found. Install with: choco install ffmpeg (or winget install Gyan.FFmpeg)"
    )


@functools.lru_cache(maxsize=1)
def find_ffprobe() -> str:
    """Find ffprobe executable. Result is cached after the first successful lookup."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        logger.debug("Found ffprobe in PATH: %s", ffprobe)
        return ffprobe

    # Derive from ffmpeg location
    ffmpeg = find_ffmpeg()
    ffprobe = str(Path(ffmpeg).parent / "ffprobe.exe")
    if Path(ffprobe).exists():
        return ffprobe
    # Try without .exe (Unix)
    ffprobe = str(Path(ffmpeg).parent / "ffprobe")
    if Path(ffprobe).exists():
        return ffprobe

    raise FileNotFoundError("ffprobe not found")


def find_gpmd_stream_index(mp4_path: str | Path) -> int | None:
    """Use ffprobe to find the GPMF data stream index in an MP4 file.

    Returns the stream index (e.g. 3) or None if no GPMF stream found.
    """
    ffprobe = find_ffprobe()
    result = subprocess.run(
        [ffprobe, "-v", "quiet", "-print_format", "json", "-show_streams", str(mp4_path)],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        logger.warning("ffprobe failed for %s: %s", mp4_path, result.stderr[:200])
        return None

    data = json.loads(result.stdout)
    for stream in data.get("streams", []):
        if stream.get("codec_tag_string") == "gpmd":
            logger.debug("Found GPMF stream at index %d in %s", stream["index"], mp4_path)
            return stream["index"]
    logger.debug("No GPMF stream found in %s", mp4_path)
    return None


def extract_gpmf_binary(mp4_path: str | Path, stream_index: int) -> bytes:
    """Extract raw GPMF binary data from an MP4 file using ffmpeg."""
    ffmpeg = find_ffmpeg()

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [ffmpeg, "-y", "-i", str(mp4_path), "-map", f"0:{stream_index}",
             "-f", "rawvideo", tmp_path],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr[:500]}")

        return Path(tmp_path).read_bytes()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def extract_telemetry(mp4_path: str | Path) -> Telemetry:
    """Extract telemetry from a GoPro MP4 file.

    Returns a Telemetry object with accelerometer and GPS DataFrames.
    """
    mp4_path = Path(mp4_path)
    logger.info("Extracting telemetry from %s", mp4_path.name)

    # Find GPMF stream
    stream_idx = find_gpmd_stream_index(mp4_path)
    if stream_idx is None:
        return Telemetry(
            source_file=mp4_path,
            accl_df=pd.DataFrame(),
            gps_df=pd.DataFrame(),
        )

    # Extract and parse
    raw_data = extract_gpmf_binary(mp4_path, stream_idx)
    streams = parse_gpmf(raw_data)

    # Build accelerometer DataFrame
    accl_streams = [s for s in streams if s.fourcc == "ACCL"]
    accl_df = _build_accl_dataframe(accl_streams)

    # Build GPS DataFrame
    gps_streams = [s for s in streams if s.fourcc == "GPS5"]
    gps_df = _build_gps_dataframe(gps_streams)

    # Build gyroscope DataFrame
    gyro_streams = [s for s in streams if s.fourcc == "GYRO"]
    gyro_df = _build_gyro_dataframe(gyro_streams)

    # Extract device name from DVNM entries
    device_name = ""
    dvnm_streams = [s for s in streams if s.fourcc == "DVNM"]
    if dvnm_streams:
        device_name = dvnm_streams[0].name

    has_gps = len(gps_df) > 0 and (gps_df["lat"].abs() > 0.001).any()

    # Classify segments from GPS data
    segments = []
    if has_gps:
        segments = _classify_segments(gps_df)

    logger.info(
        "Telemetry extracted: %d ACCL, %d GPS, %d GYRO samples, %d segments, device=%s",
        len(accl_df), len(gps_df), len(gyro_df), len(segments), device_name or "unknown",
    )

    return Telemetry(
        source_file=mp4_path,
        accl_df=accl_df,
        gps_df=gps_df,
        gyro_df=gyro_df,
        device_name=device_name,
        has_accl=len(accl_df) > 0,
        has_gps=has_gps,
        has_gyro=len(gyro_df) > 0,
        segments=segments,
    )


def _classify_segments(gps_df: pd.DataFrame) -> list[Segment]:
    """Classify GPS data into riding, chairlift, and stationary segments.

    - "chairlift": altitude increasing >0.5 m/s sustained for >60s AND speed 2-10 mph
    - "stationary": speed < 2 mph for >30s
    - "riding": everything else
    """
    if gps_df.empty or len(gps_df) < 10:
        return []

    df = gps_df.copy()
    # Smooth altitude with 10-sample rolling mean
    df["alt_smooth"] = df["alt_m"].rolling(window=10, min_periods=1).mean()
    # Compute altitude rate of change (m/s)
    dt = df["ts_sec"].diff().replace(0, np.nan)
    df["alt_rate"] = df["alt_smooth"].diff() / dt

    ts = df["ts_sec"].values
    speed = df["speed_mph"].values
    alt_rate = df["alt_rate"].fillna(0).values

    segments = []
    n = len(df)
    i = 0

    while i < n:
        # Check for chairlift: alt_rate > 0.5 m/s AND speed 2-10 mph
        if alt_rate[i] > 0.5 and 2.0 <= speed[i] <= 10.0:
            start = i
            while i < n and alt_rate[i] > 0.5 and 2.0 <= speed[i] <= 10.0:
                i += 1
            duration = ts[min(i, n - 1)] - ts[start] if i > start else 0
            if duration > 60.0:
                segments.append(Segment(
                    start_ts=float(ts[start]),
                    end_ts=float(ts[min(i - 1, n - 1)]),
                    activity="chairlift",
                ))
                logger.debug(
                    "Chairlift segment: %.1fs - %.1fs (%.0fs)",
                    ts[start], ts[min(i - 1, n - 1)], duration,
                )
                continue
            # Not long enough, fall through
            i = start

        # Check for stationary: speed < 2 mph
        if speed[i] < 2.0:
            start = i
            while i < n and speed[i] < 2.0:
                i += 1
            duration = ts[min(i, n - 1)] - ts[start] if i > start else 0
            if duration > 30.0:
                segments.append(Segment(
                    start_ts=float(ts[start]),
                    end_ts=float(ts[min(i - 1, n - 1)]),
                    activity="stationary",
                ))
                logger.debug(
                    "Stationary segment: %.1fs - %.1fs (%.0fs)",
                    ts[start], ts[min(i - 1, n - 1)], duration,
                )
                continue
            # Not long enough, fall through
            i = start

        # Riding — advance one sample
        i += 1

    # Fill gaps as "riding" segments (optional, but useful for completeness)
    return segments


def _build_accl_dataframe(accl_streams: list) -> pd.DataFrame:
    """Convert ACCL stream blocks into a timestamped DataFrame."""
    if not accl_streams:
        return pd.DataFrame()

    all_samples = []
    total_samples = sum(len(s.samples) for s in accl_streams)
    if total_samples == 0:
        return pd.DataFrame()

    # Estimate total duration from number of blocks (1 block ≈ 1 second)
    # Each block has ~200 samples at 200Hz
    for block_idx, stream in enumerate(accl_streams):
        samples_in_block = len(stream.samples)
        for i, sample in enumerate(stream.samples):
            # Timestamp: distribute samples evenly across blocks
            ts = block_idx + (i / samples_in_block)
            all_samples.append({
                "ts_sec": ts,
                "x": sample[0] if len(sample) > 0 else 0,
                "y": sample[1] if len(sample) > 1 else 0,
                "z": sample[2] if len(sample) > 2 else 0,
            })

    df = pd.DataFrame(all_samples)
    df["magnitude"] = np.sqrt(df["x"]**2 + df["y"]**2 + df["z"]**2)
    return df


def _build_gps_dataframe(gps_streams: list) -> pd.DataFrame:
    """Convert GPS5 stream blocks into a timestamped DataFrame."""
    if not gps_streams:
        return pd.DataFrame()

    all_samples = []
    for block_idx, stream in enumerate(gps_streams):
        samples_in_block = len(stream.samples)
        for i, sample in enumerate(stream.samples):
            ts = block_idx + (i / max(samples_in_block, 1))
            speed_2d = sample[3] if len(sample) > 3 else 0
            all_samples.append({
                "ts_sec": ts,
                "lat": sample[0] if len(sample) > 0 else 0,
                "lon": sample[1] if len(sample) > 1 else 0,
                "alt_m": sample[2] if len(sample) > 2 else 0,
                "speed_2d_ms": speed_2d,
                "speed_mph": speed_2d * 2.237,
            })

    return pd.DataFrame(all_samples)


def _build_gyro_dataframe(gyro_streams: list) -> pd.DataFrame:
    """Convert GYRO stream blocks into a timestamped DataFrame.

    GYRO data is angular velocity in deg/s (after SCAL is applied by gpmf_parser).
    Samples are typically at 200Hz, same as ACCL.
    """
    if not gyro_streams:
        return pd.DataFrame()

    all_samples = []
    total_samples = sum(len(s.samples) for s in gyro_streams)
    if total_samples == 0:
        return pd.DataFrame()

    for block_idx, stream in enumerate(gyro_streams):
        samples_in_block = len(stream.samples)
        for i, sample in enumerate(stream.samples):
            ts = block_idx + (i / samples_in_block)
            all_samples.append({
                "ts_sec": ts,
                "x": sample[0] if len(sample) > 0 else 0,
                "y": sample[1] if len(sample) > 1 else 0,
                "z": sample[2] if len(sample) > 2 else 0,
            })

    df = pd.DataFrame(all_samples)
    df["magnitude"] = np.sqrt(df["x"]**2 + df["y"]**2 + df["z"]**2)
    return df
