"""Tests for CsvImportEngine."""

from __future__ import annotations

from pathlib import Path

import pytest

from hcp_cms.core.csv_import_engine import ConflictStrategy, CsvImportEngine, _parse_sent_time
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
            "問題狀態,主旨\n".encode("utf-8-sig") + "待確認,測試\n".encode()
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


class TestPreview:
    def _write_csv(self, tmp_path: Path, rows: list[str]) -> Path:
        csv_file = tmp_path / "cases.csv"
        content = "問題狀態,寄件時間,公司,聯絡人,主旨\n" + "\n".join(rows)
        csv_file.write_text(content, encoding="utf-8")
        return csv_file

    def test_all_new(self, db: DatabaseManager, tmp_path: Path):
        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,達爾,王小明,測試主旨1",
            "已回覆,2026/03/02 10:00,博大,李小花,測試主旨2",
        ])
        engine = CsvImportEngine(db.connection)
        mapping = {
            "問題狀態": "status", "寄件時間": "sent_time",
            "公司": "company_id", "聯絡人": "contact_person", "主旨": "subject",
        }
        preview = engine.preview(csv_file, mapping)
        assert preview.total == 2
        assert preview.new_count == 2
        assert preview.conflict_count == 0

    def test_partial_conflict(self, db: DatabaseManager, tmp_path: Path):
        # 先插入一筆相同 case_id 的資料（第一列會產生 CS-202603-001）
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject, status) VALUES (?, ?, ?)",
            ("CS-202603-001", "既有案件", "已完成")
        )
        db.connection.commit()

        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,達爾,王小明,測試主旨1",
            "已回覆,2026/03/02 10:00,博大,李小花,測試主旨2",
        ])
        engine = CsvImportEngine(db.connection)
        mapping = {
            "問題狀態": "status", "寄件時間": "sent_time",
            "公司": "company_id", "聯絡人": "contact_person", "主旨": "subject",
        }
        preview = engine.preview(csv_file, mapping)
        assert preview.total == 2
        assert preview.conflict_count == 1
        assert preview.new_count == 1


class TestExecuteSkip:
    def _write_csv(self, tmp_path: Path, rows: list[str]) -> Path:
        csv_file = tmp_path / "cases.csv"
        content = "問題狀態,寄件時間,公司,聯絡人,主旨,技術協助人員2\n" + "\n".join(rows)
        csv_file.write_text(content, encoding="utf-8")
        return csv_file

    @pytest.fixture
    def mapping(self):
        return {
            "問題狀態": "status", "寄件時間": "sent_time",
            "公司": "company_id", "聯絡人": "contact_person",
            "主旨": "subject", "技術協助人員2": "notes",
        }

    def test_inserts_new_cases(self, db: DatabaseManager, tmp_path: Path, mapping):
        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,達爾,王小明,測試主旨,",
        ])
        engine = CsvImportEngine(db.connection)
        result = engine.execute(csv_file, mapping, ConflictStrategy.SKIP)
        assert result.success == 1
        assert result.failed == 0
        case = db.connection.execute(
            "SELECT * FROM cs_cases WHERE case_id = 'CS-202603-001'"
        ).fetchone()
        assert case is not None
        assert case["subject"] == "測試主旨"
        assert case["source"] == "csv_import"

    def test_auto_creates_company(self, db: DatabaseManager, tmp_path: Path, mapping):
        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,新客戶,王小明,主旨,",
        ])
        engine = CsvImportEngine(db.connection)
        engine.execute(csv_file, mapping, ConflictStrategy.SKIP)
        company = db.connection.execute(
            "SELECT * FROM companies WHERE company_id = '新客戶'"
        ).fetchone()
        assert company is not None

    def test_company_idempotent(self, db: DatabaseManager, tmp_path: Path, mapping):
        # 同一公司出現兩次，只建一筆
        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,達爾,王小明,主旨1,",
            "已回覆,2026/03/02 10:00,達爾,李小花,主旨2,",
        ])
        engine = CsvImportEngine(db.connection)
        engine.execute(csv_file, mapping, ConflictStrategy.SKIP)
        count = db.connection.execute(
            "SELECT COUNT(*) FROM companies WHERE company_id = '達爾'"
        ).fetchone()[0]
        assert count == 1

    def test_blank_company_no_company_record(self, db: DatabaseManager, tmp_path: Path, mapping):
        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,,王小明,主旨,",
        ])
        engine = CsvImportEngine(db.connection)
        engine.execute(csv_file, mapping, ConflictStrategy.SKIP)
        case = db.connection.execute("SELECT company_id FROM cs_cases").fetchone()
        assert case["company_id"] is None

    def test_skips_on_conflict(self, db: DatabaseManager, tmp_path: Path, mapping):
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject, status) VALUES (?, ?, ?)",
            ("CS-202603-001", "既有", "已完成")
        )
        db.connection.commit()
        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,達爾,王小明,新主旨,",
        ])
        engine = CsvImportEngine(db.connection)
        result = engine.execute(csv_file, mapping, ConflictStrategy.SKIP)
        assert result.skipped == 1
        assert result.success == 0
        # 原資料未被改變
        case = db.connection.execute(
            "SELECT subject FROM cs_cases WHERE case_id = 'CS-202603-001'"
        ).fetchone()
        assert case["subject"] == "既有"

    def test_invalid_sent_time_skipped(self, db: DatabaseManager, tmp_path: Path, mapping):
        csv_file = self._write_csv(tmp_path, [
            "待確認,無效日期,達爾,王小明,主旨,",
        ])
        engine = CsvImportEngine(db.connection)
        result = engine.execute(csv_file, mapping, ConflictStrategy.SKIP)
        assert result.failed == 1
        assert "sent_time 格式錯誤" in result.errors[0]

    def test_tech2_appended_to_notes(self, db: DatabaseManager, tmp_path: Path, mapping):
        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,達爾,王小明,主旨,技術王",
        ])
        engine = CsvImportEngine(db.connection)
        engine.execute(csv_file, mapping, ConflictStrategy.SKIP)
        case = db.connection.execute("SELECT notes FROM cs_cases").fetchone()
        assert "【技術協助2】技術王" in (case["notes"] or "")

    def test_empty_subject_skipped(self, db: DatabaseManager, tmp_path: Path, mapping):
        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,達爾,王小明,,",  # subject 為空
        ])
        engine = CsvImportEngine(db.connection)
        result = engine.execute(csv_file, mapping, ConflictStrategy.SKIP)
        assert result.failed == 1
        assert "subject 為空" in result.errors[0]


