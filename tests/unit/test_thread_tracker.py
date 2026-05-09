from pathlib import Path

import pytest

from hcp_cms.core.thread_tracker import ThreadTracker
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, Company
from hcp_cms.data.repositories import CaseRepository, CompanyRepository


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


class TestThreadTracker:
    def test_clean_subject_re(self):
        assert ThreadTracker.clean_subject("RE: 薪資問題") == "薪資問題"

    def test_clean_subject_fw(self):
        assert ThreadTracker.clean_subject("FW: FW: 系統異常") == "系統異常"
        # Recursively removes all prefixes

    def test_clean_subject_chinese(self):
        assert ThreadTracker.clean_subject("回覆: 請假問題") == "請假問題"

    def test_clean_subject_no_prefix(self):
        assert ThreadTracker.clean_subject("薪資問題") == "薪資問題"

    def test_subjects_match(self):
        assert ThreadTracker.subjects_match("RE: 薪資問題", "薪資問題") is True

    def test_subjects_not_match(self):
        assert ThreadTracker.subjects_match("薪資問題", "請假問題") is False

    def test_find_parent_by_subject(self, db):
        CompanyRepository(db.connection).insert(Company(company_id="C1", name="TestCo", domain="testco.com"))
        repo = CaseRepository(db.connection)
        repo.insert(Case(case_id="CS-2026-001", subject="薪資計算問題", company_id="C1", status="處理中"))

        tracker = ThreadTracker(db.connection)
        parent = tracker.find_thread_parent("C1", "RE: 薪資計算問題")
        assert parent is not None
        assert parent.case_id == "CS-2026-001"

    def test_find_parent_no_match(self, db):
        tracker = ThreadTracker(db.connection)
        parent = tracker.find_thread_parent("C1", "完全不同的主旨")
        assert parent is None

    def test_find_parent_different_company(self, db):
        CompanyRepository(db.connection).insert(Company(company_id="C1", name="TestCo", domain="testco.com"))
        repo = CaseRepository(db.connection)
        repo.insert(Case(case_id="CS-2026-001", subject="薪資問題", company_id="C1", status="處理中"))

        tracker = ThreadTracker(db.connection)
        parent = tracker.find_thread_parent("C2", "RE: 薪資問題")  # Different company
        assert parent is None

    def test_link_to_parent(self, db):
        repo = CaseRepository(db.connection)
        repo.insert(Case(case_id="CS-2026-001", subject="Original", reply_count=0))
        repo.insert(Case(case_id="CS-2026-002", subject="RE: Original"))

        tracker = ThreadTracker(db.connection)
        tracker.link_to_parent("CS-2026-002", "CS-2026-001")

        child = repo.get_by_id("CS-2026-002")
        parent = repo.get_by_id("CS-2026-001")
        assert child.linked_case_id == "CS-2026-001"
        assert parent.reply_count == 1

    # ------------------------------------------------------------------
    # in_reply_to 精確比對
    # ------------------------------------------------------------------
    def test_find_parent_by_in_reply_to(self, db):
        """in_reply_to 直接比對父案件 message_id，優先於主旨比對。"""
        CompanyRepository(db.connection).insert(Company(company_id="C1", name="TestCo", domain="testco.com"))
        repo = CaseRepository(db.connection)
        repo.insert(Case(
            case_id="CS-2026-001",
            subject="薪資問題",
            company_id="C1",
            status="處理中",
            message_id="<abc123@mail.example.com>",
        ))

        tracker = ThreadTracker(db.connection)
        parent = tracker.find_thread_parent(
            company_id=None,
            subject="完全不同的主旨",
            in_reply_to="<abc123@mail.example.com>",
        )
        assert parent is not None
        assert parent.case_id == "CS-2026-001"

    def test_find_parent_by_in_reply_to_beats_subject(self, db):
        """in_reply_to 比對優先於 company+subject 比對。"""
        CompanyRepository(db.connection).insert(Company(company_id="C1", name="TestCo", domain="testco.com"))
        CompanyRepository(db.connection).insert(Company(company_id="C2", name="OtherCo", domain="other.com"))
        repo = CaseRepository(db.connection)
        # 兩個案件主旨相同，但 in_reply_to 指向 C2 的案件
        repo.insert(Case(
            case_id="CS-2026-001", subject="系統問題", company_id="C1",
            status="處理中", message_id="<msg001@mail>",
        ))
        repo.insert(Case(
            case_id="CS-2026-002", subject="系統問題", company_id="C2",
            status="處理中", message_id="<msg002@mail>",
        ))

        tracker = ThreadTracker(db.connection)
        parent = tracker.find_thread_parent(
            company_id="C1",
            subject="RE: 系統問題",
            in_reply_to="<msg002@mail>",
        )
        # in_reply_to 指向 CS-2026-002，不是 company+subject 比對的 CS-2026-001
        assert parent is not None
        assert parent.case_id == "CS-2026-002"

    # ------------------------------------------------------------------
    # 無 company_id 時 subject-only fallback
    # ------------------------------------------------------------------
    def test_find_parent_no_company_fallback_by_subject(self, db):
        """company_id 為 None 時，應 fallback 以主旨比對所有開放案件。"""
        repo = CaseRepository(db.connection)
        repo.insert(Case(
            case_id="CS-2026-001",
            subject="離職同仁年假結算問題",
            company_id=None,
            status="處理中",
        ))

        tracker = ThreadTracker(db.connection)
        parent = tracker.find_thread_parent(
            company_id=None,
            subject="RE: 離職同仁年假結算問題",
        )
        assert parent is not None
        assert parent.case_id == "CS-2026-001"

    def test_find_parent_no_company_no_match(self, db):
        """company_id 為 None 且主旨不符時，回傳 None。"""
        repo = CaseRepository(db.connection)
        repo.insert(Case(
            case_id="CS-2026-001",
            subject="薪資問題",
            company_id=None,
            status="處理中",
        ))

        tracker = ThreadTracker(db.connection)
        parent = tracker.find_thread_parent(company_id=None, subject="請假申請問題")
        assert parent is None

    def test_find_parent_no_company_ignores_closed(self, db):
        """subject-only fallback 不匹配已完成案件（僅限開放中）。"""
        repo = CaseRepository(db.connection)
        repo.insert(Case(
            case_id="CS-2026-001",
            subject="薪資問題",
            company_id=None,
            status="已完成",
        ))

        tracker = ThreadTracker(db.connection)
        parent = tracker.find_thread_parent(company_id=None, subject="RE: 薪資問題")
        assert parent is None
