"""Tests for the GPMF binary parser."""

from pathlib import Path

from shredfinder.gpmf_parser import SensorStream, parse_gpmf

TEST_DATA_DIR = Path(__file__).parent.parent


def _load_bin(name: str) -> bytes:
    return (TEST_DATA_DIR / name).read_bytes()


class TestParseGpmf:
    def test_parses_small_bin(self):
        streams = parse_gpmf(_load_bin("test_gpmf.bin"))
        assert len(streams) > 0

    def test_finds_accl_streams(self):
        streams = parse_gpmf(_load_bin("test_gpmf.bin"))
        accl = [s for s in streams if s.fourcc == "ACCL"]
        assert len(accl) >= 5, f"Expected at least 5 ACCL blocks, got {len(accl)}"
        # Each block should have ~200 samples at 200Hz
        for s in accl:
            assert len(s.samples) > 100

    def test_finds_gps5_streams(self):
        streams = parse_gpmf(_load_bin("test_gpmf.bin"))
        gps = [s for s in streams if s.fourcc == "GPS5"]
        assert len(gps) >= 5
        # GPS5 has 5 values: lat, lon, alt, speed_2d, speed_3d
        for s in gps:
            assert len(s.samples) > 0
            assert len(s.samples[0]) == 5

    def test_finds_gyro_streams(self):
        streams = parse_gpmf(_load_bin("test_gpmf.bin"))
        gyro = [s for s in streams if s.fourcc == "GYRO"]
        assert len(gyro) >= 5

    def test_finds_grav_streams(self):
        streams = parse_gpmf(_load_bin("test_gpmf.bin"))
        grav = [s for s in streams if s.fourcc == "GRAV"]
        assert len(grav) >= 5

    def test_stream_has_name(self):
        streams = parse_gpmf(_load_bin("test_gpmf.bin"))
        accl = [s for s in streams if s.fourcc == "ACCL"]
        assert accl[0].name == "Accelerometer"

    def test_scale_applied_to_accl(self):
        """ACCL values should be in m/s^2 after scaling — typical range is -20 to +20."""
        streams = parse_gpmf(_load_bin("test_gpmf.bin"))
        accl = [s for s in streams if s.fourcc == "ACCL"][0]
        for sample in accl.samples[:10]:
            for val in sample:
                assert -50 < val < 50, f"ACCL value {val} seems unscaled"

    def test_gps5_coordinates_reasonable(self):
        """GPS5 lat/lon should be in a plausible range after scaling."""
        streams = parse_gpmf(_load_bin("test_gpmf.bin"))
        gps = [s for s in streams if s.fourcc == "GPS5"][0]
        for sample in gps.samples[:5]:
            lat, lon = sample[0], sample[1]
            assert -90 <= lat <= 90, f"Latitude {lat} out of range"
            assert -180 <= lon <= 180, f"Longitude {lon} out of range"

    def test_parses_long_bin(self):
        """test_gpmf_long.bin should have more blocks."""
        streams = parse_gpmf(_load_bin("test_gpmf_long.bin"))
        accl = [s for s in streams if s.fourcc == "ACCL"]
        assert len(accl) > 10, f"Long bin should have many ACCL blocks, got {len(accl)}"

    def test_returns_sensor_stream_objects(self):
        streams = parse_gpmf(_load_bin("test_gpmf.bin"))
        for s in streams:
            assert isinstance(s, SensorStream)
            assert s.fourcc in {"ACCL", "GYRO", "GPS5", "GPS9", "GRAV", "MAGN"}

    def test_empty_data(self):
        streams = parse_gpmf(b"")
        assert streams == []

    def test_truncated_data(self):
        """Should not crash on truncated input."""
        data = _load_bin("test_gpmf.bin")[:50]
        streams = parse_gpmf(data)
        # May return empty or partial — just shouldn't crash
        assert isinstance(streams, list)
