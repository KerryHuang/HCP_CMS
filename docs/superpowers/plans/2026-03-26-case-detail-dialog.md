# 案件詳情維護對話框 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 雙擊案件管理列表任一列，開啟可編輯的 3 分頁詳情對話框，支援案件欄位編輯、結構化補充記錄（客戶來信/CS 回覆/內部討論），以及 Mantis ticket 關聯與同步。

**Architecture:** `CaseLog` dataclass + `case_logs` 資料表儲存補充記錄；`CaseLogRepository`（Data 層）負責 CRUD；`CaseDetailManager`（Core 層）整合 `CaseRepository`、`CaseLogRepository`、`CaseMantisRepository`、`CaseManager`；`CaseDetailDialog`（UI 層，QDialog + QTabWidget 3 分頁）接收 conn + case_id，`case_updated` Signal 通知 CaseView 重新整理。

**Tech Stack:** Python 3.14、PySide6 6.10、SQLite（內建）

**Spec:** `docs/superpowers/specs/2026-03-26-case-detail-dialog-design.md`

---

## 檔案清單

| 檔案 | 動作 | 說明 |
|------|------|------|
| `src/hcp_cms/data/models.py` | 修改 | 新增 `CaseLog` dataclass |
| `src/hcp_cms/data/database.py` | 修改 | `_SCHEMA_SQL` 新增 `case_logs` 資料表 |
| `src/hcp_cms/data/repositories.py` | 修改 | 新增 `CaseLogRepository`；`CaseMantisRepository` 補 `unlink()` |
| `src/hcp_cms/core/case_detail_manager.py` | 新增 | `CaseDetailManager` |
| `src/hcp_cms/ui/case_detail_dialog.py` | 新增 | `CaseDetailDialog`（3 分頁）、`CaseLogAddDialog` |
| `src/hcp_cms/ui/case_view.py` | 修改 | 雙擊觸發 + `case_updated` Signal 接收後 refresh |
| `tests/unit/test_case_log_repository.py` | 新增 | Data 層 CaseLogRepository 單元測試 |
| `tests/unit/test_case_detail_manager.py` | 新增 | Core 層 CaseDetailManager 單元測試 |

---

## Task 1：CaseLog model + case_logs 資料表

**Files:**
- Modify: `src/hcp_cms/data/models.py`
- Modify: `src/hcp_cms/data/database.py`

- [ ] **Step 1: 在 `models.py` 末尾新增 `CaseLog` dataclass**

在 `src/hcp_cms/data/models.py` 最後加入：

```python
@dataclass
class CaseLog:
    """補充記錄 — case_logs table."""
    log_id: str               # LOG-YYYYMMDD-NNN
    case_id: str
    direction: str            # '客戶來信' | 'CS 回覆' | '內部討論'
    content: str
    mantis_ref: str | None = None   # Mantis Issue 編號（可空）
    logged_by: str | None = None    # 記錄人
    logged_at: str = ""             # YYYY/MM/DD HH:MM:SS
```

- [ ] **Step 2: 在 `database.py` 的 `_SCHEMA_SQL` 新增 `case_logs` 資料表**

在 `_SCHEMA_SQL` 字串中，`cases_fts` 虛擬表之前插入：

```sql
CREATE TABLE IF NOT EXISTS case_logs (
    log_id     TEXT PRIMARY KEY,
    case_id    TEXT NOT NULL REFERENCES cs_cases(case_id),
    direction  TEXT NOT NULL,
    content    TEXT NOT NULL,
    mantis_ref TEXT,
    logged_by  TEXT,
    logged_at  TEXT NOT NULL
);
```

> 注意：放在 `_SCHEMA_SQL`，**不是** `_apply_pending_migrations()`。

- [ ] **Step 3: 確認語法無誤**

```bash
cd D:/CMS && .venv/Scripts/python.exe -c "from hcp_cms.data.models import CaseLog; from hcp_cms.data.database import DatabaseManager; print('OK')"
```
預期：`OK`

- [ ] **Step 4: Commit**

```bash
cd D:/CMS && git add src/hcp_cms/data/models.py src/hcp_cms/data/database.py
git commit -m "feat: CaseLog dataclass + case_logs 資料表 schema（Task 1）"
```

---

## Task 2：CaseLogRepository + CaseMantisRepository.unlink()

**Files:**
- Modify: `src/hcp_cms/data/repositories.py`
- Create: `tests/unit/test_case_log_repository.py`

- [ ] **Step 1: 撰寫測試**

建立 `tests/unit/test_case_log_repository.py`：

