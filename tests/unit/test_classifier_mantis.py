"""TDD — Classifier 應從主旨解析 Mantis ISSUE 資訊。"""

from __future__ import annotations

import pytest

from hcp_cms.core.classifier import Classifier
from hcp_cms.data.database import DatabaseManager


@pytest.fixture()
def db():
    mgr = DatabaseManager(":memory:")
    mgr.initialize()
    conn = mgr.connection
    yield conn
    conn.close()


class TestClassifierMantis:
    def test_extracts_ticket_id_and_date(self, db):
        """主旨含 ISSUE_YYYYMMDD_INNNNN_ 時應解析出 ticket_id 與 issue_date。"""
        clf = Classifier(db)
        result = clf.classify(
            subject="ISSUE_20260325_I0017475_艾克爾 補發臨時薪資項目問題",
            body="",
            sender_email="user@example.com",
            to_recipients=[],
        )
        assert result["mantis_ticket_id"] == "0017475"
        assert result["mantis_issue_date"] == "2026/03/25"

    def test_no_issue_prefix_returns_none(self, db):
        """一般主旨不含 ISSUE_ 格式時，兩個欄位應為 None。"""
        clf = Classifier(db)
        result = clf.classify(
            subject="一般詢問：薪資計算問題",
            body="",
            sender_email="user@example.com",
            to_recipients=[],
        )
        assert result["mantis_ticket_id"] is None
        assert result["mantis_issue_date"] is None

    def test_case_insensitive(self, db):
        """ISSUE_ 大小寫不敏感。"""
        clf = Classifier(db)
        result = clf.classify(
            subject="issue_20260101_I0099999_test subject",
            body="",
            sender_email="user@example.com",
            to_recipients=[],
        )
        assert result["mantis_ticket_id"] == "0099999"
        assert result["mantis_issue_date"] == "2026/01/01"

    def test_mantis_notify_subject_sets_issue_type(self, db):
        """[公司名 NNNNN]: 格式主旨應自動設 issue_type = Mantis通知。"""
        clf = Classifier(db)
        result = clf.classify(
            subject="[客服專區 (HCPSERVICE) 001691]: 2025/6/26 上午 09:42【台晶】外傷問題",
            body="",
            sender_email="noreply@mantis.system",
            to_recipients=[],
        )
        assert result["issue_type"] == "Mantis通知"
        assert result["mantis_ticket_id"] == "001691"

    def test_issue_prefix_also_sets_issue_type(self, db):
        """ISSUE_ 格式主旨也應自動設 issue_type = Mantis通知。"""
        clf = Classifier(db)
        result = clf.classify(
            subject="ISSUE_20260325_I0017475_艾克爾 補發臨時薪資項目問題",
            body="",
            sender_email="user@example.com",
            to_recipients=[],
        )
        assert result["issue_type"] == "Mantis通知"

    def test_mantis_company_auto_assigned(self, db):
        """若 DB 有名稱含 MANTIS 的公司，應自動帶入 company_id。"""
        db.execute(
            "INSERT INTO companies (company_id, name, domain) VALUES ('mantis-sys', 'MANTIS系統', 'mantis.system')"
        )
        db.commit()
        clf = Classifier(db)
        result = clf.classify(
            subject="[客服專區 (HCPSERVICE) 001691]: 薪資問題",
            body="",
            sender_email="noreply@mantis.system",
            to_recipients=[],
        )
        assert result["company_id"] == "mantis-sys"

    def test_no_mantis_company_in_db_stays_none(self, db):
        """DB 無 MANTIS 公司時，company_id 維持 None 不報錯。"""
        clf = Classifier(db)
        result = clf.classify(
            subject="[客服專區 (HCPSERVICE) 001691]: 薪資問題",
            body="",
            sender_email="noreply@mantis.system",
            to_recipients=[],
        )
        assert result["issue_type"] == "Mantis通知"
        assert result["company_id"] is None
