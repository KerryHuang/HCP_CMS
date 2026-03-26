"""CaseRepository extra_fields 相關測試。"""
from __future__ import annotations

from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.repositories import CaseRepository, CustomColumnRepository


@pytest.fixture
def db(tmp_db_path: Path):
    mgr = DatabaseManager(tmp_db_path)
    mgr.initialize()
    yield mgr
    mgr.close()


def _insert_case(conn, case_id="CS-2026-001"):
    conn.execute(
        "INSERT INTO cs_cases (case_id, subject, status, priority, replied,"
        " sent_time, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (case_id, "測試主旨", "處理中", "中", "否",
         "2026/03/26 10:00:00", "2026/03/26 10:00:00", "2026/03/26 10:00:00"),
    )
    conn.commit()


class TestRowToCaseWithNoCustomCols:
    def test_extra_fields_empty_when_no_custom_cols(self, db: DatabaseManager):
        _insert_case(db.connection)
        repo = CaseRepository(db.connection)
        case = repo.get_by_id("CS-2026-001")
        assert case is not None
        assert case.extra_fields == {}

    def test_list_all_extra_fields_empty(self, db: DatabaseManager):
        _insert_case(db.connection)
        repo = CaseRepository(db.connection)
        cases = repo.list_all()
        assert cases[0].extra_fields == {}


class TestRowToCaseWithCustomCols:
    def test_extra_fields_filled_after_add_column(self, db: DatabaseManager):
        ccr = CustomColumnRepository(db.connection)
        ccr.add_column_to_cases("cx_1")
        ccr.insert("cx_1", "客製欄A", 1)
        _insert_case(db.connection)
        db.connection.execute("UPDATE cs_cases SET cx_1='測試值A' WHERE case_id='CS-2026-001'")
        db.connection.commit()

        repo = CaseRepository(db.connection)
        case = repo.get_by_id("CS-2026-001")
        assert case is not None
        assert case.extra_fields["cx_1"] == "測試值A"

    def test_list_by_status_includes_extra_fields(self, db: DatabaseManager):
        ccr = CustomColumnRepository(db.connection)
        ccr.add_column_to_cases("cx_1")
        ccr.insert("cx_1", "客製欄A", 1)
        _insert_case(db.connection)
        db.connection.execute("UPDATE cs_cases SET cx_1='狀態值' WHERE case_id='CS-2026-001'")
        db.connection.commit()

        repo = CaseRepository(db.connection)
        cases = repo.list_by_status("處理中")
        assert cases[0].extra_fields["cx_1"] == "狀態值"

    def test_reload_custom_columns_picks_up_new_col(self, db: DatabaseManager):
        _insert_case(db.connection)
        repo = CaseRepository(db.connection)
        assert repo.get_by_id("CS-2026-001").extra_fields == {}

        ccr = CustomColumnRepository(db.connection)
        ccr.add_column_to_cases("cx_1")
        ccr.insert("cx_1", "動態欄", 1)
        db.connection.execute("UPDATE cs_cases SET cx_1='after_reload' WHERE case_id='CS-2026-001'")
        db.connection.commit()
        repo.reload_custom_columns()

        case = repo.get_by_id("CS-2026-001")
        assert case.extra_fields["cx_1"] == "after_reload"


class TestUpdateExtraField:
    def test_update_extra_field_persists(self, db: DatabaseManager):
        ccr = CustomColumnRepository(db.connection)
        ccr.add_column_to_cases("cx_1")
        ccr.insert("cx_1", "欄A", 1)
        _insert_case(db.connection)

        repo = CaseRepository(db.connection)
        repo.update_extra_field("CS-2026-001", "cx_1", "新值")

        case = repo.get_by_id("CS-2026-001")
        assert case.extra_fields["cx_1"] == "新值"

    def test_update_extra_field_raises_on_invalid_key(self, db: DatabaseManager):
        repo = CaseRepository(db.connection)
        with pytest.raises(ValueError, match="非法 col_key"):
            repo.update_extra_field("CS-2026-001", "bad", "x")
