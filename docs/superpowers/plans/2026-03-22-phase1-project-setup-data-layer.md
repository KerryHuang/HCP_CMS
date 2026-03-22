# Phase 1：專案建置 + 資料層 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 HCP CMS 專案骨架、SQLite 資料庫（WAL 模式）、所有資料模型、Repository CRUD、FTS5 全文搜尋、備份/還原/合併功能。這是整個系統的基礎，所有上層模組都依賴此層。

**Architecture:** 使用 Python dataclass 定義資料模型，Repository 模式封裝 SQLite CRUD，FTS5 虛擬表支援中文全文搜尋（jieba 斷詞），sqlite3 backup API 實作備份。WAL 模式 + busy_timeout 支援 3 人共用。

**Tech Stack:** Python 3.10+, sqlite3, jieba, pytest, ruff, mypy

**Spec:** `docs/superpowers/specs/2026-03-22-hcp-cms-refactor-design.md`

**Phase 總覽（6 個 Phase）：**
- **Phase 1（本計劃）**：專案建置 + 資料層
- Phase 2：Core 業務邏輯（Classifier, Anonymizer, CaseManager, KMSEngine, ThreadTracker）
- Phase 3：Services 外部整合（MailProvider, MantisClient, Credential）
- Phase 4：Scheduler 排程（EmailJob, SyncJob, BackupJob, ReportJob）
- Phase 5：UI 層（PySide6 主視窗 + 所有頁面）
- Phase 6：報表引擎 + i18n + 打包部署

---

## 檔案結構

本 Phase 建立/修改的所有檔案：

```
D:/CMS/
├── pyproject.toml                          # 專案設定（dependencies, pytest, ruff, mypy）
├── src/hcp_cms/
│   ├── __init__.py                         # 版本號 __version__
│   ├── data/
│   │   ├── __init__.py
│   │   ├── database.py                     # DatabaseManager: 連線管理、WAL、schema 建立
│   │   ├── models.py                       # dataclass: Case, QAKnowledge, MantisTicket, Company, etc.
│   │   ├── repositories.py                 # CaseRepo, QARepo, MantisRepo, CompanyRepo, RuleRepo, etc.
│   │   ├── fts.py                          # FTSManager: FTS5 索引建立、jieba 斷詞搜尋、同義詞擴展
│   │   ├── backup.py                       # BackupManager: 備份、還原、保留策略清理
│   │   ├── merge.py                        # MergeManager: 多 DB 合併匯入、衝突偵測
│   │   └── migration.py                    # MigrationManager: 舊 DB schema 偵測、資料轉換匯入
│   └── i18n/                               # （空目錄，Phase 6 填充）
├── tests/
│   ├── conftest.py                         # pytest fixtures（temp DB, sample data）
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_database.py                # DatabaseManager 測試
│   │   ├── test_models.py                  # 資料模型測試
│   │   ├── test_repositories.py            # Repository CRUD 測試
│   │   ├── test_fts.py                     # FTS5 搜尋測試
│   │   ├── test_backup.py                  # 備份/還原測試
│   │   ├── test_merge.py                   # 合併匯入測試
│   │   └── test_migration.py               # 舊 DB 遷移測試
│   └── integration/
│       └── __init__.py
└── resources/                              # 靜態資源（空目錄）
```

---

### Task 1: 專案骨架建置

**Files:**
- Create: `pyproject.toml`
- Create: `src/hcp_cms/__init__.py`
- Create: `src/hcp_cms/data/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`

