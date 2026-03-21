"""Tests for the event detector module."""

from pathlib import Path

import numpy as np
import pandas as pd

from shredfinder.detector import (
    Event, _compute_jump_confidence, _detect_crashes, _detect_jumps,
    _detect_speed_peaks, _detect_spins, _merge_overlapping,
    _quantize_spin, _score_landing_quality, _speed_at_timestamp, detect_events,
)
from shredfinder.gpmf_parser import parse_gpmf
from shredfinder.telemetry import Telemetry, _build_accl_dataframe, _build_gps_dataframe, _build_gyro_dataframe

TEST_DATA_DIR = Path(__file__).parent.parent


def _make_telemetry_from_bin(name: str = "test_gpmf.bin") -> Telemetry:
    """Build a Telemetry object from a test binary file."""
    data = (TEST_DATA_DIR / name).read_bytes()
    streams = parse_gpmf(data)
    accl_streams = [s for s in streams if s.fourcc == "ACCL"]
    gps_streams = [s for s in streams if s.fourcc == "GPS5"]
    gyro_streams = [s for s in streams if s.fourcc == "GYRO"]
    accl_df = _build_accl_dataframe(accl_streams)
    gps_df = _build_gps_dataframe(gps_streams)
    gyro_df = _build_gyro_dataframe(gyro_streams)
    return Telemetry(
        source_file=Path(name),
        accl_df=accl_df,
        gps_df=gps_df,
        gyro_df=gyro_df,
        has_accl=len(accl_df) > 0,
        has_gps=len(gps_df) > 0 and (gps_df["lat"].abs() > 0.001).any(),
        has_gyro=len(gyro_df) > 0,
    )


# ── Jump Detection ──────────────────────────────────────────────────────

class TestDetectJumps:
    def test_synthetic_freefall_with_landing(self):
        """A 1-second freefall with a clear landing spike should be detected."""
        n = 2000
        ts = np.linspace(0, 10, n)
        mag = np.full(n, 9.8)
        mag[800:1000] = 1.0
        mag[1000:1020] = 25.0

        df = pd.DataFrame({
            "ts_sec": ts, "x": mag * 0.1, "y": mag * 0.1, "z": mag * 0.98, "magnitude": mag,
        })
        events = _detect_jumps(df, 0.4, 5.0, 15.0, 3.0, 12.0)
        assert len(events) == 1
        assert events[0].event_type == "jump"
        assert events[0].airtime_sec >= 0.9
        assert events[0].confidence > 0.5

    def test_freefall_without_landing_rejected(self):
        n = 2000
        ts = np.linspace(0, 10, n)
        mag = np.full(n, 9.8)
        mag[800:1000] = 1.0

        df = pd.DataFrame({"ts_sec": ts, "x": [0]*n, "y": [0]*n, "z": mag, "magnitude": mag})
        events = _detect_jumps(df, 0.4, 5.0, 15.0, 3.0, 12.0)
        assert len(events) == 0

    def test_stationary_freefall_rejected(self):
        n = 2000
        ts = np.linspace(0, 10, n)
        mag = np.full(n, 9.8)
        mag[800:1000] = 1.0
        mag[1000:1020] = 25.0

        df = pd.DataFrame({"ts_sec": ts, "x": [0]*n, "y": [0]*n, "z": mag, "magnitude": mag})
        speed_index = pd.Series([0.0] * 10, index=np.linspace(0, 10, 10))
        events = _detect_jumps(df, 0.4, 5.0, 15.0, 3.0, 12.0, speed_at_time=speed_index)
        assert len(events) == 0

    def test_short_freefall_ignored(self):
        n = 2000
        ts = np.linspace(0, 10, n)
        mag = np.full(n, 9.8)
        mag[500:510] = 1.0
        mag[510:530] = 25.0

        df = pd.DataFrame({"ts_sec": ts, "x": [0]*n, "y": [0]*n, "z": mag, "magnitude": mag})
        events = _detect_jumps(df, 0.4, 5.0, 15.0, 3.0, 12.0)
        assert len(events) == 0

    def test_empty_dataframe(self):
        assert _detect_jumps(pd.DataFrame(), 0.4, 5.0, 15.0, 3.0, 12.0) == []


# ── Confidence ──────────────────────────────────────────────────────────

class TestJumpConfidence:
    def test_perfect_jump(self):
        c = _compute_jump_confidence(airtime=1.5, min_mag=0.5, landing_mag=30.0, speed_mph=20.0)
        assert c >= 0.8

    def test_weak_jump(self):
        c = _compute_jump_confidence(airtime=0.3, min_mag=4.0, landing_mag=12.0, speed_mph=5.0)
        assert c < 0.5

    def test_no_gps(self):
        c = _compute_jump_confidence(airtime=1.0, min_mag=1.0, landing_mag=25.0, speed_mph=-1.0)
        assert 0.5 < c < 0.9


