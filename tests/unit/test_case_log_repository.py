"""Tests for CaseLogRepository."""
from __future__ import annotations

from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import CaseLog
from hcp_cms.data.repositories import CaseLogRepository, CaseMantisRepository


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    # 插入一筆父案件供 FK 使用
    db.connection.execute(
        "INSERT INTO cs_cases (case_id, subject, status) VALUES (?, ?, ?)",
        ("CS-202603-001", "測試主旨", "處理中"),
    )
    db.connection.commit()
    yield db
    db.close()


class TestNextLogId:
    def test_first_log_of_day(self, db: DatabaseManager):
        repo = CaseLogRepository(db.connection)
        log_id = repo.next_log_id()
        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        assert log_id == f"LOG-{today}-001"

    def test_sequential_same_day(self, db: DatabaseManager):
        repo = CaseLogRepository(db.connection)
        id1 = repo.next_log_id()
        # 手動插入第一筆
        db.connection.execute(
            "INSERT INTO case_logs (log_id, case_id, direction, content, logged_at) VALUES (?, ?, ?, ?, ?)",
            (id1, "CS-202603-001", "客戶來信", "內容", "2026/03/26 10:00:00"),
        )
        db.connection.commit()
        id2 = repo.next_log_id()
        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        assert id2 == f"LOG-{today}-002"


class TestCaseLogRepositoryInsert:
    def test_insert_and_retrieve(self, db: DatabaseManager):
        repo = CaseLogRepository(db.connection)
        log = CaseLog(
            log_id="LOG-20260326-001",
            case_id="CS-202603-001",
            direction="客戶來信",
            content="客戶反映問題",
            mantis_ref="1234",
            logged_by="Jill",
            logged_at="2026/03/26 10:00:00",
        )
        repo.insert(log)
        logs = repo.list_by_case("CS-202603-001")
        assert len(logs) == 1
        assert logs[0].log_id == "LOG-20260326-001"
        assert logs[0].mantis_ref == "1234"
        assert logs[0].logged_by == "Jill"


class TestCaseLogRepositoryListByCase:
    def test_filters_by_case_id(self, db: DatabaseManager):
        # 插入兩個不同案件的記錄
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject, status) VALUES (?, ?, ?)",
            ("CS-202603-002", "另一案件", "處理中"),
        )
        db.connection.commit()
        repo = CaseLogRepository(db.connection)
        repo.insert(CaseLog("LOG-20260326-001", "CS-202603-001", "客戶來信", "A", logged_at="2026/03/26 10:00:00"))
        repo.insert(CaseLog("LOG-20260326-002", "CS-202603-002", "CS 回覆", "B", logged_at="2026/03/26 11:00:00"))
        logs = repo.list_by_case("CS-202603-001")
        assert len(logs) == 1
        assert logs[0].case_id == "CS-202603-001"

    def test_sorted_by_logged_at_asc(self, db: DatabaseManager):
        repo = CaseLogRepository(db.connection)
        repo.insert(CaseLog("LOG-20260326-001", "CS-202603-001", "客戶來信", "舊", logged_at="2026/03/26 08:00:00"))
        repo.insert(CaseLog("LOG-20260326-002", "CS-202603-001", "CS 回覆", "新", logged_at="2026/03/26 15:00:00"))
        logs = repo.list_by_case("CS-202603-001")
        assert logs[0].content == "舊"
        assert logs[1].content == "新"


class TestCaseLogRepositoryDelete:
    def test_delete_removes_record(self, db: DatabaseManager):
        repo = CaseLogRepository(db.connection)
        repo.insert(CaseLog("LOG-20260326-001", "CS-202603-001", "客戶來信", "內容", logged_at="2026/03/26 10:00:00"))
        repo.delete("LOG-20260326-001")
        logs = repo.list_by_case("CS-202603-001")
        assert len(logs) == 0


class TestCaseMantisRepositoryUnlink:
    def test_unlink_removes_association(self, db: DatabaseManager):
        # 插入 mantis ticket
        db.connection.execute(
            "INSERT INTO mantis_tickets "
            "(ticket_id, summary, priority, status, issue_type, module, handler, progress) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("1234", "測試 ticket", "中", "開放中", "Bug", "系統", "工程師", "進行中"),
        )
        db.connection.execute(
            "INSERT INTO case_mantis (case_id, ticket_id) VALUES (?, ?)",
            ("CS-202603-001", "1234"),
        )
        db.connection.commit()
        repo = CaseMantisRepository(db.connection)
        repo.unlink("CS-202603-001", "1234")
        tickets = repo.get_tickets_for_case("CS-202603-001")
        assert "1234" not in tickets
