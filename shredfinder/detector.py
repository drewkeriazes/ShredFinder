"""Detect highlight events (jumps, speed peaks) from telemetry data."""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .telemetry import Telemetry

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """A detected highlight event."""
    event_type: str       # "jump", "speed", "spin", "crash"
    peak_ts: float        # timestamp of peak moment (seconds)
    clip_start: float     # recommended clip start (seconds)
    clip_duration: float  # recommended clip duration (seconds)
    # Jump-specific
    airtime_sec: float = 0.0
    min_magnitude: float = 0.0
    landing_magnitude: float = 0.0
    confidence: float = 0.0  # 0.0–1.0 confidence score
    # Speed-specific
    peak_speed_mph: float = 0.0
    # Spin-specific
    spin_degrees: float = 0.0
    spin_axis: str = ""
    # Crash-specific
    crash_severity: float = 0.0
    # Landing quality
    landing_quality: str = ""   # "stomped", "sketchy", "crash"
    landing_score: float = 0.0  # 0.0–1.0
    # Source file (set by clipper for output organization)
    source_label: str = ""


def detect_events(
    telemetry: Telemetry,
    min_airtime_sec: float = 0.3,
    g_threshold: float = 4.0,
    min_speed_mph: float = 20.0,
    clip_pad_sec: float = 3.0,
    clip_max_sec: float = 12.0,
    min_landing_g: float = 15.0,
    min_spin_degrees: float = 180.0,
    spin_axis: str = "z",
    crash_g_threshold: float = 25.0,
    filter_chairlift: bool = True,
) -> list[Event]:
    """Detect jumps, speed peaks, spins, and crashes from telemetry data.

    Args:
        telemetry: Extracted telemetry from one file.
        min_airtime_sec: Minimum freefall duration to count as a jump.
        g_threshold: Acceleration magnitude threshold for freefall (m/s²).
            Normal gravity ≈ 9.8. Lower values = stricter (fewer false positives).
            Default 4.0 requires significant freefall, not just minor G dips.
        min_speed_mph: Minimum speed to count as a speed event.
        clip_pad_sec: Seconds of padding before/after each event.
        clip_max_sec: Maximum clip duration.
        min_landing_g: Minimum landing impact magnitude (m/s²) to confirm a jump.
            Real jumps produce a clear impact spike on landing. Default 15.0.
        min_spin_degrees: Minimum cumulative rotation to count as a spin. Default 180.
        spin_axis: Which gyro axis corresponds to yaw ("x", "y", or "z"). Default "z".
        crash_g_threshold: G-force spike threshold for crash detection (m/s²). Default 25.0.

    Returns:
        List of detected Event objects, sorted by timestamp.
    """
    events = []

    # Build a speed lookup from GPS for cross-referencing
    speed_at_time = None
    if telemetry.has_gps and not telemetry.gps_df.empty:
        speed_at_time = telemetry.gps_df.set_index("ts_sec")["speed_mph"]

    if telemetry.has_accl:
        jump_events = _detect_jumps(
            telemetry.accl_df, min_airtime_sec, g_threshold,
            min_landing_g, clip_pad_sec, clip_max_sec, speed_at_time,
        )
        # Score landing quality using GYRO if available
        if telemetry.has_gyro:
            for e in jump_events:
                _score_landing_quality(e, telemetry.accl_df, telemetry.gyro_df, speed_at_time)
        events.extend(jump_events)

    if telemetry.has_gps:
        events.extend(_detect_speed_peaks(
            telemetry.gps_df, min_speed_mph, clip_pad_sec, clip_max_sec,
        ))

    if telemetry.has_gyro:
        events.extend(_detect_spins(
            telemetry.gyro_df, telemetry.accl_df if telemetry.has_accl else pd.DataFrame(),
            min_spin_degrees, spin_axis, g_threshold, clip_pad_sec, clip_max_sec,
        ))

    if telemetry.has_accl:
        events.extend(_detect_crashes(
            telemetry.accl_df, crash_g_threshold, clip_pad_sec, clip_max_sec,
            speed_at_time,
            telemetry.gyro_df if telemetry.has_gyro else pd.DataFrame(),
        ))

    # Filter out events occurring during chairlift or stationary segments
    if filter_chairlift and telemetry.segments:
        filtered = []
        for e in events:
            in_excluded = False
            for seg in telemetry.segments:
                if seg.activity in ("chairlift", "stationary") and seg.start_ts <= e.peak_ts <= seg.end_ts:
                    logger.debug(
                        "Filtered %s event at %.1fs (inside %s segment %.1fs-%.1fs)",
                        e.event_type, e.peak_ts, seg.activity, seg.start_ts, seg.end_ts,
                    )
                    in_excluded = True
                    break
            if not in_excluded:
                filtered.append(e)
        if len(filtered) < len(events):
            logger.info(
                "Chairlift filter removed %d of %d events",
                len(events) - len(filtered), len(events),
            )
        events = filtered

    events.sort(key=lambda e: e.clip_start)
    events = _merge_overlapping(events, gap_sec=4.0)

    return events


