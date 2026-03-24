"""Tests for DatabaseManager."""

import sqlite3
from pathlib import Path

from hcp_cms.data.database import DatabaseManager


class TestDatabaseManager:
    def test_create_database(self, tmp_db_path: Path):
        db = DatabaseManager(tmp_db_path)
        db.initialize()
        assert tmp_db_path.exists()
        db.close()

    def test_wal_mode_enabled(self, tmp_db_path: Path):
        db = DatabaseManager(tmp_db_path)
        db.initialize()
        result = db.connection.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"
        db.close()

    def test_busy_timeout_set(self, tmp_db_path: Path):
        db = DatabaseManager(tmp_db_path)
        db.initialize()
        result = db.connection.execute("PRAGMA busy_timeout").fetchone()
        assert result[0] == 5000
        db.close()

    def test_all_tables_created(self, tmp_db_path: Path):
        db = DatabaseManager(tmp_db_path)
        db.initialize()
        cursor = db.connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = {row[0] for row in cursor.fetchall()}
        expected = {
            "cs_cases",
            "qa_knowledge",
            "mantis_tickets",
            "companies",
            "case_mantis",
            "processed_files",
            "classification_rules",
            "synonyms",
            "db_meta",
        }
        assert expected.issubset(tables)
        db.close()

    def test_schema_version_set(self, tmp_db_path: Path):
        db = DatabaseManager(tmp_db_path)
        db.initialize()
        result = db.connection.execute("SELECT value FROM db_meta WHERE key = 'schema_version'").fetchone()
        assert result[0] == "2.0.0"
        db.close()

    def test_fts_tables_created(self, tmp_db_path: Path):
        db = DatabaseManager(tmp_db_path)
        db.initialize()
        cursor = db.connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%fts%'")
        fts_tables = {row[0] for row in cursor.fetchall()}
        assert "qa_fts" in fts_tables
        assert "cases_fts" in fts_tables
        db.close()

    def test_context_manager(self, tmp_db_path: Path):
        with DatabaseManager(tmp_db_path) as db:
            db.initialize()
            assert db.connection is not None

    def test_get_connection_with_retry(self, tmp_db_path: Path):
        db = DatabaseManager(tmp_db_path)
        db.initialize()
        conn = db.connection
        assert isinstance(conn, sqlite3.Connection)
        db.close()


class TestQAKnowledgeStatusColumn:
    def test_qa_knowledge_has_status_column(self, tmp_db_path):
        from hcp_cms.data.database import DatabaseManager

        db = DatabaseManager(tmp_db_path)
        db.initialize()
        cols = {row[1] for row in db.connection.execute("PRAGMA table_info(qa_knowledge)")}
        db.close()
        assert "status" in cols

    def test_status_default_is_已完成(self, tmp_db_path):
        from hcp_cms.data.database import DatabaseManager

        db = DatabaseManager(tmp_db_path)
        db.initialize()
        db.connection.execute("INSERT INTO qa_knowledge (qa_id, question, answer) VALUES ('QA-T01', 'q', 'a')")
        db.connection.commit()
        row = db.connection.execute("SELECT status FROM qa_knowledge WHERE qa_id = 'QA-T01'").fetchone()
        db.close()
        assert row[0] == "已完成"