- [ ] **Step 1: 建立 pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "hcp-cms"
version = "2.0.0"
description = "HCP Customer Service Management System"
requires-python = ">=3.10"
dependencies = [
    "PySide6>=6.6",
    "openpyxl>=3.1",
    "extract-msg>=0.48",
    "exchangelib>=5.1",
    "requests>=2.31",
    "keyring>=25.0",
    "jieba>=0.42",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-qt>=4.3",
    "pytest-cov>=4.1",
    "pytest-mock>=3.12",
    "ruff>=0.3",
    "mypy>=1.8",
    "pyinstaller>=6.3",
    "pre-commit>=3.6",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = "-v --tb=short"

[tool.ruff]
target-version = "py310"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

- [ ] **Step 2: 建立套件初始化檔案**

`src/hcp_cms/__init__.py`:
```python
"""HCP Customer Service Management System."""

__version__ = "2.0.0"
```

`src/hcp_cms/data/__init__.py`:
```python
"""Data access layer — database, models, repositories, FTS, backup."""
```

`tests/conftest.py`:
```python
"""Shared pytest fixtures for HCP CMS tests."""

import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Provide a temporary database file path."""
    return tmp_path / "test_cs_tracker.db"


@pytest.fixture
def db_conn(tmp_db_path: Path) -> sqlite3.Connection:
    """Provide a fresh SQLite connection with WAL mode."""
    conn = sqlite3.connect(str(tmp_db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
```

`tests/unit/__init__.py` 和 `tests/integration/__init__.py`: 空檔案。

- [ ] **Step 3: 建立目錄結構**

```bash
mkdir -p src/hcp_cms/data src/hcp_cms/i18n tests/unit tests/integration resources
```

- [ ] **Step 4: 安裝開發依賴並驗證**

```bash
pip install -e ".[dev]"
pytest --co -q
```

Expected: 顯示 "no tests ran" 但無錯誤。

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/ tests/ resources/
git commit -m "feat: initialize project skeleton with pyproject.toml and test infrastructure"
```

---

### Task 2: 資料模型（models.py）

**Files:**
- Create: `src/hcp_cms/data/models.py`
- Create: `tests/unit/test_models.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/unit/test_models.py`:
```python
"""Tests for data models."""

from hcp_cms.data.models import (
    Case,
    CaseMantisLink,
    ClassificationRule,
    Company,
    MantisTicket,
    ProcessedFile,
    QAKnowledge,
    Synonym,
)


class TestCase:
    def test_create_case_with_defaults(self):
        case = Case(case_id="CS-2026-001", subject="Test issue")
        assert case.case_id == "CS-2026-001"
        assert case.status == "處理中"
        assert case.priority == "中"
        assert case.replied == "否"
        assert case.reply_count == 0
        assert case.source == "email"

    def test_case_is_open(self):
        case = Case(case_id="CS-2026-001", subject="Test")
        assert case.is_open is True
        case.status = "已完成"
        assert case.is_open is False
        case.status = "Closed"
        assert case.is_open is False

    def test_case_is_overdue_sla(self):
        case = Case(
            case_id="CS-2026-001",
            subject="Test",
            priority="高",
            sent_time="2026/03/20 09:00",
            replied="否",
        )
        # High priority SLA is 4 hours — this case has no reply
        assert case.sla_hours == 4

    def test_case_sla_hours_by_priority(self):
        normal = Case(case_id="CS-2026-001", subject="Test", priority="中")
        assert normal.sla_hours == 24

        high = Case(case_id="CS-2026-002", subject="Test", priority="高")
        assert high.sla_hours == 4

    def test_case_sla_hours_custom(self):
        custom = Case(
            case_id="CS-2026-003",
            subject="Test",
            issue_type="客制需求",
        )
        assert custom.sla_hours == 48


class TestCompany:
    def test_create_company(self):
        company = Company(
            company_id="COMP-001",
            name="日月光集團",
            domain="aseglobal.com",
        )
        assert company.company_id == "COMP-001"
        assert company.name == "日月光集團"
        assert company.domain == "aseglobal.com"
        assert company.alias is None


class TestQAKnowledge:
    def test_create_qa(self):
        qa = QAKnowledge(
            qa_id="QA-202603-001",
            question="如何計算薪資？",
            answer="進入薪資模組...",
        )
        assert qa.qa_id == "QA-202603-001"
        assert qa.source == "manual"


class TestMantisTicket:
    def test_create_ticket(self):
        ticket = MantisTicket(ticket_id="15562", summary="加班費計算")
        assert ticket.ticket_id == "15562"
        assert ticket.status is None


class TestClassificationRule:
    def test_create_rule(self):
        rule = ClassificationRule(
            rule_type="issue",
            pattern=r"bug|錯誤|異常",
            value="BUG",
            priority=1,
        )
        assert rule.enabled is True
        assert rule.rule_id is None


class TestProcessedFile:
    def test_create_processed_file(self):
        pf = ProcessedFile(file_hash="abc123", filename="test.msg")
        assert pf.file_hash == "abc123"
        assert pf.message_id is None


class TestSynonym:
    def test_create_synonym(self):
        syn = Synonym(word="薪水", synonym="薪資", group_name="薪資相關")
        assert syn.word == "薪水"
        assert syn.id is None


class TestCaseMantisLink:
    def test_create_link(self):
        link = CaseMantisLink(case_id="CS-2026-001", ticket_id="15562")
        assert link.case_id == "CS-2026-001"
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
pytest tests/unit/test_models.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'hcp_cms.data.models'`

- [ ] **Step 3: 實作 models.py**

`src/hcp_cms/data/models.py`:
```python
"""Data models for HCP CMS — all entities as dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


# SLA constants
SLA_HOURS_NORMAL = 24
SLA_HOURS_HIGH = 4
SLA_HOURS_CUSTOM = 48


@dataclass
class Case:
    """客服案件 — cs_cases table."""

    case_id: str
    subject: str
    contact_method: str = "Email"
    status: str = "處理中"
    priority: str = "中"
    replied: str = "否"
    sent_time: str | None = None
    company_id: str | None = None
    contact_person: str | None = None
    system_product: str | None = None
    issue_type: str | None = None
    error_type: str | None = None
    impact_period: str | None = None
    progress: str | None = None
    actual_reply: str | None = None
    notes: str | None = None
    rd_assignee: str | None = None
    handler: str | None = None
    reply_count: int = 0
    linked_case_id: str | None = None
    source: str = "email"
    created_at: str | None = None
    updated_at: str | None = None

    @property
    def is_open(self) -> bool:
        """Case is open if not completed or closed."""
        return self.status not in ("已完成", "Closed")

    @property
    def sla_hours(self) -> int:
        """Return SLA hours based on priority and issue type."""
        if self.issue_type == "客制需求":
            return SLA_HOURS_CUSTOM
        if self.priority == "高":
            return SLA_HOURS_HIGH
        return SLA_HOURS_NORMAL


@dataclass
class Company:
    """客戶公司 — companies table."""

    company_id: str
    name: str
    domain: str
    alias: str | None = None
    contact_info: str | None = None
    created_at: str | None = None


@dataclass
class QAKnowledge:
    """QA 知識庫 — qa_knowledge table."""

    qa_id: str
    question: str
    answer: str
    system_product: str | None = None
    issue_type: str | None = None
    error_type: str | None = None
    solution: str | None = None
    keywords: str | None = None
    has_image: str = "否"
    doc_name: str | None = None
    company_id: str | None = None
    source_case_id: str | None = None
    source: str = "manual"
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    notes: str | None = None


@dataclass
class MantisTicket:
    """Mantis 票務 — mantis_tickets table."""

    ticket_id: str
    summary: str
    created_time: str | None = None
    company_id: str | None = None
    priority: str | None = None
    status: str | None = None
    issue_type: str | None = None
    module: str | None = None
    handler: str | None = None
    planned_fix: str | None = None
    actual_fix: str | None = None
    progress: str | None = None
    notes: str | None = None
    synced_at: str | None = None


@dataclass
class ClassificationRule:
    """分類規則 — classification_rules table."""

    rule_type: str
    pattern: str
    value: str
    priority: int
    rule_id: int | None = None
    enabled: bool = True
    created_at: str | None = None


@dataclass
class ProcessedFile:
    """已處理信件 — processed_files table."""

    file_hash: str
    filename: str
    message_id: str | None = None
    processed_at: str | None = None


@dataclass
class Synonym:
    """同義詞 — synonyms table."""

    word: str
    synonym: str
    group_name: str
    id: int | None = None


@dataclass
class CaseMantisLink:
    """案件-Mantis 關聯 — case_mantis table."""

    case_id: str
    ticket_id: str
```

- [ ] **Step 4: 執行測試確認通過**

```bash
pytest tests/unit/test_models.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/data/models.py tests/unit/test_models.py
git commit -m "feat: add data models for all database entities"
```

---

### Task 3: 資料庫管理（database.py）

**Files:**
- Create: `src/hcp_cms/data/database.py`
- Create: `tests/unit/test_database.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/unit/test_database.py`:
```python
"""Tests for DatabaseManager."""

import sqlite3
from pathlib import Path

import pytest

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
        cursor = db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
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
        result = db.connection.execute(
            "SELECT value FROM db_meta WHERE key = 'schema_version'"
        ).fetchone()
        assert result[0] == "2.0.0"
        db.close()

    def test_fts_tables_created(self, tmp_db_path: Path):
        db = DatabaseManager(tmp_db_path)
        db.initialize()
        cursor = db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%fts%'"
        )
        fts_tables = {row[0] for row in cursor.fetchall()}
        assert "qa_fts" in fts_tables
        assert "cases_fts" in fts_tables
        db.close()

    def test_context_manager(self, tmp_db_path: Path):
        with DatabaseManager(tmp_db_path) as db:
            db.initialize()
            assert db.connection is not None
        # After context exit, connection should be closed

    def test_get_connection_with_retry(self, tmp_db_path: Path):
        db = DatabaseManager(tmp_db_path)
        db.initialize()
        conn = db.connection
        assert isinstance(conn, sqlite3.Connection)
        db.close()
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
pytest tests/unit/test_database.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 實作 database.py**

`src/hcp_cms/data/database.py`:
```python
"""SQLite database manager with WAL mode and schema initialization."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "2.0.0"
BUSY_TIMEOUT_MS = 5000

# Schema DDL statements
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

-- FTS5 virtual tables (pre-tokenized content, space-separated)
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
        """Return the active database connection."""
        if self._conn is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._conn

    def initialize(self) -> None:
        """Open connection, set WAL mode, create schema if needed."""
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
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> DatabaseManager:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        self.close()
```

- [ ] **Step 4: 執行測試確認通過**

```bash
pytest tests/unit/test_database.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/data/database.py tests/unit/test_database.py
git commit -m "feat: add DatabaseManager with WAL mode and full schema"
```

---

### Task 4: Repository — Company CRUD

**Files:**
- Create: `src/hcp_cms/data/repositories.py`
- Create: `tests/unit/test_repositories.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/unit/test_repositories.py`:
```python
"""Tests for Repository CRUD operations."""

from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Company
from hcp_cms.data.repositories import CompanyRepository


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    """Provide an initialized DatabaseManager."""
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


class TestCompanyRepository:
    def test_insert_and_get(self, db: DatabaseManager):
        repo = CompanyRepository(db.connection)
        company = Company(
            company_id="COMP-001",
            name="日月光集團",
            domain="aseglobal.com",
        )
        repo.insert(company)
        result = repo.get_by_id("COMP-001")
        assert result is not None
        assert result.name == "日月光集團"
        assert result.domain == "aseglobal.com"

    def test_get_by_domain(self, db: DatabaseManager):
        repo = CompanyRepository(db.connection)
        company = Company(
            company_id="COMP-001",
            name="日月光集團",
            domain="aseglobal.com",
        )
        repo.insert(company)
        result = repo.get_by_domain("aseglobal.com")
        assert result is not None
        assert result.company_id == "COMP-001"

    def test_get_by_domain_not_found(self, db: DatabaseManager):
        repo = CompanyRepository(db.connection)
        result = repo.get_by_domain("unknown.com")
        assert result is None

    def test_list_all(self, db: DatabaseManager):
        repo = CompanyRepository(db.connection)
        repo.insert(Company(company_id="C1", name="公司A", domain="a.com"))
        repo.insert(Company(company_id="C2", name="公司B", domain="b.com"))
        results = repo.list_all()
        assert len(results) == 2

    def test_update(self, db: DatabaseManager):
        repo = CompanyRepository(db.connection)
        company = Company(company_id="C1", name="舊名", domain="a.com")
        repo.insert(company)
        company.name = "新名"
        repo.update(company)
        result = repo.get_by_id("C1")
        assert result is not None
        assert result.name == "新名"

    def test_delete(self, db: DatabaseManager):
        repo = CompanyRepository(db.connection)
        repo.insert(Company(company_id="C1", name="公司", domain="a.com"))
        repo.delete("C1")
        result = repo.get_by_id("C1")
        assert result is None
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
pytest tests/unit/test_repositories.py::TestCompanyRepository -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: 實作 CompanyRepository**

`src/hcp_cms/data/repositories.py`:
```python
"""Repository pattern for database CRUD operations."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from hcp_cms.data.models import (
    Case,
    CaseMantisLink,
    ClassificationRule,
    Company,
    MantisTicket,
    ProcessedFile,
    QAKnowledge,
    Synonym,
)


def _now() -> str:
    return datetime.now().strftime("%Y/%m/%d %H:%M:%S")


class CompanyRepository:
    """CRUD for companies table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, company: Company) -> None:
        if company.created_at is None:
            company.created_at = _now()
        self._conn.execute(
            """INSERT INTO companies (company_id, name, domain, alias, contact_info, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (company.company_id, company.name, company.domain,
             company.alias, company.contact_info, company.created_at),
        )
        self._conn.commit()

    def get_by_id(self, company_id: str) -> Company | None:
        row = self._conn.execute(
            "SELECT * FROM companies WHERE company_id = ?", (company_id,)
        ).fetchone()
        if row is None:
            return None
        return Company(**dict(row))

    def get_by_domain(self, domain: str) -> Company | None:
        row = self._conn.execute(
            "SELECT * FROM companies WHERE domain = ?", (domain,)
        ).fetchone()
        if row is None:
            return None
        return Company(**dict(row))

    def list_all(self) -> list[Company]:
        rows = self._conn.execute("SELECT * FROM companies ORDER BY name").fetchall()
        return [Company(**dict(row)) for row in rows]

    def update(self, company: Company) -> None:
        self._conn.execute(
            """UPDATE companies SET name=?, domain=?, alias=?, contact_info=?
               WHERE company_id=?""",
            (company.name, company.domain, company.alias,
             company.contact_info, company.company_id),
        )
        self._conn.commit()

    def delete(self, company_id: str) -> None:
        self._conn.execute("DELETE FROM companies WHERE company_id = ?", (company_id,))
        self._conn.commit()
```

- [ ] **Step 4: 執行測試確認通過**

```bash
pytest tests/unit/test_repositories.py::TestCompanyRepository -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/data/repositories.py tests/unit/test_repositories.py
git commit -m "feat: add CompanyRepository with CRUD operations"
```

---

### Task 5: Repository — Case CRUD

**Files:**
- Modify: `src/hcp_cms/data/repositories.py`
- Modify: `tests/unit/test_repositories.py`

- [ ] **Step 1: 寫失敗的測試（追加至 test_repositories.py）**

追加至 `tests/unit/test_repositories.py`:
```python
from hcp_cms.data.repositories import CaseRepository


class TestCaseRepository:
    def test_insert_and_get(self, db: DatabaseManager):
        repo = CaseRepository(db.connection)
        case = Case(case_id="CS-2026-001", subject="薪資計算問題")
        repo.insert(case)
        result = repo.get_by_id("CS-2026-001")
        assert result is not None
        assert result.subject == "薪資計算問題"
        assert result.status == "處理中"

    def test_next_case_id_first(self, db: DatabaseManager):
        repo = CaseRepository(db.connection)
        next_id = repo.next_case_id()
        assert next_id == "CS-2026-001"

    def test_next_case_id_sequential(self, db: DatabaseManager):
        repo = CaseRepository(db.connection)
        repo.insert(Case(case_id="CS-2026-001", subject="Test 1"))
        repo.insert(Case(case_id="CS-2026-005", subject="Test 5"))
        next_id = repo.next_case_id()
        assert next_id == "CS-2026-006"

    def test_list_by_status(self, db: DatabaseManager):
        repo = CaseRepository(db.connection)
        repo.insert(Case(case_id="CS-2026-001", subject="A", status="處理中"))
        repo.insert(Case(case_id="CS-2026-002", subject="B", status="已完成"))
        repo.insert(Case(case_id="CS-2026-003", subject="C", status="處理中"))
        open_cases = repo.list_by_status("處理中")
        assert len(open_cases) == 2

    def test_list_by_month(self, db: DatabaseManager):
        repo = CaseRepository(db.connection)
        repo.insert(Case(case_id="CS-2026-001", subject="A", sent_time="2026/03/15 09:00"))
        repo.insert(Case(case_id="CS-2026-002", subject="B", sent_time="2026/02/10 10:00"))
        march_cases = repo.list_by_month(2026, 3)
        assert len(march_cases) == 1
        assert march_cases[0].case_id == "CS-2026-001"

    def test_update_status(self, db: DatabaseManager):
        repo = CaseRepository(db.connection)
        repo.insert(Case(case_id="CS-2026-001", subject="Test"))
        repo.update_status("CS-2026-001", "已回覆")
        result = repo.get_by_id("CS-2026-001")
        assert result is not None
        assert result.status == "已回覆"

    def test_update(self, db: DatabaseManager):
        repo = CaseRepository(db.connection)
        case = Case(case_id="CS-2026-001", subject="Old")
        repo.insert(case)
        case.subject = "New"
        case.progress = "已處理"
        repo.update(case)
        result = repo.get_by_id("CS-2026-001")
        assert result is not None
        assert result.subject == "New"
        assert result.progress == "已處理"

    def test_count_by_month(self, db: DatabaseManager):
        repo = CaseRepository(db.connection)
        repo.insert(Case(case_id="CS-2026-001", subject="A", sent_time="2026/03/15 09:00"))
        repo.insert(Case(case_id="CS-2026-002", subject="B", sent_time="2026/03/20 10:00"))
        assert repo.count_by_month(2026, 3) == 2
        assert repo.count_by_month(2026, 2) == 0
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
pytest tests/unit/test_repositories.py::TestCaseRepository -v
```

Expected: FAIL

- [ ] **Step 3: 實作 CaseRepository**

追加至 `src/hcp_cms/data/repositories.py`:
```python
class CaseRepository:
    """CRUD for cs_cases table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, case: Case) -> None:
        now = _now()
        if case.created_at is None:
            case.created_at = now
        if case.updated_at is None:
            case.updated_at = now
        self._conn.execute(
            """INSERT INTO cs_cases
               (case_id, contact_method, status, priority, replied, sent_time,
                company_id, contact_person, subject, system_product, issue_type,
                error_type, impact_period, progress, actual_reply, notes,
                rd_assignee, handler, reply_count, linked_case_id, source,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (case.case_id, case.contact_method, case.status, case.priority,
             case.replied, case.sent_time, case.company_id, case.contact_person,
             case.subject, case.system_product, case.issue_type, case.error_type,
             case.impact_period, case.progress, case.actual_reply, case.notes,
             case.rd_assignee, case.handler, case.reply_count, case.linked_case_id,
             case.source, case.created_at, case.updated_at),
        )
        self._conn.commit()

    def get_by_id(self, case_id: str) -> Case | None:
        row = self._conn.execute(
            "SELECT * FROM cs_cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if row is None:
            return None
        return Case(**dict(row))

    def next_case_id(self) -> str:
        year = datetime.now().year
        prefix = f"CS-{year}-"
        row = self._conn.execute(
            "SELECT case_id FROM cs_cases WHERE case_id LIKE ? ORDER BY case_id DESC LIMIT 1",
            (f"{prefix}%",),
        ).fetchone()
        if row is None:
            return f"{prefix}001"
        last_num = int(row[0].split("-")[-1])
        return f"{prefix}{last_num + 1:03d}"

    def list_by_status(self, status: str) -> list[Case]:
        rows = self._conn.execute(
            "SELECT * FROM cs_cases WHERE status = ? ORDER BY sent_time DESC", (status,)
        ).fetchall()
        return [Case(**dict(row)) for row in rows]

    def list_by_month(self, year: int, month: int) -> list[Case]:
        prefix = f"{year}/{month:02d}"
        rows = self._conn.execute(
            "SELECT * FROM cs_cases WHERE sent_time LIKE ? ORDER BY sent_time DESC",
            (f"{prefix}%",),
        ).fetchall()
        return [Case(**dict(row)) for row in rows]

    def update_status(self, case_id: str, status: str) -> None:
        self._conn.execute(
            "UPDATE cs_cases SET status=?, updated_at=? WHERE case_id=?",
            (status, _now(), case_id),
        )
        self._conn.commit()

    def update(self, case: Case) -> None:
        case.updated_at = _now()
        self._conn.execute(
            """UPDATE cs_cases SET
               contact_method=?, status=?, priority=?, replied=?, sent_time=?,
               company_id=?, contact_person=?, subject=?, system_product=?,
               issue_type=?, error_type=?, impact_period=?, progress=?,
               actual_reply=?, notes=?, rd_assignee=?, handler=?,
               reply_count=?, linked_case_id=?, source=?, updated_at=?
               WHERE case_id=?""",
            (case.contact_method, case.status, case.priority, case.replied,
             case.sent_time, case.company_id, case.contact_person, case.subject,
             case.system_product, case.issue_type, case.error_type,
             case.impact_period, case.progress, case.actual_reply, case.notes,
             case.rd_assignee, case.handler, case.reply_count,
             case.linked_case_id, case.source, case.updated_at, case.case_id),
        )
        self._conn.commit()

    def count_by_month(self, year: int, month: int) -> int:
        prefix = f"{year}/{month:02d}"
        row = self._conn.execute(
            "SELECT COUNT(*) FROM cs_cases WHERE sent_time LIKE ?",
            (f"{prefix}%",),
        ).fetchone()
        return row[0]
```

- [ ] **Step 4: 執行測試確認通過**

```bash
pytest tests/unit/test_repositories.py -v
```

Expected: 全部 PASS（Company + Case）

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/data/repositories.py tests/unit/test_repositories.py
git commit -m "feat: add CaseRepository with CRUD, next_case_id, and query methods"
```

---

### Task 6: Repository — QA, Mantis, Rules, ProcessedFile, Synonym, CaseMantis

**Files:**
- Modify: `src/hcp_cms/data/repositories.py`
- Modify: `tests/unit/test_repositories.py`

- [ ] **Step 1: 寫失敗的測試**

追加至 `tests/unit/test_repositories.py`:
```python
from hcp_cms.data.repositories import (
    QARepository,
    MantisRepository,
    RuleRepository,
    ProcessedFileRepository,
    SynonymRepository,
    CaseMantisRepository,
)
from hcp_cms.data.models import (
    QAKnowledge,
    MantisTicket,
    ClassificationRule,
    ProcessedFile,
    Synonym,
    CaseMantisLink,
)


class TestQARepository:
    def test_insert_and_get(self, db: DatabaseManager):
        repo = QARepository(db.connection)
        qa = QAKnowledge(qa_id="QA-202603-001", question="如何計算？", answer="進入模組...")
        repo.insert(qa)
        result = repo.get_by_id("QA-202603-001")
        assert result is not None
        assert result.question == "如何計算？"

    def test_next_qa_id(self, db: DatabaseManager):
        repo = QARepository(db.connection)
        next_id = repo.next_qa_id()
        assert next_id == "QA-202603-001"

    def test_list_all(self, db: DatabaseManager):
        repo = QARepository(db.connection)
        repo.insert(QAKnowledge(qa_id="QA-202603-001", question="Q1", answer="A1"))
        repo.insert(QAKnowledge(qa_id="QA-202603-002", question="Q2", answer="A2"))
        assert len(repo.list_all()) == 2


class TestMantisRepository:
    def test_insert_and_get(self, db: DatabaseManager):
        repo = MantisRepository(db.connection)
        ticket = MantisTicket(ticket_id="15562", summary="加班費計算")
        repo.upsert(ticket)
        result = repo.get_by_id("15562")
        assert result is not None
        assert result.summary == "加班費計算"

    def test_upsert_updates_existing(self, db: DatabaseManager):
        repo = MantisRepository(db.connection)
        repo.upsert(MantisTicket(ticket_id="15562", summary="Old"))
        repo.upsert(MantisTicket(ticket_id="15562", summary="New"))
        result = repo.get_by_id("15562")
        assert result is not None
        assert result.summary == "New"


class TestRuleRepository:
    def test_insert_and_list_by_type(self, db: DatabaseManager):
        repo = RuleRepository(db.connection)
        rule = ClassificationRule(rule_type="issue", pattern="bug", value="BUG", priority=1)
        repo.insert(rule)
        rules = repo.list_by_type("issue")
        assert len(rules) == 1
        assert rules[0].value == "BUG"
        assert rules[0].rule_id is not None

    def test_list_by_type_ordered_by_priority(self, db: DatabaseManager):
        repo = RuleRepository(db.connection)
        repo.insert(ClassificationRule(rule_type="issue", pattern="b", value="B", priority=2))
        repo.insert(ClassificationRule(rule_type="issue", pattern="a", value="A", priority=1))
        rules = repo.list_by_type("issue")
        assert rules[0].value == "A"
        assert rules[1].value == "B"

    def test_delete(self, db: DatabaseManager):
        repo = RuleRepository(db.connection)
        rule = ClassificationRule(rule_type="issue", pattern="x", value="X", priority=1)
        repo.insert(rule)
        rules = repo.list_by_type("issue")
        repo.delete(rules[0].rule_id)
        assert len(repo.list_by_type("issue")) == 0


class TestProcessedFileRepository:
    def test_insert_and_exists(self, db: DatabaseManager):
        repo = ProcessedFileRepository(db.connection)
        pf = ProcessedFile(file_hash="abc123", filename="test.msg")
        repo.insert(pf)
        assert repo.exists("abc123") is True
        assert repo.exists("unknown") is False


class TestSynonymRepository:
    def test_insert_and_get_synonyms(self, db: DatabaseManager):
        repo = SynonymRepository(db.connection)
        repo.insert(Synonym(word="薪水", synonym="薪資", group_name="薪資"))
        repo.insert(Synonym(word="薪水", synonym="工資", group_name="薪資"))
        synonyms = repo.get_synonyms("薪水")
        assert "薪資" in synonyms
        assert "工資" in synonyms

    def test_get_synonyms_reverse(self, db: DatabaseManager):
        repo = SynonymRepository(db.connection)
        repo.insert(Synonym(word="薪水", synonym="薪資", group_name="薪資"))
        # Searching for "薪資" should find "薪水" via group
        synonyms = repo.get_group_words("薪資")
        assert "薪水" in synonyms
        assert "薪資" in synonyms


class TestCaseMantisRepository:
    def test_link_and_get(self, db: DatabaseManager):
        # Insert prerequisite data
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject) VALUES (?, ?)",
            ("CS-2026-001", "Test"),
        )
        db.connection.execute(
            "INSERT INTO mantis_tickets (ticket_id, summary) VALUES (?, ?)",
            ("15562", "Bug"),
        )
        db.connection.commit()

        repo = CaseMantisRepository(db.connection)
        repo.link(CaseMantisLink(case_id="CS-2026-001", ticket_id="15562"))
        tickets = repo.get_tickets_for_case("CS-2026-001")
        assert "15562" in tickets
        cases = repo.get_cases_for_ticket("15562")
        assert "CS-2026-001" in cases
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
pytest tests/unit/test_repositories.py -v -k "not TestCompany and not TestCase"
```

Expected: FAIL — ImportError

- [ ] **Step 3: 實作剩餘 Repository 類別**

追加至 `src/hcp_cms/data/repositories.py`:
```python
class QARepository:
    """CRUD for qa_knowledge table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, qa: QAKnowledge) -> None:
        now = _now()
        if qa.created_at is None:
            qa.created_at = now
        if qa.updated_at is None:
            qa.updated_at = now
        self._conn.execute(
            """INSERT INTO qa_knowledge
               (qa_id, system_product, issue_type, error_type, question, answer,
                solution, keywords, has_image, doc_name, company_id, source_case_id,
                source, created_by, created_at, updated_at, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (qa.qa_id, qa.system_product, qa.issue_type, qa.error_type,
             qa.question, qa.answer, qa.solution, qa.keywords, qa.has_image,
             qa.doc_name, qa.company_id, qa.source_case_id, qa.source,
             qa.created_by, qa.created_at, qa.updated_at, qa.notes),
        )
        self._conn.commit()

    def get_by_id(self, qa_id: str) -> QAKnowledge | None:
        row = self._conn.execute(
            "SELECT * FROM qa_knowledge WHERE qa_id = ?", (qa_id,)
        ).fetchone()
        if row is None:
            return None
        return QAKnowledge(**dict(row))

    def next_qa_id(self) -> str:
        now = datetime.now()
        prefix = f"QA-{now.year}{now.month:02d}-"
        row = self._conn.execute(
            "SELECT qa_id FROM qa_knowledge WHERE qa_id LIKE ? ORDER BY qa_id DESC LIMIT 1",
            (f"{prefix}%",),
        ).fetchone()
        if row is None:
            return f"{prefix}001"
        last_num = int(row[0].split("-")[-1])
        return f"{prefix}{last_num + 1:03d}"

    def list_all(self) -> list[QAKnowledge]:
        rows = self._conn.execute(
            "SELECT * FROM qa_knowledge ORDER BY created_at DESC"
        ).fetchall()
        return [QAKnowledge(**dict(row)) for row in rows]

    def update(self, qa: QAKnowledge) -> None:
        qa.updated_at = _now()
        self._conn.execute(
            """UPDATE qa_knowledge SET
               system_product=?, issue_type=?, error_type=?, question=?, answer=?,
               solution=?, keywords=?, has_image=?, doc_name=?, company_id=?,
               source_case_id=?, source=?, created_by=?, updated_at=?, notes=?
               WHERE qa_id=?""",
            (qa.system_product, qa.issue_type, qa.error_type, qa.question,
             qa.answer, qa.solution, qa.keywords, qa.has_image, qa.doc_name,
             qa.company_id, qa.source_case_id, qa.source, qa.created_by,
             qa.updated_at, qa.notes, qa.qa_id),
        )
        self._conn.commit()

    def delete(self, qa_id: str) -> None:
        self._conn.execute("DELETE FROM qa_knowledge WHERE qa_id = ?", (qa_id,))
        self._conn.commit()


