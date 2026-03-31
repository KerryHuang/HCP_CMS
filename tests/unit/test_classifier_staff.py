"""Tests for Classifier domain → handler resolution via Staff/Company tables."""

import pytest

from hcp_cms.core.classifier import Classifier
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Company, Staff
from hcp_cms.data.repositories import CompanyRepository, StaffRepository


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(tmp_path / "test.db")
    manager.initialize()
    yield manager
    manager.close()


@pytest.fixture
def db_with_company_staff(db):
    """插入 JILL（客服）並綁定到 ABC 公司（domain: abc.com.tw）。"""
    StaffRepository(db.connection).insert(
        Staff(staff_id="STAFF-001", name="JILL", email="jill@ares.com.tw", role="cs")
    )
    CompanyRepository(db.connection).insert(
        Company(company_id="COMP-001", name="ABC 公司", domain="abc.com.tw",
                cs_staff_id="STAFF-001")
    )
    return db


class TestClassifierDomainToHandler:
    def test_handler_resolved_from_sender_domain(self, db_with_company_staff):
        """寄件人 abc.com.tw 應自動設 handler = JILL。"""
        clf = Classifier(db_with_company_staff.connection)
        result = clf.classify(
            subject="系統問題",
            body="請幫忙處理",
            sender_email="customer@abc.com.tw",
            to_recipients=["hcpservice@ares.com.tw"],
        )
        assert result["handler"] == "JILL"

    def test_subject_tag_overrides_domain_handler(self, db_with_company_staff):
        """主旨含 (RD_TONY) 時，標記優先於 domain 查詢。"""
        clf = Classifier(db_with_company_staff.connection)
        result = clf.classify(
            subject="問題 (RD_TONY)",
            body="內容",
            sender_email="customer@abc.com.tw",
            to_recipients=["hcpservice@ares.com.tw"],
        )
        assert result["handler"] == "TONY"

    def test_no_handler_if_company_not_in_db(self, db_with_company_staff):
        """寄件人 domain 不在 companies 表時，handler 為 None。"""
        clf = Classifier(db_with_company_staff.connection)
        result = clf.classify(
            subject="問題",
            body="內容",
            sender_email="someone@unknown.com",
            to_recipients=["hcpservice@ares.com.tw"],
        )
        assert result["handler"] is None or result["handler"] == ""

    def test_no_handler_if_company_has_no_staff(self, db):
        """公司存在但未綁定客服時，handler 為 None。"""
        CompanyRepository(db.connection).insert(
            Company(company_id="COMP-002", name="XYZ 公司", domain="xyz.com.tw")
        )
        clf = Classifier(db.connection)
        result = clf.classify(
            subject="問題",
            body="內容",
            sender_email="someone@xyz.com.tw",
            to_recipients=["hcpservice@ares.com.tw"],
        )
        assert result["handler"] is None or result["handler"] == ""

    def test_subdomain_fallback(self, db_with_company_staff):
        """寄件人為子網域 mail.abc.com.tw 時，fallback 比對 abc.com.tw。"""
        clf = Classifier(db_with_company_staff.connection)
        result = clf.classify(
            subject="問題",
            body="內容",
            sender_email="user@mail.abc.com.tw",
            to_recipients=["hcpservice@ares.com.tw"],
        )
        assert result["handler"] == "JILL"
