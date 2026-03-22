"""Tests for MigrationManager."""

import sqlite3
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.migration import MigrationManager


@pytest.fixture
def old_db_path(tmp_path: Path) -> Path:
    """Provide a legacy database fixture with the old schema."""
    path = tmp_path / "old_cs_tracker.db"
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE cs_cases (
            case_id TEXT PRIMARY KEY, contact_method TEXT,
            status TEXT DEFAULT '處理中', priority TEXT DEFAULT '中',
            replied TEXT DEFAULT '否', sent_time TEXT, company TEXT,
            contact_person TEXT, subject TEXT, system_product TEXT,
            issue_type TEXT, error_type TEXT, impact_period TEXT,
            progress TEXT, actual_reply TEXT, notes TEXT,
            rd_assignee TEXT, handler TEXT
        );
        CREATE TABLE qa_knowledge (
            qa_id TEXT PRIMARY KEY, system_product TEXT,
            issue_type TEXT, error_type TEXT, question TEXT,
            answer TEXT, has_image TEXT, created_date TEXT,
            created_by TEXT, notes TEXT, company TEXT
        );
        CREATE TABLE mantis_tickets (
            ticket_id TEXT PRIMARY KEY, created_time TEXT,
            customer TEXT, issue_summary TEXT,
            related_cs_case TEXT, status TEXT,
            priority TEXT, notes TEXT
        );
        INSERT INTO cs_cases (case_id, company, subject, status)
            VALUES ('CS-2025-001', 'aseglobal.com', 'Test case', '處理中');
        INSERT INTO cs_cases (case_id, company, subject, status)
            VALUES ('CS-2025-002', 'unimicron.com', 'Another case', '已完成');
        INSERT INTO qa_knowledge (qa_id, question, answer, company)
            VALUES ('QA-20250301-001', 'How to?', 'Do this.', 'aseglobal.com');
        INSERT INTO mantis_tickets (ticket_id, issue_summary, related_cs_case)
            VALUES ('15562', 'Bug fix', 'CS-2025-001;CS-2025-002');
    """)
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def new_conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "new_cs_tracker.db"
    mgr = DatabaseManager(db_path)
    mgr.initialize()
    return mgr.connection


class TestSchemaDetection:
    def test_detect_legacy_schema(self, old_db_path: Path, new_conn: sqlite3.Connection):
        """Old DB with 'company' TEXT column → is_legacy_schema returns True."""
        mm = MigrationManager(new_conn)
        assert mm.is_legacy_schema(old_db_path) is True

    def test_detect_new_schema(self, new_conn: sqlite3.Connection, tmp_path: Path):
        """New DB with 'company_id' FK column → is_legacy_schema returns False."""
        new_db_path = tmp_path / "new_cs_tracker.db"
        # Write new schema to a file so we can test detection
        new_db_path2 = tmp_path / "new2.db"
        mgr2 = DatabaseManager(new_db_path2)
        mgr2.initialize()
        mgr2.close()

        mm = MigrationManager(new_conn)
        assert mm.is_legacy_schema(new_db_path2) is False


class TestMigrationPreview:
    def test_preview_migration(self, old_db_path: Path, new_conn: sqlite3.Connection):
        """Preview returns correct counts: 2 cases, 1 QA, 1 mantis."""
        mm = MigrationManager(new_conn)
        preview = mm.preview(old_db_path)
        assert preview.cases_count == 2
        assert preview.qa_count == 1
        assert preview.mantis_count == 1


class TestMigration:
    def test_migrate_cases(self, old_db_path: Path, new_conn: sqlite3.Connection):
        """Migrated cases appear in the new DB with correct data."""
        mm = MigrationManager(new_conn)
        mm.migrate(old_db_path)

        row = new_conn.execute(
            "SELECT subject, status FROM cs_cases WHERE case_id = ?",
            ("CS-2025-001",),
        ).fetchone()
        assert row is not None
        assert row[0] == "Test case"
        assert row[1] == "處理中"

    def test_migrate_creates_companies(
        self, old_db_path: Path, new_conn: sqlite3.Connection
    ):
        """Unique company domains become rows in the companies table."""
        mm = MigrationManager(new_conn)
        mm.migrate(old_db_path)

        companies = new_conn.execute(
            "SELECT domain FROM companies ORDER BY domain"
        ).fetchall()
        domains = {row[0] for row in companies}
        assert "aseglobal.com" in domains
        assert "unimicron.com" in domains

    def test_migrate_splits_mantis_relations(
        self, old_db_path: Path, new_conn: sqlite3.Connection
    ):
        """related_cs_case 'CS-001;CS-002' → 2 rows in case_mantis."""
        mm = MigrationManager(new_conn)
        mm.migrate(old_db_path)

        links = new_conn.execute(
            "SELECT case_id FROM case_mantis WHERE ticket_id = ?", ("15562",)
        ).fetchall()
        case_ids = {row[0] for row in links}
        assert "CS-2025-001" in case_ids
        assert "CS-2025-002" in case_ids
        assert len(links) == 2