class MantisRepository:
    """CRUD for mantis_tickets table (upsert pattern)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, ticket: MantisTicket) -> None:
        ticket.synced_at = _now()
        self._conn.execute(
            """INSERT INTO mantis_tickets
               (ticket_id, created_time, company_id, summary, priority, status,
                issue_type, module, handler, planned_fix, actual_fix, progress,
                notes, synced_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(ticket_id) DO UPDATE SET
                summary=excluded.summary, priority=excluded.priority,
                status=excluded.status, issue_type=excluded.issue_type,
                module=excluded.module, handler=excluded.handler,
                planned_fix=excluded.planned_fix, actual_fix=excluded.actual_fix,
                progress=excluded.progress, notes=excluded.notes,
                synced_at=excluded.synced_at""",
            (ticket.ticket_id, ticket.created_time, ticket.company_id,
             ticket.summary, ticket.priority, ticket.status, ticket.issue_type,
             ticket.module, ticket.handler, ticket.planned_fix, ticket.actual_fix,
             ticket.progress, ticket.notes, ticket.synced_at),
        )
        self._conn.commit()

    def get_by_id(self, ticket_id: str) -> MantisTicket | None:
        row = self._conn.execute(
            "SELECT * FROM mantis_tickets WHERE ticket_id = ?", (ticket_id,)
        ).fetchone()
        if row is None:
            return None
        return MantisTicket(**dict(row))

    def list_all(self) -> list[MantisTicket]:
        rows = self._conn.execute(
            "SELECT * FROM mantis_tickets ORDER BY created_time DESC"
        ).fetchall()
        return [MantisTicket(**dict(row)) for row in rows]


class RuleRepository:
    """CRUD for classification_rules table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, rule: ClassificationRule) -> None:
        if rule.created_at is None:
            rule.created_at = _now()
        cursor = self._conn.execute(
            """INSERT INTO classification_rules
               (rule_type, pattern, value, priority, enabled, created_at)
               VALUES (?,?,?,?,?,?)""",
            (rule.rule_type, rule.pattern, rule.value, rule.priority,
             1 if rule.enabled else 0, rule.created_at),
        )
        rule.rule_id = cursor.lastrowid
        self._conn.commit()

    def list_by_type(self, rule_type: str) -> list[ClassificationRule]:
        rows = self._conn.execute(
            """SELECT * FROM classification_rules
               WHERE rule_type = ? AND enabled = 1
               ORDER BY priority ASC""",
            (rule_type,),
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["enabled"] = bool(d["enabled"])
            result.append(ClassificationRule(**d))
        return result

    def delete(self, rule_id: int | None) -> None:
        if rule_id is None:
            return
        self._conn.execute(
            "DELETE FROM classification_rules WHERE rule_id = ?", (rule_id,)
        )
        self._conn.commit()


class ProcessedFileRepository:
    """CRUD for processed_files table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, pf: ProcessedFile) -> None:
        if pf.processed_at is None:
            pf.processed_at = _now()
        self._conn.execute(
            """INSERT OR IGNORE INTO processed_files
               (file_hash, filename, message_id, processed_at)
               VALUES (?,?,?,?)""",
            (pf.file_hash, pf.filename, pf.message_id, pf.processed_at),
        )
        self._conn.commit()

    def exists(self, file_hash: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM processed_files WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        return row is not None


class SynonymRepository:
    """CRUD for synonyms table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, syn: Synonym) -> None:
        self._conn.execute(
            "INSERT INTO synonyms (word, synonym, group_name) VALUES (?,?,?)",
            (syn.word, syn.synonym, syn.group_name),
        )
        self._conn.commit()

    def get_synonyms(self, word: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT synonym FROM synonyms WHERE word = ?", (word,)
        ).fetchall()
        return [row[0] for row in rows]

    def get_group_words(self, group_name: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT word FROM synonyms WHERE group_name = ? "
            "UNION SELECT DISTINCT synonym FROM synonyms WHERE group_name = ?",
            (group_name, group_name),
        ).fetchall()
        return [row[0] for row in rows]

    def list_groups(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT group_name FROM synonyms ORDER BY group_name"
        ).fetchall()
        return [row[0] for row in rows]

    def delete_group(self, group_name: str) -> None:
        self._conn.execute(
            "DELETE FROM synonyms WHERE group_name = ?", (group_name,)
        )
        self._conn.commit()


