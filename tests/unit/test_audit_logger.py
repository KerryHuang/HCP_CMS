"""AuditLogger 雙寫測試。"""
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case
from hcp_cms.data.repositories import (
    CaseLogRepository,
    CaseRepository,
    WebAuditLogRepository,
)
from hcp_cms.web.audit import AuditLogger


@pytest.fixture
def setup(tmp_path: Path):
    db = DatabaseManager(tmp_path / "t.db")
    db.initialize()
    CaseRepository(db.connection).insert(Case(case_id="C-1", subject="test"))
    yield db
    db.close()


def test_log_field_change_writes_audit_log(setup) -> None:
    db = setup
    logger = AuditLogger(db.connection)
    logger.log_field_change(staff_id="S001", case_id="C-1", field_name="status")
    rows = WebAuditLogRepository(db.connection).list_by_case_id("C-1")
    assert len(rows) == 1
    assert rows[0].field_name == "status"


def test_log_field_change_does_not_write_case_log(setup) -> None:
    db = setup
    logger = AuditLogger(db.connection)
    logger.log_field_change(staff_id="S001", case_id="C-1", field_name="status")
    logs = CaseLogRepository(db.connection).list_by_case("C-1")
    assert len(logs) == 0


def test_log_mantis_push_writes_both(setup) -> None:
    db = setup
    logger = AuditLogger(db.connection)
    logger.log_mantis_push(
        staff_id="S001",
        case_id="C-1",
        ticket_id="9999",
        mode="new_ticket",
    )

    audit_rows = WebAuditLogRepository(db.connection).list_by_case_id("C-1")
    assert len(audit_rows) == 1
    assert audit_rows[0].field_name == "mantis_push"

    case_logs = CaseLogRepository(db.connection).list_by_case("C-1")
    assert len(case_logs) == 1
    assert case_logs[0].direction == "Mantis 推送"
    assert case_logs[0].mantis_ref == "9999"
    assert "9999" in (case_logs[0].content or "")
    assert "new_ticket" in (case_logs[0].content or "")


def test_log_mantis_push_bugnote_mode(setup) -> None:
    db = setup
    logger = AuditLogger(db.connection)
    logger.log_mantis_push(
        staff_id="S001",
        case_id="C-1",
        ticket_id="9999",
        mode="bugnote",
    )
    case_logs = CaseLogRepository(db.connection).list_by_case("C-1")
    assert "bugnote" in (case_logs[0].content or "")
