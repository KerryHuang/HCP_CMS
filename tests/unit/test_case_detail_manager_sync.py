"""測試 CaseDetailManager.sync_mantis_ticket() — 三態返回 + 欄位映射。"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from hcp_cms.core.case_detail_manager import CaseDetailManager, SyncResult
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, CaseLog, CaseMantisLink, MantisTicket
from hcp_cms.data.repositories import (
    CaseLogRepository,
    CaseMantisRepository,
    CaseRepository,
    MantisRepository,
)
from hcp_cms.services.mantis.base import MantisIssue, MantisNote


@pytest.fixture
def manager(tmp_path):
    db_path = tmp_path / "test.db"
    mgr = DatabaseManager(db_path)
    mgr.initialize()
    yield CaseDetailManager(mgr.connection)
    mgr.close()


@pytest.fixture
def db_with_case_and_ticket(tmp_path):
    """提供：DB + 一個 Case(C-1) + 連結到 ticket #9999。"""
    db = DatabaseManager(tmp_path / "t.db")
    db.initialize()
    case = Case(
        case_id="C-1",
        subject="測試案件",
        company_id=None,
        sent_time="2026/05/04 10:00:00",
    )
    CaseRepository(db.connection).insert(case)
    # mantis_tickets（case_mantis FK 依賴）
    MantisRepository(db.connection).upsert(MantisTicket(ticket_id="9999", summary=""))
    link = CaseMantisLink(case_id="C-1", ticket_id="9999")
    CaseMantisRepository(db.connection).insert(link)
    yield db, case, link
    db.close()


# ============= 既有 SUCCESS 路徑（升級為 tuple unpack） =============


def test_sync_maps_new_fields(manager):
    issue = MantisIssue(
        id="99001",
        summary="測試票",
        status="resolved",
        severity="major",
        reporter="林美麗",
        date_submitted="2026-01-15T10:00:00",
        target_version="v2.5.1",
        fixed_in_version="v2.5.2",
        description="詳細描述內容。",
        notes_list=[
            MantisNote(note_id="1", reporter="王小明", text="已修復", date_submitted="2026-01-20"),
        ],
        notes_count=1,
    )
    mock_client = MagicMock()
    mock_client.get_issue.return_value = issue

    result, ticket = manager.sync_mantis_ticket("99001", client=mock_client)

    assert result == SyncResult.SUCCESS
    assert ticket is not None
    assert ticket.severity == "major"
    assert ticket.reporter == "林美麗"
    assert ticket.planned_fix == "v2.5.1"
    assert ticket.actual_fix == "v2.5.2"
    assert ticket.description == "詳細描述內容。"
    assert ticket.notes_count == 1
    notes = json.loads(ticket.notes_json or "[]")
    assert notes[0]["text"] == "已修復"
    assert notes[0]["date_submitted"] == "2026-01-20"


# ============= SyncResult 三態 =============


def test_sync_returns_not_found_when_last_error_says_not_found(
    db_with_case_and_ticket,
):
    """client.get_issue 回 None 且 last_error 含 'not found' → NOT_FOUND。"""
    db, _case, _link = db_with_case_and_ticket
    mgr = CaseDetailManager(db.connection)
    client = MagicMock()
    client.get_issue.return_value = None
    client.last_error = "SOAP 錯誤：Issue #9999 not found"

    result, ticket = mgr.sync_mantis_ticket("9999", client=client)

    assert result == SyncResult.NOT_FOUND
    assert ticket is None


def test_sync_returns_error_when_connection_fails(db_with_case_and_ticket):
    """client.get_issue 回 None 且 last_error 為連線錯誤 → ERROR。"""
    db, _case, _link = db_with_case_and_ticket
    mgr = CaseDetailManager(db.connection)
    client = MagicMock()
    client.get_issue.return_value = None
    client.last_error = "連線失敗：HTTPSConnectionPool..."

    result, ticket = mgr.sync_mantis_ticket("9999", client=client)

    assert result == SyncResult.ERROR
    assert ticket is None


