"""Tests for CsvImportEngine."""

from __future__ import annotations

from pathlib import Path

import pytest

from hcp_cms.core.csv_import_engine import CsvImportEngine, _parse_sent_time
from hcp_cms.data.database import DatabaseManager


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


class TestParseHeaders:
    def test_utf8_csv(self, tmp_path: Path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("問題狀態,主旨,寄件時間\n待確認,測試,2026/01/01\n", encoding="utf-8")
        engine = CsvImportEngine.__new__(CsvImportEngine)
        headers = engine.parse_headers(csv_file)
        assert headers == ["問題狀態", "主旨", "寄件時間"]

    def test_utf8_bom_csv(self, tmp_path: Path):
        csv_file = tmp_path / "test_bom.csv"
        csv_file.write_bytes(
            "問題狀態,主旨\n".encode("utf-8-sig") + "待確認,測試\n".encode("utf-8")
        )
        engine = CsvImportEngine.__new__(CsvImportEngine)
        headers = engine.parse_headers(csv_file)
        assert headers[0] == "問題狀態"  # BOM 已移除

    def test_big5_csv(self, tmp_path: Path):
        csv_file = tmp_path / "test_big5.csv"
        csv_file.write_bytes("問題狀態,主旨\n".encode("big5"))
        engine = CsvImportEngine.__new__(CsvImportEngine)
        headers = engine.parse_headers(csv_file)
        assert "問題狀態" in headers

    def test_invalid_encoding_raises(self, tmp_path: Path):
        csv_file = tmp_path / "test_bad.csv"
        csv_file.write_bytes(b"\xff\xfe\x00\x01\x02")  # 無效編碼
        engine = CsvImportEngine.__new__(CsvImportEngine)
        with pytest.raises(ValueError, match="無法識別編碼"):
            engine.parse_headers(csv_file)


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


class TestNextCaseId:
    def test_first_id_for_month(self, db: DatabaseManager):
        engine = CsvImportEngine(db.connection)
        base: dict[str, int] = {}
        result = engine._next_case_id("202510", base)
        assert result == "CS-202510-001"

    def test_sequential_ids_same_month(self, db: DatabaseManager):
        engine = CsvImportEngine(db.connection)
        base: dict[str, int] = {}
        id1 = engine._next_case_id("202510", base)
        id2 = engine._next_case_id("202510", base)
        id3 = engine._next_case_id("202510", base)
        assert id1 == "CS-202510-001"
        assert id2 == "CS-202510-002"
        assert id3 == "CS-202510-003"

    def test_different_months_independent(self, db: DatabaseManager):
        engine = CsvImportEngine(db.connection)
        base: dict[str, int] = {}
        id_oct = engine._next_case_id("202510", base)
        id_nov = engine._next_case_id("202511", base)
        assert id_oct == "CS-202510-001"
        assert id_nov == "CS-202511-001"

    def test_continues_from_existing_max(self, db: DatabaseManager):
        # 先插入既有記錄
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject, status) VALUES (?, ?, ?)",
            ("CS-202510-007", "舊案件", "已完成")
        )
        db.connection.commit()
        engine = CsvImportEngine(db.connection)
        base: dict[str, int] = {}
        result = engine._next_case_id("202510", base)
        assert result == "CS-202510-008"

    def test_old_format_does_not_interfere(self, db: DatabaseManager):
        # 插入舊格式 CS-YYYY-NNN，不應影響 CS-YYYYMM-NNN 流水號
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject, status) VALUES (?, ?, ?)",
            ("CS-2025-010", "舊格式案件", "已完成")
        )
        db.connection.commit()
        engine = CsvImportEngine(db.connection)
        base: dict[str, int] = {}
        result = engine._next_case_id("202510", base)
        assert result == "CS-202510-001"  # 不受舊格式影響
