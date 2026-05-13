"""MantisPushManager 三模式測試（mock MantisClient）。"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, CaseMantisLink, MantisTicket
from hcp_cms.data.repositories import (
    CaseMantisRepository,
    CaseRepository,
    MantisRepository,
)
from hcp_cms.core.mantis_push import MantisPushManager


def _link_with_ticket(conn, case_id: str, ticket_id: str) -> None:
    """Helper：插入 mantis_tickets 後再 link case_mantis（避免 FK 錯誤）。"""
    MantisRepository(conn).upsert(MantisTicket(ticket_id=ticket_id, summary=""))
    CaseMantisRepository(conn).insert(
        CaseMantisLink(case_id=case_id, ticket_id=ticket_id)
    )


@pytest.fixture
def setup(tmp_path: Path):
    db = DatabaseManager(tmp_path / "t.db")
    db.initialize()
    CaseRepository(db.connection).insert(
        Case(
            case_id="C-1",
            subject="印表機異常",
            progress="已聯絡客戶確認",
            priority="高",
            handler="YOGA",
        )
    )
    yield db
    db.close()


# ============= 模式 (a) 單筆推新 ticket =============


def test_push_case_as_new_ticket_success(setup) -> None:
    db = setup
    client = MagicMock()
    client.create_issue.return_value = "12345"

    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    success, payload = mgr.push_case_as_new_ticket("C-1", "S-YOGA")
    assert success is True
    assert payload == "12345"

    # 確認寫入 case_mantis
    links = CaseMantisRepository(db.connection).list_by_case_id("C-1")
    assert len(links) == 1
    assert links[0].ticket_id == "12345"

    # 確認 SOAP 帶入正確欄位
    call_kwargs = client.create_issue.call_args.kwargs
    assert call_kwargs["project_id"] == "218"
    assert call_kwargs["summary"] == "印表機異常"
    assert "[HCP-CMS: C-1]" in call_kwargs["description"]
    assert "已聯絡客戶確認" in call_kwargs["description"]
    assert call_kwargs["priority"] == "high"  # 高→high
    assert call_kwargs["handler"] == "YOGA"
    assert call_kwargs["category"] == "General"  # POC 發現 category 必填


def test_push_case_as_new_ticket_priority_mapping(setup) -> None:
    db = setup
    client = MagicMock()
    client.create_issue.return_value = "1"
    mgr = MantisPushManager(db.connection, client=client, project_id="218")

    CaseRepository(db.connection).insert(Case(case_id="C-M", subject="中", priority="中", handler="YOGA"))
    mgr.push_case_as_new_ticket("C-M", "S-YOGA")
    assert client.create_issue.call_args.kwargs["priority"] == "normal"

    CaseRepository(db.connection).insert(Case(case_id="C-L", subject="低", priority="低", handler="YOGA"))
    mgr.push_case_as_new_ticket("C-L", "S-YOGA")
    assert client.create_issue.call_args.kwargs["priority"] == "low"


def test_push_case_as_new_ticket_already_linked_fails(setup) -> None:
    db = setup
    _link_with_ticket(db.connection, case_id="C-1", ticket_id="9999")
    client = MagicMock()
    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    success, payload = mgr.push_case_as_new_ticket("C-1", "S-YOGA")
    assert success is False
    assert "已連結" in payload
    client.create_issue.assert_not_called()


def test_push_case_as_new_ticket_case_not_found(setup) -> None:
    db = setup
    client = MagicMock()
    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    success, payload = mgr.push_case_as_new_ticket("C-NONEXIST", "S-YOGA")
    assert success is False
    assert "不存在" in payload
    client.create_issue.assert_not_called()


def test_push_case_as_new_ticket_works_for_closed_case(setup) -> None:
    """已結案案件若先前未連結 Mantis，仍應可建新 ticket（補建歷史紀錄）。"""
    db = setup
    # 把 C-1 標為 已結案
    case_repo = CaseRepository(db.connection)
    case = case_repo.get_by_id("C-1")
    case.status = "已結案"
    case_repo.update(case)

    client = MagicMock()
    client.create_issue.return_value = "888"
    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    success, payload = mgr.push_case_as_new_ticket("C-1", "S-YOGA")

    assert success is True
    assert payload == "888"
    # 狀態保持 已結案，不被推送動作影響
    assert case_repo.get_by_id("C-1").status == "已結案"


def test_push_case_as_new_ticket_soap_failure_does_not_write_link(setup) -> None:
    db = setup
    client = MagicMock()
    client.create_issue.return_value = None
    client.last_error = "Mantis 拒絕連線"

    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    success, payload = mgr.push_case_as_new_ticket("C-1", "S-YOGA")
    assert success is False
    assert "Mantis 拒絕連線" in payload

    links = CaseMantisRepository(db.connection).list_by_case_id("C-1")
    assert len(links) == 0


# ============= 模式 (c) 推 bugnote =============


def test_push_case_as_bugnote_success(setup) -> None:
    db = setup
    _link_with_ticket(db.connection, case_id="C-1", ticket_id="9999")
    client = MagicMock()
    client.add_note.return_value = "note-456"

    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    success, payload = mgr.push_case_as_bugnote("C-1", "S-YOGA")

    assert success is True
    assert payload == "note-456"
    call_kwargs = client.add_note.call_args.kwargs
    assert call_kwargs["issue_id"] == "9999"
    assert "已聯絡客戶確認" in call_kwargs["text"]


def test_push_case_as_bugnote_not_linked_fails(setup) -> None:
    db = setup
    client = MagicMock()
    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    success, payload = mgr.push_case_as_bugnote("C-1", "S-YOGA")
    assert success is False
    assert "尚未連結" in payload
    client.add_note.assert_not_called()


def test_push_case_as_bugnote_soap_failure(setup) -> None:
    db = setup
    _link_with_ticket(db.connection, case_id="C-1", ticket_id="9999")
    client = MagicMock()
    client.add_note.return_value = None
    client.last_error = "Issue locked"

    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    success, payload = mgr.push_case_as_bugnote("C-1", "S-YOGA")
    assert success is False
    assert "Issue locked" in payload


# ============= 模式 (b) 批次 =============


def test_push_cases_batch_mixed_results(setup) -> None:
    db = setup
    CaseRepository(db.connection).insert(Case(case_id="C-2", subject="A", handler="YOGA"))
    CaseRepository(db.connection).insert(Case(case_id="C-3", subject="B", handler="YOGA"))

    # C-3 已連結 → 應 skip
    _link_with_ticket(db.connection, case_id="C-3", ticket_id="EXISTING-1")

    client = MagicMock()
    # C-1 成功，C-2 失敗，C-3 略過
    client.create_issue.side_effect = ["111", None]
    client.last_error = "SOAP 錯誤"

    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    results = mgr.push_cases_batch(
        case_ids=["C-1", "C-2", "C-3"],
        operator_staff_id="S-YOGA",
    )

    by_id = {r[0]: r for r in results}
    assert by_id["C-1"][1] == "success"
    assert by_id["C-1"][2] == "111"
    assert by_id["C-2"][1] == "failed"
    assert "SOAP 錯誤" in by_id["C-2"][2]
    assert by_id["C-3"][1] == "skipped"
    assert "已連結" in by_id["C-3"][2]


def test_push_cases_batch_empty_list(setup) -> None:
    db = setup
    client = MagicMock()
    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    results = mgr.push_cases_batch([], "S-YOGA")
    assert results == []
    client.create_issue.assert_not_called()