class CaseMantisRepository:
    """CRUD for case_mantis junction table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def link(self, link: CaseMantisLink) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO case_mantis (case_id, ticket_id) VALUES (?,?)",
            (link.case_id, link.ticket_id),
        )
        self._conn.commit()

    def get_tickets_for_case(self, case_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT ticket_id FROM case_mantis WHERE case_id = ?", (case_id,)
        ).fetchall()
        return [row[0] for row in rows]

    def get_cases_for_ticket(self, ticket_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT case_id FROM case_mantis WHERE ticket_id = ?", (ticket_id,)
        ).fetchall()
        return [row[0] for row in rows]
```

- [ ] **Step 4: 執行全部 Repository 測試**

```bash
pytest tests/unit/test_repositories.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/data/repositories.py tests/unit/test_repositories.py
git commit -m "feat: add QA, Mantis, Rule, ProcessedFile, Synonym, CaseMantis repositories"
```

---

### Task 7: FTS5 全文搜尋（fts.py）

**Files:**
- Create: `src/hcp_cms/data/fts.py`
- Create: `tests/unit/test_fts.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/unit/test_fts.py`:
```python
"""Tests for FTS5 full-text search with jieba tokenization."""

from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.fts import FTSManager


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def fts(db: DatabaseManager) -> FTSManager:
    return FTSManager(db.connection)


class TestFTSManager:
    def test_index_qa_and_search(self, fts: FTSManager):
        fts.index_qa("QA-001", "員工離職薪資如何計算", "進入薪資模組設定", "按比例計算", "薪資 離職")
        results = fts.search_qa("薪資")
        assert len(results) > 0
        assert results[0]["qa_id"] == "QA-001"

    def test_search_qa_with_synonym_expansion(self, fts: FTSManager, db: DatabaseManager):
        # Insert synonym
        db.connection.execute(
            "INSERT INTO synonyms (word, synonym, group_name) VALUES (?,?,?)",
            ("薪水", "薪資", "薪資相關"),
        )
        db.connection.commit()

        fts.index_qa("QA-001", "員工薪資計算", "進入薪資模組", None, None)
        # Search with "薪水" should find "薪資" via synonym
        results = fts.search_qa("薪水")
        assert len(results) > 0

    def test_search_qa_no_results(self, fts: FTSManager):
        fts.index_qa("QA-001", "薪資計算", "進入模組", None, None)
        results = fts.search_qa("完全不相關的詞")
        assert len(results) == 0

    def test_index_case_and_search(self, fts: FTSManager):
        fts.index_case("CS-2026-001", "薪資計算異常", "已回覆客戶", "需確認設定")
        results = fts.search_cases("薪資")
        assert len(results) > 0
        assert results[0]["case_id"] == "CS-2026-001"

    def test_remove_qa_index(self, fts: FTSManager):
        fts.index_qa("QA-001", "薪資", "回覆", None, None)
        fts.remove_qa_index("QA-001")
        results = fts.search_qa("薪資")
        assert len(results) == 0

    def test_update_qa_index(self, fts: FTSManager):
        fts.index_qa("QA-001", "舊問題", "舊回覆", None, None)
        fts.update_qa_index("QA-001", "新問題關於請假", "新回覆", None, None)
        assert len(fts.search_qa("請假")) > 0
        assert len(fts.search_qa("舊問題")) == 0

    def test_tokenize_chinese(self, fts: FTSManager):
        tokens = fts.tokenize("員工離職薪水怎麼算")
        assert isinstance(tokens, str)
        assert " " in tokens  # space-separated
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
pytest tests/unit/test_fts.py -v
```

Expected: FAIL

- [ ] **Step 3: 實作 fts.py**

`src/hcp_cms/data/fts.py`:
```python
"""FTS5 full-text search with jieba Chinese tokenization and synonym expansion."""

from __future__ import annotations

import sqlite3

import jieba


class FTSManager:
    """Manages FTS5 indexing and searching with Chinese tokenization."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def tokenize(self, text: str) -> str:
        """Tokenize Chinese text using jieba, return space-separated tokens."""
        if not text:
            return ""
        words = jieba.cut(text, cut_all=False)
        return " ".join(w.strip() for w in words if w.strip())

    def _expand_with_synonyms(self, query: str) -> str:
        """Expand query terms with synonyms from DB."""
        tokens = self.tokenize(query).split()
        expanded: set[str] = set(tokens)

        for token in tokens:
            # Direct synonyms
            rows = self._conn.execute(
                "SELECT synonym FROM synonyms WHERE word = ?", (token,)
            ).fetchall()
            for row in rows:
                expanded.update(self.tokenize(row[0]).split())

            # Reverse synonyms (token is a synonym of another word)
            rows = self._conn.execute(
                "SELECT word FROM synonyms WHERE synonym = ?", (token,)
            ).fetchall()
            for row in rows:
                expanded.update(self.tokenize(row[0]).split())

            # Group-based expansion
            groups = self._conn.execute(
                "SELECT DISTINCT group_name FROM synonyms WHERE word = ? OR synonym = ?",
                (token, token),
            ).fetchall()
            for group_row in groups:
                group_words = self._conn.execute(
                    "SELECT word, synonym FROM synonyms WHERE group_name = ?",
                    (group_row[0],),
                ).fetchall()
                for gw in group_words:
                    expanded.update(self.tokenize(gw[0]).split())
                    expanded.update(self.tokenize(gw[1]).split())

        return " OR ".join(expanded)

    # --- QA FTS ---

    def index_qa(
        self,
        qa_id: str,
        question: str | None,
        answer: str | None,
        solution: str | None,
        keywords: str | None,
    ) -> None:
        """Insert or replace a QA entry in the FTS index."""
        self._conn.execute("DELETE FROM qa_fts WHERE qa_id = ?", (qa_id,))
        self._conn.execute(
            "INSERT INTO qa_fts (qa_id, question, answer, solution, keywords) VALUES (?,?,?,?,?)",
            (
                qa_id,
                self.tokenize(question or ""),
                self.tokenize(answer or ""),
                self.tokenize(solution or ""),
                self.tokenize(keywords or ""),
            ),
        )
        self._conn.commit()

    def remove_qa_index(self, qa_id: str) -> None:
        self._conn.execute("DELETE FROM qa_fts WHERE qa_id = ?", (qa_id,))
        self._conn.commit()

    def update_qa_index(
        self,
        qa_id: str,
        question: str | None,
        answer: str | None,
        solution: str | None,
        keywords: str | None,
    ) -> None:
        self.index_qa(qa_id, question, answer, solution, keywords)

    def search_qa(self, query: str, limit: int = 50) -> list[dict[str, str]]:
        """Search QA FTS index with synonym expansion. Returns list of {qa_id, rank}."""
        expanded = self._expand_with_synonyms(query)
        if not expanded:
            return []
        try:
            rows = self._conn.execute(
                """SELECT qa_id, rank FROM qa_fts
                   WHERE qa_fts MATCH ? ORDER BY rank LIMIT ?""",
                (expanded, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [{"qa_id": row[0], "rank": row[1]} for row in rows]

    # --- Case FTS ---

    def index_case(
        self,
        case_id: str,
        subject: str | None,
        progress: str | None,
        notes: str | None,
    ) -> None:
        self._conn.execute("DELETE FROM cases_fts WHERE case_id = ?", (case_id,))
        self._conn.execute(
            "INSERT INTO cases_fts (case_id, subject, progress, notes) VALUES (?,?,?,?)",
            (
                case_id,
                self.tokenize(subject or ""),
                self.tokenize(progress or ""),
                self.tokenize(notes or ""),
            ),
        )
        self._conn.commit()

    def search_cases(self, query: str, limit: int = 50) -> list[dict[str, str]]:
        expanded = self._expand_with_synonyms(query)
        if not expanded:
            return []
        try:
            rows = self._conn.execute(
                """SELECT case_id, rank FROM cases_fts
                   WHERE cases_fts MATCH ? ORDER BY rank LIMIT ?""",
                (expanded, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [{"case_id": row[0], "rank": row[1]} for row in rows]
```

- [ ] **Step 4: 執行測試確認通過**

```bash
pytest tests/unit/test_fts.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/data/fts.py tests/unit/test_fts.py
git commit -m "feat: add FTS5 search with jieba tokenization and synonym expansion"
```

---

### Task 8: 備份/還原（backup.py）

**Files:**
- Create: `src/hcp_cms/data/backup.py`
- Create: `tests/unit/test_backup.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/unit/test_backup.py`:
```python
"""Tests for backup, restore, and retention management."""

import time
from pathlib import Path

import pytest

from hcp_cms.data.backup import BackupManager
from hcp_cms.data.database import DatabaseManager


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def backup_dir(tmp_path: Path) -> Path:
    d = tmp_path / "backups"
    d.mkdir()
    return d


class TestBackupManager:
    def test_create_backup(self, db: DatabaseManager, backup_dir: Path):
        mgr = BackupManager(db.connection, backup_dir)
        backup_path = mgr.create_backup()
        assert backup_path.exists()
        assert backup_path.suffix == ".db"
        assert "cs_tracker_" in backup_path.name

    def test_backup_is_valid_db(self, db: DatabaseManager, backup_dir: Path):
        # Insert some data first
        db.connection.execute(
            "INSERT INTO companies (company_id, name, domain) VALUES (?,?,?)",
            ("C1", "Test", "test.com"),
        )
        db.connection.commit()

        mgr = BackupManager(db.connection, backup_dir)
        backup_path = mgr.create_backup()

        # Verify backup contains the data
        import sqlite3
        conn = sqlite3.connect(str(backup_path))
        row = conn.execute("SELECT name FROM companies WHERE company_id='C1'").fetchone()
        assert row[0] == "Test"
        conn.close()

    def test_list_backups(self, db: DatabaseManager, backup_dir: Path):
        mgr = BackupManager(db.connection, backup_dir)
        mgr.create_backup()
        time.sleep(0.1)
        mgr.create_backup()
        backups = mgr.list_backups()
        assert len(backups) == 2

    def test_restore_backup(self, db: DatabaseManager, backup_dir: Path, tmp_db_path: Path):
        # Insert data, backup, then delete data
        db.connection.execute(
            "INSERT INTO companies (company_id, name, domain) VALUES (?,?,?)",
            ("C1", "Original", "test.com"),
        )
        db.connection.commit()

        mgr = BackupManager(db.connection, backup_dir)
        backup_path = mgr.create_backup()

        # Delete the data
        db.connection.execute("DELETE FROM companies")
        db.connection.commit()
        row = db.connection.execute("SELECT COUNT(*) FROM companies").fetchone()
        assert row[0] == 0

        # Restore
        mgr.restore_backup(backup_path, tmp_db_path)

        # Reconnect and verify
        db.close()
        db2 = DatabaseManager(tmp_db_path)
        db2.initialize()
        row = db2.connection.execute("SELECT name FROM companies WHERE company_id='C1'").fetchone()
        assert row[0] == "Original"
        db2.close()

    def test_cleanup_old_backups(self, db: DatabaseManager, backup_dir: Path):
        mgr = BackupManager(db.connection, backup_dir)
        # Create 5 backups
        paths = []
        for _ in range(5):
            paths.append(mgr.create_backup())
            time.sleep(0.05)

        # Keep only 2
        mgr.cleanup_old_backups(keep_count=2)
        remaining = mgr.list_backups()
        assert len(remaining) == 2

    def test_export_as_zip(self, db: DatabaseManager, backup_dir: Path):
        mgr = BackupManager(db.connection, backup_dir)
        zip_path = mgr.export_zip(backup_dir / "export.zip")
        assert zip_path.exists()
        assert zip_path.suffix == ".zip"

    def test_restore_from_zip(self, db: DatabaseManager, backup_dir: Path, tmp_db_path: Path):
        db.connection.execute(
            "INSERT INTO companies (company_id, name, domain) VALUES (?,?,?)",
            ("C1", "ZipTest", "zip.com"),
        )
        db.connection.commit()

        mgr = BackupManager(db.connection, backup_dir)
        zip_path = mgr.export_zip(backup_dir / "export.zip")

        # Clear data
        db.connection.execute("DELETE FROM companies")
        db.connection.commit()

        # Restore from zip
        mgr.restore_from_zip(zip_path, tmp_db_path)

        db.close()
        db2 = DatabaseManager(tmp_db_path)
        db2.initialize()
        row = db2.connection.execute("SELECT name FROM companies WHERE company_id='C1'").fetchone()
        assert row[0] == "ZipTest"
        db2.close()
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
pytest tests/unit/test_backup.py -v
```

Expected: FAIL

- [ ] **Step 3: 實作 backup.py**

`src/hcp_cms/data/backup.py`:
```python
"""Database backup, restore, and retention management."""

from __future__ import annotations

import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path


class BackupManager:
    """Manages SQLite database backup, restore, and cleanup."""

    def __init__(self, conn: sqlite3.Connection, backup_dir: Path) -> None:
        self._conn = conn
        self._backup_dir = backup_dir
        self._backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self) -> Path:
        """Create a backup using sqlite3 backup API."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = self._backup_dir / f"cs_tracker_{timestamp}.db"

        backup_conn = sqlite3.connect(str(backup_path))
        self._conn.backup(backup_conn)
        backup_conn.close()

        return backup_path

    def list_backups(self) -> list[Path]:
        """List all backup files sorted by modification time (newest first)."""
        backups = sorted(
            self._backup_dir.glob("cs_tracker_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return backups

    def restore_backup(self, backup_path: Path, target_db_path: Path) -> None:
        """Restore a backup by copying it over the target database."""
        shutil.copy2(str(backup_path), str(target_db_path))

    def cleanup_old_backups(self, keep_count: int = 30) -> int:
        """Remove oldest backups, keeping only keep_count most recent. Returns count removed."""
        backups = self.list_backups()
        removed = 0
        for backup in backups[keep_count:]:
            backup.unlink()
            removed += 1
        return removed

    def export_zip(self, zip_path: Path) -> Path:
        """Export current database as a zip file."""
        backup_path = self.create_backup()
        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(str(backup_path), backup_path.name)
        backup_path.unlink()  # Clean up temp backup
        return zip_path

    def restore_from_zip(self, zip_path: Path, target_db_path: Path) -> None:
        """Restore database from a zip export."""
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            db_files = [f for f in zf.namelist() if f.endswith(".db")]
            if not db_files:
                raise ValueError("No .db file found in zip archive")
            zf.extract(db_files[0], str(target_db_path.parent))
            extracted = target_db_path.parent / db_files[0]
            shutil.move(str(extracted), str(target_db_path))
```

- [ ] **Step 4: 執行測試確認通過**

```bash
pytest tests/unit/test_backup.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/data/backup.py tests/unit/test_backup.py
git commit -m "feat: add BackupManager with backup, restore, zip export, and cleanup"
```

---

### Task 9: 合併匯入（merge.py）

**Files:**
- Create: `src/hcp_cms/data/merge.py`
- Create: `tests/unit/test_merge.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/unit/test_merge.py`:
```python
"""Tests for multi-DB merge import."""

from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.merge import MergeManager, MergePreview, ConflictStrategy
from hcp_cms.data.models import Case, Company


@pytest.fixture
def local_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_path / "local.db")
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def remote_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_path / "remote.db")
    db.initialize()
    yield db
    db.close()


class TestMergeManager:
    def test_preview_new_records(self, local_db: DatabaseManager, remote_db: DatabaseManager):
        # Remote has a case that local doesn't
        remote_db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject, status) VALUES (?,?,?)",
            ("CS-2026-001", "Remote case", "處理中"),
        )
        remote_db.connection.commit()

        mgr = MergeManager(local_db.connection)
        preview = mgr.preview(remote_db.connection)
        assert preview.cases_new == 1
        assert preview.cases_conflict == 0

    def test_preview_conflict_records(self, local_db: DatabaseManager, remote_db: DatabaseManager):
        # Both have same case_id with different data
        local_db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject) VALUES (?,?)",
            ("CS-2026-001", "Local version"),
        )
        local_db.connection.commit()

        remote_db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject) VALUES (?,?)",
            ("CS-2026-001", "Remote version"),
        )
        remote_db.connection.commit()

        mgr = MergeManager(local_db.connection)
        preview = mgr.preview(remote_db.connection)
        assert preview.cases_new == 0
        assert preview.cases_conflict == 1

    def test_merge_keep_local(self, local_db: DatabaseManager, remote_db: DatabaseManager):
        local_db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject) VALUES (?,?)",
            ("CS-2026-001", "Local"),
        )
        local_db.connection.commit()
        remote_db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject) VALUES (?,?)",
            ("CS-2026-001", "Remote"),
        )
        remote_db.connection.commit()

        mgr = MergeManager(local_db.connection)
        mgr.merge(remote_db.connection, ConflictStrategy.KEEP_LOCAL)

        row = local_db.connection.execute(
            "SELECT subject FROM cs_cases WHERE case_id='CS-2026-001'"
        ).fetchone()
        assert row[0] == "Local"

    def test_merge_keep_remote(self, local_db: DatabaseManager, remote_db: DatabaseManager):
        local_db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject) VALUES (?,?)",
            ("CS-2026-001", "Local"),
        )
        local_db.connection.commit()
        remote_db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject) VALUES (?,?)",
            ("CS-2026-001", "Remote"),
        )
        remote_db.connection.commit()

        mgr = MergeManager(local_db.connection)
        mgr.merge(remote_db.connection, ConflictStrategy.KEEP_REMOTE)

        row = local_db.connection.execute(
            "SELECT subject FROM cs_cases WHERE case_id='CS-2026-001'"
        ).fetchone()
        assert row[0] == "Remote"

    def test_merge_new_records_imported(self, local_db: DatabaseManager, remote_db: DatabaseManager):
        remote_db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject) VALUES (?,?)",
            ("CS-2026-099", "New from remote"),
        )
        remote_db.connection.commit()

        mgr = MergeManager(local_db.connection)
        result = mgr.merge(remote_db.connection, ConflictStrategy.KEEP_LOCAL)
        assert result.imported == 1

        row = local_db.connection.execute(
            "SELECT subject FROM cs_cases WHERE case_id='CS-2026-099'"
        ).fetchone()
        assert row[0] == "New from remote"

    def test_merge_companies(self, local_db: DatabaseManager, remote_db: DatabaseManager):
        remote_db.connection.execute(
            "INSERT INTO companies (company_id, name, domain) VALUES (?,?,?)",
            ("C1", "Remote Co", "remote.com"),
        )
        remote_db.connection.commit()

        mgr = MergeManager(local_db.connection)
        mgr.merge(remote_db.connection, ConflictStrategy.KEEP_LOCAL)

        row = local_db.connection.execute(
            "SELECT name FROM companies WHERE company_id='C1'"
        ).fetchone()
        assert row[0] == "Remote Co"
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
pytest tests/unit/test_merge.py -v
```

Expected: FAIL

- [ ] **Step 3: 實作 merge.py**

`src/hcp_cms/data/merge.py`:
```python
"""Multi-database merge import with conflict detection."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from enum import Enum


class ConflictStrategy(Enum):
    KEEP_LOCAL = "keep_local"
    KEEP_REMOTE = "keep_remote"


@dataclass
class MergePreview:
    """Preview of what a merge would do."""

    cases_new: int = 0
    cases_conflict: int = 0
    cases_skip: int = 0
    qa_new: int = 0
    qa_conflict: int = 0
    companies_new: int = 0
    companies_conflict: int = 0


@dataclass
class MergeResult:
    """Result of a completed merge."""

    imported: int = 0
    skipped: int = 0
    overwritten: int = 0


_MERGE_TABLES = [
    ("companies", "company_id"),
    ("cs_cases", "case_id"),
    ("qa_knowledge", "qa_id"),
    ("mantis_tickets", "ticket_id"),
]


class MergeManager:
    """Merges data from a remote database into the local database."""

    def __init__(self, local_conn: sqlite3.Connection) -> None:
        self._local = local_conn

    def preview(self, remote_conn: sqlite3.Connection) -> MergePreview:
        """Preview merge without making changes."""
        preview = MergePreview()

        for table, pk in _MERGE_TABLES:
            remote_rows = remote_conn.execute(f"SELECT {pk} FROM {table}").fetchall()
            for row in remote_rows:
                local_row = self._local.execute(
                    f"SELECT {pk} FROM {table} WHERE {pk} = ?", (row[0],)
                ).fetchone()
                attr_new = table.split("_")[0] if table != "cs_cases" else "cases"
                # Normalize attribute names
                if table == "cs_cases":
                    if local_row is None:
                        preview.cases_new += 1
                    else:
                        preview.cases_conflict += 1
                elif table == "qa_knowledge":
                    if local_row is None:
                        preview.qa_new += 1
                    else:
                        preview.qa_conflict += 1
                elif table == "companies":
                    if local_row is None:
                        preview.companies_new += 1
                    else:
                        preview.companies_conflict += 1

        return preview

    def merge(
        self,
        remote_conn: sqlite3.Connection,
        strategy: ConflictStrategy,
    ) -> MergeResult:
        """Execute merge from remote into local."""
        result = MergeResult()

        for table, pk in _MERGE_TABLES:
            remote_rows = remote_conn.execute(f"SELECT * FROM {table}").fetchall()
            if not remote_rows:
                continue

            columns = [desc[0] for desc in remote_conn.execute(f"SELECT * FROM {table} LIMIT 1").description]
            pk_idx = columns.index(pk)

            for row in remote_rows:
                pk_val = row[pk_idx]
                local_exists = self._local.execute(
                    f"SELECT {pk} FROM {table} WHERE {pk} = ?", (pk_val,)
                ).fetchone()

                if local_exists is None:
                    # New record — always import
                    placeholders = ",".join("?" * len(columns))
                    col_names = ",".join(columns)
                    self._local.execute(
                        f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                        tuple(row),
                    )
                    result.imported += 1
                elif strategy == ConflictStrategy.KEEP_REMOTE:
                    # Overwrite local with remote
                    set_clause = ",".join(f"{c}=?" for c in columns if c != pk)
                    values = [row[i] for i, c in enumerate(columns) if c != pk]
                    values.append(pk_val)
                    self._local.execute(
                        f"UPDATE {table} SET {set_clause} WHERE {pk}=?",
                        values,
                    )
                    result.overwritten += 1
                else:
                    # KEEP_LOCAL — skip
                    result.skipped += 1

        self._local.commit()
        return result
```

- [ ] **Step 4: 執行測試確認通過**

```bash
pytest tests/unit/test_merge.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/data/merge.py tests/unit/test_merge.py
git commit -m "feat: add MergeManager with preview, conflict strategies, and multi-table merge"
```

---

### Task 10: 舊 DB 遷移（migration.py）

**Files:**
- Create: `src/hcp_cms/data/migration.py`
- Create: `tests/unit/test_migration.py`

- [ ] **Step 1: 寫失敗的測試**

`tests/unit/test_migration.py`:
```python
"""Tests for legacy database migration."""

import sqlite3
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.migration import MigrationManager, MigrationPreview


@pytest.fixture
def new_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_path / "new.db")
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def old_db_path(tmp_path: Path) -> Path:
    """Create a legacy-format database."""
    path = tmp_path / "old_cs_tracker.db"
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE cs_cases (
            case_id TEXT PRIMARY KEY,
            contact_method TEXT,
            status TEXT DEFAULT '處理中',
            priority TEXT DEFAULT '中',
            replied TEXT DEFAULT '否',
            sent_time TEXT,
            company TEXT,
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
            handler TEXT
        );
        CREATE TABLE qa_knowledge (
            qa_id TEXT PRIMARY KEY,
            system_product TEXT,
            issue_type TEXT,
            error_type TEXT,
            question TEXT,
            answer TEXT,
            has_image TEXT,
            created_date TEXT,
            created_by TEXT,
            notes TEXT,
            company TEXT
        );
        CREATE TABLE mantis_tickets (
            ticket_id TEXT PRIMARY KEY,
            created_time TEXT,
            customer TEXT,
            issue_summary TEXT,
            related_cs_case TEXT,
            status TEXT,
            priority TEXT,
            notes TEXT
        );
        INSERT INTO cs_cases (case_id, company, subject, status)
            VALUES ('CS-2025-001', 'aseglobal.com', 'Test case', '處理中');
        INSERT INTO cs_cases (case_id, company, subject, status)
            VALUES ('CS-2025-002', 'unimicron.com', 'Another case', '已完成');
        INSERT INTO qa_knowledge (qa_id, question, answer, company)
            VALUES ('QA-20250301-001', 'How to?', 'Do this.', 'aseglobal.com');
        INSERT INTO mantis_tickets (ticket_id, issue_summary, related_cs_case)
            VALUES ('15562', 'Bug fix', 'CS-2025-001;CS-2025-002');
    """)
    conn.commit()
    conn.close()
    return path


class TestMigrationManager:
    def test_detect_legacy_schema(self, new_db: DatabaseManager, old_db_path: Path):
        mgr = MigrationManager(new_db.connection)
        assert mgr.is_legacy_schema(old_db_path) is True

    def test_detect_new_schema(self, new_db: DatabaseManager, tmp_path: Path):
        # New schema DB should not be detected as legacy
        new_path = tmp_path / "new2.db"
        db2 = DatabaseManager(new_path)
        db2.initialize()
        db2.close()

        mgr = MigrationManager(new_db.connection)
        assert mgr.is_legacy_schema(new_path) is False

    def test_preview_migration(self, new_db: DatabaseManager, old_db_path: Path):
        mgr = MigrationManager(new_db.connection)
        preview = mgr.preview(old_db_path)
        assert preview.cases_count == 2
        assert preview.qa_count == 1
        assert preview.mantis_count == 1

    def test_migrate_cases(self, new_db: DatabaseManager, old_db_path: Path):
        mgr = MigrationManager(new_db.connection)
        mgr.migrate(old_db_path)

        row = new_db.connection.execute(
            "SELECT subject FROM cs_cases WHERE case_id='CS-2025-001'"
        ).fetchone()
        assert row[0] == "Test case"

    def test_migrate_creates_companies(self, new_db: DatabaseManager, old_db_path: Path):
        mgr = MigrationManager(new_db.connection)
        mgr.migrate(old_db_path)

        companies = new_db.connection.execute("SELECT * FROM companies").fetchall()
        assert len(companies) >= 1  # At least one company created from domains

    def test_migrate_splits_mantis_relations(self, new_db: DatabaseManager, old_db_path: Path):
        mgr = MigrationManager(new_db.connection)
        mgr.migrate(old_db_path)

        links = new_db.connection.execute("SELECT * FROM case_mantis").fetchall()
        assert len(links) == 2  # "CS-2025-001;CS-2025-002" split into 2 links
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
pytest tests/unit/test_migration.py -v
```

Expected: FAIL

- [ ] **Step 3: 實作 migration.py**

`src/hcp_cms/data/migration.py`:
```python
"""Legacy database migration — converts old schema to new format."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MigrationPreview:
    """Preview of data available for migration."""

    cases_count: int = 0
    qa_count: int = 0
    mantis_count: int = 0


class MigrationManager:
    """Migrates data from legacy cs_tracker.db to new schema."""

    def __init__(self, new_conn: sqlite3.Connection) -> None:
        self._new = new_conn

    def is_legacy_schema(self, old_db_path: Path) -> bool:
        """Check if the database uses the legacy schema (has 'company' text column, no 'company_id')."""
        conn = sqlite3.connect(str(old_db_path))
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(cs_cases)").fetchall()}
            # Legacy has 'company' (text), new has 'company_id' (FK)
            return "company" in cols and "company_id" not in cols
        except sqlite3.OperationalError:
            return False
        finally:
            conn.close()

    def preview(self, old_db_path: Path) -> MigrationPreview:
        """Count records available for migration."""
        conn = sqlite3.connect(str(old_db_path))
        preview = MigrationPreview()
        try:
            preview.cases_count = conn.execute("SELECT COUNT(*) FROM cs_cases").fetchone()[0]
            try:
                preview.qa_count = conn.execute("SELECT COUNT(*) FROM qa_knowledge").fetchone()[0]
            except sqlite3.OperationalError:
                pass
            try:
                preview.mantis_count = conn.execute("SELECT COUNT(*) FROM mantis_tickets").fetchone()[0]
            except sqlite3.OperationalError:
                pass
        finally:
            conn.close()
        return preview

    def migrate(self, old_db_path: Path) -> MigrationPreview:
        """Execute migration from legacy DB to new DB."""
        old_conn = sqlite3.connect(str(old_db_path))
        old_conn.row_factory = sqlite3.Row
        preview = MigrationPreview()

        try:
            # Step 1: Extract unique company domains and create companies
            domain_to_id: dict[str, str] = {}
            cases = old_conn.execute("SELECT * FROM cs_cases").fetchall()
            for case in cases:
                domain = dict(case).get("company", "")
                if domain and domain not in domain_to_id:
                    comp_id = f"COMP-{uuid.uuid4().hex[:8]}"
                    domain_to_id[domain] = comp_id
                    self._new.execute(
                        "INSERT OR IGNORE INTO companies (company_id, name, domain) VALUES (?,?,?)",
                        (comp_id, domain, domain),
                    )

            # Step 2: Migrate cases
            for case in cases:
                d = dict(case)
                company_id = domain_to_id.get(d.get("company", ""))
                self._new.execute(
                    """INSERT OR IGNORE INTO cs_cases
                       (case_id, contact_method, status, priority, replied, sent_time,
                        company_id, contact_person, subject, system_product, issue_type,
                        error_type, impact_period, progress, actual_reply, notes,
                        rd_assignee, handler, reply_count, source)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,'email')""",
                    (d.get("case_id"), d.get("contact_method"), d.get("status"),
                     d.get("priority"), d.get("replied"), d.get("sent_time"),
                     company_id, d.get("contact_person"), d.get("subject"),
                     d.get("system_product"), d.get("issue_type"), d.get("error_type"),
                     d.get("impact_period"), d.get("progress"), d.get("actual_reply"),
                     d.get("notes"), d.get("rd_assignee"), d.get("handler")),
                )
                preview.cases_count += 1

            # Step 3: Migrate QA
            try:
                qas = old_conn.execute("SELECT * FROM qa_knowledge").fetchall()
                for qa in qas:
                    d = dict(qa)
                    self._new.execute(
                        """INSERT OR IGNORE INTO qa_knowledge
                           (qa_id, system_product, issue_type, error_type, question, answer,
                            has_image, created_by, created_at, notes, source)
                           VALUES (?,?,?,?,?,?,?,?,?,?,'email')""",
                        (d.get("qa_id"), d.get("system_product"), d.get("issue_type"),
                         d.get("error_type"), d.get("question"), d.get("answer"),
                         d.get("has_image"), d.get("created_by"),
                         d.get("created_date"), d.get("notes")),
                    )
                    preview.qa_count += 1
            except sqlite3.OperationalError:
                pass

            # Step 4: Migrate Mantis tickets and split related_cs_case
            try:
                tickets = old_conn.execute("SELECT * FROM mantis_tickets").fetchall()
                for ticket in tickets:
                    d = dict(ticket)
                    self._new.execute(
                        """INSERT OR IGNORE INTO mantis_tickets
                           (ticket_id, created_time, summary, status, priority, notes)
                           VALUES (?,?,?,?,?,?)""",
                        (d.get("ticket_id"), d.get("created_time"),
                         d.get("issue_summary", d.get("summary")),
                         d.get("status"), d.get("priority"), d.get("notes")),
                    )
                    preview.mantis_count += 1

                    # Split "CS-001;CS-002" into case_mantis links
                    related = d.get("related_cs_case", "") or ""
                    for case_id in related.split(";"):
                        case_id = case_id.strip()
                        if case_id:
                            self._new.execute(
                                "INSERT OR IGNORE INTO case_mantis (case_id, ticket_id) VALUES (?,?)",
                                (case_id, d.get("ticket_id")),
                            )
            except sqlite3.OperationalError:
                pass

            self._new.commit()
        finally:
            old_conn.close()

        return preview
```

- [ ] **Step 4: 執行測試確認通過**

```bash
pytest tests/unit/test_migration.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/data/migration.py tests/unit/test_migration.py
git commit -m "feat: add MigrationManager for legacy DB schema detection and data migration"
```

---

### Task 11: 整合測試 + 最終驗證

**Files:**
- Modify: `tests/conftest.py`（加入 shared fixtures）
- Create: `tests/integration/test_data_layer.py`

- [ ] **Step 1: 寫整合測試**

`tests/integration/test_data_layer.py`:
```python
"""Integration tests for the complete data layer."""

from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, Company, QAKnowledge, ClassificationRule, Synonym
from hcp_cms.data.repositories import (
    CaseRepository, CompanyRepository, QARepository, RuleRepository, SynonymRepository,
)
from hcp_cms.data.fts import FTSManager
from hcp_cms.data.backup import BackupManager


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_path / "integration.db")
    db.initialize()
    yield db
    db.close()


class TestFullWorkflow:
    """Test a realistic workflow: create company → create case → create QA → search."""

    def test_company_case_qa_workflow(self, db: DatabaseManager):
        comp_repo = CompanyRepository(db.connection)
        case_repo = CaseRepository(db.connection)
        qa_repo = QARepository(db.connection)
        fts = FTSManager(db.connection)

        # 1. Create company
        comp_repo.insert(Company(company_id="C1", name="日月光", domain="aseglobal.com"))

        # 2. Create case linked to company
        case_id = case_repo.next_case_id()
        case = Case(
            case_id=case_id,
            subject="薪資計算異常",
            company_id="C1",
            system_product="HCP",
            issue_type="BUG",
        )
        case_repo.insert(case)
        fts.index_case(case_id, case.subject, None, None)

        # 3. Create QA from case
        qa_id = qa_repo.next_qa_id()
        qa = QAKnowledge(
            qa_id=qa_id,
            question="薪資計算出現異常怎麼辦？",
            answer="請檢查薪資參數設定",
            solution="進入系統設定 > 薪資參數 > 檢查計算公式",
            source="email",
            source_case_id=case_id,
        )
        qa_repo.insert(qa)
        fts.index_qa(qa_id, qa.question, qa.answer, qa.solution, None)

        # 4. Search should find the QA
        results = fts.search_qa("薪資異常")
        assert len(results) > 0
        assert results[0]["qa_id"] == qa_id

        # 5. Search cases
        case_results = fts.search_cases("薪資")
        assert len(case_results) > 0

    def test_synonym_enhanced_search(self, db: DatabaseManager):
        qa_repo = QARepository(db.connection)
        syn_repo = SynonymRepository(db.connection)
        fts = FTSManager(db.connection)

        # Setup synonyms
        syn_repo.insert(Synonym(word="薪水", synonym="薪資", group_name="薪資相關"))
        syn_repo.insert(Synonym(word="薪水", synonym="工資", group_name="薪資相關"))

        # Create QA with "薪資"
        qa_repo.insert(QAKnowledge(qa_id="QA-202603-001", question="薪資如何計算", answer="按月計算"))
        fts.index_qa("QA-202603-001", "薪資如何計算", "按月計算", None, None)

        # Search with "薪水" should find it via synonym
        results = fts.search_qa("薪水")
        assert len(results) > 0

    def test_backup_and_restore_preserves_data(self, db: DatabaseManager, tmp_path: Path):
        case_repo = CaseRepository(db.connection)
        case_repo.insert(Case(case_id="CS-2026-001", subject="Important case"))

        backup_mgr = BackupManager(db.connection, tmp_path / "backups")
        backup_path = backup_mgr.create_backup()

        # Delete the case
        db.connection.execute("DELETE FROM cs_cases")
        db.connection.commit()
        assert case_repo.count_by_month(2026, 3) == 0

        # Restore
        db_path = tmp_path / "integration.db"
        backup_mgr.restore_backup(backup_path, db_path)

        # Reconnect
        db.close()
        db2 = DatabaseManager(db_path)
        db2.initialize()
        result = db2.connection.execute(
            "SELECT subject FROM cs_cases WHERE case_id='CS-2026-001'"
        ).fetchone()
        assert result[0] == "Important case"
        db2.close()

    def test_rules_from_db(self, db: DatabaseManager):
        rule_repo = RuleRepository(db.connection)

        # Insert rules similar to original rules_config.py
        rule_repo.insert(ClassificationRule(
            rule_type="issue", pattern=r"bug|錯誤|異常", value="BUG", priority=1
        ))
        rule_repo.insert(ClassificationRule(
            rule_type="issue", pattern=r"客制|客製", value="客制需求", priority=0
        ))

        rules = rule_repo.list_by_type("issue")
        assert len(rules) == 2
        # Priority 0 should come first
        assert rules[0].value == "客制需求"
        assert rules[1].value == "BUG"
```

- [ ] **Step 2: 執行整合測試**

```bash
pytest tests/integration/test_data_layer.py -v
```

Expected: 全部 PASS

- [ ] **Step 3: 執行全部測試 + 覆蓋率**

```bash
pytest --cov=hcp_cms --cov-report=term-missing -v
```

Expected: 全部 PASS，覆蓋率 > 85%

- [ ] **Step 4: 執行 ruff 和 mypy**

```bash
ruff check src/ tests/
mypy src/hcp_cms/data/
```

Expected: 無錯誤（或僅有可接受的 mypy 警告）

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_data_layer.py
git commit -m "feat: add integration tests for complete data layer workflow"
```

---

## Phase 1 完成標準

- [ ] 所有 11 個 Task 完成
- [ ] `pytest -v` 全部通過
- [ ] `ruff check` 無錯誤
- [ ] 資料庫 schema 包含所有 7 張主表 + 2 FTS5 + db_meta
- [ ] FTS5 搜尋支援中文斷詞 + 同義詞擴展
- [ ] 備份/還原/合併/遷移功能可用
- [ ] 所有 Repository 具備 CRUD 操作
