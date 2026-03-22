"""SQLite database manager with WAL mode and schema initialization."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "2.0.0"
BUSY_TIMEOUT_MS = 5000

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS companies (
    company_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT UNIQUE,
    alias TEXT,
    contact_info TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS cs_cases (
    case_id TEXT PRIMARY KEY,
    contact_method TEXT DEFAULT 'Email',
    status TEXT DEFAULT '處理中',
    priority TEXT DEFAULT '中',
    replied TEXT DEFAULT '否',
    sent_time TEXT,
    company_id TEXT REFERENCES companies(company_id),
    contact_person TEXT,
    subject TEXT,
    system_product TEXT,
    issue_type TEXT,
    error_type TEXT,
    impact_period TEXT,
    progress TEXT,
    actual_reply TEXT,
    notes TEXT,
    rd_assignee TEXT,
    handler TEXT,
    reply_count INTEGER DEFAULT 0,
    linked_case_id TEXT REFERENCES cs_cases(case_id),
    source TEXT DEFAULT 'email',
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS qa_knowledge (
    qa_id TEXT PRIMARY KEY,
    system_product TEXT,
    issue_type TEXT,
    error_type TEXT,
    question TEXT,
    answer TEXT,
    solution TEXT,
    keywords TEXT,
    has_image TEXT DEFAULT '否',
    doc_name TEXT,
    company_id TEXT REFERENCES companies(company_id),
    source_case_id TEXT REFERENCES cs_cases(case_id),
    source TEXT DEFAULT 'manual',
    created_by TEXT,
    created_at TEXT,
    updated_at TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS mantis_tickets (
    ticket_id TEXT PRIMARY KEY,
    created_time TEXT,
    company_id TEXT REFERENCES companies(company_id),
    summary TEXT,
    priority TEXT,
    status TEXT,
    issue_type TEXT,
    module TEXT,
    handler TEXT,
    planned_fix TEXT,
    actual_fix TEXT,
    progress TEXT,
    notes TEXT,
    synced_at TEXT
);

CREATE TABLE IF NOT EXISTS case_mantis (
    case_id TEXT REFERENCES cs_cases(case_id),
    ticket_id TEXT REFERENCES mantis_tickets(ticket_id),
    PRIMARY KEY (case_id, ticket_id)
);

CREATE TABLE IF NOT EXISTS processed_files (
    file_hash TEXT PRIMARY KEY,
    filename TEXT,
    message_id TEXT,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS classification_rules (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_type TEXT NOT NULL,
    pattern TEXT NOT NULL,
    value TEXT NOT NULL,
    priority INTEGER NOT NULL,
    enabled INTEGER DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS synonyms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL,
    synonym TEXT NOT NULL,
    group_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS db_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS qa_fts USING fts5(
    qa_id UNINDEXED,
    question,
    answer,
    solution,
    keywords
);

CREATE VIRTUAL TABLE IF NOT EXISTS cases_fts USING fts5(
    case_id UNINDEXED,
    subject,
    progress,
    notes
);
"""


class DatabaseManager:
    """Manages SQLite connection with WAL mode and schema initialization."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._conn

    def initialize(self) -> None:
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.row_factory = sqlite3.Row

        self._conn.executescript(_SCHEMA_SQL)
        self._conn.execute(
            "INSERT OR IGNORE INTO db_meta (key, value) VALUES (?, ?)",
            ("schema_version", SCHEMA_VERSION),
        )
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> DatabaseManager:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self.close()
