"""FFmpeg command builder and runner.

Provides helpers for proxy generation, thumbnail extraction, video info
extraction, and timeline rendering. All commands run as async subprocesses.
"""

import asyncio
import json
import logging
import re
from pathlib import Path

from server.config import settings

logger = logging.getLogger(__name__)


async def get_video_info(file_path: Path) -> dict:
    """Extract video metadata using ffprobe.

    Returns dict with keys: duration, width, height, fps, codec, audio_codec.
    """
    cmd = [
        settings.FFPROBE_PATH,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {stderr.decode()}")

    data = json.loads(stdout.decode())

    # Find the video stream
    video_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if video_stream is None:
        raise RuntimeError(f"No video stream found in {file_path}")

    # Parse frame rate (e.g. "60000/1001" or "30/1")
    fps = 0.0
    r_frame_rate = video_stream.get("r_frame_rate", "0/1")
    if "/" in r_frame_rate:
        num, den = r_frame_rate.split("/")
        fps = float(num) / float(den) if float(den) != 0 else 0.0
    else:
        fps = float(r_frame_rate)

    fmt = data.get("format", {})

    return {
        "duration": float(fmt.get("duration", 0)),
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "fps": round(fps, 3),
        "codec": video_stream.get("codec_name", ""),
        "audio_codec": next(
            (s.get("codec_name", "") for s in data.get("streams", [])
             if s.get("codec_type") == "audio"),
            "",
        ),
    }


async def generate_proxy(input_path: Path, output_path: Path,
                         height: int = 720, crf: int = 23,
                         progress_callback=None) -> Path:
    """Generate a lower-resolution proxy video (H.264, AAC).

    Args:
        input_path: Path to the source video.
        output_path: Where to write the proxy.
        height: Target height in pixels (width auto-scaled).
        crf: Constant rate factor (lower = higher quality).
        progress_callback: Optional async callable(percent: float).

    Returns:
        The output_path on success.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Get duration for progress calculation
    duration = 0.0
    try:
        info = await get_video_info(input_path)
        duration = info["duration"]
    except Exception:
        pass

    cmd = [
        settings.FFMPEG_PATH,
        "-y",
        "-i", str(input_path),
        "-vf", f"scale=-2:{height}",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", str(crf),
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        str(output_path),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    if progress_callback and duration > 0:
        await _parse_progress(proc, duration, progress_callback)

    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg proxy generation failed: {stderr.decode()[-500:]}")

    return output_path


async def extract_thumbnail(input_path: Path, output_path: Path,
                            timestamp: float = 2.0) -> Path:
    """Extract a single frame as a JPEG thumbnail.

    Args:
        input_path: Path to the source video.
        output_path: Where to write the thumbnail JPEG.
        timestamp: Time offset in seconds for the frame.

    Returns:
        The output_path on success.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        settings.FFMPEG_PATH,
        "-y",
        "-ss", str(timestamp),
        "-i", str(input_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(output_path),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg thumbnail extraction failed: {stderr.decode()[-500:]}")

    return output_path


async def render_concat(segments: list[dict], output_path: Path,
                        transition: str = "none", transition_duration: float = 0.5,
                        progress_callback=None) -> Path:
    """Render a timeline by concatenating video segments.

    Each segment dict has keys: path (str), start (float), end (float).
    Supports transitions: "none", "crossfade", "fade".

    Args:
        segments: Ordered list of segment dicts.
        output_path: Where to write the rendered output.
        transition: Transition type between segments.
        transition_duration: Duration of each transition in seconds.
        progress_callback: Optional async callable(percent: float).

    Returns:
        The output_path on success.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not segments:
        raise ValueError("No segments provided for rendering")

    if transition == "none" or len(segments) == 1:
        return await _render_simple_concat(segments, output_path, progress_callback)
    elif transition in ("crossfade", "fade"):
        return await _render_with_transitions(
            segments, output_path, transition, transition_duration, progress_callback
        )
    else:
        raise ValueError(f"Unsupported transition type: {transition}")


async def _render_simple_concat(segments: list[dict], output_path: Path,
                                progress_callback=None) -> Path:
    """Concatenate segments without transitions using the concat demuxer."""
    import tempfile

    # Build a concat file list with trim filters
    # We need to use the filter_complex approach for trimming
    filter_parts = []
    inputs = []
    total_duration = 0.0

    for i, seg in enumerate(segments):
        inputs.extend(["-i", seg["path"]])
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        duration = end - start
        total_duration += duration
        filter_parts.append(
            f"[{i}:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}];"
            f"[{i}:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]"
        )

    n = len(segments)
    v_concat = "".join(f"[v{i}]" for i in range(n))
    a_concat = "".join(f"[a{i}]" for i in range(n))
    filter_parts.append(f"{v_concat}concat=n={n}:v=1:a=0[outv];{a_concat}concat=n={n}:v=0:a=1[outa]")

    filter_complex = ";".join(filter_parts)

    cmd = [
        settings.FFMPEG_PATH, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        str(output_path),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    if progress_callback and total_duration > 0:
        await _parse_progress(proc, total_duration, progress_callback)

    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg concat render failed: {stderr.decode()[-500:]}")

    return output_path


async def _render_with_transitions(segments: list[dict], output_path: Path,
                                   transition: str, transition_duration: float,
                                   progress_callback=None) -> Path:
    """Render segments with crossfade/fade transitions using xfade filter."""
    inputs = []
    filter_parts = []
    total_duration = 0.0

    for i, seg in enumerate(segments):
        inputs.extend(["-i", seg["path"]])
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        duration = end - start
        total_duration += duration
        filter_parts.append(
            f"[{i}:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}];"
            f"[{i}:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]"
        )

    # Build xfade chain for video and acrossfade for audio
    n = len(segments)
    if n == 1:
        filter_parts.append("[v0]null[outv];[a0]anull[outa]")
    else:
        # Chain xfade filters pairwise
        xfade_transition = "fade" if transition == "fade" else "fade"
        durations = []
        for seg in segments:
            durations.append(seg.get("end", 0) - seg.get("start", 0))

        prev_v = "v0"
        prev_a = "a0"
        offset = durations[0] - transition_duration

        for i in range(1, n):
            out_v = "outv" if i == n - 1 else f"xv{i}"
            out_a = "outa" if i == n - 1 else f"xa{i}"

            filter_parts.append(
                f"[{prev_v}][v{i}]xfade=transition={xfade_transition}"
                f":duration={transition_duration}:offset={max(0, offset)}[{out_v}]"
            )
            filter_parts.append(
                f"[{prev_a}][a{i}]acrossfade=d={transition_duration}[{out_a}]"
            )

            prev_v = out_v
            prev_a = out_a
            offset += durations[i] - transition_duration

    filter_complex = ";".join(filter_parts)

    cmd = [
        settings.FFMPEG_PATH, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        str(output_path),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    if progress_callback and total_duration > 0:
        await _parse_progress(proc, total_duration, progress_callback)

    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg transition render failed: {stderr.decode()[-500:]}")

    return output_path


async def _parse_progress(proc: asyncio.subprocess.Process,
                          total_duration: float,
                          callback) -> None:
    """Parse FFmpeg progress output and call the callback with percent complete."""
    time_pattern = re.compile(r"out_time_us=(\d+)")

    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        decoded = line.decode("utf-8", errors="replace").strip()
        match = time_pattern.search(decoded)
        if match:
            current_us = int(match.group(1))
            current_sec = current_us / 1_000_000
            percent = min(100.0, (current_sec / total_duration) * 100)
            try:
                await callback(percent)
            except Exception:
                pass