```python
"""Tests for CaseLogRepository."""
from __future__ import annotations

from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import CaseLog
from hcp_cms.data.repositories import CaseLogRepository, CaseMantisRepository


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    # 插入一筆父案件供 FK 使用
    db.connection.execute(
        "INSERT INTO cs_cases (case_id, subject, status) VALUES (?, ?, ?)",
        ("CS-202603-001", "測試主旨", "處理中"),
    )
    db.connection.commit()
    yield db
    db.close()


class TestNextLogId:
    def test_first_log_of_day(self, db: DatabaseManager):
        repo = CaseLogRepository(db.connection)
        log_id = repo.next_log_id()
        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        assert log_id == f"LOG-{today}-001"

    def test_sequential_same_day(self, db: DatabaseManager):
        repo = CaseLogRepository(db.connection)
        id1 = repo.next_log_id()
        # 手動插入第一筆
        db.connection.execute(
            "INSERT INTO case_logs (log_id, case_id, direction, content, logged_at) VALUES (?, ?, ?, ?, ?)",
            (id1, "CS-202603-001", "客戶來信", "內容", "2026/03/26 10:00:00"),
        )
        db.connection.commit()
        id2 = repo.next_log_id()
        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        assert id2 == f"LOG-{today}-002"


class TestCaseLogRepositoryInsert:
    def test_insert_and_retrieve(self, db: DatabaseManager):
        repo = CaseLogRepository(db.connection)
        log = CaseLog(
            log_id="LOG-20260326-001",
            case_id="CS-202603-001",
            direction="客戶來信",
            content="客戶反映問題",
            mantis_ref="1234",
            logged_by="Jill",
            logged_at="2026/03/26 10:00:00",
        )
        repo.insert(log)
        logs = repo.list_by_case("CS-202603-001")
        assert len(logs) == 1
        assert logs[0].log_id == "LOG-20260326-001"
        assert logs[0].mantis_ref == "1234"
        assert logs[0].logged_by == "Jill"


class TestCaseLogRepositoryListByCase:
    def test_filters_by_case_id(self, db: DatabaseManager):
        # 插入兩個不同案件的記錄
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject, status) VALUES (?, ?, ?)",
            ("CS-202603-002", "另一案件", "處理中"),
        )
        db.connection.commit()
        repo = CaseLogRepository(db.connection)
        repo.insert(CaseLog("LOG-20260326-001", "CS-202603-001", "客戶來信", "A", logged_at="2026/03/26 10:00:00"))
        repo.insert(CaseLog("LOG-20260326-002", "CS-202603-002", "CS 回覆", "B", logged_at="2026/03/26 11:00:00"))
        logs = repo.list_by_case("CS-202603-001")
        assert len(logs) == 1
        assert logs[0].case_id == "CS-202603-001"

    def test_sorted_by_logged_at_asc(self, db: DatabaseManager):
        repo = CaseLogRepository(db.connection)
        repo.insert(CaseLog("LOG-20260326-001", "CS-202603-001", "客戶來信", "舊", logged_at="2026/03/26 08:00:00"))
        repo.insert(CaseLog("LOG-20260326-002", "CS-202603-001", "CS 回覆", "新", logged_at="2026/03/26 15:00:00"))
        logs = repo.list_by_case("CS-202603-001")
        assert logs[0].content == "舊"
        assert logs[1].content == "新"


class TestCaseLogRepositoryDelete:
    def test_delete_removes_record(self, db: DatabaseManager):
        repo = CaseLogRepository(db.connection)
        repo.insert(CaseLog("LOG-20260326-001", "CS-202603-001", "客戶來信", "內容", logged_at="2026/03/26 10:00:00"))
        repo.delete("LOG-20260326-001")
        logs = repo.list_by_case("CS-202603-001")
        assert len(logs) == 0


class TestCaseMantisRepositoryUnlink:
    def test_unlink_removes_association(self, db: DatabaseManager):
        # 插入 mantis ticket
        db.connection.execute(
            "INSERT INTO mantis_tickets (ticket_id, summary, priority, status, issue_type, module, handler, progress) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("1234", "測試 ticket", "中", "開放中", "Bug", "系統", "工程師", "進行中"),
        )
        db.connection.execute(
            "INSERT INTO case_mantis (case_id, ticket_id) VALUES (?, ?)",
            ("CS-202603-001", "1234"),
        )
        db.connection.commit()
        repo = CaseMantisRepository(db.connection)
        repo.unlink("CS-202603-001", "1234")
        tickets = repo.get_tickets_for_case("CS-202603-001")
        assert "1234" not in tickets
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_case_log_repository.py -v
```
預期：`ImportError`（`CaseLogRepository` 不存在）

- [ ] **Step 3: 在 `repositories.py` 末尾新增 `CaseLogRepository`**

在 `src/hcp_cms/data/repositories.py` 末尾（`CaseMantisRepository` 之後）加入：

```python
# ---------------------------------------------------------------------------
# CaseLogRepository
# ---------------------------------------------------------------------------


class CaseLogRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def next_log_id(self) -> str:
        today = datetime.now().strftime("%Y%m%d")
        prefix = f"LOG-{today}-"
        row = self._conn.execute(
            "SELECT MAX(log_id) FROM case_logs WHERE log_id LIKE ?",
            (f"{prefix}%",),
        ).fetchone()
        max_id: str | None = row[0] if row else None
        try:
            next_num = int(max_id[-3:]) + 1 if max_id else 1
        except (TypeError, ValueError):
            next_num = 1
        return f"{prefix}{next_num:03d}"

    def insert(self, log: CaseLog) -> None:
        self._conn.execute(
            """
            INSERT INTO case_logs (log_id, case_id, direction, content, mantis_ref, logged_by, logged_at)
            VALUES (:log_id, :case_id, :direction, :content, :mantis_ref, :logged_by, :logged_at)
            """,
            {
                "log_id": log.log_id,
                "case_id": log.case_id,
                "direction": log.direction,
                "content": log.content,
                "mantis_ref": log.mantis_ref,
                "logged_by": log.logged_by,
                "logged_at": log.logged_at,
            },
        )
        self._conn.commit()

    def list_by_case(self, case_id: str) -> list[CaseLog]:
        rows = self._conn.execute(
            "SELECT * FROM case_logs WHERE case_id = ? ORDER BY logged_at ASC",
            (case_id,),
        ).fetchall()
        return [CaseLog(**dict(row)) for row in rows]

    def delete(self, log_id: str) -> None:
        self._conn.execute("DELETE FROM case_logs WHERE log_id = ?", (log_id,))
        self._conn.commit()
```

