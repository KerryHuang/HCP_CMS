"""D-2：已結案案件客戶回信時的行為。"""
from pathlib import Path

import pytest

from hcp_cms.core.case_manager import CaseManager
from hcp_cms.core.thread_tracker import ThreadTracker
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, Company
from hcp_cms.data.repositories import (
    CaseLogRepository,
    CaseRepository,
    CompanyRepository,
)


@pytest.fixture
def db(tmp_path: Path):
    d = DatabaseManager(tmp_path / "t.db")
    d.initialize()
    yield d
    d.close()


def _make_closed_parent_case(conn) -> str:
    """準備一個 已結案 parent case + 對應 Company。"""
    CompanyRepository(conn).insert(
        Company(company_id="CO-1", name="ABC", domain="abc.com")
    )
    repo = CaseRepository(conn)
    case = Case(
        case_id="C-PARENT",
        subject="印表機異常",
        company_id="CO-1",
        status="已結案",
        message_id="<msg-001@abc.com>",
        sent_time="2026/05/01 10:00:00",
    )
    repo.insert(case)
    return case.case_id


def test_thread_tracker_finds_closed_parent(db) -> None:
    """ThreadTracker 必須能找到 已結案 case 作為 parent。"""
    _make_closed_parent_case(db.connection)
    tracker = ThreadTracker(db.connection)
    parent = tracker.find_thread_parent(
        company_id="CO-1",
        subject="Re: 印表機異常",
        in_reply_to=None,
    )
    assert parent is not None
    assert parent.case_id == "C-PARENT"


def test_customer_reply_to_closed_does_not_create_new_case(db) -> None:
    """已結案 parent 收客戶回信時，不建新子案件，返回 parent。"""
    _make_closed_parent_case(db.connection)
    mgr = CaseManager(db.connection)
    before_count = len(CaseRepository(db.connection).list_all())
    result = mgr.create_case(
        subject="Re: 印表機異常",
        body="客戶再次來信",
        sender_email="customer@abc.com",
        message_id="<msg-002@abc.com>",
        in_reply_to="<msg-001@abc.com>",
        sent_time="2026/05/13 10:00:00",
    )
    after_count = len(CaseRepository(db.connection).list_all())
    # 案件數量沒變（沒建新 case）
    assert after_count == before_count
    # 回傳 parent
    assert result.case_id == "C-PARENT"


def test_customer_reply_to_closed_adds_case_log(db) -> None:
    """已結案 parent 收客戶回信時，加一筆 case_log 到 parent。"""
    _make_closed_parent_case(db.connection)
    mgr = CaseManager(db.connection)
    mgr.create_case(
        subject="Re: 印表機異常",
        body="客戶補充：依然有問題",
        sender_email="customer@abc.com",
        message_id="<msg-002@abc.com>",
        in_reply_to="<msg-001@abc.com>",
        sent_time="2026/05/13 10:00:00",
    )
    logs = CaseLogRepository(db.connection).list_by_case("C-PARENT")
    matching = [
        log for log in logs
        if log.direction == "客戶來信" and "依然有問題" in (log.content or "")
    ]
    assert len(matching) >= 1


def test_customer_reply_to_closed_does_not_change_status(db) -> None:
    """已結案 parent 收客戶回信後，狀態仍為 已結案。"""
    _make_closed_parent_case(db.connection)
    mgr = CaseManager(db.connection)
    mgr.create_case(
        subject="Re: 印表機異常",
        body="再次回信",
        sender_email="customer@abc.com",
        message_id="<msg-003@abc.com>",
        in_reply_to="<msg-001@abc.com>",
        sent_time="2026/05/13 10:00:00",
    )
    parent = CaseRepository(db.connection).get_by_id("C-PARENT")
    assert parent.status == "已結案"
