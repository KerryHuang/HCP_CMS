"""Web Portal 端到端流程測試（mock Mantis client）。"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, Company, Staff
from hcp_cms.data.repositories import (
    CaseRepository,
    CompanyRepository,
    StaffRepository,
    WebAuditLogRepository,
)
from hcp_cms.web.audit import AuditLogger
from hcp_cms.web.auth import WebAuthManager
from hcp_cms.core.mantis_push import MantisPushManager
from hcp_cms.web.visibility import CaseVisibilityFilter


@pytest.fixture
def full_setup(tmp_path: Path):
    db = DatabaseManager(tmp_path / "t.db")
    db.initialize()
    StaffRepository(db.connection).insert(
        Staff(staff_id="S-YOGA", name="YOGA", email="y@x.com", role="cs")
    )
    CompanyRepository(db.connection).insert(
        Company(company_id="CO-A", name="A", domain="a.com", cs_staff_id="S-YOGA")
    )
    CaseRepository(db.connection).insert(
        Case(
            case_id="C-100",
            subject="印表機問題",
            handler="YOGA",
            company_id="CO-A",
            priority="高",
        )
    )
    yield db
    db.close()


def test_full_flow_login_to_mantis_push(full_setup) -> None:
    """端到端：登入 → 列案 → 推 Mantis → 稽核 → 推 bugnote。"""
    db = full_setup
    auth = WebAuthManager(db.connection)
    visibility = CaseVisibilityFilter(db.connection)

    # 1. 登入
    staff = auth.get_staff_by_id("S-YOGA")
    assert staff is not None

    # 2. 列案件
    cases = visibility.visible_cases(staff)
    assert any(c.case_id == "C-100" for c in cases)

    # 3. 推送 Mantis（建新 ticket）
    client = MagicMock()
    client.create_issue.return_value = "555"
    pusher = MantisPushManager(db.connection, client, project_id="218")
    success, ticket_id = pusher.push_case_as_new_ticket("C-100", "S-YOGA")
    assert success is True
    assert ticket_id == "555"

    # 4. 稽核紀錄存在
    audit_rows = WebAuditLogRepository(db.connection).list_by_case_id("C-100")
    assert any(r.field_name == "mantis_push" for r in audit_rows)

    # 5. 再推一次應失敗（已連結）
    success, msg = pusher.push_case_as_new_ticket("C-100", "S-YOGA")
    assert success is False
    assert "已連結" in msg

    # 6. 推為 bugnote
    client.add_note.return_value = "note-1"
    success, note_id = pusher.push_case_as_bugnote("C-100", "S-YOGA")
    assert success is True
    assert note_id == "note-1"


def test_audit_logger_field_change_isolated_from_mantis(full_setup) -> None:
    """log_field_change 不影響 case_logs，只進 web_audit_log。"""
    db = full_setup
    audit = AuditLogger(db.connection)

    audit.log_field_change("S-YOGA", "C-100", "status")
    audit.log_field_change("S-YOGA", "C-100", "handler")

    audit_rows = WebAuditLogRepository(db.connection).list_by_case_id("C-100")
    assert len(audit_rows) == 2

    from hcp_cms.data.repositories import CaseLogRepository
    logs = CaseLogRepository(db.connection).list_by_case("C-100")
    assert len(logs) == 0
