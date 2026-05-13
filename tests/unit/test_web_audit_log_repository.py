"""WebAuditLogRepository CRUD 測試。"""
import re
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.repositories import WebAuditLogRepository


@pytest.fixture
def repo(tmp_path: Path):
    db = DatabaseManager(tmp_path / "test.db")
    db.initialize()
    yield WebAuditLogRepository(db.connection)
    db.close()


def test_insert_and_list_by_case(repo: WebAuditLogRepository) -> None:
    repo.insert(staff_id="S001", case_id="C-1", field_name="status")
    repo.insert(staff_id="S002", case_id="C-1", field_name="handler")
    repo.insert(staff_id="S001", case_id="C-2", field_name="status")

    rows = repo.list_by_case_id("C-1")
    assert len(rows) == 2
    assert {r.staff_id for r in rows} == {"S001", "S002"}
    assert {r.field_name for r in rows} == {"status", "handler"}


def test_list_by_staff_id(repo: WebAuditLogRepository) -> None:
    repo.insert(staff_id="S001", case_id="C-1", field_name="status")
    repo.insert(staff_id="S001", case_id="C-2", field_name="progress")
    repo.insert(staff_id="S002", case_id="C-1", field_name="handler")

    rows = repo.list_by_staff_id("S001")
    assert len(rows) == 2


def test_list_all_ordered_desc(repo: WebAuditLogRepository) -> None:
    repo.insert(staff_id="S001", case_id="C-1", field_name="first")
    repo.insert(staff_id="S001", case_id="C-1", field_name="second")
    repo.insert(staff_id="S001", case_id="C-1", field_name="third")

    rows = repo.list_all(limit=10)
    # id DESC，最新 insert 在前
    assert [r.field_name for r in rows] == ["third", "second", "first"]


def test_occurred_at_format(repo: WebAuditLogRepository) -> None:
    repo.insert(staff_id="S001", case_id="C-1", field_name="status")
    rows = repo.list_by_case_id("C-1")
    assert re.match(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}$", rows[0].occurred_at)