確認 `from datetime import datetime` 已在 `repositories.py` 頂部 import（已存在）。並確認 `CaseLog` 已加入 models import。在 `repositories.py` 頂部的 models import 加入 `CaseLog`：

```python
from hcp_cms.data.models import (
    Case,
    CaseLog,           # ← 新增
    CaseMantisLink,
    Company,
    MantisTicket,
    QAKnowledge,
    Synonym,
)
```

- [ ] **Step 4: 在 `CaseMantisRepository` 加入 `unlink()` 方法**

在 `CaseMantisRepository.get_cases_for_ticket()` 之後加入：

```python
    def unlink(self, case_id: str, ticket_id: str) -> None:
        self._conn.execute(
            "DELETE FROM case_mantis WHERE case_id = ? AND ticket_id = ?",
            (case_id, ticket_id),
        )
        self._conn.commit()
```

- [ ] **Step 5: 執行測試確認通過**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_case_log_repository.py -v
```
預期：7 tests PASSED

- [ ] **Step 6: Commit**

```bash
cd D:/CMS && git add src/hcp_cms/data/repositories.py tests/unit/test_case_log_repository.py
git commit -m "feat: CaseLogRepository + CaseMantisRepository.unlink()（Task 2）"
```

---

## Task 3：CaseDetailManager

**Files:**
- Create: `src/hcp_cms/core/case_detail_manager.py`
- Create: `tests/unit/test_case_detail_manager.py`

- [ ] **Step 1: 撰寫測試**

建立 `tests/unit/test_case_detail_manager.py`：

```python
"""Tests for CaseDetailManager."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hcp_cms.core.case_detail_manager import CaseDetailManager
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import CaseLog, MantisTicket


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    db.connection.execute(
        "INSERT INTO cs_cases (case_id, subject, status, priority, replied, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("CS-202603-001", "測試主旨", "處理中", "中", "否", "2026/01/01 00:00:00"),
    )
    db.connection.commit()
    yield db
    db.close()


class TestUpdateCase:
    def test_updates_fields(self, db: DatabaseManager):
        manager = CaseDetailManager(db.connection)
        case = manager.get_case("CS-202603-001")
        case.subject = "新主旨"
        case.handler = "小明"
        manager.update_case(case)
        updated = manager.get_case("CS-202603-001")
        assert updated.subject == "新主旨"
        assert updated.handler == "小明"

    def test_updated_at_refreshed(self, db: DatabaseManager):
        manager = CaseDetailManager(db.connection)
        case = manager.get_case("CS-202603-001")
        old_updated_at = case.updated_at
        case.subject = "變更"
        manager.update_case(case)
        updated = manager.get_case("CS-202603-001")
        assert updated.updated_at != old_updated_at


class TestAddLog:
    def test_log_id_format(self, db: DatabaseManager):
        from datetime import datetime
        manager = CaseDetailManager(db.connection)
        log = manager.add_log(
            case_id="CS-202603-001",
            direction="客戶來信",
            content="客戶詢問進度",
        )
        today = datetime.now().strftime("%Y%m%d")
        assert log.log_id == f"LOG-{today}-001"

    def test_all_fields_stored(self, db: DatabaseManager):
        manager = CaseDetailManager(db.connection)
        log = manager.add_log(
            case_id="CS-202603-001",
            direction="CS 回覆",
            content="已處理",
            mantis_ref="5678",
            logged_by="Jill",
        )
        logs = manager.list_logs("CS-202603-001")
        assert len(logs) == 1
        assert logs[0].mantis_ref == "5678"
        assert logs[0].logged_by == "Jill"


class TestListLogs:
    def test_filters_by_case_id(self, db: DatabaseManager):
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject, status) VALUES (?, ?, ?)",
            ("CS-202603-002", "另一案件", "處理中"),
        )
        db.connection.commit()
        manager = CaseDetailManager(db.connection)
        manager.add_log("CS-202603-001", "客戶來信", "A")
        manager.add_log("CS-202603-002", "CS 回覆", "B")
        logs = manager.list_logs("CS-202603-001")
        assert len(logs) == 1

    def test_sorted_asc(self, db: DatabaseManager):
        manager = CaseDetailManager(db.connection)
        manager.add_log("CS-202603-001", "客戶來信", "舊")
        manager.add_log("CS-202603-001", "CS 回覆", "新")
        logs = manager.list_logs("CS-202603-001")
        assert logs[0].content == "舊"
        assert logs[1].content == "新"


class TestLinkUnlinkMantis:
    def _insert_ticket(self, db: DatabaseManager, ticket_id: str) -> None:
        db.connection.execute(
            "INSERT INTO mantis_tickets (ticket_id, summary, priority, status, issue_type, module, handler, progress) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (ticket_id, "摘要", "中", "開放中", "Bug", "系統", "工程師", "進行中"),
        )
        db.connection.commit()

    def test_link_creates_association(self, db: DatabaseManager):
        self._insert_ticket(db, "0001")
        manager = CaseDetailManager(db.connection)
        manager.link_mantis("CS-202603-001", "0001")
        tickets = manager.list_linked_tickets("CS-202603-001")
        assert len(tickets) == 1
        assert tickets[0].ticket_id == "0001"

    def test_unlink_removes_association(self, db: DatabaseManager):
        self._insert_ticket(db, "0001")
        manager = CaseDetailManager(db.connection)
        manager.link_mantis("CS-202603-001", "0001")
        manager.unlink_mantis("CS-202603-001", "0001")
        tickets = manager.list_linked_tickets("CS-202603-001")
        assert len(tickets) == 0

    def test_link_nonexistent_ticket_returns_false(self, db: DatabaseManager):
        manager = CaseDetailManager(db.connection)
        result = manager.link_mantis("CS-202603-001", "9999")
        assert result is False


class TestSyncMantisTicket:
    def test_sync_updates_local(self, db: DatabaseManager):
        mock_client = MagicMock()
        from hcp_cms.services.mantis.base import MantisIssue
        mock_client.get_issue.return_value = MantisIssue(
            id="0001", summary="遠端摘要", status="已修復", priority="高",
            handler="工程師", notes="",
            created="2026/03/01",
        )
        manager = CaseDetailManager(db.connection)
        ticket = manager.sync_mantis_ticket("0001", client=mock_client)
        assert ticket is not None
        assert ticket.summary == "遠端摘要"
        assert ticket.status == "已修復"

    def test_sync_without_client_returns_none(self, db: DatabaseManager):
        manager = CaseDetailManager(db.connection)
        result = manager.sync_mantis_ticket("0001", client=None)
        assert result is None
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_case_detail_manager.py -v
```
預期：`ImportError`（`CaseDetailManager` 不存在）

- [ ] **Step 3: 建立 `case_detail_manager.py`**

建立 `src/hcp_cms/core/case_detail_manager.py`：

```python
"""CaseDetailManager — 案件詳情維護業務邏輯。"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from hcp_cms.core.case_manager import CaseManager
from hcp_cms.data.models import Case, CaseLog, MantisTicket
from hcp_cms.data.repositories import (
    CaseLogRepository,
    CaseMantisRepository,
    CaseRepository,
    MantisRepository,
)