def _speed_at_timestamp(speed_index: pd.Series | None, ts: float) -> float:
    """Look up approximate speed (mph) at a given timestamp from GPS data."""
    if speed_index is None or speed_index.empty:
        return -1.0  # unknown — don't filter on speed
    idx = speed_index.index.searchsorted(ts)
    idx = min(idx, len(speed_index) - 1)
    return float(speed_index.iloc[idx])


def _compute_jump_confidence(
    airtime: float, min_mag: float, landing_mag: float, speed_mph: float,
) -> float:
    """Compute a 0.0–1.0 confidence score for a jump detection.

    Factors:
      - Freefall depth: lower min_mag = more convincing (weight 0.3)
      - Landing spike: higher landing_mag = more convincing (weight 0.3)
      - Airtime: longer = more convincing (weight 0.2)
      - Speed: must be moving to be a real jump (weight 0.2)
    """
    # Freefall depth: 0 m/s² = perfect freefall (1.0), 5+ m/s² = weak (0.0)
    depth_score = max(0.0, 1.0 - min_mag / 5.0)

    # Landing spike: 20+ m/s² = strong (1.0), 10 m/s² = weak (0.0)
    landing_score = min(1.0, max(0.0, (landing_mag - 10.0) / 10.0))

    # Airtime: 1.0+ sec = great (1.0), 0.3 sec = minimal (0.2)
    airtime_score = min(1.0, airtime / 1.0)

    # Speed: 10+ mph = moving (1.0), 0 mph = stationary (0.0), unknown = neutral (0.5)
    if speed_mph < 0:
        speed_score = 0.5  # no GPS data — don't penalize
    else:
        speed_score = min(1.0, speed_mph / 10.0)

    confidence = (
        0.3 * depth_score
        + 0.3 * landing_score
        + 0.2 * airtime_score
        + 0.2 * speed_score
    )
    return round(confidence, 2)


