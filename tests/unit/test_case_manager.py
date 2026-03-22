from pathlib import Path

import pytest

from hcp_cms.core.case_manager import CaseManager
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import ClassificationRule, Company
from hcp_cms.data.repositories import CaseRepository, CompanyRepository, RuleRepository


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def seeded_db(db: DatabaseManager) -> DatabaseManager:
    """DB with rules and companies for classification."""
    RuleRepository(db.connection).insert(
        ClassificationRule(rule_type="issue", pattern=r"bug|異常", value="BUG", priority=1)
    )
    RuleRepository(db.connection).insert(
        ClassificationRule(rule_type="error", pattern=r"薪資", value="薪資獎金計算", priority=1)
    )
    CompanyRepository(db.connection).insert(
        Company(company_id="C-ASE", name="日月光", domain="aseglobal.com")
    )
    return db


class TestCaseManager:
    def test_create_case(self, seeded_db):
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(
            subject="薪資計算異常",
            body="員工薪資有 bug",
            sender_email="user@aseglobal.com",
            sent_time="2026/03/20 09:00",
        )
        assert case.case_id.startswith("CS-")
        assert case.issue_type == "BUG"
        assert case.error_type == "薪資獎金計算"
        assert case.company_id == "C-ASE"

    def test_mark_replied(self, seeded_db):
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(subject="Test", body="body")
        mgr.mark_replied(case.case_id, "2026/03/20 12:00")

        updated = CaseRepository(seeded_db.connection).get_by_id(case.case_id)
        assert updated.status == "已回覆"
        assert updated.replied == "是"
        assert updated.actual_reply == "2026/03/20 12:00"

    def test_reopen_case(self, seeded_db):
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(subject="Test", body="body")
        mgr.mark_replied(case.case_id)
        mgr.reopen_case(case.case_id, "客戶再次來信")

        updated = CaseRepository(seeded_db.connection).get_by_id(case.case_id)
        assert updated.status == "處理中"
        assert updated.reply_count == 1
        assert "重開" in updated.notes

    def test_close_case(self, seeded_db):
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(subject="Test", body="body")
        mgr.close_case(case.case_id)

        updated = CaseRepository(seeded_db.connection).get_by_id(case.case_id)
        assert updated.status == "已完成"

    def test_dashboard_stats(self, seeded_db):
        mgr = CaseManager(seeded_db.connection)
        # Create cases
        c1 = mgr.create_case(subject="A", body="", sent_time="2026/03/10 09:00")
        c2 = mgr.create_case(subject="B", body="", sent_time="2026/03/15 10:00")
        mgr.create_case(subject="C", body="", sent_time="2026/03/20 14:00")

        mgr.mark_replied(c1.case_id, "2026/03/10 11:00")
        mgr.mark_replied(c2.case_id, "2026/03/16 10:00")

        stats = mgr.get_dashboard_stats(2026, 3)
        assert stats["total"] == 3
        assert stats["replied"] == 2
        assert stats["pending"] == 1  # c3 is still open
        assert stats["reply_rate"] == 66.7

    def test_frt_calculation(self, seeded_db):
        mgr = CaseManager(seeded_db.connection)
        c = mgr.create_case(subject="X", body="", sent_time="2026/03/20 09:00")
        mgr.mark_replied(c.case_id, "2026/03/20 12:00")

        stats = mgr.get_dashboard_stats(2026, 3)
        assert stats["avg_frt"] == 3.0  # 3 hours

    def test_frt_excludes_outliers(self, seeded_db):
        mgr = CaseManager(seeded_db.connection)
        c1 = mgr.create_case(subject="Normal", body="", sent_time="2026/03/10 09:00")
        mgr.mark_replied(c1.case_id, "2026/03/10 12:00")  # 3h

        c2 = mgr.create_case(subject="Outlier", body="", sent_time="2026/03/01 09:00")
        mgr.mark_replied(c2.case_id, "2026/03/31 09:00")  # 720h, excluded

        stats = mgr.get_dashboard_stats(2026, 3)
        assert stats["avg_frt"] == 3.0  # Only c1 counted

    def test_thread_detection_links_cases(self, seeded_db):
        mgr = CaseManager(seeded_db.connection)
        c1 = mgr.create_case(
            subject="薪資問題", body="original",
            sender_email="user@aseglobal.com", sent_time="2026/03/20 09:00"
        )
        # Reply from same company, same subject
        c2 = mgr.create_case(
            subject="RE: 薪資問題", body="follow up",
            sender_email="user@aseglobal.com", sent_time="2026/03/21 10:00"
        )

        repo = CaseRepository(seeded_db.connection)
        child = repo.get_by_id(c2.case_id)
        assert child.linked_case_id == c1.case_id
