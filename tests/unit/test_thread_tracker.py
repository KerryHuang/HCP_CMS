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
        assert ThreadTracker.clean_subject("FW: FW: 系統異常") == "FW: 系統異常"
        # Only removes first prefix; that's OK

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