def _detect_jumps(
    accl_df: pd.DataFrame,
    min_airtime_sec: float,
    g_threshold: float,
    min_landing_g: float,
    clip_pad_sec: float,
    clip_max_sec: float,
    speed_at_time: pd.Series | None = None,
) -> list[Event]:
    """Detect jumps as sustained low-G windows in accelerometer data.

    A jump = acceleration magnitude drops below g_threshold for at least
    min_airtime_sec, followed by a landing spike >= min_landing_g.

    Additional validation:
      - Landing impact must exceed min_landing_g to confirm it's a real jump
      - GPS speed is checked to reject stationary false positives
      - A confidence score ranks detection quality
    """
    if accl_df.empty:
        return []

    ts = accl_df["ts_sec"].values
    mag = accl_df["magnitude"].values

    low_g = mag < g_threshold
    events = []

    # Find contiguous windows of low-G
    in_air = False
    start_idx = 0

    for i in range(len(low_g)):
        if low_g[i] and not in_air:
            in_air = True
            start_idx = i
        elif not low_g[i] and in_air:
            in_air = False
            duration = ts[i] - ts[start_idx]
            if duration < min_airtime_sec:
                continue

            # Find the lowest magnitude in this window (deepest freefall)
            window_mag = mag[start_idx:i]
            min_mag = float(np.min(window_mag))
            min_mag_idx = start_idx + int(np.argmin(window_mag))

            # Find landing spike (max magnitude in the 1 second after freefall)
            landing_end = min(len(mag), i + 200)  # ~1 sec at 200Hz
            landing_mag = float(np.max(mag[i:landing_end])) if i < landing_end else 0

            # Filter: require a clear landing impact
            if landing_mag < min_landing_g:
                logger.debug(
                    "Rejected jump candidate at %.1fs: landing_mag=%.1f < %.1f threshold",
                    ts[start_idx], landing_mag, min_landing_g,
                )
                continue

            # Check GPS speed — reject if stationary (< 3 mph)
            speed = _speed_at_timestamp(speed_at_time, float(ts[start_idx]))
            if speed >= 0 and speed < 3.0:
                logger.debug(
                    "Rejected jump candidate at %.1fs: speed=%.1f mph (stationary)",
                    ts[start_idx], speed,
                )
                continue

            peak_ts = float(ts[min_mag_idx])
            clip_start = max(0, float(ts[start_idx]) - clip_pad_sec)
            clip_end = min(float(ts[min(landing_end - 1, len(ts) - 1)]), clip_start + clip_max_sec)

            confidence = _compute_jump_confidence(duration, min_mag, landing_mag, speed)

            events.append(Event(
                event_type="jump",
                peak_ts=round(peak_ts, 2),
                clip_start=round(clip_start, 2),
                clip_duration=round(clip_end - clip_start, 2),
                airtime_sec=round(duration, 3),
                min_magnitude=round(min_mag, 2),
                landing_magnitude=round(landing_mag, 2),
                confidence=confidence,
            ))
            logger.info(
                "Jump detected at %.1fs: airtime=%.2fs, min_g=%.1f, landing_g=%.1f, speed=%.1fmph, confidence=%.2f",
                peak_ts, duration, min_mag, landing_mag, speed, confidence,
            )

    return events


def _detect_speed_peaks(
    gps_df: pd.DataFrame,
    min_speed_mph: float,
    clip_pad_sec: float,
    clip_max_sec: float,
) -> list[Event]:
    """Detect sustained high-speed windows in GPS data."""
    if gps_df.empty:
        return []

    ts = gps_df["ts_sec"].values
    speed = gps_df["speed_mph"].values

    # Filter GPS noise: reject speeds > 80 mph as unrealistic for snowboarding
    speed = np.where(speed > 80, 0, speed)

    # Validate GPS coordinates — reject rows with impossible lat/lon
    if "lat" in gps_df.columns and "lon" in gps_df.columns:
        lat = gps_df["lat"].values
        lon = gps_df["lon"].values
        invalid = (np.abs(lat) > 90) | (np.abs(lon) > 180) | ((np.abs(lat) < 0.001) & (np.abs(lon) < 0.001))
        speed = np.where(invalid, 0, speed)

    fast = speed >= min_speed_mph
    events = []

    in_run = False
    start_idx = 0
    peak_speed = 0.0
    peak_idx = 0

    for i in range(len(fast)):
        if fast[i] and not in_run:
            in_run = True
            start_idx = i
            peak_speed = speed[i]
            peak_idx = i
        elif fast[i] and in_run:
            if speed[i] > peak_speed:
                peak_speed = speed[i]
                peak_idx = i
        elif not fast[i] and in_run:
            in_run = False
            duration = ts[i] - ts[start_idx]
            if duration >= 2.0:
                peak_ts = float(ts[peak_idx])
                clip_start = max(0, peak_ts - clip_pad_sec)
                clip_end = min(peak_ts + clip_pad_sec, clip_start + clip_max_sec)

                events.append(Event(
                    event_type="speed",
                    peak_ts=round(peak_ts, 2),
                    clip_start=round(clip_start, 2),
                    clip_duration=round(clip_end - clip_start, 2),
                    peak_speed_mph=round(float(peak_speed), 1),
                ))
                logger.info(
                    "Speed event at %.1fs: peak=%.1f mph, duration=%.1fs",
                    peak_ts, peak_speed, duration,
                )

    return events


