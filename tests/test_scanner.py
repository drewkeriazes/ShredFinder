"""Tests for the footage scanner module."""

import tempfile
from pathlib import Path

import pytest

from shredfinder.scanner import scan_footage


class TestScanFootage:
    def test_finds_mp4_files(self, tmp_path):
        (tmp_path / "GH010001.MP4").write_bytes(b"\x00" * 100)
        (tmp_path / "GH010002.MP4").write_bytes(b"\x00" * 200)
        results = scan_footage(tmp_path)
        assert len(results) == 2
        assert results[0]["filename"] == "GH010001.MP4"

    def test_skips_non_mp4(self, tmp_path):
        (tmp_path / "GH010001.MP4").write_bytes(b"\x00" * 100)
        (tmp_path / "GH010001.LRV").write_bytes(b"\x00" * 50)
        (tmp_path / "GH010001.THM").write_bytes(b"\x00" * 10)
        (tmp_path / "photo.JPG").write_bytes(b"\x00" * 30)
        results = scan_footage(tmp_path)
        assert len(results) == 1

    def test_skips_empty_mp4(self, tmp_path):
        (tmp_path / "GH010001.MP4").write_bytes(b"\x00" * 100)
        (tmp_path / "empty.MP4").write_bytes(b"")
        results = scan_footage(tmp_path)
        assert len(results) == 1

    def test_raises_on_no_mp4(self, tmp_path):
        (tmp_path / "readme.txt").write_text("hi")
        with pytest.raises(FileNotFoundError, match="No MP4"):
            scan_footage(tmp_path)

    def test_raises_on_missing_dir(self):
        with pytest.raises(FileNotFoundError):
            scan_footage("/nonexistent/dir/12345")

    def test_case_insensitive_extension(self, tmp_path):
        (tmp_path / "video.mp4").write_bytes(b"\x00" * 100)
        results = scan_footage(tmp_path)
        assert len(results) == 1

    def test_size_human_format(self, tmp_path):
        (tmp_path / "big.MP4").write_bytes(b"\x00" * 2048)
        results = scan_footage(tmp_path)
        assert "KB" in results[0]["size_human"]
