"""Integration tests for core business logic layer."""

from pathlib import Path

import pytest

from hcp_cms.core.case_manager import CaseManager
from hcp_cms.core.kms_engine import KMSEngine
from hcp_cms.core.report_engine import ReportEngine
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import ClassificationRule, Company, Synonym
from hcp_cms.data.repositories import (
    CaseRepository,
    CompanyRepository,
    RuleRepository,
    SynonymRepository,
)


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_path / "core_integration.db")
    db.initialize()

    # Seed classification rules
    rule_repo = RuleRepository(db.connection)
    rule_repo.insert(ClassificationRule(rule_type="issue", pattern=r"bug|異常|錯誤", value="BUG", priority=1))
    rule_repo.insert(ClassificationRule(rule_type="issue", pattern=r"請問|如何|怎麼", value="邏輯咨詢", priority=5))
    rule_repo.insert(ClassificationRule(rule_type="error", pattern=r"薪資|薪水", value="薪資獎金計算", priority=1))
    rule_repo.insert(ClassificationRule(rule_type="error", pattern=r"請假|休假", value="差勤請假管理", priority=2))
    rule_repo.insert(ClassificationRule(rule_type="priority", pattern=r"緊急|urgent", value="高", priority=1))

    # Seed company
    CompanyRepository(db.connection).insert(
        Company(company_id="C-ASE", name="日月光", domain="aseglobal.com")
    )

    # Seed synonyms
    syn_repo = SynonymRepository(db.connection)
    syn_repo.insert(Synonym(word="薪水", synonym="薪資", group_name="薪資相關"))

    yield db
    db.close()


class TestEmailToCaseToQAWorkflow:
    """Simulate: email arrives → classify → create case → auto-extract QA → search KMS."""

    def test_full_workflow(self, db: DatabaseManager) -> None:
        case_mgr = CaseManager(db.connection)
        kms = KMSEngine(db.connection)

        # 1. Create case from "email"
        # Subject starts with "薪資" so jieba tokenizes it as its own token,
        # enabling FTS search to find it later.
        case = case_mgr.create_case(
            subject="薪資計算有問題怎麼處理",
            body="員工薪資出現 bug，金額計算有誤，請問如何解決",
            sender_email="user@aseglobal.com",
            sent_time="2026/03/20 09:00",
            contact_person="王大明",
            handler="JILL",
        )

        assert case.company_id == "C-ASE"
        assert case.issue_type == "BUG"  # body contains "bug" which matches priority=1 rule first
        assert case.error_type == "薪資獎金計算"

        # 2. Auto-extract QA from case
        qa = kms.auto_extract_qa(case, company_domain="aseglobal.com", company_aliases=["日月光"])
        assert qa is not None
        assert qa.source == "email"
        assert qa.source_case_id == case.case_id
        # QA should be anonymized
        assert "aseglobal.com" not in qa.question

        # 3. Search KMS should find the QA
        results = kms.search("薪資")
        assert len(results) > 0

        # 4. Mark case replied
        case_mgr.mark_replied(case.case_id, "2026/03/20 12:00")

        # 5. Check dashboard stats
        stats = case_mgr.get_dashboard_stats(2026, 3)
        assert stats["total"] >= 1
        assert stats["replied"] >= 1


class TestThreadTrackingWorkflow:
    """Simulate: original email → reply → re-reply (thread detection + reopen)."""

    def test_thread_workflow(self, db: DatabaseManager) -> None:
        case_mgr = CaseManager(db.connection)
        case_repo = CaseRepository(db.connection)

        # 1. Original email
        original = case_mgr.create_case(
            subject="薪資設定問題",
            body="計算有誤",
            sender_email="user@aseglobal.com",
            sent_time="2026/03/20 09:00",
        )

        # 2. CS replies
        case_mgr.mark_replied(original.case_id, "2026/03/20 12:00")

        # 3. Customer replies back (thread detection should link and reopen)
        reply = case_mgr.create_case(
            subject="RE: 薪資設定問題",
            body="問題仍然存在",
            sender_email="user@aseglobal.com",
            sent_time="2026/03/21 10:00",
        )

        # Verify thread linking
        reply_case = case_repo.get_by_id(reply.case_id)
        assert reply_case.linked_case_id == original.case_id

        # Verify original was reopened
        original_updated = case_repo.get_by_id(original.case_id)
        assert original_updated.status == "處理中"
        assert original_updated.reply_count >= 1


class TestReportGenerationWithRealData:
    """Create cases, then generate tracking table and monthly report."""

    def test_report_workflow(self, db: DatabaseManager, tmp_path: Path) -> None:
        case_mgr = CaseManager(db.connection)

        # Create several cases
        case_mgr.create_case(
            subject="薪資異常", body="bug",
            sender_email="a@aseglobal.com", sent_time="2026/03/10 09:00",
        )
        c2 = case_mgr.create_case(
            subject="請假問題", body="如何設定",
            sender_email="b@aseglobal.com", sent_time="2026/03/15 10:00",
        )
        case_mgr.mark_replied(c2.case_id, "2026/03/15 14:00")

        engine = ReportEngine(db.connection)

        # Generate tracking table
        tracking = engine.generate_tracking_table(2026, 3, tmp_path / "tracking.xlsx")
        assert tracking.exists()

        # Generate monthly report
        report = engine.generate_monthly_report(2026, 3, tmp_path / "report.xlsx")
        assert report.exists()

        # Verify report content
        import openpyxl
        wb = openpyxl.load_workbook(str(report))
        ws = wb["月報摘要"]
        total = ws.cell(row=2, column=2).value
        assert total >= 2
        wb.close()