def _detect_spins(
    gyro_df: pd.DataFrame,
    accl_df: pd.DataFrame,
    min_spin_degrees: float,
    spin_axis: str,
    g_threshold: float,
    clip_pad_sec: float,
    clip_max_sec: float,
) -> list[Event]:
    """Detect spins by integrating angular velocity on the yaw axis.

    Looks for windows of high angular velocity, integrates to get total
    rotation, and filters by minimum degrees. Requires co-occurrence with
    freefall (low-G in ACCL) to reject ground pivots like turning.
    """
    if gyro_df.empty:
        return []

    if spin_axis not in gyro_df.columns:
        logger.warning("Spin axis '%s' not found in GYRO data", spin_axis)
        return []

    ts = gyro_df["ts_sec"].values
    yaw_rate = gyro_df[spin_axis].values  # deg/s after SCAL applied
    mag = gyro_df["magnitude"].values

    # Build a freefall mask from ACCL data for co-occurrence check
    has_accl = not accl_df.empty
    airborne_times = set()
    if has_accl:
        accl_ts = accl_df["ts_sec"].values
        accl_mag = accl_df["magnitude"].values
        for i, t in enumerate(accl_ts):
            if accl_mag[i] < g_threshold:
                # Round to 0.1s buckets for fast lookup
                airborne_times.add(round(t, 1))

    # Threshold for "spinning" — angular velocity must exceed this
    spin_rate_threshold = 150.0  # deg/s

    events = []
    in_spin = False
    start_idx = 0

    for i in range(len(ts)):
        fast_rotation = abs(yaw_rate[i]) > spin_rate_threshold

        if fast_rotation and not in_spin:
            in_spin = True
            start_idx = i
        elif not fast_rotation and in_spin:
            in_spin = False
            duration = ts[i] - ts[start_idx]
            if duration < 0.1 or duration > 3.0:
                continue  # too short or too long for a trick spin

            # Integrate angular velocity to get total rotation
            window_ts = ts[start_idx:i]
            window_rate = yaw_rate[start_idx:i]
            # np.trapezoid replaces np.trapz in NumPy 2.0+
            _integrate = np.trapezoid if hasattr(np, "trapezoid") else np.trapz
            total_rotation = float(np.abs(_integrate(window_rate, window_ts)))

            if total_rotation < min_spin_degrees:
                continue

            # Check co-occurrence with freefall (must overlap with airborne)
            spin_mid = (ts[start_idx] + ts[i]) / 2
            is_airborne = round(spin_mid, 1) in airborne_times
            if not is_airborne and has_accl:
                # Check a small window around the spin for freefall
                is_airborne = any(
                    round(t, 1) in airborne_times
                    for t in np.linspace(ts[start_idx], ts[i], min(10, i - start_idx + 1))
                )

            if not is_airborne and has_accl:
                logger.debug(
                    "Rejected spin at %.1fs: %.0f° but no freefall (ground pivot)",
                    ts[start_idx], total_rotation,
                )
                continue

            # Quantize to nearest common spin amount
            spin_label = _quantize_spin(total_rotation)
            peak_idx = start_idx + int(np.argmax(np.abs(window_rate)))
            peak_ts = float(ts[peak_idx])
            clip_start = max(0, float(ts[start_idx]) - clip_pad_sec)
            clip_end = min(float(ts[i]) + clip_pad_sec, clip_start + clip_max_sec)

            events.append(Event(
                event_type="spin",
                peak_ts=round(peak_ts, 2),
                clip_start=round(clip_start, 2),
                clip_duration=round(clip_end - clip_start, 2),
                spin_degrees=round(total_rotation, 0),
                spin_axis=spin_axis,
                confidence=min(1.0, total_rotation / 360.0),
            ))
            logger.info(
                "Spin detected at %.1fs: %.0f° (%s) on %s-axis, duration=%.2fs",
                peak_ts, total_rotation, spin_label, spin_axis, duration,
            )

    return events


