"""FFmpeg command builder and runner.

Uses subprocess.run in a thread pool for Windows compatibility.
asyncio.create_subprocess_exec doesn't work reliably on Windows
in FastAPI background tasks.
"""

import asyncio
import json
import logging
import subprocess
from pathlib import Path

from server.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Frontend transition name → FFmpeg xfade transition name
# ---------------------------------------------------------------------------
TRANSITION_MAP: dict[str, str] = {
    "crossfade": "fade",
    "fade": "fade",
    "fade-from-black": "fadegrays",
    "wipe-left": "wipeleft",
    "wipe-right": "wiperight",
    "slide-left": "slideleft",
    "slide-right": "slideright",
    "dissolve": "dissolve",
    "none": "fade",  # fallback
}


def _map_transition(frontend_name: str) -> str:
    """Map a frontend transition name to an FFmpeg xfade transition name."""
    return TRANSITION_MAP.get(frontend_name, "fade")


def _run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command synchronously, capturing output."""
    logger.debug("Running: %s", " ".join(cmd))
    return subprocess.run(
        cmd, capture_output=True, check=check,
    )


async def _run_cmd_async(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run a command in a thread pool so we don't block the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_cmd, cmd, False)


async def get_video_info(file_path: Path) -> dict:
    """Extract video metadata using ffprobe."""
    cmd = [
        settings.FFPROBE_PATH,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]
    result = await _run_cmd_async(cmd)

    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr.decode()}")

    data = json.loads(result.stdout.decode())

    video_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if video_stream is None:
        raise RuntimeError(f"No video stream found in {file_path}")

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
    """Generate a lower-resolution proxy video (H.264, AAC)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

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
        str(output_path),
    ]

    result = await _run_cmd_async(cmd)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg proxy generation failed: {result.stderr.decode()[-500:]}")

    return output_path


async def extract_thumbnail(input_path: Path, output_path: Path,
                            timestamp: float = 2.0) -> Path:
    """Extract a single frame as a JPEG thumbnail."""
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

    result = await _run_cmd_async(cmd)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg thumbnail extraction failed: {result.stderr.decode()[-500:]}")

    return output_path


def _build_segment_filters(index: int, seg: dict) -> tuple[str, str]:
    """Build the trim + optional speed/volume filters for a single segment.

    Returns (video_filter_chain, audio_filter_chain) strings that produce
    labels [v{index}] and [a{index}].
    """
    start = seg.get("start", 0)
    end = seg.get("end", 0)
    speed = seg.get("speed", 1)
    volume = seg.get("volume", 100)

    # -- Video chain --
    v_filters = [f"trim=start={start}:end={end}", "setpts=PTS-STARTPTS"]
    if speed != 1 and speed > 0:
        # setpts adjusts playback speed; < 1 = slower, > 1 = faster
        v_filters.append(f"setpts={1/speed}*PTS")

    v_chain = f"[{index}:v]" + ",".join(v_filters) + f"[v{index}]"

    # -- Audio chain --
    a_filters = [f"atrim=start={start}:end={end}", "asetpts=PTS-STARTPTS"]
    if speed != 1 and speed > 0:
        a_filters.append(f"atempo={speed}")
    if volume == 0:
        a_filters.append("volume=0")
    elif volume != 100:
        a_filters.append(f"volume={volume / 100:.2f}")

    a_chain = f"[{index}:a]" + ",".join(a_filters) + f"[a{index}]"

    return v_chain, a_chain


