"""案件刪除 — CaseManager.delete_case() / delete_cases_by_date_range() 測試。"""
from __future__ import annotations

from pathlib import Path

import pytest

from hcp_cms.core.case_manager import CaseManager
from hcp_cms.data.database import DatabaseManager


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    mgr = DatabaseManager(tmp_db_path)
    mgr.initialize()
    yield mgr
    mgr.close()


def _insert_case(conn, case_id: str, created_at: str = "2026/03/01 10:00:00") -> None:
    conn.execute(
        "INSERT INTO cs_cases (case_id, subject, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (case_id, f"主旨 {case_id}", "處理中", created_at, created_at),
    )
    conn.commit()


def _insert_qa(conn, qa_id: str, case_id: str, status: str) -> None:
    conn.execute(
        "INSERT INTO qa_knowledge (qa_id, question, answer, source_case_id, status) VALUES (?, ?, ?, ?, ?)",
        (qa_id, "問題", "答案", case_id, status),
    )
    conn.commit()


class TestCaseManagerDelete:
    def test_delete_case(self, db: DatabaseManager) -> None:
        """呼叫 CaseManager.delete_case(case_id)，case 被刪除。"""
        conn = db.connection
        _insert_case(conn, "CS-2026-101")
        mgr = CaseManager(conn)

        mgr.delete_case("CS-2026-101")

        count = conn.execute(
            "SELECT COUNT(*) FROM cs_cases WHERE case_id = ?", ("CS-2026-101",)
        ).fetchone()[0]
        assert count == 0

    def test_delete_case_keeps_approved_kms(self, db: DatabaseManager) -> None:
        """呼叫 delete_case 後，已發布的 KMS 條目仍存在。"""
        conn = db.connection
        _insert_case(conn, "CS-2026-102")
        _insert_qa(conn, "QA-101", "CS-2026-102", "已發布")
        _insert_qa(conn, "QA-102", "CS-2026-102", "待審查")
        mgr = CaseManager(conn)

        mgr.delete_case("CS-2026-102")

        # 已發布 → 保留
        approved = conn.execute(
            "SELECT COUNT(*) FROM qa_knowledge WHERE qa_id = ?", ("QA-101",)
        ).fetchone()[0]
        assert approved == 1

        # 待審查 → 刪除
        pending = conn.execute(
            "SELECT COUNT(*) FROM qa_knowledge WHERE qa_id = ?", ("QA-102",)
        ).fetchone()[0]
        assert pending == 0

    def test_delete_cases_by_date_range(self, db: DatabaseManager) -> None:
        """批次刪除指定日期範圍內的案件，回傳刪除筆數。"""
        conn = db.connection
        _insert_case(conn, "CS-2026-201", created_at="2026/02/10 08:00:00")
        _insert_case(conn, "CS-2026-202", created_at="2026/02/20 08:00:00")
        _insert_case(conn, "CS-2026-203", created_at="2026/03/01 08:00:00")
        mgr = CaseManager(conn)

        deleted = mgr.delete_cases_by_date_range("2026/02/01", "2026/02/28")

        assert deleted == 2
        # 範圍外的案件保留
        remaining = conn.execute(
            "SELECT COUNT(*) FROM cs_cases WHERE case_id = ?", ("CS-2026-203",)
        ).fetchone()[0]
        assert remaining == 1