def _quantize_spin(degrees: float) -> str:
    """Round spin degrees to the nearest common trick name."""
    # Each bucket covers ±90° around the target
    buckets = [180, 360, 540, 720, 900, 1080]
    best = min(buckets, key=lambda b: abs(degrees - b))
    if abs(degrees - best) <= 90:
        return str(best)
    return f"{int(round(degrees / 180) * 180)}"


def _detect_crashes(
    accl_df: pd.DataFrame,
    crash_g_threshold: float,
    clip_pad_sec: float,
    clip_max_sec: float,
    speed_at_time: pd.Series | None,
    gyro_df: pd.DataFrame | None = None,
) -> list[Event]:
    """Detect crashes: high-G spike + rapid deceleration to zero.

    A crash signature:
      1. Very high G spike (>= crash_g_threshold) — harder than a normal landing
      2. GPS speed drops from moving to near-zero within 5 seconds
      3. Optional: chaotic multi-axis GYRO (tumbling)
    """
    if accl_df.empty:
        return []

    ts = accl_df["ts_sec"].values
    mag = accl_df["magnitude"].values

    events = []
    # Use a cooldown to avoid detecting the same crash multiple times
    last_crash_ts = -10.0

    for i in range(len(mag)):
        if mag[i] < crash_g_threshold:
            continue
        if ts[i] - last_crash_ts < 5.0:
            continue  # cooldown

        # Check speed before and after the spike — require confirmed GPS
        speed_before = _speed_at_timestamp(speed_at_time, float(ts[i]) - 1.0)
        speed_after = _speed_at_timestamp(speed_at_time, float(ts[i]) + 3.0)

        # Require GPS data — can't confirm a crash without speed context
        if speed_before < 0 or speed_after < 0:
            continue
        # Must be moving before and stopped after
        if speed_before < 5.0:
            continue  # wasn't really moving
        if speed_after > 5.0:
            continue  # didn't stop — probably just a hard landing

        # Check for tumbling via GYRO (multi-axis high rotation)
        tumble_score = 0.0
        if gyro_df is not None and not gyro_df.empty:
            gyro_window = gyro_df[
                (gyro_df["ts_sec"] >= ts[i]) & (gyro_df["ts_sec"] <= ts[i] + 2.0)
            ]
            if not gyro_window.empty:
                # Tumble = high rotation on multiple axes simultaneously
                avg_mag = float(gyro_window["magnitude"].mean())
                tumble_score = min(1.0, avg_mag / 500.0)

        # Compute crash severity
        g_score = min(1.0, (float(mag[i]) - crash_g_threshold) / 30.0)
        decel_score = 1.0 if (speed_before >= 0 and speed_after >= 0 and speed_after < 2.0) else 0.5
        severity = round(0.4 * g_score + 0.3 * decel_score + 0.3 * tumble_score, 2)

        peak_ts = float(ts[i])
        clip_start = max(0, peak_ts - clip_pad_sec)
        clip_end = min(peak_ts + clip_pad_sec + 2.0, clip_start + clip_max_sec)

        events.append(Event(
            event_type="crash",
            peak_ts=round(peak_ts, 2),
            clip_start=round(clip_start, 2),
            clip_duration=round(clip_end - clip_start, 2),
            landing_magnitude=round(float(mag[i]), 2),
            crash_severity=severity,
            confidence=severity,
        ))
        last_crash_ts = ts[i]
        logger.info(
            "Crash detected at %.1fs: G=%.1f, speed %.1f->%.1f mph, tumble=%.2f, severity=%.2f",
            peak_ts, mag[i], speed_before, speed_after, tumble_score, severity,
        )

    return events


