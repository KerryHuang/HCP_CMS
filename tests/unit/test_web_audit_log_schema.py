"""驗證 web_audit_log 表結構（Migration 後存在且結構正確）。"""
import sqlite3
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager


@pytest.fixture
def db_conn(tmp_path: Path) -> sqlite3.Connection:
    db = DatabaseManager(tmp_path / "test.db")
    db.initialize()
    yield db.connection
    db.close()


def test_web_audit_log_table_exists(db_conn: sqlite3.Connection) -> None:
    cur = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='web_audit_log'"
    )
    assert cur.fetchone() is not None


def test_web_audit_log_columns(db_conn: sqlite3.Connection) -> None:
    cur = db_conn.execute("PRAGMA table_info(web_audit_log)")
    cols = {row[1]: row[2] for row in cur.fetchall()}
    assert cols == {
        "id": "INTEGER",
        "staff_id": "TEXT",
        "occurred_at": "TEXT",
        "case_id": "TEXT",
        "field_name": "TEXT",
    }


def test_web_audit_log_indexes(db_conn: sqlite3.Connection) -> None:
    cur = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='web_audit_log'"
    )
    names = {row[0] for row in cur.fetchall()}
    assert "idx_audit_case" in names
    assert "idx_audit_staff" in names
