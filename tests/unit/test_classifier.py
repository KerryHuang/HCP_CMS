"""Tests for Classifier."""

from pathlib import Path

import pytest

from hcp_cms.core.classifier import Classifier
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import ClassificationRule, Company
from hcp_cms.data.repositories import CompanyRepository, RuleRepository


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def seeded_db(db: DatabaseManager) -> DatabaseManager:
    """DB with sample classification rules and companies."""
    rule_repo = RuleRepository(db.connection)
    comp_repo = CompanyRepository(db.connection)

    # Product rules
    rule_repo.insert(ClassificationRule(rule_type="product", pattern=r"WebLogic|WLS", value="WebLogic", priority=1))
    rule_repo.insert(ClassificationRule(rule_type="product", pattern=r"ERP|企業資源", value="ERP", priority=2))
    # HCP is the default, no rule needed

    # Issue type rules
    rule_repo.insert(ClassificationRule(
        rule_type="issue", pattern=r"客制|客製|customize", value="客制需求", priority=0,
    ))
    rule_repo.insert(ClassificationRule(
        rule_type="issue", pattern=r"bug|錯誤|異常|Exception", value="BUG", priority=1,
    ))
    rule_repo.insert(ClassificationRule(rule_type="issue", pattern=r"新功能|新增|Add feature", value="NEW", priority=2))
    rule_repo.insert(ClassificationRule(rule_type="issue", pattern=r"請問|如何|怎麼", value="邏輯咨詢", priority=5))

    # Error type rules
    rule_repo.insert(ClassificationRule(rule_type="error", pattern=r"薪資|薪水|工資", value="薪資獎金計算", priority=1))
    rule_repo.insert(ClassificationRule(rule_type="error", pattern=r"請假|休假|假單", value="差勤請假管理", priority=2))

    # Priority rules
    rule_repo.insert(ClassificationRule(
        rule_type="priority", pattern=r"緊急|urgent|asap|\(急\)", value="高", priority=1,
    ))

    # Broadcast rules
    rule_repo.insert(ClassificationRule(
        rule_type="broadcast", pattern=r"維護客戶|更新公告|大PATCH", value="broadcast", priority=1,
    ))

    # Companies
    comp_repo.insert(Company(company_id="C-ASE", name="日月光集團", domain="aseglobal.com"))
    comp_repo.insert(Company(company_id="C-UNI", name="欣興電子", domain="unimicron.com"))

    return db


class TestClassifier:
    def test_classify_product_weblogic(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify("WebLogic server error", "The WLS instance crashed")
        assert result["system_product"] == "WebLogic"

    def test_classify_product_default_hcp(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify("薪資計算問題", "員工薪資有誤")
        assert result["system_product"] == "HCP"

    def test_classify_issue_type_bug(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify("系統異常回報", "程式出現 Exception")
        assert result["issue_type"] == "BUG"

    def test_classify_issue_type_custom(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify("客製化需求", "需要客制開發")
        assert result["issue_type"] == "客制需求"

    def test_classify_issue_type_default_oth(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify("一般通知", "無關鍵字")
        assert result["issue_type"] == "OTH"

    def test_classify_error_type(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify("薪資計算問題", "員工薪資有誤")
        assert result["error_type"] == "薪資獎金計算"

    def test_classify_error_type_default(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify("一般問題", "無關鍵字")
        assert result["error_type"] == "人事資料管理"

    def test_classify_priority_high(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify("(急)薪資問題", "urgent fix needed")
        assert result["priority"] == "高"

    def test_classify_priority_default_medium(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify("一般問題", "正常處理")
        assert result["priority"] == "中"

    def test_classify_broadcast(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify("【HCP維護客戶】大PATCH更新通知", "系統更新公告")
        assert result["is_broadcast"] is True

    def test_classify_not_broadcast(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify("薪資問題", "正常信件")
        assert result["is_broadcast"] is False

    def test_classify_company_exact_domain(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify("Test", "Body", "user@aseglobal.com")
        assert result["company_id"] == "C-ASE"

    def test_classify_company_subdomain_fallback(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify("Test", "Body", "user@mail.aseglobal.com")
        assert result["company_id"] == "C-ASE"

    def test_classify_company_unknown(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify("Test", "Body", "user@unknown.com")
        assert result["company_id"] is None

    def test_classify_company_no_email(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify("Test", "Body", "")
        assert result["company_id"] is None

    def test_classify_first_match_wins(self, seeded_db):
        """客制需求 has priority 0, so it should win over BUG (priority 1)."""
        c = Classifier(seeded_db.connection)
        result = c.classify("客製化功能異常", "customize this bug")
        assert result["issue_type"] == "客制需求"  # priority 0 wins


class TestSubjectTagParser:
    """測試主旨標記自動解析。"""

    SUBJECT = (
        "ISSUE_20260319_0017445_ 【欣興】表單開假問題~請協助確認回傳 0005 "
        "員工編號特別假類別不允許重复(RD_JACKY)(待請JACKY安排修正)"
    )

    def test_parse_issue_number(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify(self.SUBJECT, "")
        assert result.get("issue_number") == "0017445"

    def test_parse_rd_handler(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify(self.SUBJECT, "")
        assert result.get("handler") == "JACKY"

    def test_parse_progress_from_last_bracket(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify(self.SUBJECT, "")
        assert result.get("progress") == "待請JACKY安排修正"

    def test_no_issue_number_when_absent(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify("一般主旨 問題描述", "")
        assert result.get("issue_number") is None

    def test_no_rd_tag_when_absent(self, seeded_db):
        c = Classifier(seeded_db.connection)
        result = c.classify("一般主旨 無標記", "")
        # handler 應來自 DB 規則或為 None
        assert result.get("handler") is None

    def test_multiple_rd_takes_first(self, seeded_db):
        """多個 RD 標記時取第一個。"""
        c = Classifier(seeded_db.connection)
        result = c.classify("問題(RD_JACKY)(RD_PENGYI)(待確認)", "")
        assert result.get("handler") == "JACKY"

    def test_progress_only_last_non_rd_bracket(self, seeded_db):
        """只取最後一個非 RD 括號內容。"""
        c = Classifier(seeded_db.connection)
        result = c.classify("問題(RD_JACKY)(第一段說明)(最終說明)", "")
        assert result.get("progress") == "最終說明"
