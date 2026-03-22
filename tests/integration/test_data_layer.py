"""Integration tests for the complete HCP CMS data layer."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from hcp_cms.data.backup import BackupManager
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.fts import FTSManager
from hcp_cms.data.models import Case, ClassificationRule, Company, QAKnowledge, Synonym
from hcp_cms.data.repositories import (
    CaseRepository,
    CompanyRepository,
    QARepository,
    RuleRepository,
    SynonymRepository,
)


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:  # type: ignore[misc]
    database = DatabaseManager(tmp_path / "integration.db")
    database.initialize()
    yield database
    database.close()


class TestFullWorkflow:
    def test_company_case_qa_workflow(self, db: DatabaseManager) -> None:
        conn = db.connection
        company_repo = CompanyRepository(conn)
        case_repo = CaseRepository(conn)
        qa_repo = QARepository(conn)
        fts = FTSManager(conn)

        # 1. Create company
        company = Company(
            company_id="C-001",
            name="測試公司",
            domain="test.com",
        )
        company_repo.insert(company)
        assert company_repo.get_by_id("C-001") is not None

        # 2. Create case linked to company + FTS index
        case = Case(
            case_id="CS-2026-001",
            subject="薪資計算錯誤問題",
            company_id="C-001",
            progress="已確認問題原因",
        )
        case_repo.insert(case)
        fts.index_case(case.case_id, case.subject, case.progress, case.notes)

        assert case_repo.get_by_id("CS-2026-001") is not None

        # 3. Create QA from case + FTS index
        qa = QAKnowledge(
            qa_id="QA-202603-001",
            question="薪資計算如何處理？",
            answer="請檢查薪資設定",
            source_case_id="CS-2026-001",
            company_id="C-001",
        )
        qa_repo.insert(qa)
        fts.index_qa(qa.qa_id, qa.question, qa.answer, qa.solution, qa.keywords)

        assert qa_repo.get_by_id("QA-202603-001") is not None

        # 4. Search QA with FTS — should find it
        qa_results = fts.search_qa("薪資")
        qa_ids = [r["qa_id"] for r in qa_results]
        assert "QA-202603-001" in qa_ids

        # 5. Search cases with FTS — should find it
        case_results = fts.search_cases("薪資")
        case_ids = [r["case_id"] for r in case_results]
        assert "CS-2026-001" in case_ids

    def test_synonym_enhanced_search(self, db: DatabaseManager) -> None:
        conn = db.connection
        syn_repo = SynonymRepository(conn)
        qa_repo = QARepository(conn)
        fts = FTSManager(conn)

        # 1. Insert synonyms: 薪水 ↔ 薪資
        syn = Synonym(word="薪水", synonym="薪資", group_name="salary")
        syn_repo.insert(syn)

        # 2. Create QA with "薪資"
        qa = QAKnowledge(
            qa_id="QA-202603-002",
            question="如何查詢薪資明細？",
            answer="進入薪資模組查詢",
        )
        qa_repo.insert(qa)
        fts.index_qa(qa.qa_id, qa.question, qa.answer, qa.solution, qa.keywords)

        # 3. Search with "薪水" — should find via synonym expansion
        results = fts.search_qa("薪水")
        qa_ids = [r["qa_id"] for r in results]
        assert "QA-202603-002" in qa_ids

    def test_backup_and_restore_preserves_data(
        self, db: DatabaseManager, tmp_path: Path
    ) -> None:
        conn = db.connection
        case_repo = CaseRepository(conn)
        backup_dir = tmp_path / "backups"

        # 1. Insert case
        case = Case(
            case_id="CS-2026-002",
            subject="備份還原測試案件",
        )
        case_repo.insert(case)
        assert case_repo.get_by_id("CS-2026-002") is not None

        # 2. Backup
        bm = BackupManager(conn, backup_dir)
        backup_path = bm.create_backup()
        assert backup_path.exists()

        # 3. Delete case from live DB
        conn.execute("DELETE FROM cs_cases WHERE case_id = ?", ("CS-2026-002",))
        conn.commit()
        assert case_repo.get_by_id("CS-2026-002") is None

        # 4. Restore backup to a separate file and verify data is present
        restored_path = tmp_path / "restored.db"
        bm.restore_backup(backup_path, restored_path)

        # 5. Verify case exists in the restored database
        restored_conn = sqlite3.connect(str(restored_path))
        restored_conn.row_factory = sqlite3.Row
        row = restored_conn.execute(
            "SELECT * FROM cs_cases WHERE case_id = ?", ("CS-2026-002",)
        ).fetchone()
        restored_conn.close()

        assert row is not None
        assert row["subject"] == "備份還原測試案件"

    def test_rules_from_db(self, db: DatabaseManager) -> None:
        conn = db.connection
        rule_repo = RuleRepository(conn)

        # 1. Insert classification rules for issue_type
        rules = [
            ClassificationRule(
                rule_type="issue_type",
                pattern="薪資",
                value="薪資問題",
                priority=2,
            ),
            ClassificationRule(
                rule_type="issue_type",
                pattern="請假",
                value="假勤問題",
                priority=1,
            ),
            ClassificationRule(
                rule_type="issue_type",
                pattern="報表",
                value="報表問題",
                priority=3,
            ),
        ]
        for rule in rules:
            rule_repo.insert(rule)

        # 2. List by type — verify order by priority ascending
        results = rule_repo.list_by_type("issue_type")
        assert len(results) == 3
        priorities = [r.priority for r in results]
        assert priorities == sorted(priorities), "Rules must be ordered by priority ASC"
        assert results[0].value == "假勤問題"   # priority=1
        assert results[1].value == "薪資問題"   # priority=2
        assert results[2].value == "報表問題"   # priority=3
