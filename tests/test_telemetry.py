"""Tests for the telemetry extraction module (using pre-extracted binary data)."""

from pathlib import Path

import numpy as np
import pandas as pd

from shredfinder.gpmf_parser import parse_gpmf
from shredfinder.telemetry import Telemetry, _build_accl_dataframe, _build_gps_dataframe, _build_gyro_dataframe

TEST_DATA_DIR = Path(__file__).parent.parent


def _load_streams(name: str = "test_gpmf.bin"):
    data = (TEST_DATA_DIR / name).read_bytes()
    return parse_gpmf(data)


class TestBuildAcclDataframe:
    def test_builds_dataframe(self):
        streams = _load_streams()
        accl_streams = [s for s in streams if s.fourcc == "ACCL"]
        df = _build_accl_dataframe(accl_streams)
        assert not df.empty
        assert set(df.columns) >= {"ts_sec", "x", "y", "z", "magnitude"}

    def test_timestamps_monotonic(self):
        streams = _load_streams()
        accl_streams = [s for s in streams if s.fourcc == "ACCL"]
        df = _build_accl_dataframe(accl_streams)
        assert df["ts_sec"].is_monotonic_increasing

    def test_magnitude_is_sqrt_sum_squares(self):
        streams = _load_streams()
        accl_streams = [s for s in streams if s.fourcc == "ACCL"]
        df = _build_accl_dataframe(accl_streams)
        expected = np.sqrt(df["x"]**2 + df["y"]**2 + df["z"]**2)
        np.testing.assert_allclose(df["magnitude"], expected)

    def test_gravity_present_in_magnitude(self):
        """Magnitude should average around 9.8 m/s^2 when at rest."""
        streams = _load_streams()
        accl_streams = [s for s in streams if s.fourcc == "ACCL"]
        df = _build_accl_dataframe(accl_streams)
        mean_mag = df["magnitude"].mean()
        # Should be in the range of gravity (6-15 m/s^2) for a mix of activity
        assert 5 < mean_mag < 20, f"Mean magnitude {mean_mag} not near gravity"

    def test_empty_streams(self):
        df = _build_accl_dataframe([])
        assert df.empty


class TestBuildGpsDataframe:
    def test_builds_dataframe(self):
        streams = _load_streams()
        gps_streams = [s for s in streams if s.fourcc == "GPS5"]
        df = _build_gps_dataframe(gps_streams)
        assert not df.empty
        assert set(df.columns) >= {"ts_sec", "lat", "lon", "alt_m", "speed_2d_ms", "speed_mph"}

    def test_speed_conversion(self):
        """speed_mph should be speed_2d_ms * 2.237."""
        streams = _load_streams()
        gps_streams = [s for s in streams if s.fourcc == "GPS5"]
        df = _build_gps_dataframe(gps_streams)
        expected = df["speed_2d_ms"] * 2.237
        np.testing.assert_allclose(df["speed_mph"], expected)

    def test_empty_streams(self):
        df = _build_gps_dataframe([])
        assert df.empty


class TestBuildGyroDataframe:
    def test_builds_dataframe(self):
        streams = _load_streams()
        gyro_streams = [s for s in streams if s.fourcc == "GYRO"]
        df = _build_gyro_dataframe(gyro_streams)
        assert not df.empty
        assert set(df.columns) >= {"ts_sec", "x", "y", "z", "magnitude"}

    def test_timestamps_monotonic(self):
        streams = _load_streams()
        gyro_streams = [s for s in streams if s.fourcc == "GYRO"]
        df = _build_gyro_dataframe(gyro_streams)
        if not df.empty:
            assert df["ts_sec"].is_monotonic_increasing

    def test_magnitude_is_sqrt_sum_squares(self):
        streams = _load_streams()
        gyro_streams = [s for s in streams if s.fourcc == "GYRO"]
        df = _build_gyro_dataframe(gyro_streams)
        if not df.empty:
            expected = np.sqrt(df["x"]**2 + df["y"]**2 + df["z"]**2)
            np.testing.assert_allclose(df["magnitude"], expected)

    def test_empty_streams(self):
        df = _build_gyro_dataframe([])
        assert df.empty
