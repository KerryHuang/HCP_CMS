"""TDD — Classifier 應從主旨解析 Mantis ISSUE 資訊。"""

from __future__ import annotations

import sqlite3
import pytest
from hcp_cms.data.database import DatabaseManager
from hcp_cms.core.classifier import Classifier


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