class TestSpeedAtTimestamp:
    def test_lookup(self):
        index = pd.Series([10.0, 20.0, 30.0], index=[0.0, 5.0, 10.0])
        assert _speed_at_timestamp(index, 5.0) == 20.0

    def test_no_gps(self):
        assert _speed_at_timestamp(None, 5.0) == -1.0


# ── Speed Detection ────────────────────────────────────────────────────

class TestDetectSpeedPeaks:
    def test_synthetic_speed_run(self):
        n = 100
        ts = np.linspace(0, 30, n)
        speed = np.full(n, 10.0)
        speed[33:67] = 25.0

        df = pd.DataFrame({
            "ts_sec": ts, "lat": [40.0]*n, "lon": [-105.0]*n,
            "alt_m": [3000]*n, "speed_2d_ms": speed / 2.237, "speed_mph": speed,
        })
        events = _detect_speed_peaks(df, 20.0, 3.0, 12.0)
        assert len(events) == 1
        assert events[0].peak_speed_mph >= 24.0

    def test_invalid_gps_rejected(self):
        n = 100
        ts = np.linspace(0, 30, n)
        speed = np.full(n, 25.0)

        df = pd.DataFrame({
            "ts_sec": ts, "lat": [0.0]*n, "lon": [0.0]*n,
            "alt_m": [0]*n, "speed_2d_ms": speed / 2.237, "speed_mph": speed,
        })
        events = _detect_speed_peaks(df, 20.0, 3.0, 12.0)
        assert len(events) == 0

    def test_below_threshold_ignored(self):
        n = 100
        ts = np.linspace(0, 30, n)
        speed = np.full(n, 15.0)

        df = pd.DataFrame({
            "ts_sec": ts, "lat": [40]*n, "lon": [-105]*n,
            "alt_m": [3000]*n, "speed_2d_ms": speed / 2.237, "speed_mph": speed,
        })
        events = _detect_speed_peaks(df, 20.0, 3.0, 12.0)
        assert len(events) == 0

    def test_empty_dataframe(self):
        assert _detect_speed_peaks(pd.DataFrame(), 20.0, 3.0, 12.0) == []


# ── Spin Detection ─────────────────────────────────────────────────────

class TestDetectSpins:
    def _make_gyro_df(self, n, ts_range, z_rate):
        """Helper to create GYRO DataFrame with constant z rotation rate."""
        ts = np.linspace(*ts_range, n)
        return pd.DataFrame({
            "ts_sec": ts, "x": np.zeros(n), "y": np.zeros(n),
            "z": np.full(n, z_rate),
            "magnitude": np.full(n, abs(z_rate)),
        })

    def _make_accl_freefall(self, n, ts_range, freefall_range):
        """Helper to create ACCL DataFrame with a freefall window."""
        ts = np.linspace(*ts_range, n)
        mag = np.full(n, 9.8)
        start_frac = int((freefall_range[0] - ts_range[0]) / (ts_range[1] - ts_range[0]) * n)
        end_frac = int((freefall_range[1] - ts_range[0]) / (ts_range[1] - ts_range[0]) * n)
        mag[start_frac:end_frac] = 1.0
        return pd.DataFrame({
            "ts_sec": ts, "x": np.zeros(n), "y": np.zeros(n), "z": mag, "magnitude": mag,
        })

    def test_360_spin_detected(self):
        """A 1-second window at 400 deg/s = 400° total, should detect a 360."""
        # Spin from t=4 to t=5 at 400 deg/s
        gyro_df = pd.DataFrame({
            "ts_sec": np.linspace(0, 10, 2000),
            "x": np.zeros(2000),
            "y": np.zeros(2000),
            "z": np.concatenate([np.zeros(800), np.full(200, 400.0), np.zeros(1000)]),
            "magnitude": np.concatenate([np.zeros(800), np.full(200, 400.0), np.zeros(1000)]),
        })
        # Freefall during the spin
        accl_df = pd.DataFrame({
            "ts_sec": np.linspace(0, 10, 2000),
            "x": np.zeros(2000),
            "y": np.zeros(2000),
            "z": np.concatenate([np.full(800, 9.8), np.full(200, 1.0), np.full(1000, 9.8)]),
            "magnitude": np.concatenate([np.full(800, 9.8), np.full(200, 1.0), np.full(1000, 9.8)]),
        })
        events = _detect_spins(gyro_df, accl_df, 180.0, "z", 5.0, 3.0, 12.0)
        assert len(events) == 1
        assert events[0].event_type == "spin"
        assert events[0].spin_degrees >= 180

    def test_slow_rotation_ignored(self):
        """50 deg/s should not trigger spin detection (below 150 threshold)."""
        gyro_df = pd.DataFrame({
            "ts_sec": np.linspace(0, 10, 2000),
            "x": np.zeros(2000), "y": np.zeros(2000),
            "z": np.full(2000, 50.0),
            "magnitude": np.full(2000, 50.0),
        })
        events = _detect_spins(gyro_df, pd.DataFrame(), 180.0, "z", 5.0, 3.0, 12.0)
        assert len(events) == 0

    def test_ground_pivot_rejected(self):
        """High rotation without freefall (normal ACCL) should be rejected."""
        gyro_df = pd.DataFrame({
            "ts_sec": np.linspace(0, 10, 2000),
            "x": np.zeros(2000), "y": np.zeros(2000),
            "z": np.concatenate([np.zeros(800), np.full(200, 400.0), np.zeros(1000)]),
            "magnitude": np.concatenate([np.zeros(800), np.full(200, 400.0), np.zeros(1000)]),
        })
        # Normal gravity throughout — no freefall
        accl_df = pd.DataFrame({
            "ts_sec": np.linspace(0, 10, 2000),
            "x": np.zeros(2000), "y": np.zeros(2000),
            "z": np.full(2000, 9.8),
            "magnitude": np.full(2000, 9.8),
        })
        events = _detect_spins(gyro_df, accl_df, 180.0, "z", 5.0, 3.0, 12.0)
        assert len(events) == 0

    def test_empty_gyro(self):
        assert _detect_spins(pd.DataFrame(), pd.DataFrame(), 180.0, "z", 5.0, 3.0, 12.0) == []


