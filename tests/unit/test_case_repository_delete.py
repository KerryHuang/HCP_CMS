"""案件刪除 — CaseRepository.delete() / delete_by_date_range() 測試。"""
from __future__ import annotations

from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.repositories import (
    CaseRepository,
)


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    mgr = DatabaseManager(tmp_db_path)
    mgr.initialize()
    yield mgr
    mgr.close()


def _insert_case(conn, case_id: str, created_at: str = "2026/03/01 10:00:00") -> None:
    """直接 SQL 插入一筆案件（避免 CaseManager 額外副作用）。"""
    conn.execute(
        "INSERT INTO cs_cases (case_id, subject, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (case_id, f"主旨 {case_id}", "處理中", created_at, created_at),
    )
    conn.commit()


def _insert_case_log(conn, log_id: str, case_id: str) -> None:
    conn.execute(
        "INSERT INTO case_logs (log_id, case_id, direction, content, logged_at) VALUES (?, ?, ?, ?, ?)",
        (log_id, case_id, "客戶來信", "測試內容", "2026/03/01 10:00:00"),
    )
    conn.commit()


def _insert_mantis_and_link(conn, case_id: str, ticket_id: str) -> None:
    """插入 mantis_ticket 並建立 case_mantis 連結。"""
    conn.execute(
        "INSERT INTO mantis_tickets (ticket_id, summary) VALUES (?, ?)",
        (ticket_id, f"票務 {ticket_id}"),
    )
    conn.execute(
        "INSERT INTO case_mantis (case_id, ticket_id) VALUES (?, ?)",
        (case_id, ticket_id),
    )
    conn.commit()


def _insert_cases_fts(conn, case_id: str) -> None:
    conn.execute(
        "INSERT INTO cases_fts (case_id, subject) VALUES (?, ?)",
        (case_id, f"FTS 主旨 {case_id}"),
    )
    conn.commit()


def _insert_qa(conn, qa_id: str, case_id: str, status: str) -> None:
    conn.execute(
        "INSERT INTO qa_knowledge (qa_id, question, answer, source_case_id, status) VALUES (?, ?, ?, ?, ?)",
        (qa_id, "問題", "答案", case_id, status),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestCaseRepositoryDelete:
    def test_delete_removes_case(self, db: DatabaseManager) -> None:
        """刪除後 cs_cases 中找不到該 case_id。"""
        conn = db.connection
        _insert_case(conn, "CS-2026-001")
        repo = CaseRepository(conn)

        repo.delete("CS-2026-001")

        result = conn.execute(
            "SELECT COUNT(*) FROM cs_cases WHERE case_id = ?", ("CS-2026-001",)
        ).fetchone()
        assert result[0] == 0

    def test_delete_removes_case_logs(self, db: DatabaseManager) -> None:
        """刪除後 case_logs 中無該 case_id 的記錄。"""
        conn = db.connection
        _insert_case(conn, "CS-2026-002")
        _insert_case_log(conn, "LOG-001", "CS-2026-002")
        repo = CaseRepository(conn)

        repo.delete("CS-2026-002")

        count = conn.execute(
            "SELECT COUNT(*) FROM case_logs WHERE case_id = ?", ("CS-2026-002",)
        ).fetchone()[0]
        assert count == 0

    def test_delete_removes_case_mantis(self, db: DatabaseManager) -> None:
        """刪除後 case_mantis 中無該 case_id 的連結。"""
        conn = db.connection
        _insert_case(conn, "CS-2026-003")
        _insert_mantis_and_link(conn, "CS-2026-003", "MT-0001")
        repo = CaseRepository(conn)

        repo.delete("CS-2026-003")

        count = conn.execute(
            "SELECT COUNT(*) FROM case_mantis WHERE case_id = ?", ("CS-2026-003",)
        ).fetchone()[0]
        assert count == 0

    def test_delete_removes_fts(self, db: DatabaseManager) -> None:
        """刪除後 cases_fts 中無該 case_id 的記錄。"""
        conn = db.connection
        _insert_case(conn, "CS-2026-004")
        _insert_cases_fts(conn, "CS-2026-004")
        repo = CaseRepository(conn)

        repo.delete("CS-2026-004")

        count = conn.execute(
            "SELECT COUNT(*) FROM cases_fts WHERE case_id = ?", ("CS-2026-004",)
        ).fetchone()[0]
        assert count == 0

    def test_delete_removes_pending_kms(self, db: DatabaseManager) -> None:
        """刪除案件時，status='待審查' 的 qa_knowledge 一同刪除。"""
        conn = db.connection
        _insert_case(conn, "CS-2026-005")
        _insert_qa(conn, "QA-001", "CS-2026-005", "待審查")
        repo = CaseRepository(conn)

        repo.delete("CS-2026-005")

        count = conn.execute(
            "SELECT COUNT(*) FROM qa_knowledge WHERE source_case_id = ?", ("CS-2026-005",)
        ).fetchone()[0]
        assert count == 0

    def test_delete_keeps_approved_kms(self, db: DatabaseManager) -> None:
        """刪除案件時，status='已發布' 的 qa_knowledge 應保留。"""
        conn = db.connection
        _insert_case(conn, "CS-2026-006")
        _insert_qa(conn, "QA-002", "CS-2026-006", "已發布")
        repo = CaseRepository(conn)

        repo.delete("CS-2026-006")

        count = conn.execute(
            "SELECT COUNT(*) FROM qa_knowledge WHERE qa_id = ?", ("QA-002",)
        ).fetchone()[0]
        assert count == 1

    def test_delete_by_date_range_returns_count(self, db: DatabaseManager) -> None:
        """按 created_at 範圍批次刪除，回傳正確刪除筆數。"""
        conn = db.connection
        # 範圍內：3 筆
        _insert_case(conn, "CS-2026-010", created_at="2026/01/05 09:00:00")
        _insert_case(conn, "CS-2026-011", created_at="2026/01/15 09:00:00")
        _insert_case(conn, "CS-2026-012", created_at="2026/01/31 23:59:59")
        # 範圍外：1 筆
        _insert_case(conn, "CS-2026-013", created_at="2026/02/01 00:00:00")
        repo = CaseRepository(conn)

        deleted = repo.delete_by_date_range("2026/01/01", "2026/01/31")

        assert deleted == 3
        # 範圍外的案件應保留
        remaining = conn.execute(
            "SELECT COUNT(*) FROM cs_cases WHERE case_id = ?", ("CS-2026-013",)
        ).fetchone()[0]
        assert remaining == 1