class CaseDetailManager:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._case_repo = CaseRepository(conn)
        self._log_repo = CaseLogRepository(conn)
        self._case_mantis_repo = CaseMantisRepository(conn)
        self._mantis_repo = MantisRepository(conn)
        self._case_manager = CaseManager(conn)

    # ------------------------------------------------------------------
    # 案件
    # ------------------------------------------------------------------

    def get_case(self, case_id: str) -> Case | None:
        return self._case_repo.get_by_id(case_id)

    def update_case(self, case: Case) -> None:
        self._case_repo.update(case)

    def mark_replied(self, case_id: str) -> None:
        self._case_manager.mark_replied(case_id)

    def close_case(self, case_id: str) -> None:
        self._case_manager.close_case(case_id)

    # ------------------------------------------------------------------
    # 補充記錄
    # ------------------------------------------------------------------

    def add_log(
        self,
        case_id: str,
        direction: str,
        content: str,
        mantis_ref: str | None = None,
        logged_by: str | None = None,
    ) -> CaseLog:
        log_id = self._log_repo.next_log_id()
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        log = CaseLog(
            log_id=log_id,
            case_id=case_id,
            direction=direction,
            content=content,
            mantis_ref=mantis_ref,
            logged_by=logged_by,
            logged_at=now,
        )
        self._log_repo.insert(log)
        return log

    def list_logs(self, case_id: str) -> list[CaseLog]:
        return self._log_repo.list_by_case(case_id)

    def delete_log(self, log_id: str) -> None:
        self._log_repo.delete(log_id)

    # ------------------------------------------------------------------
    # Mantis 關聯
    # ------------------------------------------------------------------

    def link_mantis(self, case_id: str, ticket_id: str) -> bool:
        """關聯 Mantis ticket。若 ticket 不在本地則回傳 False。"""
        from hcp_cms.data.models import CaseMantisLink
        if self._mantis_repo.get_by_id(ticket_id) is None:
            return False
        self._case_mantis_repo.link(CaseMantisLink(case_id=case_id, ticket_id=ticket_id))
        return True

    def unlink_mantis(self, case_id: str, ticket_id: str) -> None:
        self._case_mantis_repo.unlink(case_id, ticket_id)

    def list_linked_tickets(self, case_id: str) -> list[MantisTicket]:
        ticket_ids = self._case_mantis_repo.get_tickets_for_case(case_id)
        result = []
        for tid in ticket_ids:
            ticket = self._mantis_repo.get_by_id(tid)
            if ticket is not None:
                result.append(ticket)
        return result

    def sync_mantis_ticket(
        self,
        ticket_id: str,
        client: object | None = None,
    ) -> MantisTicket | None:
        """呼叫 MantisClient 同步單一 ticket，更新本地快取。"""
        if client is None:
            return None
        issue = client.get_issue(ticket_id)
        if issue is None:
            return None
        ticket = MantisTicket(
            ticket_id=issue.id,
            summary=issue.summary,
            status=issue.status,
            priority=issue.priority,
            handler=issue.handler,
            notes=issue.notes,
        )
        self._mantis_repo.upsert(ticket)
        return self._mantis_repo.get_by_id(ticket_id)