def _score_landing_quality(
    event: Event,
    accl_df: pd.DataFrame,
    gyro_df: pd.DataFrame,
    speed_at_time: pd.Series | None,
) -> None:
    """Score the landing quality of a jump event in-place.

    Analyzes the post-impact ACCL and GYRO pattern:
      - Single clean spike -> return to ~9.8 = "stomped"
      - Multiple spikes / wobble = "sketchy"
      - Sustained chaos / deceleration = "crash"
    """
    if accl_df.empty:
        return

    # Get the 1.5-second window after the freefall ends (landing zone)
    landing_start = event.peak_ts + event.airtime_sec / 2
    landing_end = landing_start + 1.5

    window = accl_df[(accl_df["ts_sec"] >= landing_start) & (accl_df["ts_sec"] <= landing_end)]
    if window.empty:
        return

    mag = window["magnitude"].values

    # Count significant spikes (> 15 m/s²) in the landing window
    spike_threshold = 15.0
    spikes = np.diff((mag > spike_threshold).astype(int))
    num_spikes = max(1, int(np.sum(spikes == 1)))

    # How quickly does it return to normal gravity?
    normal_g = 9.8
    deviation = np.abs(mag - normal_g)
    # Fraction of samples within 3 m/s² of normal gravity in second half of window
    half = len(deviation) // 2
    if half > 0:
        recovery = float(np.mean(deviation[half:] < 3.0))
    else:
        recovery = 0.5

    # GYRO stability after landing
    gyro_stability = 1.0
    if not gyro_df.empty:
        gyro_window = gyro_df[
            (gyro_df["ts_sec"] >= landing_start + 0.3) & (gyro_df["ts_sec"] <= landing_end)
        ]
        if not gyro_window.empty:
            avg_gyro = float(gyro_window["magnitude"].mean())
            gyro_stability = max(0.0, 1.0 - avg_gyro / 300.0)

    # Speed maintenance
    speed_score = 0.5  # neutral if no GPS
    if speed_at_time is not None:
        speed_before = _speed_at_timestamp(speed_at_time, landing_start)
        speed_after = _speed_at_timestamp(speed_at_time, landing_end)
        if speed_before > 0 and speed_after >= 0:
            speed_score = min(1.0, speed_after / speed_before) if speed_before > 3 else 0.5

    # Composite score
    spike_score = max(0.0, 1.0 - (num_spikes - 1) * 0.3)  # 1 spike = 1.0, 4+ = 0.1
    landing_score = round(
        0.3 * spike_score + 0.3 * recovery + 0.2 * gyro_stability + 0.2 * speed_score,
        2,
    )

    # Label
    if landing_score >= 0.7:
        event.landing_quality = "stomped"
    elif landing_score >= 0.4:
        event.landing_quality = "sketchy"
    else:
        event.landing_quality = "crash"

    event.landing_score = landing_score
    logger.debug(
        "Landing quality at %.1fs: %s (score=%.2f, spikes=%d, recovery=%.2f, gyro=%.2f)",
        event.peak_ts, event.landing_quality, landing_score, num_spikes, recovery, gyro_stability,
    )


def _merge_overlapping(events: list[Event], gap_sec: float) -> list[Event]:
    """Merge events whose clip windows overlap or are within gap_sec of each other."""
    if len(events) <= 1:
        return events

    merged = [events[0]]
    for e in events[1:]:
        prev = merged[-1]
        prev_end = prev.clip_start + prev.clip_duration

        if e.clip_start <= prev_end + gap_sec:
            # Extend previous event to cover both
            new_end = max(prev_end, e.clip_start + e.clip_duration)
            prev.clip_duration = round(new_end - prev.clip_start, 2)
            # Combine types if different
            if e.event_type not in prev.event_type:
                prev.event_type = f"{prev.event_type}+{e.event_type}"
        else:
            merged.append(e)

    return merged
