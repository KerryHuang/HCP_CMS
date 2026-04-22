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
    reply_time TEXT,
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
    status TEXT DEFAULT '已完成',
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
    summary TEXT,
    issue_date TEXT,
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

CREATE TABLE IF NOT EXISTS staff (
    staff_id   TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL UNIQUE,
    role       TEXT NOT NULL DEFAULT 'cs',
    phone      TEXT,
    notes      TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS case_logs (
    log_id     TEXT PRIMARY KEY,
    case_id    TEXT NOT NULL REFERENCES cs_cases(case_id),
    direction  TEXT NOT NULL,
    content    TEXT NOT NULL,
    mantis_ref TEXT,
    logged_by  TEXT,
    logged_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_columns (
    col_key          TEXT PRIMARY KEY,
    col_label        TEXT NOT NULL,
    col_order        INTEGER NOT NULL,
    visible_in_list  INTEGER NOT NULL DEFAULT 1
);

CREATE VIRTUAL TABLE IF NOT EXISTS cases_fts USING fts5(
    case_id UNINDEXED,
    subject,
    progress,
    notes
);

CREATE TABLE IF NOT EXISTS cs_patches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    type       TEXT NOT NULL DEFAULT 'single',
    month_str  TEXT,
    patch_dir  TEXT,
    status     TEXT NOT NULL DEFAULT 'in_progress',
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS cs_patch_issues (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    patch_id       INTEGER NOT NULL REFERENCES cs_patches(id),
    issue_no       TEXT NOT NULL,
    program_code   TEXT,
    program_name   TEXT,
    issue_type     TEXT DEFAULT 'BugFix',
    region         TEXT DEFAULT '共用',
    description    TEXT,
    impact         TEXT,
    test_direction TEXT,
    mantis_detail  TEXT,
    source         TEXT DEFAULT 'manual',
    sort_order     INTEGER DEFAULT 0,
    created_at     TEXT
);

CREATE TABLE IF NOT EXISTS cs_release_keywords (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword   TEXT    NOT NULL,
    ktype     TEXT    NOT NULL DEFAULT 'confirm',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS cs_release_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id           TEXT,
    mantis_ticket_id  TEXT,
    assignee          TEXT,
    client_name       TEXT,
    note              TEXT,
    status            TEXT NOT NULL DEFAULT '待發',
    month_str         TEXT,
    patch_id          INTEGER,
    created_at        TEXT
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
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.row_factory = sqlite3.Row

        self._conn.executescript(_SCHEMA_SQL)
        self._conn.execute(
            "INSERT OR IGNORE INTO db_meta (key, value) VALUES (?, ?)",
            ("schema_version", SCHEMA_VERSION),
        )
        self._apply_pending_migrations()
        self._conn.commit()

    def _apply_pending_migrations(self) -> None:
        """冪等補欄遷移：確保各資料表存在所有必要欄位。

        每次 initialize() 都會執行，對已存在欄位直接跳過（OperationalError 被吞掉）。
        """
        assert self._conn is not None
        pending: list[str] = [
            "ALTER TABLE qa_knowledge ADD COLUMN status TEXT DEFAULT '已完成'",
            "ALTER TABLE cs_cases ADD COLUMN reply_time TEXT",
            "ALTER TABLE case_mantis ADD COLUMN summary TEXT",
            "ALTER TABLE case_mantis ADD COLUMN issue_date TEXT",
            "ALTER TABLE cs_cases DROP COLUMN replied",
            "ALTER TABLE mantis_tickets ADD COLUMN severity TEXT",
            "ALTER TABLE mantis_tickets ADD COLUMN reporter TEXT",
            "ALTER TABLE mantis_tickets ADD COLUMN description TEXT",
            "ALTER TABLE mantis_tickets ADD COLUMN notes_json TEXT",
            "ALTER TABLE mantis_tickets ADD COLUMN last_updated TEXT",
            "ALTER TABLE mantis_tickets ADD COLUMN notes_count INTEGER",
            "ALTER TABLE case_logs ADD COLUMN reply_time TEXT",
            "ALTER TABLE companies ADD COLUMN cs_staff_id TEXT",
            "ALTER TABLE companies ADD COLUMN sales_staff_id TEXT",
            "ALTER TABLE companies ADD COLUMN hcp_version TEXT",
            "ALTER TABLE cs_cases ADD COLUMN message_id TEXT",
        ]
        for sql in pending:
            try:
                self._conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # 欄位已存在或不存在，略過

        # 預設待發關鍵字種子資料（冪等）
        default_keywords = [
            ("測試ok",   "confirm"),
            ("測試OK",   "confirm"),
            ("test ok",  "confirm"),
            ("安排出貨", "ship"),
            ("請出貨",   "ship"),
            ("可以出貨", "ship"),
        ]
        for kw, kt in default_keywords:
            try:
                self._conn.execute(
                    "INSERT INTO cs_release_keywords (keyword, ktype, created_at)"
                    " SELECT ?, ?, datetime('now')"
                    " WHERE NOT EXISTS (SELECT 1 FROM cs_release_keywords WHERE keyword = ?)",
                    (kw, kt, kw),
                )
            except sqlite3.OperationalError:
                pass

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