```

- [ ] **Step 4: 確認 `CaseMantisLink` 存在於 models**

```bash
cd D:/CMS && .venv/Scripts/python.exe -c "from hcp_cms.data.models import CaseMantisLink; print('OK')"
```
若失敗，在 `models.py` 加入：
```python
@dataclass
class CaseMantisLink:
    case_id: str
    ticket_id: str
```

- [ ] **Step 5: 執行測試確認通過**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_case_detail_manager.py -v
```
預期：全部 PASSED

- [ ] **Step 6: Commit**

```bash
cd D:/CMS && git add src/hcp_cms/core/case_detail_manager.py tests/unit/test_case_detail_manager.py
git commit -m "feat: CaseDetailManager — 案件詳情業務邏輯（Task 3）"
```

---

## Task 4：CaseDetailDialog Tab 1 + CaseView 雙擊觸發

**Files:**
- Create: `src/hcp_cms/ui/case_detail_dialog.py`
- Modify: `src/hcp_cms/ui/case_view.py`

- [ ] **Step 1: 建立 `case_detail_dialog.py` — Dialog 骨架 + Tab 1**

建立 `src/hcp_cms/ui/case_detail_dialog.py`：

```python
"""案件詳情維護對話框 — 3 分頁 QDialog。"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.case_detail_manager import CaseDetailManager
from hcp_cms.data.models import Case


class CaseDetailDialog(QDialog):
    """3 分頁案件詳情維護對話框。"""

    case_updated = Signal()

    def __init__(
        self,
        conn: sqlite3.Connection,
        case_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._case_id = case_id
        self._manager = CaseDetailManager(conn)
        self.setWindowTitle(f"案件詳情 — {case_id}")
        self.setMinimumSize(900, 650)
        self._setup_ui()
        self._load_case()

    # ------------------------------------------------------------------
    # UI 建構
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_tab1(), "📋 案件資訊")
        self._tabs.addTab(self._build_tab2(), "📝 補充記錄")
        self._tabs.addTab(self._build_tab3(), "🔧 Mantis 關聯")
        layout.addWidget(self._tabs)

    def _build_tab1(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)

        # 兩欄式表單
        cols = QHBoxLayout()
        left = QFormLayout()
        right = QFormLayout()

        # 左欄
        self._f_case_id = QLabel()
        self._f_subject = QLineEdit()
        self._f_company = QLineEdit()
        self._f_contact = QLineEdit()
        self._f_sent_time = QLineEdit()
        self._f_contact_method = QComboBox()
        self._f_contact_method.addItems(["Email", "電話", "現場"])
        self._f_source = QLabel()

        left.addRow("案件編號：", self._f_case_id)
        left.addRow("主旨：", self._f_subject)
        left.addRow("公司：", self._f_company)
        left.addRow("聯絡人：", self._f_contact)
        left.addRow("寄件時間：", self._f_sent_time)
        left.addRow("聯絡方式：", self._f_contact_method)
        left.addRow("來源：", self._f_source)

        # 右欄
        self._f_status = QComboBox()
        self._f_status.addItems(["處理中", "已回覆", "已完成", "Closed"])
        self._f_priority = QComboBox()
        self._f_priority.addItems(["高", "中", "低"])
        self._f_issue_type = QLineEdit()
        self._f_error_type = QLineEdit()
        self._f_system_product = QLineEdit()
        self._f_rd_assignee = QLineEdit()
        self._f_handler = QLineEdit()
        self._f_reply_time = QLineEdit()
        self._f_impact_period = QLineEdit()

        right.addRow("狀態：", self._f_status)
        right.addRow("優先：", self._f_priority)
        right.addRow("問題類型：", self._f_issue_type)
        right.addRow("功能模組：", self._f_error_type)
        right.addRow("系統產品：", self._f_system_product)
        right.addRow("技術負責人：", self._f_rd_assignee)
        right.addRow("處理人員：", self._f_handler)
        right.addRow("回覆時間：", self._f_reply_time)
        right.addRow("影響期間：", self._f_impact_period)

        cols.addLayout(left)
        cols.addSpacing(20)
        cols.addLayout(right)
        outer.addLayout(cols)

        # 下方全寬
        self._f_progress = QTextEdit()
        self._f_progress.setMaximumHeight(80)
        self._f_notes = QTextEdit()
        self._f_notes.setMaximumHeight(80)
        self._f_actual_reply = QTextEdit()
        self._f_actual_reply.setMaximumHeight(80)

        pf = QFormLayout()
        pf.addRow("處理進度：", self._f_progress)
        pf.addRow("備註：", self._f_notes)
        pf.addRow("實際回覆：", self._f_actual_reply)
        outer.addLayout(pf)

        # 按鈕列
        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾 儲存")
        save_btn.clicked.connect(self._on_save)
        replied_btn = QPushButton("✅ 標記已回覆")
        replied_btn.clicked.connect(self._on_mark_replied)
        close_btn = QPushButton("🔒 結案")
        close_btn.clicked.connect(self._on_close_case)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(replied_btn)
        btn_row.addWidget(close_btn)
        outer.addLayout(btn_row)

        return w

    def _build_tab2(self) -> QWidget:
        # 實作於 Task 5
        return QWidget()

    def _build_tab3(self) -> QWidget:
        # 實作於 Task 6
        return QWidget()

    # ------------------------------------------------------------------
    # 資料載入
    # ------------------------------------------------------------------

    def _load_case(self) -> None:
        case = self._manager.get_case(self._case_id)
        if case is None:
            return
        self._case = case
        self._f_case_id.setText(case.case_id)
        self._f_subject.setText(case.subject or "")
        self._f_company.setText(case.company_id or "")
        self._f_contact.setText(case.contact_person or "")
        self._f_sent_time.setText(case.sent_time or "")
        idx = self._f_contact_method.findText(case.contact_method or "Email")
        self._f_contact_method.setCurrentIndex(max(idx, 0))
        self._f_source.setText(case.source or "")
        idx = self._f_status.findText(case.status)
        self._f_status.setCurrentIndex(max(idx, 0))
        idx = self._f_priority.findText(case.priority)
        self._f_priority.setCurrentIndex(max(idx, 0))
        self._f_issue_type.setText(case.issue_type or "")
        self._f_error_type.setText(case.error_type or "")
        self._f_system_product.setText(case.system_product or "")
        self._f_rd_assignee.setText(case.rd_assignee or "")
        self._f_handler.setText(case.handler or "")
        self._f_reply_time.setText(case.reply_time or "")
        self._f_impact_period.setText(case.impact_period or "")
        self._f_progress.setPlainText(case.progress or "")
        self._f_notes.setPlainText(case.notes or "")
        self._f_actual_reply.setPlainText(case.actual_reply or "")

    def _collect_case(self) -> Case:
        case = self._case
        case.subject = self._f_subject.text()
        case.company_id = self._f_company.text() or None
        case.contact_person = self._f_contact.text() or None
        case.sent_time = self._f_sent_time.text() or None
        case.contact_method = self._f_contact_method.currentText()
        case.status = self._f_status.currentText()
        case.priority = self._f_priority.currentText()
        case.issue_type = self._f_issue_type.text() or None
        case.error_type = self._f_error_type.text() or None
        case.system_product = self._f_system_product.text() or None
        case.rd_assignee = self._f_rd_assignee.text() or None
        case.handler = self._f_handler.text() or None
        case.reply_time = self._f_reply_time.text() or None
        case.impact_period = self._f_impact_period.text() or None
        case.progress = self._f_progress.toPlainText() or None
        case.notes = self._f_notes.toPlainText() or None
        case.actual_reply = self._f_actual_reply.toPlainText() or None
        return case

    # ------------------------------------------------------------------
    # Slot
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        try:
            self._manager.update_case(self._collect_case())
            self._load_case()
            self.case_updated.emit()
        except Exception as e:
            QMessageBox.critical(self, "儲存失敗", str(e))

    def _on_mark_replied(self) -> None:
        try:
            self._manager.mark_replied(self._case_id)
            self._load_case()
            self.case_updated.emit()
        except Exception as e:
            QMessageBox.critical(self, "操作失敗", str(e))

    def _on_close_case(self) -> None:
        try:
            self._manager.close_case(self._case_id)
            self._load_case()
            self.case_updated.emit()
        except Exception as e:
            QMessageBox.critical(self, "操作失敗", str(e))
```