def test_sync_returns_error_when_client_is_none(db_with_case_and_ticket):
    """client=None → ERROR。"""
    db, _case, _link = db_with_case_and_ticket
    mgr = CaseDetailManager(db.connection)
    result, ticket = mgr.sync_mantis_ticket("9999", client=None)
    assert result == SyncResult.ERROR
    assert ticket is None


# ============= unlink_mantis_with_audit =============


def test_unlink_mantis_with_audit_removes_link_and_logs(
    db_with_case_and_ticket,
):
    """解除連結 + case_log 寫入 reason。"""
    db, case, _link = db_with_case_and_ticket
    mgr = CaseDetailManager(db.connection)

    # 先確認連結存在
    links_before = CaseMantisRepository(db.connection).get_tickets_for_case(case.case_id)
    assert "9999" in links_before

    mgr.unlink_mantis_with_audit(
        case.case_id, "9999",
        reason="Mantis 找不到此 ticket（同步時偵測）",
    )

    # 連結移除
    links_after = CaseMantisRepository(db.connection).get_tickets_for_case(case.case_id)
    assert "9999" not in links_after

    # case_log 多一筆
    logs = CaseLogRepository(db.connection).list_by_case(case.case_id)
    sync_logs = [log for log in logs if "Mantis" in (log.content or "") and "找不到" in (log.content or "")]
    assert len(sync_logs) == 1
    assert sync_logs[0].mantis_ref == "9999"
    assert sync_logs[0].logged_by == "system"


# ============= sync_bugnotes_outbound =============


def test_sync_outbound_pushes_eligible_logs(db_with_case_and_ticket):
    """推符合 direction 且 bugnote_id 為 NULL 的 case_logs。"""
    db, _case, _link = db_with_case_and_ticket
    log_repo = CaseLogRepository(db.connection)
    log_repo.insert(CaseLog(
        log_id=log_repo.next_log_id(),
        case_id="C-1",
        direction="內部討論",
        content="進度筆記 1",
        logged_at="2026/05/13 10:00:00",
    ))
    log_repo.insert(CaseLog(
        log_id=log_repo.next_log_id(),
        case_id="C-1",
        direction="HCP 信件回覆",
        content="已回覆客戶",
        logged_at="2026/05/13 11:00:00",
    ))

    client = MagicMock()
    client.add_note.side_effect = ["N-100", "N-101"]

    mgr = CaseDetailManager(db.connection)
    success, fail = mgr.sync_bugnotes_outbound("C-1", "9999", client)

    assert success == 2
    assert fail == 0

    logs = log_repo.list_by_case("C-1")
    push_logs = [log for log in logs if log.direction != "Mantis 推送"]
    bugnote_ids = {log.bugnote_id for log in push_logs if log.bugnote_id}
    assert "N-100" in bugnote_ids
    assert "N-101" in bugnote_ids


def test_sync_outbound_skips_non_pushable_directions(db_with_case_and_ticket):
    """客戶來信 / Mantis 推送 / Mantis bugnote 都不應推。"""
    db, _case, _link = db_with_case_and_ticket
    log_repo = CaseLogRepository(db.connection)
    for direction in ("客戶來信", "Mantis 推送", "Mantis bugnote"):
        log_repo.insert(CaseLog(
            log_id=log_repo.next_log_id(),
            case_id="C-1",
            direction=direction,
            content=f"{direction} 內容",
            logged_at="2026/05/13 10:00:00",
        ))

    client = MagicMock()
    mgr = CaseDetailManager(db.connection)
    success, fail = mgr.sync_bugnotes_outbound("C-1", "9999", client)

    assert success == 0
    assert fail == 0
    client.add_note.assert_not_called()


def test_sync_outbound_skips_already_synced(db_with_case_and_ticket):
    """bugnote_id 已寫的 case_log 不重推。"""
    db, _case, _link = db_with_case_and_ticket
    log_repo = CaseLogRepository(db.connection)
    log_repo.insert(CaseLog(
        log_id=log_repo.next_log_id(),
        case_id="C-1",
        direction="內部討論",
        content="已同步過",
        bugnote_id="N-999",
        logged_at="2026/05/13 10:00:00",
    ))

    client = MagicMock()
    mgr = CaseDetailManager(db.connection)
    success, fail = mgr.sync_bugnotes_outbound("C-1", "9999", client)

    assert success == 0
    assert fail == 0
    client.add_note.assert_not_called()


