"""CsvImportEngine 自訂欄位功能測試。"""
import csv
import tempfile
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.repositories import CaseRepository, CustomColumnRepository
from hcp_cms.core.csv_import_engine import CsvImportEngine, ConflictStrategy


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def engine(db: DatabaseManager) -> CsvImportEngine:
    return CsvImportEngine(db.connection)


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


class TestCreateCustomColumns:
    def test_creates_columns_and_returns_list(self, db: DatabaseManager, engine: CsvImportEngine):
        cols = engine.create_custom_columns([("備註欄", "特殊備註"), ("來源欄", "來源系統")])
        assert len(cols) == 2
        assert cols[0].col_key == "cx_1"
        assert cols[0].col_label == "特殊備註"
        assert cols[1].col_key == "cx_2"

    def test_columns_exist_in_db_after_create(self, db: DatabaseManager, engine: CsvImportEngine):
        engine.create_custom_columns([("備註欄", "特殊備註")])
        db_cols = {row[1] for row in db.connection.execute("PRAGMA table_info(cs_cases)")}
        assert "cx_1" in db_cols


class TestImportWithCustomCols:
    def test_import_fills_extra_field(self, db: DatabaseManager, engine: CsvImportEngine, tmp_path: Path):
        engine.create_custom_columns([("自訂欄位", "客製資訊")])

        csv_path = tmp_path / "test.csv"
        _write_csv(csv_path, [{
            "主旨": "測試案件",
            "寄件時間": "2026/03/26 10:00:00",
            "公司": "測試公司",
            "自訂欄位": "自訂值123",
        }])

        mapping = {
            "主旨": "subject",
            "寄件時間": "sent_time",
            "公司": "company_id",
            "自訂欄位": "cx_1",
        }
        result = engine.execute(csv_path, mapping, ConflictStrategy.SKIP)
        assert result.success == 1

        repo = CaseRepository(db.connection)
        cases = repo.list_all()
        assert len(cases) == 1
        assert cases[0].extra_fields.get("cx_1") == "自訂值123"

    def test_execute_reloads_case_repository(self, db: DatabaseManager, engine: CsvImportEngine, tmp_path: Path):
        engine.create_custom_columns([("標籤欄", "標籤")])
        csv_path = tmp_path / "test.csv"
        _write_csv(csv_path, [{
            "主旨": "案件A", "寄件時間": "2026/03/26 10:00:00",
            "公司": "公司A", "標籤欄": "tagX",
        }])
        mapping = {"主旨": "subject", "寄件時間": "sent_time",
                   "公司": "company_id", "標籤欄": "cx_1"}
        engine.execute(csv_path, mapping, ConflictStrategy.SKIP)

        cases = engine._case_repo.list_all()
        assert cases[0].extra_fields.get("cx_1") == "tagX"