- [ ] **Step 2: 修改 `case_view.py`，加入雙擊觸發**

在 `_setup_ui()` 的 `self._table.itemSelectionChanged.connect(...)` 之後加入：

```python
self._table.itemDoubleClicked.connect(self._on_row_double_clicked)
```

在 class 末尾加入：

```python
    def _on_row_double_clicked(self, item) -> None:
        if not self._conn or not hasattr(self, '_cases'):
            return
        row = item.row()
        if row < 0 or row >= len(self._cases):
            return
        case_id = self._cases[row].case_id
        from hcp_cms.ui.case_detail_dialog import CaseDetailDialog
        dlg = CaseDetailDialog(self._conn, case_id, parent=self)
        dlg.case_updated.connect(self.refresh)
        dlg.exec()
```

- [ ] **Step 3: 確認無語法錯誤**

```bash
cd D:/CMS && .venv/Scripts/python.exe -c "from hcp_cms.ui.case_detail_dialog import CaseDetailDialog; print('OK')"
```
預期：`OK`

- [ ] **Step 4: Lint**

```bash
cd D:/CMS && .venv/Scripts/ruff.exe check src/hcp_cms/ui/case_detail_dialog.py src/hcp_cms/ui/case_view.py
```
若有格式問題執行 `ruff format` 修正。