def test_sync_outbound_handles_soap_failure(db_with_case_and_ticket):
    """add_note 回 None 時 fail 計數 +1，不寫回 bugnote_id。"""
    db, _case, _link = db_with_case_and_ticket
    log_repo = CaseLogRepository(db.connection)
    log_repo.insert(CaseLog(
        log_id=log_repo.next_log_id(),
        case_id="C-1",
        direction="內部討論",
        content="會失敗",
        logged_at="2026/05/13 10:00:00",
    ))

    client = MagicMock()
    client.add_note.return_value = None
    client.last_error = "Issue locked"

    mgr = CaseDetailManager(db.connection)
    success, fail = mgr.sync_bugnotes_outbound("C-1", "9999", client)

    assert success == 0
    assert fail == 1

    logs = log_repo.list_by_case("C-1")
    push_logs = [log for log in logs if log.direction == "內部討論"]
    assert push_logs[0].bugnote_id is None


# ============= sync_bugnotes_inbound =============


def test_sync_inbound_pulls_new_bugnotes(db_with_case_and_ticket):
    """Mantis 端有的 note_id 不在 case_logs.bugnote_id → 插入新 case_log。"""
    db, _case, _link = db_with_case_and_ticket

    client = MagicMock()
    client.get_issue.return_value = MantisIssue(
        id="9999",
        summary="x",
        notes_list=[
            MantisNote(note_id="N-200", reporter="RD 王", text="RD 已修", date_submitted="2026/05/13"),
            MantisNote(note_id="N-201", reporter="RD 林", text="測試通過", date_submitted="2026/05/13"),
        ],
        notes_count=2,
    )

    mgr = CaseDetailManager(db.connection)
    pulled, fail = mgr.sync_bugnotes_inbound("C-1", "9999", client)

    assert pulled == 2
    assert fail == 0

    logs = CaseLogRepository(db.connection).list_by_case("C-1")
    inbound_logs = [log for log in logs if log.direction == "Mantis bugnote"]
    assert len(inbound_logs) == 2
    contents = {log.content for log in inbound_logs}
    assert "RD 已修" in contents
    assert "測試通過" in contents
    ids = {log.bugnote_id for log in inbound_logs}
    assert ids == {"N-200", "N-201"}


def test_sync_inbound_skips_existing_bugnote_id(db_with_case_and_ticket):
    """已有對應 bugnote_id 的 case_log 不重複插入。"""
    db, _case, _link = db_with_case_and_ticket
    log_repo = CaseLogRepository(db.connection)
    log_repo.insert(CaseLog(
        log_id=log_repo.next_log_id(),
        case_id="C-1",
        direction="Mantis bugnote",
        content="先前已存在",
        bugnote_id="N-300",
        logged_at="2026/05/12 09:00:00",
    ))

    client = MagicMock()
    client.get_issue.return_value = MantisIssue(
        id="9999", summary="x",
        notes_list=[
            MantisNote(note_id="N-300", reporter="RD", text="重複", date_submitted="2026/05/12"),
            MantisNote(note_id="N-301", reporter="RD", text="新的", date_submitted="2026/05/13"),
        ],
        notes_count=2,
    )

    mgr = CaseDetailManager(db.connection)
    pulled, fail = mgr.sync_bugnotes_inbound("C-1", "9999", client)

    assert pulled == 1
    inbound_logs = [log for log in log_repo.list_by_case("C-1") if log.direction == "Mantis bugnote"]
    assert len(inbound_logs) == 2
    new_log = next(log for log in inbound_logs if log.bugnote_id == "N-301")
    assert new_log.content == "新的"


def test_sync_inbound_handles_get_issue_failure(db_with_case_and_ticket):
    """client.get_issue 回 None → fail += 1，pulled = 0。"""
    db, _case, _link = db_with_case_and_ticket
    client = MagicMock()
    client.get_issue.return_value = None

    mgr = CaseDetailManager(db.connection)
    pulled, fail = mgr.sync_bugnotes_inbound("C-1", "9999", client)

    assert pulled == 0
    assert fail == 1
