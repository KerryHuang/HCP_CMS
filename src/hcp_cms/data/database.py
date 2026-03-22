"""資料庫連線管理與 schema 初始化"""

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path.home() / ".hcp_cms" / "hcp_cms.db"


def get_connection(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """取得資料庫連線"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """初始化資料庫 schema"""
    conn.executescript(_SCHEMA_SQL)


_SCHEMA_SQL = """
-- 公司表
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    short_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 客服案件
CREATE TABLE IF NOT EXISTS cs_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_number TEXT NOT NULL UNIQUE,
    company_id INTEGER REFERENCES companies(id),
    subject TEXT NOT NULL,
    sender TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT NOT NULL DEFAULT 'normal',
    category TEXT,
    received_at TEXT NOT NULL,
    replied_at TEXT,
    closed_at TEXT,
    first_response_time INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Mantis 工單
CREATE TABLE IF NOT EXISTS mantis_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL UNIQUE,
    summary TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL,
    priority TEXT,
    category TEXT,
    reporter TEXT,
    assigned_to TEXT,
    synced_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 案件-Mantis 多對多關聯
CREATE TABLE IF NOT EXISTS case_mantis (
    case_id INTEGER NOT NULL REFERENCES cs_cases(id),
    mantis_id INTEGER NOT NULL REFERENCES mantis_tickets(id),
    PRIMARY KEY (case_id, mantis_id)
);

-- QA 知識庫
CREATE TABLE IF NOT EXISTS qa_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    solution TEXT,
    keywords TEXT,
    category TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'approved',
    case_id INTEGER REFERENCES cs_cases(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 已處理檔案
CREATE TABLE IF NOT EXISTS processed_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    file_type TEXT NOT NULL,
    processed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 分類規則
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    rule_type TEXT NOT NULL,
    pattern TEXT NOT NULL,
    category TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 同義詞表
CREATE TABLE IF NOT EXISTS synonyms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL,
    synonym TEXT NOT NULL,
    UNIQUE(word, synonym)
);

-- FTS5 虛擬表：案件全文搜尋
CREATE VIRTUAL TABLE IF NOT EXISTS cases_fts USING fts5(
    case_number, subject, sender, category,
    content='cs_cases',
    content_rowid='id'
);

-- FTS5 虛擬表：QA 知識庫全文搜尋
CREATE VIRTUAL TABLE IF NOT EXISTS qa_fts USING fts5(
    question, answer, solution, keywords,
    content='qa_knowledge',
    content_rowid='id'
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_cases_company ON cs_cases(company_id);
CREATE INDEX IF NOT EXISTS idx_cases_status ON cs_cases(status);
CREATE INDEX IF NOT EXISTS idx_cases_received ON cs_cases(received_at);
CREATE INDEX IF NOT EXISTS idx_qa_category ON qa_knowledge(category);
CREATE INDEX IF NOT EXISTS idx_qa_status ON qa_knowledge(status);
CREATE INDEX IF NOT EXISTS idx_files_sha256 ON processed_files(sha256);
CREATE INDEX IF NOT EXISTS idx_synonyms_word ON synonyms(word);
"""
