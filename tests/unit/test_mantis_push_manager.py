"""MantisPushManager 三模式測試（mock MantisClient）。"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hcp_cms.core.mantis_push import MantisPushManager
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, CaseMantisLink, Company, MantisTicket
from hcp_cms.data.repositories import (
    CaseMantisRepository,
    CaseRepository,
    CompanyRepository,
    MantisRepository,
)


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
    # 補 Company（format_case_header 需要 company name）
    CompanyRepository(db.connection).insert(
        Company(company_id="CO-1", name="測試公司", domain="test.com")
    )
    CaseRepository(db.connection).insert(
        Case(
            case_id="C-1",
            subject="印表機異常",
            progress="已聯絡客戶確認",
            priority="高",
            handler="YOGA",
            company_id="CO-1",
            sent_time="2026/05/04 16:46:00",
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
    # summary 為 format_case_header 輸出（含日期/星期/主旨；主旨優先，不再前加公司名）
    assert "印表機異常" in call_kwargs["summary"]
    assert "2026/5/4" in call_kwargs["summary"]
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

    CaseRepository(db.connection).insert(Case(
        case_id="C-M", subject="中", priority="中", handler="YOGA",
        company_id="CO-1", sent_time="2026/05/04 16:46:00",
    ))
    mgr.push_case_as_new_ticket("C-M", "S-YOGA")
    assert client.create_issue.call_args.kwargs["priority"] == "normal"

    CaseRepository(db.connection).insert(Case(
        case_id="C-L", subject="低", priority="低", handler="YOGA",
        company_id="CO-1", sent_time="2026/05/04 16:46:00",
    ))
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
    CaseRepository(db.connection).insert(Case(
        case_id="C-2", subject="A", handler="YOGA",
        company_id="CO-1", sent_time="2026/05/04 16:46:00",
    ))
    CaseRepository(db.connection).insert(Case(
        case_id="C-3", subject="B", handler="YOGA",
        company_id="CO-1", sent_time="2026/05/04 16:46:00",
    ))

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


# ============= format_case_header 整合 =============


def test_push_uses_formatted_summary(setup) -> None:
    """推送時 SOAP 收到的 summary 應為 format_case_header 的輸出（主旨優先，不前加公司名）。"""
    db = setup
    client = MagicMock()
    client.create_issue.return_value = "777"

    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    success, _ = mgr.push_case_as_new_ticket("C-1", "S-YOGA")
    assert success is True

    sent_summary = client.create_issue.call_args.kwargs["summary"]
    assert "2026/5/4" in sent_summary
    assert "(週一)" in sent_summary
    assert "下午 04:46" in sent_summary
    assert "印表機異常" in sent_summary
    # 公司名不再前加；主旨本身已可能含 【公司】 前綴
    assert "【測試公司】" not in sent_summary


def test_push_succeeds_without_company(setup) -> None:
    """case.company_id 為 None 也應成功 push（format_case_header 不再依賴公司名）。"""
    db = setup
    CaseRepository(db.connection).insert(
        Case(
            case_id="C-NO-COMPANY",
            subject="無公司案件",
            handler="YOGA",
            sent_time="2026/05/04 10:00:00",
        )
    )
    client = MagicMock()
    client.create_issue.return_value = "888"
    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    success, payload = mgr.push_case_as_new_ticket("C-NO-COMPANY", "S-YOGA")

    assert success is True
    assert payload == "888"
    sent_summary = client.create_issue.call_args.kwargs["summary"]
    assert "無公司案件" in sent_summary


# ============= description 用客戶來信 + custom_fields =============


def test_push_description_uses_first_customer_log(setup) -> None:
    """description 應為第一筆 direction=客戶來信 的 case_log content（list_by_case 為 ASC，第一筆是最舊）。"""
    from hcp_cms.data.models import CaseLog
    from hcp_cms.data.repositories import CaseLogRepository
    db = setup
    log_repo = CaseLogRepository(db.connection)
    log_repo.insert(CaseLog(
        log_id=log_repo.next_log_id(),
        case_id="C-1",
        direction="客戶來信",
        content="原始來信內容",
        logged_at="2026/05/04 09:00:00",
    ))
    log_repo.insert(CaseLog(
        log_id=log_repo.next_log_id(),
        case_id="C-1",
        direction="客戶來信",
        content="第二封補充來信",
        logged_at="2026/05/05 10:00:00",
    ))

    client = MagicMock()
    client.create_issue.return_value = "100"
    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    mgr.push_case_as_new_ticket("C-1", "S-YOGA")

    description = client.create_issue.call_args.kwargs["description"]
    assert "原始來信內容" in description
    assert "第二封補充來信" not in description
    assert "[HCP-CMS: C-1]" in description


def test_push_sends_contact_person_as_custom_field(setup) -> None:
    """contact_person 應作為 custom_field '客戶提問人員' 送進 SOAP。"""
    db = setup
    case_repo = CaseRepository(db.connection)
    case = case_repo.get_by_id("C-1")
    case.contact_person = "customer@xyz.com"
    case_repo.update(case)

    client = MagicMock()
    client.create_issue.return_value = "101"
    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    mgr.push_case_as_new_ticket("C-1", "S-YOGA")

    custom_fields = client.create_issue.call_args.kwargs.get("custom_fields")
    assert custom_fields == {"客戶提問人員": "customer@xyz.com"}


def test_push_omits_custom_field_when_no_contact_person(setup) -> None:
    """無 contact_person → 不送 custom_fields。"""
    db = setup
    case_repo = CaseRepository(db.connection)
    case = case_repo.get_by_id("C-1")
    case.contact_person = None
    case_repo.update(case)

    client = MagicMock()
    client.create_issue.return_value = "102"
    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    mgr.push_case_as_new_ticket("C-1", "S-YOGA")

    assert client.create_issue.call_args.kwargs.get("custom_fields") is None


# ============= thread-aware 批次推送 =============


class TestPushCasesThreadAware:
    """以 thread 為單位推送：root 建新 ticket，子案件成為 bugnote。"""

    def _make_thread(self, conn, root_id: str = "T-ROOT", child_ids: list[str] | None = None) -> None:
        """Helper：建立一個 thread（root + 多個 children）。"""
        case_repo = CaseRepository(conn)
        case_repo.insert(Case(
            case_id=root_id, subject="原始客戶問題", company_id="CO-1",
            sent_time="2026/05/01 09:00:00",
        ))
        for cid in (child_ids or []):
            case_repo.insert(Case(
                case_id=cid, subject="RE: 原始客戶問題", company_id="CO-1",
                sent_time="2026/05/05 14:30:00",
                linked_case_id=root_id,
            ))

    def test_single_case_no_thread_pushes_as_new_ticket(self, setup) -> None:
        """獨立案件（無 linked_case_id 也無子案件）→ 推為新 ticket，不產生 bugnote。"""
        db = setup
        client = MagicMock()
        client.create_issue.return_value = "9001"
        mgr = MantisPushManager(db.connection, client=client, project_id="218")

        results = mgr.push_cases_thread_aware(["C-1"], "S-YOGA")

        assert client.create_issue.call_count == 1
        assert client.add_note.call_count == 0
        assert any(r["action"] == "new_ticket" and r["case_id"] == "C-1" for r in results)

    def test_root_plus_children_one_ticket_plus_bugnotes(self, setup) -> None:
        """root + 2 個 children 同時選 → 1 張新 ticket + 2 則 bugnote。"""
        db = setup
        self._make_thread(db.connection, "T-ROOT", ["T-A", "T-B"])
        client = MagicMock()
        client.create_issue.return_value = "9002"
        client.add_note.return_value = "note-1"
        mgr = MantisPushManager(db.connection, client=client, project_id="218")

        mgr.push_cases_thread_aware(["T-ROOT", "T-A", "T-B"], "S-YOGA")

        assert client.create_issue.call_count == 1
        assert client.add_note.call_count == 2
        # 子案件也記為已連結 ticket（後續可同步、查 case_mantis）
        for cid in ("T-ROOT", "T-A", "T-B"):
            links = CaseMantisRepository(db.connection).list_by_case_id(cid)
            assert any(lk.ticket_id == "9002" for lk in links), f"{cid} 未連結 9002"

    def test_select_only_child_auto_includes_root(self, setup) -> None:
        """只選子案件，未選 root → 自動把 root 推為 ticket，子案件成 bugnote。"""
        db = setup
        self._make_thread(db.connection, "T-ROOT", ["T-A"])
        client = MagicMock()
        client.create_issue.return_value = "9003"
        client.add_note.return_value = "note-1"
        mgr = MantisPushManager(db.connection, client=client, project_id="218")

        results = mgr.push_cases_thread_aware(["T-A"], "S-YOGA")

        # root 自動推
        new_ticket_results = [r for r in results if r["action"] == "new_ticket"]
        assert len(new_ticket_results) == 1
        assert new_ticket_results[0]["case_id"] == "T-ROOT"
        # 子案件成 bugnote
        bugnote_results = [r for r in results if r["action"] == "bugnote"]
        assert len(bugnote_results) == 1
        assert bugnote_results[0]["case_id"] == "T-A"

    def test_root_already_linked_children_become_bugnotes_on_existing(self, setup) -> None:
        """root 已連結 Mantis ticket → 不重推 root，子案件附到既有 ticket。"""
        db = setup
        self._make_thread(db.connection, "T-ROOT", ["T-A"])
        _link_with_ticket(db.connection, "T-ROOT", "9999")
        client = MagicMock()
        client.add_note.return_value = "note-1"
        mgr = MantisPushManager(db.connection, client=client, project_id="218")

        mgr.push_cases_thread_aware(["T-ROOT", "T-A"], "S-YOGA")

        # 不再建新 ticket
        assert client.create_issue.call_count == 0
        # 子案件附到 9999
        assert client.add_note.call_count == 1
        assert client.add_note.call_args.kwargs["issue_id"] == "9999"
        # 子案件也建立 case_mantis 連結到 9999
        a_links = CaseMantisRepository(db.connection).list_by_case_id("T-A")
        assert any(lk.ticket_id == "9999" for lk in a_links)

    def test_skip_already_linked_child(self, setup) -> None:
        """子案件本身已連結別的 Mantis ticket → 跳過，不重推也不重 bugnote。"""
        db = setup
        self._make_thread(db.connection, "T-ROOT", ["T-A"])
        _link_with_ticket(db.connection, "T-A", "8888")  # T-A 已連結到別張 ticket
        client = MagicMock()
        client.create_issue.return_value = "9004"
        mgr = MantisPushManager(db.connection, client=client, project_id="218")

        results = mgr.push_cases_thread_aware(["T-ROOT", "T-A"], "S-YOGA")

        # root 仍推新
        assert client.create_issue.call_count == 1
        # T-A 跳過（不 add_note）
        assert client.add_note.call_count == 0
        skipped = [r for r in results if r["action"] == "skipped" and r["case_id"] == "T-A"]
        assert len(skipped) == 1

    def test_multiple_independent_threads(self, setup) -> None:
        """選兩個不同 thread 的案件 → 各建一張 ticket（不混在一起）。"""
        db = setup
        self._make_thread(db.connection, "T-ROOT-A", ["T-A1"])
        self._make_thread(db.connection, "T-ROOT-B", ["T-B1"])
        client = MagicMock()
        client.create_issue.side_effect = ["9005", "9006"]
        client.add_note.return_value = "note-x"
        mgr = MantisPushManager(db.connection, client=client, project_id="218")

        mgr.push_cases_thread_aware(
            ["T-ROOT-A", "T-A1", "T-ROOT-B", "T-B1"], "S-YOGA"
        )

        # 兩張新 ticket，兩則 bugnote
        assert client.create_issue.call_count == 2
        assert client.add_note.call_count == 2

    def test_empty_input_returns_empty(self, setup) -> None:
        db = setup
        client = MagicMock()
        mgr = MantisPushManager(db.connection, client=client, project_id="218")
        assert mgr.push_cases_thread_aware([], "S-YOGA") == []
        client.create_issue.assert_not_called()
        client.add_note.assert_not_called()


# ============= bugnote 文字格式 =============


class TestBugnoteText:
    """_build_bugnote_text 應含寄件者/收件者/內容等對話資訊。"""

    def test_bugnote_includes_contact_person(self, setup) -> None:
        """bugnote 應含 case.contact_person。"""
        db = setup
        case_repo = CaseRepository(db.connection)
        case = case_repo.get_by_id("C-1")
        case.contact_person = '"Jill" <jill@test.com>'
        case_repo.update(case)
        _link_with_ticket(db.connection, "C-1", "9999")
        client = MagicMock()
        client.add_note.return_value = "n-1"

        mgr = MantisPushManager(db.connection, client=client, project_id="218")
        mgr.push_case_as_bugnote("C-1", "S-YOGA")

        text = client.add_note.call_args.kwargs["text"]
        assert "Jill" in text
        assert "jill@test.com" in text

    def test_bugnote_includes_all_case_logs(self, setup) -> None:
        """bugnote 應含所有 case_logs（不只最新一筆），按時間排序顯示。"""
        from hcp_cms.data.models import CaseLog
        from hcp_cms.data.repositories import CaseLogRepository
        db = setup
        log_repo = CaseLogRepository(db.connection)
        log_repo.insert(CaseLog(
            log_id=log_repo.next_log_id(), case_id="C-1",
            direction="客戶來信", content="原始客戶問題：印表機無法列印",
            logged_at="2026/05/01 09:00:00",
        ))
        log_repo.insert(CaseLog(
            log_id=log_repo.next_log_id(), case_id="C-1",
            direction="HCP 信件回覆", content="已協助處理，請確認",
            logged_at="2026/05/04 16:46:00",
        ))
        _link_with_ticket(db.connection, "C-1", "9999")
        client = MagicMock()
        client.add_note.return_value = "n-1"

        mgr = MantisPushManager(db.connection, client=client, project_id="218")
        mgr.push_case_as_bugnote("C-1", "S-YOGA")

        text = client.add_note.call_args.kwargs["text"]
        # 兩筆 log 都要出現
        assert "原始客戶問題：印表機無法列印" in text
        assert "已協助處理，請確認" in text
        # direction 標籤都要出現
        assert "客戶來信" in text
        assert "HCP 信件回覆" in text

    def test_bugnote_excludes_mantis_push_logs(self, setup) -> None:
        """direction=Mantis 推送 的 log 不顯示（避免無限循環推送內容）。"""
        from hcp_cms.data.models import CaseLog
        from hcp_cms.data.repositories import CaseLogRepository
        db = setup
        log_repo = CaseLogRepository(db.connection)
        log_repo.insert(CaseLog(
            log_id=log_repo.next_log_id(), case_id="C-1",
            direction="Mantis 推送", content="不應顯示的內容",
            logged_at="2026/05/04 17:00:00",
        ))
        log_repo.insert(CaseLog(
            log_id=log_repo.next_log_id(), case_id="C-1",
            direction="客戶來信", content="應顯示的客戶內容",
            logged_at="2026/05/01 09:00:00",
        ))
        _link_with_ticket(db.connection, "C-1", "9999")
        client = MagicMock()
        client.add_note.return_value = "n-1"

        mgr = MantisPushManager(db.connection, client=client, project_id="218")
        mgr.push_case_as_bugnote("C-1", "S-YOGA")

        text = client.add_note.call_args.kwargs["text"]
        assert "應顯示的客戶內容" in text
        assert "不應顯示的內容" not in text
