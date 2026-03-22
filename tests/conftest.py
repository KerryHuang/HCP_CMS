"""共用 fixtures"""

import sqlite3

import pytest

from hcp_cms.data.database import init_schema


@pytest.fixture
def db() -> sqlite3.Connection:
    """建立記憶體內 SQLite 測試資料庫"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    yield conn
    conn.close()