class TestQuantizeSpin:
    def test_180(self):
        assert _quantize_spin(170) == "180"

    def test_360(self):
        assert _quantize_spin(350) == "360"

    def test_540(self):
        assert _quantize_spin(500) == "540"

    def test_large(self):
        assert _quantize_spin(1100) == "1080"


# ── Crash Detection ────────────────────────────────────────────────────

class TestDetectCrashes:
    def test_high_g_with_deceleration(self):
        """High G spike + speed drops to zero = crash."""
        n = 2000
        ts = np.linspace(0, 10, n)
        mag = np.full(n, 9.8)
        # Big spike at t=5
        spike_idx = 1000
        mag[spike_idx:spike_idx + 10] = 35.0

        df = pd.DataFrame({"ts_sec": ts, "x": [0]*n, "y": [0]*n, "z": mag, "magnitude": mag})

        # Speed: 20 mph before, 0 mph after
        speed_ts = np.linspace(0, 10, 20)
        speed_vals = np.concatenate([np.full(10, 20.0), np.full(10, 0.0)])
        speed_index = pd.Series(speed_vals, index=speed_ts)

        events = _detect_crashes(df, 25.0, 3.0, 12.0, speed_index)
        assert len(events) == 1
        assert events[0].event_type == "crash"
        assert events[0].crash_severity > 0

    def test_hard_landing_not_crash(self):
        """High G spike but speed maintained = hard landing, not crash."""
        n = 2000
        ts = np.linspace(0, 10, n)
        mag = np.full(n, 9.8)
        mag[1000:1010] = 30.0

        df = pd.DataFrame({"ts_sec": ts, "x": [0]*n, "y": [0]*n, "z": mag, "magnitude": mag})

        # Speed stays at 20 mph throughout
        speed_index = pd.Series(np.full(20, 20.0), index=np.linspace(0, 10, 20))
        events = _detect_crashes(df, 25.0, 3.0, 12.0, speed_index)
        assert len(events) == 0

    def test_stationary_spike_not_crash(self):
        """Spike while not moving = not a crash (sensor bump)."""
        n = 2000
        ts = np.linspace(0, 10, n)
        mag = np.full(n, 9.8)
        mag[1000:1010] = 30.0

        df = pd.DataFrame({"ts_sec": ts, "x": [0]*n, "y": [0]*n, "z": mag, "magnitude": mag})
        speed_index = pd.Series(np.full(20, 1.0), index=np.linspace(0, 10, 20))
        events = _detect_crashes(df, 25.0, 3.0, 12.0, speed_index)
        assert len(events) == 0

    def test_empty_dataframe(self):
        assert _detect_crashes(pd.DataFrame(), 25.0, 3.0, 12.0, None) == []


# ── Landing Quality ────────────────────────────────────────────────────

