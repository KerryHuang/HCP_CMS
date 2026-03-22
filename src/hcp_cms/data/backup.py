"""BackupManager — SQLite backup, restore, zip export, and cleanup."""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path


class BackupManager:
    """Manages database backups: create, list, restore, cleanup, and zip export."""

    def __init__(self, conn: sqlite3.Connection, backup_dir: Path) -> None:
        self._conn = conn
        self._backup_dir = backup_dir
        self._backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self) -> Path:
        """Create a backup using the SQLite backup API.

        Filename format: cs_tracker_YYYYMMDD_HHMMSS_ffffff.db
        Microseconds are appended to ensure uniqueness within the same second.
        """
        now = datetime.now()
        filename = now.strftime("cs_tracker_%Y%m%d_%H%M%S_%f") + ".db"
        backup_path = self._backup_dir / filename

        backup_conn = sqlite3.connect(str(backup_path))
        try:
            self._conn.backup(backup_conn)
        finally:
            backup_conn.close()

        return backup_path

    def list_backups(self) -> list[Path]:
        """Return all backup files sorted by modification time, newest first."""
        backups = list(self._backup_dir.glob("cs_tracker_*.db"))
        backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return backups

    def restore_backup(self, backup_path: Path, target_db_path: Path) -> None:
        """Copy a backup file to the target path using shutil.copy2."""
        shutil.copy2(backup_path, target_db_path)

    def cleanup_old_backups(self, keep_count: int = 30) -> int:
        """Delete old backups, keeping the newest keep_count files.

        Returns the number of files removed.
        """
        backups = self.list_backups()
        to_delete = backups[keep_count:]
        for path in to_delete:
            path.unlink()
        return len(to_delete)

    def export_zip(self, zip_path: Path) -> Path:
        """Create a temporary backup, compress it into a zip, then delete the temp file.

        Returns zip_path.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_backup = Path(tmp_dir) / "cs_tracker_export.db"
            backup_conn = sqlite3.connect(str(tmp_backup))
            try:
                self._conn.backup(backup_conn)
            finally:
                backup_conn.close()

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(tmp_backup, tmp_backup.name)

        return zip_path

    def restore_from_zip(self, zip_path: Path, target_db_path: Path) -> None:
        """Extract the .db file from a zip archive and move it to target_db_path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            with zipfile.ZipFile(zip_path, "r") as zf:
                # Find the .db file inside the zip
                db_names = [name for name in zf.namelist() if name.endswith(".db")]
                if not db_names:
                    raise ValueError(f"No .db file found in zip: {zip_path}")
                zf.extract(db_names[0], tmp_dir_path)
                extracted = tmp_dir_path / db_names[0]

            shutil.copy2(extracted, target_db_path)
