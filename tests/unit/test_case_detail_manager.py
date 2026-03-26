"""Tests for CaseDetailManager."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hcp_cms.core.case_detail_manager import CaseDetailManager
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import CaseLog, MantisTicket  # noqa: F401


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    db.connection.execute(
        "INSERT INTO cs_cases (case_id, subject, status, priority, replied, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("CS-202603-001", "測試主旨", "處理中", "中", "否", "2026/01/01 00:00:00"),
    )
    db.connection.commit()
    yield db
    db.close()


class TestUpdateCase:
    def test_updates_fields(self, db: DatabaseManager):
        manager = CaseDetailManager(db.connection)
        case = manager.get_case("CS-202603-001")
        case.subject = "新主旨"
        case.handler = "小明"
        manager.update_case(case)
        updated = manager.get_case("CS-202603-001")
        assert updated.subject == "新主旨"
        assert updated.handler == "小明"

    def test_updated_at_refreshed(self, db: DatabaseManager):
        manager = CaseDetailManager(db.connection)
        case = manager.get_case("CS-202603-001")
        old_updated_at = case.updated_at
        case.subject = "變更"
        manager.update_case(case)
        updated = manager.get_case("CS-202603-001")
        assert updated.updated_at != old_updated_at


class TestAddLog:
    def test_log_id_format(self, db: DatabaseManager):
        from datetime import datetime
        manager = CaseDetailManager(db.connection)
        log = manager.add_log(
            case_id="CS-202603-001",
            direction="客戶來信",
            content="客戶詢問進度",
        )
        today = datetime.now().strftime("%Y%m%d")
        assert log.log_id == f"LOG-{today}-001"

    def test_all_fields_stored(self, db: DatabaseManager):
        manager = CaseDetailManager(db.connection)
        manager.add_log(
            case_id="CS-202603-001",
            direction="CS 回覆",
            content="已處理",
            mantis_ref="5678",
            logged_by="Jill",
        )
        logs = manager.list_logs("CS-202603-001")
        assert len(logs) == 1
        assert logs[0].mantis_ref == "5678"
        assert logs[0].logged_by == "Jill"


class TestListLogs:
    def test_filters_by_case_id(self, db: DatabaseManager):
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject, status) VALUES (?, ?, ?)",
            ("CS-202603-002", "另一案件", "處理中"),
        )
        db.connection.commit()
        manager = CaseDetailManager(db.connection)
        manager.add_log("CS-202603-001", "客戶來信", "A")
        manager.add_log("CS-202603-002", "CS 回覆", "B")
        logs = manager.list_logs("CS-202603-001")
        assert len(logs) == 1

    def test_sorted_asc(self, db: DatabaseManager):
        manager = CaseDetailManager(db.connection)
        manager.add_log("CS-202603-001", "客戶來信", "舊")
        manager.add_log("CS-202603-001", "CS 回覆", "新")
        logs = manager.list_logs("CS-202603-001")
        assert logs[0].content == "舊"
        assert logs[1].content == "新"


class TestLinkUnlinkMantis:
    def _insert_ticket(self, db: DatabaseManager, ticket_id: str) -> None:
        db.connection.execute(
            "INSERT INTO mantis_tickets"
            " (ticket_id, summary, priority, status, issue_type, module, handler, progress)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (ticket_id, "摘要", "中", "開放中", "Bug", "系統", "工程師", "進行中"),
        )
        db.connection.commit()

    def test_link_creates_association(self, db: DatabaseManager):
        self._insert_ticket(db, "0001")
        manager = CaseDetailManager(db.connection)
        manager.link_mantis("CS-202603-001", "0001")
        tickets = manager.list_linked_tickets("CS-202603-001")
        assert len(tickets) == 1
        assert tickets[0].ticket_id == "0001"

    def test_unlink_removes_association(self, db: DatabaseManager):
        self._insert_ticket(db, "0001")
        manager = CaseDetailManager(db.connection)
        manager.link_mantis("CS-202603-001", "0001")
        manager.unlink_mantis("CS-202603-001", "0001")
        tickets = manager.list_linked_tickets("CS-202603-001")
        assert len(tickets) == 0

    def test_link_nonexistent_ticket_returns_false(self, db: DatabaseManager):
        manager = CaseDetailManager(db.connection)
        result = manager.link_mantis("CS-202603-001", "9999")
        assert result is False


class TestSyncMantisTicket:
    def test_sync_updates_local(self, db: DatabaseManager):
        mock_client = MagicMock()
        from hcp_cms.services.mantis.base import MantisIssue
        mock_client.get_issue.return_value = MantisIssue(
            id="0001", summary="遠端摘要", status="已修復", priority="高",
            handler="工程師", notes="",
            created="2026/03/01",
        )
        manager = CaseDetailManager(db.connection)
        ticket = manager.sync_mantis_ticket("0001", client=mock_client)
        assert ticket is not None
        assert ticket.summary == "遠端摘要"
        assert ticket.status == "已修復"

    def test_sync_without_client_returns_none(self, db: DatabaseManager):
        manager = CaseDetailManager(db.connection)
        result = manager.sync_mantis_ticket("0001", client=None)
        assert result is None
