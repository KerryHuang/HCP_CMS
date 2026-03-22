"""Tests for BackupManager."""

import sqlite3
import zipfile
from pathlib import Path

import pytest

from hcp_cms.data.backup import BackupManager
from hcp_cms.data.database import DatabaseManager


@pytest.fixture
def db_conn(tmp_path: Path):
    """Provide an initialized database connection."""
    db_path = tmp_path / "test_cs_tracker.db"
    mgr = DatabaseManager(db_path)
    mgr.initialize()
    yield mgr.connection
    mgr.close()


@pytest.fixture
def backup_dir(tmp_path: Path) -> Path:
    return tmp_path / "backups"


class TestBackupManager:
    def test_create_backup(self, db_conn: sqlite3.Connection, backup_dir: Path):
        bm = BackupManager(db_conn, backup_dir)
        backup_path = bm.create_backup()
        assert backup_path.exists()
        assert backup_path.suffix == ".db"
        assert "cs_tracker_" in backup_path.name

    def test_backup_is_valid_db(self, db_conn: sqlite3.Connection, backup_dir: Path, tmp_path: Path):
        """Insert data into source, backup, verify data is in backup."""
        db_conn.execute(
            "INSERT INTO companies (company_id, name, domain) VALUES (?, ?, ?)",
            ("C-001", "Test Corp", "testcorp.com"),
        )
        db_conn.commit()

        bm = BackupManager(db_conn, backup_dir)
        backup_path = bm.create_backup()

        backup_conn = sqlite3.connect(str(backup_path))
        row = backup_conn.execute(
            "SELECT name FROM companies WHERE company_id = ?", ("C-001",)
        ).fetchone()
        backup_conn.close()

        assert row is not None
        assert row[0] == "Test Corp"

    def test_list_backups(self, db_conn: sqlite3.Connection, backup_dir: Path):
        bm = BackupManager(db_conn, backup_dir)
        bm.create_backup()
        bm.create_backup()
        backups = bm.list_backups()
        assert len(backups) == 2

    def test_restore_backup(self, tmp_path: Path, backup_dir: Path):
        """Insert data, backup, then restore to a different path and verify."""
        source_path = tmp_path / "source.db"
        mgr = DatabaseManager(source_path)
        mgr.initialize()
        conn = mgr.connection

        conn.execute(
            "INSERT INTO companies (company_id, name, domain) VALUES (?, ?, ?)",
            ("C-002", "Restore Corp", "restore.com"),
        )
        conn.commit()

        bm = BackupManager(conn, backup_dir)
        backup_path = bm.create_backup()
        mgr.close()

        target_path = tmp_path / "restored.db"
        bm.restore_backup(backup_path, target_path)

        assert target_path.exists()
        restored_conn = sqlite3.connect(str(target_path))
        row = restored_conn.execute(
            "SELECT name FROM companies WHERE company_id = ?", ("C-002",)
        ).fetchone()
        restored_conn.close()
        assert row is not None
        assert row[0] == "Restore Corp"

    def test_cleanup_old_backups(self, db_conn: sqlite3.Connection, backup_dir: Path):
        """Create 5 backups, keep 2, verify only 2 remain."""
        bm = BackupManager(db_conn, backup_dir)
        for _ in range(5):
            bm.create_backup()

        removed = bm.cleanup_old_backups(keep_count=2)
        remaining = bm.list_backups()

        assert removed == 3
        assert len(remaining) == 2

    def test_export_as_zip(self, db_conn: sqlite3.Connection, backup_dir: Path, tmp_path: Path):
        bm = BackupManager(db_conn, backup_dir)
        zip_path = tmp_path / "export.zip"
        result = bm.export_zip(zip_path)
        assert result.exists()
        assert result.suffix == ".zip"

    def test_restore_from_zip(self, tmp_path: Path, backup_dir: Path):
        """Insert data, export zip, restore from zip, verify data."""
        source_path = tmp_path / "source.db"
        mgr = DatabaseManager(source_path)
        mgr.initialize()
        conn = mgr.connection

        conn.execute(
            "INSERT INTO companies (company_id, name, domain) VALUES (?, ?, ?)",
            ("C-003", "Zip Corp", "zip.com"),
        )
        conn.commit()

        bm = BackupManager(conn, backup_dir)
        zip_path = tmp_path / "export.zip"
        bm.export_zip(zip_path)
        mgr.close()

        target_path = tmp_path / "from_zip.db"
        bm.restore_from_zip(zip_path, target_path)

        assert target_path.exists()
        restored_conn = sqlite3.connect(str(target_path))
        row = restored_conn.execute(
            "SELECT name FROM companies WHERE company_id = ?", ("C-003",)
        ).fetchone()
        restored_conn.close()
        assert row is not None
        assert row[0] == "Zip Corp"
