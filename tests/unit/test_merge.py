"""Tests for MergeManager."""

import sqlite3
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.merge import ConflictStrategy, MergeManager, MergePreview


@pytest.fixture
def local_conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "local.db"
    mgr = DatabaseManager(db_path)
    mgr.initialize()
    return mgr.connection


@pytest.fixture
def remote_conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "remote.db"
    mgr = DatabaseManager(db_path)
    mgr.initialize()
    return mgr.connection


class TestMergePreview:
    def test_preview_new_records(
        self, local_conn: sqlite3.Connection, remote_conn: sqlite3.Connection
    ):
        """Records in remote but not in local → counted as new."""
        remote_conn.execute(
            "INSERT INTO cs_cases (case_id, subject) VALUES (?, ?)",
            ("CS-2025-001", "Remote-only case"),
        )
        remote_conn.commit()

        mm = MergeManager(local_conn)
        preview = mm.preview(remote_conn)

        assert preview.cases_new == 1
        assert preview.cases_conflict == 0

    def test_preview_conflict_records(
        self, local_conn: sqlite3.Connection, remote_conn: sqlite3.Connection
    ):
        """Same case_id in both local and remote → counted as conflict."""
        for conn in (local_conn, remote_conn):
            conn.execute(
                "INSERT INTO cs_cases (case_id, subject) VALUES (?, ?)",
                ("CS-2025-001", "Shared case"),
            )
            conn.commit()

        mm = MergeManager(local_conn)
        preview = mm.preview(remote_conn)

        assert preview.cases_conflict == 1
        assert preview.cases_new == 0


class TestMergeBehavior:
    def test_merge_keep_local(
        self, local_conn: sqlite3.Connection, remote_conn: sqlite3.Connection
    ):
        """KEEP_LOCAL: conflicting records keep local data unchanged."""
        local_conn.execute(
            "INSERT INTO cs_cases (case_id, subject) VALUES (?, ?)",
            ("CS-2025-001", "Local subject"),
        )
        local_conn.commit()

        remote_conn.execute(
            "INSERT INTO cs_cases (case_id, subject) VALUES (?, ?)",
            ("CS-2025-001", "Remote subject"),
        )
        remote_conn.commit()

        mm = MergeManager(local_conn)
        result = mm.merge(remote_conn, ConflictStrategy.KEEP_LOCAL)

        row = local_conn.execute(
            "SELECT subject FROM cs_cases WHERE case_id = ?", ("CS-2025-001",)
        ).fetchone()
        assert row[0] == "Local subject"
        assert result.skipped == 1

    def test_merge_keep_remote(
        self, local_conn: sqlite3.Connection, remote_conn: sqlite3.Connection
    ):
        """KEEP_REMOTE: conflicting records overwrite local data with remote."""
        local_conn.execute(
            "INSERT INTO cs_cases (case_id, subject) VALUES (?, ?)",
            ("CS-2025-001", "Local subject"),
        )
        local_conn.commit()

        remote_conn.execute(
            "INSERT INTO cs_cases (case_id, subject) VALUES (?, ?)",
            ("CS-2025-001", "Remote subject"),
        )
        remote_conn.commit()

        mm = MergeManager(local_conn)
        result = mm.merge(remote_conn, ConflictStrategy.KEEP_REMOTE)

        row = local_conn.execute(
            "SELECT subject FROM cs_cases WHERE case_id = ?", ("CS-2025-001",)
        ).fetchone()
        assert row[0] == "Remote subject"
        assert result.overwritten == 1

    def test_merge_new_records_imported(
        self, local_conn: sqlite3.Connection, remote_conn: sqlite3.Connection
    ):
        """Non-conflicting remote records are always inserted into local."""
        remote_conn.execute(
            "INSERT INTO cs_cases (case_id, subject) VALUES (?, ?)",
            ("CS-2025-NEW", "Brand new case"),
        )
        remote_conn.commit()

        mm = MergeManager(local_conn)
        result = mm.merge(remote_conn, ConflictStrategy.KEEP_LOCAL)

        row = local_conn.execute(
            "SELECT subject FROM cs_cases WHERE case_id = ?", ("CS-2025-NEW",)
        ).fetchone()
        assert row is not None
        assert row[0] == "Brand new case"
        assert result.imported == 1

    def test_merge_companies(
        self, local_conn: sqlite3.Connection, remote_conn: sqlite3.Connection
    ):
        """Company records in remote are imported into local."""
        remote_conn.execute(
            "INSERT INTO companies (company_id, name, domain) VALUES (?, ?, ?)",
            ("C-REMOTE-001", "Remote Corp", "remote.com"),
        )
        remote_conn.commit()

        mm = MergeManager(local_conn)
        result = mm.merge(remote_conn, ConflictStrategy.KEEP_LOCAL)

        row = local_conn.execute(
            "SELECT name FROM companies WHERE company_id = ?", ("C-REMOTE-001",)
        ).fetchone()
        assert row is not None
        assert row[0] == "Remote Corp"
        assert result.imported >= 1
