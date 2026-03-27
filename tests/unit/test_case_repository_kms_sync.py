"""TDD — CaseRepository.update() 應同步 qa_knowledge 中 status='待審查' 的條目。"""
from __future__ import annotations

import sqlite3

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, QAKnowledge
from hcp_cms.data.repositories import CaseRepository, QARepository


@pytest.fixture()
def db(tmp_path):
    mgr = DatabaseManager(tmp_path / "test.db")
    mgr.initialize()
    conn = mgr.connection
    yield conn
    mgr.close()


def _make_case(conn: sqlite3.Connection) -> Case:
    # 先建立相依的公司記錄（FK: cs_cases.company_id → companies.company_id）
    conn.execute(
        "INSERT OR IGNORE INTO companies (company_id, name, created_at) VALUES (?,?,?)",
        ("C001", "測試公司", "2026/03/27 10:00:00"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO companies (company_id, name, created_at) VALUES (?,?,?)",
        ("C999", "目標公司", "2026/03/27 10:00:00"),
    )
    conn.commit()

    case = Case(
        case_id="CS-2026-0001",
        subject="測試主旨",
        company_id="C001",
        system_product="ERP",
        issue_type="操作問題",
        error_type="畫面異常",
        status="處理中",
        priority="中",
        source="Email",
    )
    conn.execute(
        """INSERT INTO cs_cases (case_id, subject, company_id, system_product,
           issue_type, error_type, status, priority, source)
           VALUES (:case_id, :subject, :company_id, :system_product,
                   :issue_type, :error_type, :status, :priority, :source)""",
        {
            "case_id": case.case_id, "subject": case.subject,
            "company_id": case.company_id, "system_product": case.system_product,
            "issue_type": case.issue_type, "error_type": case.error_type,
            "status": case.status, "priority": case.priority, "source": case.source,
        },
    )
    conn.execute(
        "INSERT INTO cases_fts (case_id, subject, progress, notes) VALUES (?,?,?,?)",
        (case.case_id, case.subject, "", ""),
    )
    conn.commit()
    return case


def _make_qa(conn: sqlite3.Connection, source_case_id: str, status: str) -> str:
    """插入一筆 qa_knowledge，回傳 qa_id。"""
    qa_id = f"KM-{status[:2]}-001"
    conn.execute(
        """INSERT INTO qa_knowledge
           (qa_id, system_product, issue_type, error_type, company_id,
            question, answer, source_case_id, status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (qa_id, "ERP", "操作問題", "畫面異常", "C001",
         "問題描述", "解答", source_case_id, status,
         "2026/03/27 10:00:00", "2026/03/27 10:00:00"),
    )
    conn.commit()
    return qa_id


class TestCaseRepositoryKmsSync:

    def test_update_syncs_pending_kms(self, db):
        """更新案件欄位後，待審查 KMS 條目應同步更新。"""
        case = _make_case(db)
        qa_id = _make_qa(db, case.case_id, "待審查")

        case.system_product = "CRM"
        case.issue_type = "資料問題"
        case.error_type = "計算錯誤"
        case.company_id = "C999"

        CaseRepository(db).update(case)

        row = db.execute(
            "SELECT system_product, issue_type, error_type, company_id FROM qa_knowledge WHERE qa_id=?",
            (qa_id,),
        ).fetchone()
        assert row["system_product"] == "CRM"
        assert row["issue_type"] == "資料問題"
        assert row["error_type"] == "計算錯誤"
        assert row["company_id"] == "C999"

    def test_update_does_not_touch_approved_kms(self, db):
        """更新案件欄位後，已審核（非待審查）KMS 條目不應被修改。"""
        case = _make_case(db)
        qa_id = _make_qa(db, case.case_id, "已完成")

        case.system_product = "CRM"
        CaseRepository(db).update(case)

        row = db.execute(
            "SELECT system_product FROM qa_knowledge WHERE qa_id=?",
            (qa_id,),
        ).fetchone()
        assert row["system_product"] == "ERP"  # 未被修改

    def test_update_without_linked_kms(self, db):
        """無關聯 KMS 條目時，update() 不應拋出例外。"""
        case = _make_case(db)
        case.system_product = "CRM"
        # 不 raise 即通過
        CaseRepository(db).update(case)
