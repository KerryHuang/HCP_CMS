"""TDD — CaseMantisLink.issue_date 欄位正確存取。"""

from __future__ import annotations

import pytest
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import CaseMantisLink
from hcp_cms.data.repositories import CaseMantisRepository


@pytest.fixture()
def db():
    mgr = DatabaseManager(":memory:")
    mgr.initialize()
    conn = mgr.connection
    # 插入一筆 company 和 case（FK 需求）
    conn.execute("INSERT INTO companies (company_id, name, domain) VALUES ('C001', '測試公司', 'test.com')")
    conn.execute(
        """INSERT INTO cs_cases (case_id, subject, company_id, status, priority, source)
           VALUES ('CS-2026-0001', '測試主旨', 'C001', '處理中', '中', 'Email')"""
    )
    conn.execute(
        "INSERT INTO cases_fts (case_id, subject, progress, notes) VALUES ('CS-2026-0001', '測試主旨', '', '')"
    )
    # 預先插入測試用 mantis ticket，避免 FK 約束失敗
    conn.execute("INSERT INTO mantis_tickets (ticket_id, summary) VALUES ('0017475', '測試票')")
    conn.execute("INSERT INTO mantis_tickets (ticket_id, summary) VALUES ('0099999', '測試票2')")
    conn.commit()
    yield conn
    conn.close()


class TestCaseMantisIssueDate:
    def test_insert_and_retrieve_issue_date(self, db):
        """插入含 issue_date 的連結後，讀取應正確返回。"""
        repo = CaseMantisRepository(db)
        link = CaseMantisLink(
            case_id="CS-2026-0001",
            ticket_id="0017475",
            summary="自動連結",
            issue_date="2026/03/25",
        )
        repo.insert(link)
        results = repo.list_by_case_id("CS-2026-0001")
        assert len(results) == 1
        assert results[0].issue_date == "2026/03/25"

    def test_issue_date_defaults_to_none(self, db):
        """未指定 issue_date 時，讀回應為 None。"""
        repo = CaseMantisRepository(db)
        link = CaseMantisLink(
            case_id="CS-2026-0001",
            ticket_id="0099999",
        )
        repo.insert(link)
        results = repo.list_by_case_id("CS-2026-0001")
        assert results[0].issue_date is None
