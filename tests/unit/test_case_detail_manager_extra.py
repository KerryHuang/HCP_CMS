"""CaseDetailManager.update_extra_field 測試。"""
from __future__ import annotations

from pathlib import Path

import pytest

from hcp_cms.core.case_detail_manager import CaseDetailManager
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.repositories import CaseRepository, CustomColumnRepository


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


def _setup(db: DatabaseManager) -> None:
    ccr = CustomColumnRepository(db.connection)
    ccr.add_column_to_cases("cx_1")
    ccr.insert("cx_1", "客製欄", 1)
    db.connection.execute(
        "INSERT INTO cs_cases (case_id, subject, status, priority,"
        " sent_time, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (
            "CS-2026-001", "主旨", "處理中", "中",
            "2026/03/26 10:00:00", "2026/03/26 10:00:00", "2026/03/26 10:00:00",
        ),
    )
    db.connection.commit()


class TestUpdateExtraField:
    def test_delegates_to_repository(self, db: DatabaseManager):
        _setup(db)
        mgr = CaseDetailManager(db.connection)
        mgr.update_extra_field("CS-2026-001", "cx_1", "測試值")

        repo = CaseRepository(db.connection)
        case = repo.get_by_id("CS-2026-001")
        assert case.extra_fields.get("cx_1") == "測試值"

    def test_raises_on_invalid_col_key(self, db: DatabaseManager):
        _setup(db)
        mgr = CaseDetailManager(db.connection)
        with pytest.raises(ValueError):
            mgr.update_extra_field("CS-2026-001", "invalid", "x")