- [ ] **Step 5: Commit**

```bash
cd D:/CMS && git add src/hcp_cms/ui/case_detail_dialog.py src/hcp_cms/ui/case_view.py
git commit -m "feat: CaseDetailDialog Tab 1 案件資訊 + CaseView 雙擊觸發（Task 4）"
```

---

## Task 5：CaseDetailDialog Tab 2 — 補充記錄

**Files:**
- Modify: `src/hcp_cms/ui/case_detail_dialog.py`

- [ ] **Step 1: 在 `case_detail_dialog.py` 補充以下 imports（若未有）**

確認頂部 import 包含：
```python
from PySide6.QtWidgets import (
    ...,
    QTableWidget,
    QTableWidgetItem,
)
```

- [ ] **Step 2: 替換 `_build_tab2()` 實作**

將目前 `_build_tab2` 的 `return QWidget()` 替換為完整實作：

```python
    def _build_tab2(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        toolbar = QHBoxLayout()
        add_btn = QPushButton("➕ 新增記錄")
        add_btn.clicked.connect(self._on_add_log)
        toolbar.addWidget(add_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._log_table = QTableWidget(0, 5)
        self._log_table.setHorizontalHeaderLabels(
            ["時間", "方向", "記錄人", "Mantis 參照", "內容摘要"]
        )
        self._log_table.horizontalHeader().setStretchLastSection(True)
        self._log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._log_table)

        return w

    def _refresh_log_table(self) -> None:
        logs = self._manager.list_logs(self._case_id)
        self._log_table.setRowCount(len(logs))
        for i, log in enumerate(logs):
            self._log_table.setItem(i, 0, QTableWidgetItem(log.logged_at))
            self._log_table.setItem(i, 1, QTableWidgetItem(log.direction))
            self._log_table.setItem(i, 2, QTableWidgetItem(log.logged_by or ""))
            self._log_table.setItem(i, 3, QTableWidgetItem(log.mantis_ref or ""))
            self._log_table.setItem(i, 4, QTableWidgetItem((log.content or "")[:60]))

    def _on_add_log(self) -> None:
        from hcp_cms.ui.case_detail_dialog import CaseLogAddDialog
        dlg = CaseLogAddDialog(parent=self)
        if dlg.exec():
            data = dlg.get_data()
            self._manager.add_log(
                case_id=self._case_id,
                direction=data["direction"],
                content=data["content"],
                mantis_ref=data["mantis_ref"] or None,
                logged_by=data["logged_by"] or None,
            )
            self._refresh_log_table()
```

在 `_setup_ui()` 的 `self._load_case()` 呼叫之後，`_setup_ui` 末尾加入 Tab 切換時更新記錄列表：
```python
        self._tabs.currentChanged.connect(self._on_tab_changed)
```

加入：
```python
    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            self._refresh_log_table()
        elif index == 2:
            self._refresh_mantis_table()
```

- [ ] **Step 3: 在同一檔案末尾加入 `CaseLogAddDialog`**

```python
class CaseLogAddDialog(QDialog):
    """新增補充記錄的小對話框。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新增補充記錄")
        self.setMinimumWidth(500)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QFormLayout(self)

        self._direction = QComboBox()
        self._direction.addItems(["客戶來信", "CS 回覆", "內部討論"])
        layout.addRow("方向：", self._direction)

        self._content = QTextEdit()
        self._content.setMinimumHeight(120)
        self._content.textChanged.connect(self._on_content_changed)
        layout.addRow("內容：", self._content)

        self._mantis_ref = QLineEdit()
        self._mantis_ref.setPlaceholderText("可空")
        layout.addRow("Mantis 編號：", self._mantis_ref)

        self._logged_by = QLineEdit()
        self._logged_by.setPlaceholderText("可空")
        layout.addRow("記錄人：", self._logged_by)

        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("儲存")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._save_btn)
        layout.addRow(btn_row)

    def _on_content_changed(self) -> None:
        self._save_btn.setEnabled(bool(self._content.toPlainText().strip()))

    def get_data(self) -> dict:
        return {
            "direction": self._direction.currentText(),
            "content": self._content.toPlainText().strip(),
            "mantis_ref": self._mantis_ref.text().strip(),
            "logged_by": self._logged_by.text().strip(),
        }
```

- [ ] **Step 4: 修正 `_on_add_log` 的 import（改用直接 import）**

`_on_add_log` 中的 `from hcp_cms.ui.case_detail_dialog import CaseLogAddDialog` 改為直接使用（因為在同一檔案），改成：

```python
    def _on_add_log(self) -> None:
        dlg = CaseLogAddDialog(parent=self)
        ...
```

- [ ] **Step 5: 確認無語法錯誤**

```bash
cd D:/CMS && .venv/Scripts/python.exe -c "from hcp_cms.ui.case_detail_dialog import CaseDetailDialog, CaseLogAddDialog; print('OK')"
```
預期：`OK`

- [ ] **Step 6: Lint**

```bash
cd D:/CMS && .venv/Scripts/ruff.exe check src/hcp_cms/ui/case_detail_dialog.py
```

- [ ] **Step 7: Commit**