async def render_concat(segments: list[dict], output_path: Path,
                        transition: str = "none", transition_duration: float = 0.5,
                        progress_callback=None) -> Path:
    """Render a timeline by concatenating video segments.

    Each segment dict has keys:
        path (str), start (float), end (float)
    Optional per-segment keys:
        speed (float), volume (int 0-100),
        transition (str - frontend name), transition_duration (float)

    The `transition` parameter controls the mode:
        - "none" — simple concat, no transitions
        - "per-clip" — each segment carries its own transition info
        - "crossfade"/"fade" — uniform transition applied between all clips
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not segments:
        raise ValueError("No segments provided for rendering")

    if len(segments) == 1:
        return await _render_simple_concat(segments, output_path)

    if transition == "none":
        return await _render_simple_concat(segments, output_path)
    elif transition == "per-clip":
        return await _render_with_per_clip_transitions(segments, output_path)
    elif transition in TRANSITION_MAP:
        return await _render_with_transitions(
            segments, output_path, transition, transition_duration
        )
    else:
        logger.warning("Unknown transition type '%s', falling back to simple concat", transition)
        return await _render_simple_concat(segments, output_path)


async def _render_simple_concat(segments: list[dict], output_path: Path) -> Path:
    """Concatenate segments without transitions, respecting speed/volume."""
    filter_parts = []
    inputs = []

    for i, seg in enumerate(segments):
        inputs.extend(["-i", seg["path"]])
        v_chain, a_chain = _build_segment_filters(i, seg)
        filter_parts.append(f"{v_chain};{a_chain}")

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
        str(output_path),
    ]

    result = await _run_cmd_async(cmd)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat render failed: {result.stderr.decode()[-500:]}")

    return output_path


async def _render_with_transitions(segments: list[dict], output_path: Path,
                                   transition: str, transition_duration: float) -> Path:
    """Render segments with a uniform transition using xfade filter."""
    inputs = []
    filter_parts = []

    xfade_name = _map_transition(transition)

    for i, seg in enumerate(segments):
        inputs.extend(["-i", seg["path"]])
        v_chain, a_chain = _build_segment_filters(i, seg)
        filter_parts.append(f"{v_chain};{a_chain}")

    n = len(segments)
    if n == 1:
        filter_parts.append("[v0]null[outv];[a0]anull[outa]")
    else:
        durations = _compute_segment_durations(segments)

        prev_v = "v0"
        prev_a = "a0"
        offset = durations[0] - transition_duration

        for i in range(1, n):
            out_v = "outv" if i == n - 1 else f"xv{i}"
            out_a = "outa" if i == n - 1 else f"xa{i}"

            filter_parts.append(
                f"[{prev_v}][v{i}]xfade=transition={xfade_name}"
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
        str(output_path),
    ]

    result = await _run_cmd_async(cmd)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg transition render failed: {result.stderr.decode()[-500:]}")

    return output_path


async def _render_with_per_clip_transitions(segments: list[dict], output_path: Path) -> Path:
    """Render segments where each clip can have its own transition type/duration."""
    inputs = []
    filter_parts = []

    for i, seg in enumerate(segments):
        inputs.extend(["-i", seg["path"]])
        v_chain, a_chain = _build_segment_filters(i, seg)
        filter_parts.append(f"{v_chain};{a_chain}")

    n = len(segments)
    if n == 1:
        filter_parts.append("[v0]null[outv];[a0]anull[outa]")
    else:
        durations = _compute_segment_durations(segments)

        prev_v = "v0"
        prev_a = "a0"
        # Running offset: time at which the next xfade starts (in the output timeline)
        offset = durations[0]

        for i in range(1, n):
            out_v = "outv" if i == n - 1 else f"xv{i}"
            out_a = "outa" if i == n - 1 else f"xa{i}"

            seg = segments[i]
            t_type = seg.get("transition")
            t_dur = seg.get("transition_duration", 0.5)

            if t_type:
                xfade_name = _map_transition(t_type)
                xfade_offset = max(0, offset - t_dur)
                filter_parts.append(
                    f"[{prev_v}][v{i}]xfade=transition={xfade_name}"
                    f":duration={t_dur}:offset={xfade_offset}[{out_v}]"
                )
                filter_parts.append(
                    f"[{prev_a}][a{i}]acrossfade=d={t_dur}[{out_a}]"
                )
                # After a transition the timeline shrinks by t_dur
                offset = xfade_offset + durations[i]
            else:
                # No transition — straight concat via xfade with 0 duration isn't
                # valid, so use a very short fade as a seamless join
                filter_parts.append(
                    f"[{prev_v}][v{i}]xfade=transition=fade"
                    f":duration=0.01:offset={max(0, offset - 0.01)}[{out_v}]"
                )
                filter_parts.append(
                    f"[{prev_a}][a{i}]acrossfade=d=0.01[{out_a}]"
                )
                offset = max(0, offset - 0.01) + durations[i]

            prev_v = out_v
            prev_a = out_a

    filter_complex = ";".join(filter_parts)

    cmd = [
        settings.FFMPEG_PATH, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_path),
    ]

    result = await _run_cmd_async(cmd)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg per-clip transition render failed: {result.stderr.decode()[-500:]}")

    return output_path


def _compute_segment_durations(segments: list[dict]) -> list[float]:
    """Compute the effective duration of each segment, accounting for speed."""
    durations = []
    for seg in segments:
        raw_dur = seg.get("end", 0) - seg.get("start", 0)
        speed = seg.get("speed", 1)
        if speed > 0 and speed != 1:
            raw_dur = raw_dur / speed
        durations.append(raw_dur)
    return durations
