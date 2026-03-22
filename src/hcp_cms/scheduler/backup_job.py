"""Database backup background job."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from hcp_cms.data.backup import BackupManager


class BackupJob:
    """Performs scheduled database backups."""

    def __init__(self, conn: sqlite3.Connection, backup_dir: Path, keep_count: int = 30) -> None:
        self._backup_mgr = BackupManager(conn, backup_dir)
        self._keep_count = keep_count

    def run(self) -> Path:
        """Create backup and cleanup old ones. Returns backup path."""
        path = self._backup_mgr.create_backup()
        self._backup_mgr.cleanup_old_backups(self._keep_count)
        return path
