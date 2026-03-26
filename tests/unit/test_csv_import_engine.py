"""Tests for CsvImportEngine."""

from __future__ import annotations

from hcp_cms.core.csv_import_engine import _parse_sent_time


class TestParseSentTime:
    def test_chinese_morning(self):
        result = _parse_sent_time("2026/3/2 (週一) 上午 09:27")
        assert result == "2026/03/02 09:27:00"

    def test_chinese_afternoon(self):
        result = _parse_sent_time("2026/3/2 (週一) 下午 03:25")
        assert result == "2026/03/02 15:25:00"

    def test_chinese_noon(self):
        # 下午 12:00 → 12:00（不加 12）
        result = _parse_sent_time("2026/3/2 (週一) 下午 12:00")
        assert result == "2026/03/02 12:00:00"

    def test_chinese_morning_noon(self):
        # 上午 12:00 → 00:00
        result = _parse_sent_time("2026/3/2 (週一) 上午 12:00")
        assert result == "2026/03/02 00:00:00"

    def test_iso_with_seconds(self):
        result = _parse_sent_time("2026/03/02 09:27:00")
        assert result == "2026/03/02 09:27:00"

    def test_iso_without_seconds(self):
        result = _parse_sent_time("2026/03/02 09:27")
        assert result == "2026/03/02 09:27:00"

    def test_date_only(self):
        result = _parse_sent_time("2026/03/02")
        assert result == "2026/03/02 00:00:00"

    def test_invalid_returns_none(self):
        result = _parse_sent_time("無效格式")
        assert result is None

    def test_empty_returns_none(self):
        result = _parse_sent_time("")
        assert result is None

    def test_none_returns_none(self):
        result = _parse_sent_time(None)
        assert result is None