```bash
cd D:/CMS && git add src/hcp_cms/ui/case_detail_dialog.py
git commit -m "feat: CaseDetailDialog Tab 2 補充記錄 + CaseLogAddDialog（Task 5）"
```

---

## Task 6：CaseDetailDialog Tab 3 — Mantis 關聯

**Files:**
- Modify: `src/hcp_cms/ui/case_detail_dialog.py`

- [ ] **Step 1: 補充必要 imports**

確認頂部 import 包含 `QTableWidget`, `QTableWidgetItem`（Task 5 應已加入）。

- [ ] **Step 2: 替換 `_build_tab3()` 實作**

```python
    def _build_tab3(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # 工具列
        toolbar = QHBoxLayout()
        self._ticket_input = QLineEdit()
        self._ticket_input.setPlaceholderText("輸入 Ticket 編號")
        self._ticket_input.setFixedWidth(150)
        link_btn = QPushButton("🔗 連結")
        link_btn.clicked.connect(self._on_link_mantis)
        sync_btn = QPushButton("🔄 同步選取")
        sync_btn.clicked.connect(self._on_sync_mantis)
        unlink_btn = QPushButton("🗑 取消連結")
        unlink_btn.clicked.connect(self._on_unlink_mantis)
        toolbar.addWidget(self._ticket_input)
        toolbar.addWidget(link_btn)
        toolbar.addWidget(sync_btn)
        toolbar.addWidget(unlink_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._mantis_table = QTableWidget(0, 7)
        self._mantis_table.setHorizontalHeaderLabels(
            ["票號", "摘要", "狀態", "優先", "處理人", "預計修復", "最後同步"]
        )
        self._mantis_table.horizontalHeader().setStretchLastSection(True)
        self._mantis_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._mantis_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._mantis_table)

        return w

    def _refresh_mantis_table(self) -> None:
        tickets = self._manager.list_linked_tickets(self._case_id)
        self._mantis_table.setRowCount(len(tickets))
        for i, t in enumerate(tickets):
            self._mantis_table.setItem(i, 0, QTableWidgetItem(t.ticket_id))
            self._mantis_table.setItem(i, 1, QTableWidgetItem(t.summary or ""))
            self._mantis_table.setItem(i, 2, QTableWidgetItem(t.status or ""))
            self._mantis_table.setItem(i, 3, QTableWidgetItem(t.priority or ""))
            self._mantis_table.setItem(i, 4, QTableWidgetItem(t.handler or ""))
            self._mantis_table.setItem(i, 5, QTableWidgetItem(t.planned_fix or ""))
            self._mantis_table.setItem(i, 6, QTableWidgetItem(t.synced_at or ""))

    def _on_link_mantis(self) -> None:
        ticket_id = self._ticket_input.text().strip()
        if not ticket_id:
            return
        ok = self._manager.link_mantis(self._case_id, ticket_id)
        if ok:
            self._ticket_input.clear()
            self._refresh_mantis_table()
        else:
            QMessageBox.warning(
                self, "找不到 Ticket",
                f"Ticket {ticket_id} 不在本地資料庫。\n請先使用『同步選取』或前往 Mantis 同步頁面同步後再連結。"
            )

    def _on_unlink_mantis(self) -> None:
        rows = self._mantis_table.selectionModel().selectedRows()
        if not rows:
            return
        ticket_id = self._mantis_table.item(rows[0].row(), 0).text()
        self._manager.unlink_mantis(self._case_id, ticket_id)
        self._refresh_mantis_table()

    def _on_sync_mantis(self) -> None:
        rows = self._mantis_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "提示", "請先選取要同步的 Ticket。")
            return
        ticket_id = self._mantis_table.item(rows[0].row(), 0).text()
        # 嘗試從 MantisView 取得 client（無 client 時提示）
        try:
            from hcp_cms.services.mantis.soap import MantisSoapClient
            from hcp_cms.services.credential import CredentialManager
            creds = CredentialManager()
            url = creds.retrieve("mantis_url") or ""
            user = creds.retrieve("mantis_user") or ""
            pwd = creds.retrieve("mantis_password") or ""
            client = MantisSoapClient(url, user, pwd) if url else None
        except Exception:
            client = None

        result = self._manager.sync_mantis_ticket(ticket_id, client=client)
        if result is None:
            QMessageBox.warning(self, "同步失敗", "無法連線至 Mantis，或 Mantis 設定未完成。")
        else:
            self._refresh_mantis_table()
```

- [ ] **Step 3: 確認整個 Dialog 無語法錯誤**

```bash
cd D:/CMS && .venv/Scripts/python.exe -c "from hcp_cms.ui.case_detail_dialog import CaseDetailDialog, CaseLogAddDialog; print('OK')"
```
預期：`OK`

- [ ] **Step 4: Lint + 全部測試**

```bash
cd D:/CMS && .venv/Scripts/ruff.exe check src/hcp_cms/ui/case_detail_dialog.py
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_case_log_repository.py tests/unit/test_case_detail_manager.py -v
```
預期：全部 PASSED

- [ ] **Step 5: Commit**

```bash
cd D:/CMS && git add src/hcp_cms/ui/case_detail_dialog.py
git commit -m "feat: CaseDetailDialog Tab 3 Mantis 關聯（Task 6）"
```