class TestLandingQuality:
    def _make_jump_event(self, peak_ts=5.0, airtime=0.5):
        return Event(
            event_type="jump", peak_ts=peak_ts, clip_start=peak_ts - 3,
            clip_duration=6.0, airtime_sec=airtime, landing_magnitude=20.0,
        )

    def test_clean_stomp(self):
        """Single sharp spike then return to normal = stomped."""
        n = 2000
        ts = np.linspace(0, 10, n)
        mag = np.full(n, 9.8)
        # Single clean spike at t~5.25 (right after freefall ends)
        mag[1050:1060] = 22.0

        accl_df = pd.DataFrame({"ts_sec": ts, "x": [0]*n, "y": [0]*n, "z": mag, "magnitude": mag})
        gyro_df = pd.DataFrame({
            "ts_sec": ts, "x": np.zeros(n), "y": np.zeros(n),
            "z": np.full(n, 5.0), "magnitude": np.full(n, 5.0),
        })

        event = self._make_jump_event()
        _score_landing_quality(event, accl_df, gyro_df, None)
        assert event.landing_quality == "stomped"
        assert event.landing_score >= 0.7

    def test_wobble_landing(self):
        """Multiple spikes + chaotic gyro + speed loss = sketchy or crash."""
        n = 2000
        ts = np.linspace(0, 10, n)
        mag = np.full(n, 9.8)
        # Chaotic landing zone: alternating high spikes and low dips
        for offset in [1050, 1080, 1110, 1140, 1170]:
            mag[offset:offset + 10] = 25.0
            mag[offset + 10:offset + 20] = 4.0

        accl_df = pd.DataFrame({"ts_sec": ts, "x": [0]*n, "y": [0]*n, "z": mag, "magnitude": mag})
        # Very high gyro = tumbling
        gyro_df = pd.DataFrame({
            "ts_sec": ts, "x": np.full(n, 200.0),
            "y": np.full(n, 200.0),
            "z": np.full(n, 200.0),
            "magnitude": np.full(n, 350.0),
        })
        # Speed drops to zero
        speed_index = pd.Series(
            np.concatenate([np.full(10, 20.0), np.full(10, 2.0)]),
            index=np.linspace(0, 10, 20),
        )

        event = self._make_jump_event()
        _score_landing_quality(event, accl_df, gyro_df, speed_index)
        assert event.landing_quality in ("sketchy", "crash")
        assert event.landing_score < 0.7


# ── Merge Overlapping ──────────────────────────────────────────────────

class TestMergeOverlapping:
    def test_non_overlapping_preserved(self):
        events = [
            Event(event_type="jump", peak_ts=5.0, clip_start=2.0, clip_duration=6.0),
            Event(event_type="speed", peak_ts=25.0, clip_start=22.0, clip_duration=6.0),
        ]
        merged = _merge_overlapping(events, gap_sec=4.0)
        assert len(merged) == 2

    def test_overlapping_merged(self):
        events = [
            Event(event_type="jump", peak_ts=5.0, clip_start=2.0, clip_duration=6.0),
            Event(event_type="speed", peak_ts=9.0, clip_start=6.0, clip_duration=6.0),
        ]
        merged = _merge_overlapping(events, gap_sec=4.0)
        assert len(merged) == 1
        assert "jump" in merged[0].event_type
        assert "speed" in merged[0].event_type

    def test_single_event(self):
        events = [Event(event_type="jump", peak_ts=5.0, clip_start=2.0, clip_duration=6.0)]
        assert len(_merge_overlapping(events, 4.0)) == 1

    def test_empty_list(self):
        assert _merge_overlapping([], 4.0) == []


# ── Integration ────────────────────────────────────────────────────────

class TestDetectEventsIntegration:
    def test_real_telemetry_data(self):
        telemetry = _make_telemetry_from_bin("test_gpmf.bin")
        events = detect_events(telemetry)
        assert isinstance(events, list)
        for e in events:
            assert isinstance(e, Event)
            assert e.clip_start >= 0
            assert e.clip_duration > 0

    def test_long_telemetry_data(self):
        telemetry = _make_telemetry_from_bin("test_gpmf_long.bin")
        events = detect_events(telemetry)
        assert isinstance(events, list)

    def test_detects_all_event_types(self):
        """Verify detector doesn't crash and returns valid types."""
        telemetry = _make_telemetry_from_bin("test_gpmf_long.bin")
        events = detect_events(telemetry)
        valid_types = {"jump", "speed", "spin", "crash"}
        for e in events:
            # Compound types like "jump+speed" are ok
            for t in e.event_type.split("+"):
                assert t in valid_types, f"Unknown event type: {t}"
