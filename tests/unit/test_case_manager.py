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

    def test_mark_replied_increments_reply_count(self, seeded_db):
        """CS 標記已回覆時，reply_count 應 +1（參考舊版 _link_and_update_case）。"""
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(subject="Test", body="body")
        assert case.reply_count == 0
        mgr.mark_replied(case.case_id)

        updated = CaseRepository(seeded_db.connection).get_by_id(case.case_id)
        assert updated.reply_count == 1

    def test_reopen_case(self, seeded_db):
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(subject="Test", body="body")
        mgr.mark_replied(case.case_id)   # reply_count → 1
        mgr.reopen_case(case.case_id, "客戶再次來信")

        updated = CaseRepository(seeded_db.connection).get_by_id(case.case_id)
        assert updated.status == "處理中"
        # reopen 本身不應再 +1（舊版 _reopen_existing_case 不修改 reply_count）
        assert updated.reply_count == 1
        assert "重開" in updated.notes

    def test_reply_count_no_double_count_on_reopen(self, seeded_db):
        """客戶回覆已回覆案件時：link_to_parent +1 即可，reopen 不應再 +1。"""
        mgr = CaseManager(seeded_db.connection)
        repo = CaseRepository(seeded_db.connection)

        # 建立根案件並回覆
        root = mgr.create_case(
            subject="薪資問題", body="原始來信",
            sender_email="user@aseglobal.com",
        )
        mgr.mark_replied(root.case_id)  # reply_count → 1

        # 客戶再次來信（觸發 thread detection → link + reopen）
        child = mgr.create_case(
            subject="RE: 薪資問題", body="再次詢問",
            sender_email="user@aseglobal.com",
        )
        root_updated = repo.get_by_id(root.case_id)
        # link_to_parent 再 +1 → 共 2；不應因 reopen 又變 3
        assert root_updated.reply_count == 2
        assert child.linked_case_id == root.case_id

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

    def test_create_case_parses_filename_tags(self, seeded_db):
        """匯入 .msg 時，ISSUE#/handler/progress 應從檔名中解析。"""
        mgr = CaseManager(seeded_db.connection)
        filename = (
            "ISSUE_20260319_0017445_ 【欣興】表單開假問題"
            "(RD_JACKY)(待請JACKY安排修正).msg"
        )
        case = mgr.create_case(
            subject="RE: RE: 【欣興】表單開假問題",
            body="問題說明",
            sender_email="user@aseglobal.com",
            source_filename=filename,
        )
        assert case.notes and "ISSUE#0017445" in case.notes
        assert case.handler == "JACKY"
        assert case.progress == "待請JACKY安排修正"

    def test_create_case_email_subject_tags_when_no_filename(self, seeded_db):
        """無檔名時，仍能從 email 主旨本身解析 RD/進度標記。"""
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(
            subject="【問題】(RD_JACKY)(待確認)",
            body="",
        )
        assert case.handler == "JACKY"
        assert case.progress == "待確認"

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


class TestImportEmail:
    """測試 import_email() 智慧派送邏輯。"""

    @pytest.fixture
    def mgr(self, seeded_db):
        return CaseManager(seeded_db.connection)

    def test_customer_email_creates_case(self, mgr):
        """客戶發信 → 建立新案件，action 為 'created'。"""
        case, action = mgr.import_email(
            subject="薪資問題",
            body="員工薪資異常",
            sender_email="user@aseglobal.com",
            to_recipients=["hcpservice@ares.com.tw"],
            sent_time="2026/03/20 09:00",
        )
        assert action == "created"
        assert case is not None
        assert case.case_id.startswith("CS-")

    def test_our_reply_marks_parent_replied(self, mgr, seeded_db):
        """我方回覆 → 找到父案件並標記已回覆，action 為 'replied'。"""
        # 先建立父案件（客戶來信）
        parent, _ = mgr.import_email(
            subject="薪資計算問題",
            body="有異常",
            sender_email="user@aseglobal.com",
            to_recipients=["hcpservice@ares.com.tw"],
            sent_time="2026/03/20 09:00",
        )
        assert parent is not None

        # 我方回覆
        result_case, action = mgr.import_email(
            subject="RE: 薪資計算問題",
            body="已處理",
            sender_email="hcpservice@ares.com.tw",
            to_recipients=["user@aseglobal.com"],
            sent_time="2026/03/20 10:00",
        )
        assert action == "replied"
        assert result_case is not None
        assert result_case.case_id == parent.case_id

        # 確認父案件狀態更新
        from hcp_cms.data.repositories import CaseRepository
        updated = CaseRepository(seeded_db.connection).get_by_id(parent.case_id)
        assert updated.status == "已回覆"
        assert updated.reply_count == 1

    def test_our_reply_increments_reply_count(self, mgr, seeded_db):
        """我方每次回覆都應讓 reply_count +1。"""
        parent, _ = mgr.import_email(
            subject="問題追蹤",
            body="內容",
            sender_email="user@aseglobal.com",
            to_recipients=["hcpservice@ares.com.tw"],
            sent_time="2026/03/20 09:00",
        )

        mgr.import_email(
            subject="RE: 問題追蹤",
            body="第一次回覆",
            sender_email="hcpservice@ares.com.tw",
            to_recipients=["user@aseglobal.com"],
            sent_time="2026/03/20 10:00",
        )
        mgr.import_email(
            subject="RE: 問題追蹤",
            body="第二次回覆",
            sender_email="hcpservice@ares.com.tw",
            to_recipients=["user@aseglobal.com"],
            sent_time="2026/03/21 10:00",
        )

        from hcp_cms.data.repositories import CaseRepository
        updated = CaseRepository(seeded_db.connection).get_by_id(parent.case_id)
        assert updated.reply_count == 2

    def test_our_reply_no_parent_skipped(self, mgr):
        """我方回覆但找不到父案件 → action 為 'skipped'，case 為 None。"""
        case, action = mgr.import_email(
            subject="RE: 完全不存在的案件",
            body="回覆",
            sender_email="hcpservice@ares.com.tw",
            to_recipients=["user@aseglobal.com"],
            sent_time="2026/03/20 10:00",
        )
        assert action == "skipped"
        assert case is None