class TestExecuteOverwrite:
    def _write_csv(self, tmp_path: Path, subject: str, tech2: str = "") -> Path:
        csv_file = tmp_path / "cases.csv"
        content = (
            "問題狀態,寄件時間,公司,聯絡人,主旨,技術協助人員2\n"
            f"待確認,2026/03/01 09:00,達爾,王小明,{subject},{tech2}"
        )
        csv_file.write_text(content, encoding="utf-8")
        return csv_file

    @pytest.fixture
    def mapping(self):
        return {
            "問題狀態": "status", "寄件時間": "sent_time",
            "公司": "company_id", "聯絡人": "contact_person",
            "主旨": "subject", "技術協助人員2": "notes",
        }

    def test_overwrites_subject(self, db: DatabaseManager, tmp_path: Path, mapping):
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject, status, created_at) VALUES (?, ?, ?, ?)",
            ("CS-202603-001", "舊主旨", "已完成", "2025/01/01 00:00:00")
        )
        db.connection.commit()
        csv_file = self._write_csv(tmp_path, "新主旨")
        engine = CsvImportEngine(db.connection)
        result = engine.execute(csv_file, mapping, ConflictStrategy.OVERWRITE)
        assert result.overwritten == 1
        case = db.connection.execute(
            "SELECT subject, created_at FROM cs_cases WHERE case_id = 'CS-202603-001'"
        ).fetchone()
        assert case["subject"] == "新主旨"
        assert case["created_at"] == "2025/01/01 00:00:00"  # created_at 保留

    def test_overwrite_tech2_replaces_old(self, db: DatabaseManager, tmp_path: Path):
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject, status, notes) VALUES (?, ?, ?, ?)",
            ("CS-202603-001", "主旨", "待確認", "原備註\n【技術協助2】舊技術員")
        )
        db.connection.commit()
        csv_file = tmp_path / "c.csv"
        csv_file.write_text(
            "問題狀態,寄件時間,公司,聯絡人,主旨,技術協助人員2\n"
            "待確認,2026/03/01 09:00,達爾,王小明,主旨,新技術員",
            encoding="utf-8"
        )
        mapping = {
            "問題狀態": "status", "寄件時間": "sent_time",
            "公司": "company_id", "聯絡人": "contact_person",
            "主旨": "subject", "技術協助人員2": "notes",
        }
        engine = CsvImportEngine(db.connection)
        engine.execute(csv_file, mapping, ConflictStrategy.OVERWRITE)
        case = db.connection.execute("SELECT notes FROM cs_cases").fetchone()
        assert "新技術員" in (case["notes"] or "")
        assert "舊技術員" not in (case["notes"] or "")
