# 待發清單 (Pending Release List) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 當收到信件含有「測試OK + 安排出貨」等可自訂關鍵字時，自動解析指派人與 Mantis 票號，建立「待發清單」項目並整合 Patch 整理頁面。

**Architecture:** Data 層新增兩張資料表（`cs_release_items` / `cs_release_keywords`）並以 Repository 封裝；Core 層新增 `ReleaseManager`（包含關鍵字偵測與 CRUD）；UI 層分三處：Patch 整理新增「待發清單」分頁、規則設定新增「待發關鍵字」區塊、信件匯入流程自動觸發偵測。

**Tech Stack:** PySide6 6.10.2, SQLite FTS5, Python 3.14.3

---

## File Map

| 操作 | 路徑 | 責任 |
|------|------|------|
| Modify | `src/hcp_cms/data/database.py` | 新增兩張資料表的 DDL + 預設關鍵字種子資料 |
| Modify | `src/hcp_cms/data/models.py` | 新增 `ReleaseItem`、`ReleaseKeyword` dataclass |
| Modify | `src/hcp_cms/data/repositories.py` | 新增 `ReleaseItemRepository`、`ReleaseKeywordRepository` |
| Create | `src/hcp_cms/core/release_manager.py` | `ReleaseDetector`（解析信件）+ `ReleaseManager`（CRUD + 偵測整合） |
| Modify | `src/hcp_cms/core/case_manager.py` | `import_email` 尾端呼叫 `ReleaseManager.detect_and_record()` |
| Create | `src/hcp_cms/ui/pending_release_tab.py` | 待發清單 Tab Widget（月份篩選、表格、標記已發布） |
| Modify | `src/hcp_cms/ui/patch_view.py` | 新增「📋 待發清單」Tab |
| Modify | `src/hcp_cms/ui/rules_view.py` | 新增「待發關鍵字」管理區塊 |
| Create | `tests/unit/test_release_repository.py` | Repository 單元測試 |
| Create | `tests/unit/test_release_manager.py` | ReleaseDetector / ReleaseManager 單元測試 |

---

## Task 1: 資料庫 DDL + 模型

**Files:**
- Modify: `src/hcp_cms/data/database.py`
- Modify: `src/hcp_cms/data/models.py`

- [ ] **Step 1: 在 `database.py` 的 `_SCHEMA_SQL` 末端加入兩張新表**

找到 `_SCHEMA_SQL` 字串，在最後一個 `CREATE TABLE` 後面加入：

```python
"""
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
```

`ktype` 值：`'confirm'`（測試確認詞，如「測試ok」）、`'ship'`（出貨詞，如「安排出貨」）。

- [ ] **Step 2: 在 `_apply_pending_migrations` 尾端加入種子資料 INSERT**

在 `_apply_pending_migrations` 方法內現有 `pending` 清單**之後**，加入：

```python
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
```

- [ ] **Step 3: 在 `models.py` 新增兩個 dataclass**

找到最後一個 `@dataclass` 定義，在其之後加入：

```python
@dataclass
class ReleaseKeyword:
    id: int | None
    keyword: str
    ktype: str  # 'confirm' | 'ship'
    created_at: str | None = None


@dataclass
class ReleaseItem:
    id: int | None
    case_id: str | None
    mantis_ticket_id: str | None
    assignee: str | None
    client_name: str | None
    note: str | None
    status: str = "待發"      # '待發' | '已發布'
    month_str: str | None = None   # 'YYYYMM'
    patch_id: int | None = None
    created_at: str | None = None
```

- [ ] **Step 4: 確認應用程式仍能啟動**

```bash
.venv/Scripts/python.exe -m hcp_cms &
# 等視窗出現後關閉，確認無 traceback
```

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/data/database.py src/hcp_cms/data/models.py
git commit -m "feat(data): 新增 cs_release_items / cs_release_keywords 資料表與模型"
```

---

## Task 2: Repository 層

**Files:**
- Modify: `src/hcp_cms/data/repositories.py`
- Create: `tests/unit/test_release_repository.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/unit/test_release_repository.py`：

```python
"""ReleaseItemRepository / ReleaseKeywordRepository 單元測試。"""
import sqlite3
import pytest
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.repositories import ReleaseItemRepository, ReleaseKeywordRepository
from hcp_cms.data.models import ReleaseItem, ReleaseKeyword


@pytest.fixture
def conn(tmp_path):
    db = DatabaseManager(tmp_path / "test.db")
    db.initialize()
    yield db.connection
    db.close()


class TestReleaseKeywordRepository:
    def test_list_all_returns_defaults(self, conn):
        repo = ReleaseKeywordRepository(conn)
        kws = repo.list_all()
        assert any(k.keyword == "測試ok" for k in kws)
        assert any(k.ktype == "ship" for k in kws)

    def test_insert_and_delete(self, conn):
        repo = ReleaseKeywordRepository(conn)
        kw = ReleaseKeyword(id=None, keyword="客戶確認", ktype="confirm")
        new_id = repo.insert(kw)
        assert new_id > 0
        all_kws = repo.list_all()
        assert any(k.id == new_id for k in all_kws)
        repo.delete(new_id)
        assert not any(k.id == new_id for k in repo.list_all())


class TestReleaseItemRepository:
    def test_insert_and_get(self, conn):
        repo = ReleaseItemRepository(conn)
        item = ReleaseItem(
            id=None, case_id="CS-2026-001",
            mantis_ticket_id="0017095", assignee="jill",
            client_name="華碩電腦", note="測試OK，安排出貨",
            month_str="202604",
        )
        new_id = repo.insert(item)
        assert new_id > 0

    def test_list_by_month(self, conn):
        repo = ReleaseItemRepository(conn)
        item = ReleaseItem(
            id=None, case_id="CS-2026-002",
            mantis_ticket_id=None, assignee="jill",
            client_name="測試公司", note="請出貨",
            month_str="202604",
        )
        repo.insert(item)
        results = repo.list_by_month("202604")
        assert len(results) >= 1
        assert results[0].month_str == "202604"

    def test_mark_released(self, conn):
        repo = ReleaseItemRepository(conn)
        item = ReleaseItem(
            id=None, case_id="CS-2026-003",
            mantis_ticket_id=None, assignee=None,
            client_name=None, note=None,
            month_str="202604",
        )
        new_id = repo.insert(item)
        repo.mark_released(new_id)
        results = repo.list_by_month("202604")
        target = next(r for r in results if r.id == new_id)
        assert target.status == "已發布"
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_release_repository.py -v
# 預期：ImportError — ReleaseItemRepository not defined
```

- [ ] **Step 3: 在 `repositories.py` 末端加入兩個 Repository 類別**

```python
# ──────────────────────────────────────────────────────────────────────────────
# ReleaseKeywordRepository
# ──────────────────────────────────────────────────────────────────────────────

class ReleaseKeywordRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_all(self) -> list[ReleaseKeyword]:
        rows = self._conn.execute(
            "SELECT id, keyword, ktype, created_at FROM cs_release_keywords ORDER BY ktype, keyword"
        ).fetchall()
        return [ReleaseKeyword(id=r[0], keyword=r[1], ktype=r[2], created_at=r[3]) for r in rows]

    def insert(self, kw: ReleaseKeyword) -> int:
        cur = self._conn.execute(
            "INSERT INTO cs_release_keywords (keyword, ktype, created_at) VALUES (?, ?, datetime('now'))",
            (kw.keyword, kw.ktype),
        )
        self._conn.commit()
        return cur.lastrowid

    def delete(self, keyword_id: int) -> None:
        self._conn.execute("DELETE FROM cs_release_keywords WHERE id = ?", (keyword_id,))
        self._conn.commit()


# ──────────────────────────────────────────────────────────────────────────────
# ReleaseItemRepository
# ──────────────────────────────────────────────────────────────────────────────

class ReleaseItemRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, item: ReleaseItem) -> int:
        from hcp_cms.data.repositories import _now
        cur = self._conn.execute(
            """INSERT INTO cs_release_items
               (case_id, mantis_ticket_id, assignee, client_name, note,
                status, month_str, patch_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (item.case_id, item.mantis_ticket_id, item.assignee, item.client_name,
             item.note, item.status, item.month_str, item.patch_id, _now()),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_by_month(self, month_str: str) -> list[ReleaseItem]:
        rows = self._conn.execute(
            "SELECT id,case_id,mantis_ticket_id,assignee,client_name,note,"
            "status,month_str,patch_id,created_at FROM cs_release_items"
            " WHERE month_str=? ORDER BY created_at DESC",
            (month_str,),
        ).fetchall()
        return [self._row(r) for r in rows]

    def list_all(self) -> list[ReleaseItem]:
        rows = self._conn.execute(
            "SELECT id,case_id,mantis_ticket_id,assignee,client_name,note,"
            "status,month_str,patch_id,created_at FROM cs_release_items"
            " ORDER BY created_at DESC"
        ).fetchall()
        return [self._row(r) for r in rows]

    def mark_released(self, item_id: int) -> None:
        self._conn.execute(
            "UPDATE cs_release_items SET status='已發布' WHERE id=?", (item_id,)
        )
        self._conn.commit()

    def _row(self, r) -> ReleaseItem:
        return ReleaseItem(
            id=r[0], case_id=r[1], mantis_ticket_id=r[2], assignee=r[3],
            client_name=r[4], note=r[5], status=r[6], month_str=r[7],
            patch_id=r[8], created_at=r[9],
        )
```

**注意**：`_now()` 已定義於 `repositories.py` 頂端，`ReleaseItemRepository.insert` 中直接呼叫即可，移除 `from hcp_cms.data.repositories import _now` 那行（同檔內已可見）。

- [ ] **Step 4: 確認 models.py import 在 repositories.py 頂端**

repositories.py 頂端的 import 須包含新模型：
```python
from hcp_cms.data.models import (
    ...,
    ReleaseItem,
    ReleaseKeyword,
)
```

- [ ] **Step 5: 執行測試確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_release_repository.py -v
# 預期：7 passed
```

- [ ] **Step 6: Commit**

```bash
git add src/hcp_cms/data/repositories.py tests/unit/test_release_repository.py
git commit -m "feat(data): 新增 ReleaseItemRepository / ReleaseKeywordRepository"
```

---

## Task 3: Core — ReleaseManager + ReleaseDetector

**Files:**
- Create: `src/hcp_cms/core/release_manager.py`
- Create: `tests/unit/test_release_manager.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/unit/test_release_manager.py`：

```python
"""ReleaseDetector / ReleaseManager 單元測試。"""
import pytest
from hcp_cms.data.database import DatabaseManager
from hcp_cms.core.release_manager import ReleaseDetector, ReleaseManager


@pytest.fixture
def conn(tmp_path):
    db = DatabaseManager(tmp_path / "test.db")
    db.initialize()
    yield db.connection
    db.close()


class TestReleaseDetector:
    def test_detects_confirm_and_ship(self, conn):
        det = ReleaseDetector(conn)
        body = "分配給: jill\n客戶回覆測試ok，請安排出貨，謝謝。"
        result = det.detect(body)
        assert result is not None
        assert result["assignee"] == "jill"
        assert "安排出貨" in result["note"]

    def test_returns_none_when_missing_ship_keyword(self, conn):
        det = ReleaseDetector(conn)
        body = "分配給: jill\n測試OK，功能正常。"
        assert det.detect(body) is None

    def test_returns_none_when_missing_confirm_keyword(self, conn):
        det = ReleaseDetector(conn)
        body = "分配給: jill\n請安排出貨。"
        assert det.detect(body) is None

    def test_assignee_optional(self, conn):
        det = ReleaseDetector(conn)
        body = "測試OK，安排出貨。"
        result = det.detect(body)
        assert result is not None
        assert result["assignee"] is None

    def test_multiline_assignee(self, conn):
        det = ReleaseDetector(conn)
        body = "分配給:        jill\n測試ok 安排出貨"
        result = det.detect(body)
        assert result["assignee"] == "jill"


class TestReleaseManager:
    def test_detect_and_record_creates_item(self, conn):
        mgr = ReleaseManager(conn)
        mgr.detect_and_record(
            body="分配給: jill\n客戶測試OK，安排出貨",
            case_id="CS-2026-001",
            mantis_ticket_id="0017095",
            client_name="華碩電腦",
            month_str="202604",
        )
        from hcp_cms.data.repositories import ReleaseItemRepository
        items = ReleaseItemRepository(conn).list_by_month("202604")
        assert len(items) == 1
        assert items[0].assignee == "jill"
        assert items[0].mantis_ticket_id == "0017095"

    def test_detect_and_record_no_match_does_nothing(self, conn):
        mgr = ReleaseManager(conn)
        mgr.detect_and_record(
            body="一般諮詢信件",
            case_id="CS-2026-002",
            mantis_ticket_id=None,
            client_name="測試公司",
            month_str="202604",
        )
        from hcp_cms.data.repositories import ReleaseItemRepository
        items = ReleaseItemRepository(conn).list_by_month("202604")
        assert len(items) == 0
```

- [ ] **Step 2: 執行確認失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_release_manager.py -v
# 預期：ImportError — release_manager not found
```

- [ ] **Step 3: 建立 `src/hcp_cms/core/release_manager.py`**

```python
"""ReleaseDetector — 偵測信件是否為待發確認，ReleaseManager — CRUD 整合。"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime

from hcp_cms.data.models import ReleaseItem
from hcp_cms.data.repositories import ReleaseItemRepository, ReleaseKeywordRepository


_ASSIGNEE_RE = re.compile(r"分配給\s*[:：]\s*(\S+)", re.MULTILINE)


class ReleaseDetector:
    """根據 cs_release_keywords 資料表中的關鍵字偵測信件是否代表待發確認。

    規則：信件內容同時包含至少一個 confirm 詞與一個 ship 詞，才視為命中。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._kw_repo = ReleaseKeywordRepository(conn)

    def detect(self, body: str) -> dict | None:
        """分析信件本文，命中時回傳 {assignee, note}，否則回傳 None。"""
        keywords = self._kw_repo.list_all()
        confirm_kws = [k.keyword for k in keywords if k.ktype == "confirm"]
        ship_kws = [k.keyword for k in keywords if k.ktype == "ship"]

        body_lower = body.lower()
        has_confirm = any(k.lower() in body_lower for k in confirm_kws)
        has_ship = any(k.lower() in body_lower for k in ship_kws)

        if not (has_confirm and has_ship):
            return None

        assignee: str | None = None
        m = _ASSIGNEE_RE.search(body)
        if m:
            assignee = m.group(1).strip()

        # 擷取含關鍵字的段落作為備注（取第一個段落，最多 200 字）
        note = ""
        for line in body.splitlines():
            if any(k.lower() in line.lower() for k in confirm_kws + ship_kws):
                note = line.strip()[:200]
                break

        return {"assignee": assignee, "note": note}


class ReleaseManager:
    """待發清單 CRUD 與信件偵測整合。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._detector = ReleaseDetector(conn)
        self._repo = ReleaseItemRepository(conn)
        self._kw_repo = ReleaseKeywordRepository(conn)

    # ── 偵測並記錄 ────────────────────────────────────────────────────

    def detect_and_record(
        self,
        body: str,
        case_id: str | None = None,
        mantis_ticket_id: str | None = None,
        client_name: str | None = None,
        month_str: str | None = None,
    ) -> ReleaseItem | None:
        """偵測信件是否為待發確認；命中則建立 ReleaseItem 並回傳，否則回傳 None。"""
        result = self._detector.detect(body)
        if result is None:
            return None

        if month_str is None:
            month_str = datetime.now().strftime("%Y%m")

        item = ReleaseItem(
            id=None,
            case_id=case_id,
            mantis_ticket_id=mantis_ticket_id,
            assignee=result["assignee"],
            client_name=client_name,
            note=result["note"],
            month_str=month_str,
        )
        new_id = self._repo.insert(item)
        item.id = new_id
        return item

    # ── 查詢 ──────────────────────────────────────────────────────────

    def list_by_month(self, month_str: str) -> list[ReleaseItem]:
        return self._repo.list_by_month(month_str)

    def list_all(self) -> list[ReleaseItem]:
        return self._repo.list_all()

    def mark_released(self, item_id: int) -> None:
        self._repo.mark_released(item_id)

    # ── 關鍵字管理 ────────────────────────────────────────────────────

    def list_keywords(self) -> list:
        return self._kw_repo.list_all()

    def add_keyword(self, keyword: str, ktype: str) -> int:
        from hcp_cms.data.models import ReleaseKeyword
        return self._kw_repo.insert(ReleaseKeyword(id=None, keyword=keyword, ktype=ktype))

    def delete_keyword(self, keyword_id: int) -> None:
        self._kw_repo.delete(keyword_id)
```

- [ ] **Step 4: 執行測試確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_release_manager.py -v
# 預期：8 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/core/release_manager.py tests/unit/test_release_manager.py
git commit -m "feat(core): 新增 ReleaseDetector / ReleaseManager"
```

---

## Task 4: 整合 import_email 管線

**Files:**
- Modify: `src/hcp_cms/core/case_manager.py`

- [ ] **Step 1: 在 `import_email` 中加入偵測呼叫**

找到 `import_email` 方法，在 `return (case, action)` **之前**加入：

```python
        # 待發清單偵測（信件含確認+出貨關鍵字時自動記錄）
        try:
            from hcp_cms.core.release_manager import ReleaseManager
            from datetime import datetime
            month_str = datetime.now().strftime("%Y%m")
            comp = None
            if case:
                from hcp_cms.data.repositories import CompanyRepository
                comp = CompanyRepository(self._conn).get_by_id(case.company_id or "")
            mantis_id = classification.get("mantis_ticket_id")
            ReleaseManager(self._conn).detect_and_record(
                body=body,
                case_id=case.case_id if case else None,
                mantis_ticket_id=mantis_id,
                client_name=comp.name if comp else None,
                month_str=month_str,
            )
        except Exception:
            pass  # 偵測失敗不影響主流程
```

**注意**：`classification` 變數在 `import_email` 中已存在（第 137 行附近）。若 action 為 `'merged'`（非新建案件），`case` 仍是 `existing` 物件，可正常傳入。

- [ ] **Step 2: 手動測試：重啟 app，匯入含「測試OK + 安排出貨」的信件，確認 ReleaseItem 被建立**

```bash
.venv/Scripts/python.exe -c "
import sqlite3, os
db_path = os.environ.get('APPDATA', '') + '/HCP_CMS/cs_tracker.db'
conn = sqlite3.connect(db_path)
rows = conn.execute('SELECT * FROM cs_release_items ORDER BY created_at DESC LIMIT 5').fetchall()
for r in rows: print(r)
conn.close()
"
```

- [ ] **Step 3: Commit**

```bash
git add src/hcp_cms/core/case_manager.py
git commit -m "feat(core): import_email 整合待發清單偵測"
```

---

## Task 5: UI — 待發清單 Tab

**Files:**
- Create: `src/hcp_cms/ui/pending_release_tab.py`
- Modify: `src/hcp_cms/ui/patch_view.py`

- [ ] **Step 1: 建立 `pending_release_tab.py`**

```python
"""待發清單 Tab — 顯示待發布的 Patch 確認項目，支援月份篩選與標記已發布。"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from hcp_cms.core.release_manager import ReleaseManager


class PendingReleaseTab(QWidget):
    """待發清單分頁：依月份顯示待發項目，可標記已發布。"""

    def __init__(self, conn: sqlite3.Connection | None = None, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._items: list = []
        self._setup_ui()
        if conn:
            self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        # 工具列
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("月份："))
        self._month_combo = QComboBox()
        self._month_combo.setMinimumWidth(120)
        self._populate_months()
        self._month_combo.currentIndexChanged.connect(self.refresh)
        toolbar.addWidget(self._month_combo)

        refresh_btn = QPushButton("🔄 重新整理")
        refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch()

        self._release_btn = QPushButton("✅ 標記已發布")
        self._release_btn.setEnabled(False)
        self._release_btn.clicked.connect(self._on_mark_released)
        toolbar.addWidget(self._release_btn)
        layout.addLayout(toolbar)

        # 表格
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "ID", "案件編號", "Mantis 票號", "客戶", "指派人", "備注", "狀態"
        ])
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table)

    def _populate_months(self) -> None:
        """填入近 12 個月選項。"""
        now = datetime.now()
        for i in range(12):
            m = now.month - i
        year = now.year
        months = []
        for i in range(12):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            months.append(f"{y}{m:02d}")
        for ms in months:
            self._month_combo.addItem(f"{ms[:4]}/{ms[4:]}", ms)

    def refresh(self) -> None:
        if not self._conn:
            return
        month_str = self._month_combo.currentData()
        if not month_str:
            return
        mgr = ReleaseManager(self._conn)
        self._items = mgr.list_by_month(month_str)
        self._table.setRowCount(0)
        for item in self._items:
            row = self._table.rowCount()
            self._table.insertRow(row)
            vals = [
                str(item.id or ""),
                item.case_id or "",
                item.mantis_ticket_id or "",
                item.client_name or "",
                item.assignee or "",
                item.note or "",
                item.status,
            ]
            for col, v in enumerate(vals):
                cell = QTableWidgetItem(v)
                if item.status == "已發布":
                    cell.setForeground(Qt.GlobalColor.gray)
                self._table.setItem(row, col, cell)
        self._release_btn.setEnabled(False)

    def _on_selection_changed(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            self._release_btn.setEnabled(False)
            return
        row = rows[0].row()
        if 0 <= row < len(self._items):
            self._release_btn.setEnabled(self._items[row].status == "待發")

    def _on_mark_released(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows or not self._conn:
            return
        row = rows[0].row()
        if row < 0 or row >= len(self._items):
            return
        item = self._items[row]
        ReleaseManager(self._conn).mark_released(item.id)
        self.refresh()
        QMessageBox.information(self, "完成", f"已將 {item.mantis_ticket_id or item.case_id} 標記為已發布。")
```

- [ ] **Step 2: 在 `patch_view.py` 加入新 Tab**

在 `_setup_ui` 的 `self._tabs.addTab(...)` 區塊末端加入：

```python
        from hcp_cms.ui.pending_release_tab import PendingReleaseTab
        self._release_tab = PendingReleaseTab(conn=self._conn)
        self._tabs.addTab(self._release_tab, "📋 待發清單")
```

並在 `_on_tab_changed`（或 `currentChanged` slot）中加入當切換至「待發清單」時自動 refresh：

```python
    def _on_tab_changed(self, index: int) -> None:
        # 現有邏輯...
        if self._tabs.widget(index) is self._release_tab:
            self._release_tab.refresh()
```

- [ ] **Step 3: 啟動確認 Tab 正常顯示**

```bash
.venv/Scripts/python.exe -m hcp_cms
# 到 Patch 整理頁面 → 確認「📋 待發清單」Tab 存在且可切換
```

- [ ] **Step 4: Commit**

```bash
git add src/hcp_cms/ui/pending_release_tab.py src/hcp_cms/ui/patch_view.py
git commit -m "feat(ui): Patch 整理新增待發清單 Tab"
```

---

## Task 6: UI — 規則設定新增「待發關鍵字」區塊

**Files:**
- Modify: `src/hcp_cms/ui/rules_view.py`

- [ ] **Step 1: 了解現有 rules_view 結構**

`rules_view.py` 目前以 `QTabWidget` 或 `QVBoxLayout` 顯示分類規則。在最底部新增一個獨立 section。

- [ ] **Step 2: 在 `RulesView._setup_ui` 末端加入待發關鍵字區塊**

找到 `RulesView` 的主 layout 建立位置，在其末端（最後一個 `addWidget` 或 `addLayout` 之後）加入：

```python
        # ── 待發關鍵字管理 ────────────────────────────────────────────
        from hcp_cms.core.release_manager import ReleaseManager
        kw_frame = QFrame()
        kw_frame.setFrameShape(QFrame.Shape.StyledPanel)
        kw_layout = QVBoxLayout(kw_frame)

        kw_title = QLabel("📦 待發關鍵字")
        kw_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        kw_layout.addWidget(kw_title)
        kw_layout.addWidget(QLabel("同時包含「確認詞」和「出貨詞」的信件將自動加入待發清單。"))

        # 表格
        self._kw_table = QTableWidget(0, 3)
        self._kw_table.setHorizontalHeaderLabels(["ID", "關鍵字", "類型"])
        self._kw_table.horizontalHeader().setStretchLastSection(True)
        self._kw_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._kw_table.setMaximumHeight(200)
        kw_layout.addWidget(self._kw_table)

        # 新增列
        add_row = QHBoxLayout()
        self._kw_input = QLineEdit()
        self._kw_input.setPlaceholderText("輸入關鍵字")
        self._kw_type_combo = QComboBox()
        self._kw_type_combo.addItem("確認詞", "confirm")
        self._kw_type_combo.addItem("出貨詞", "ship")
        add_kw_btn = QPushButton("➕ 新增")
        add_kw_btn.clicked.connect(self._on_add_keyword)
        del_kw_btn = QPushButton("🗑 刪除選取")
        del_kw_btn.clicked.connect(self._on_delete_keyword)
        add_row.addWidget(self._kw_input)
        add_row.addWidget(self._kw_type_combo)
        add_row.addWidget(add_kw_btn)
        add_row.addWidget(del_kw_btn)
        kw_layout.addLayout(add_row)

        layout.addWidget(kw_frame)   # layout = RulesView 的主 layout
        self._load_keywords()
```

- [ ] **Step 3: 加入三個 slot 方法**

在 `RulesView` 類別中加入：

```python
    def _load_keywords(self) -> None:
        if not self._conn:
            return
        from hcp_cms.core.release_manager import ReleaseManager
        kws = ReleaseManager(self._conn).list_keywords()
        self._kw_table.setRowCount(0)
        type_labels = {"confirm": "確認詞", "ship": "出貨詞"}
        for kw in kws:
            row = self._kw_table.rowCount()
            self._kw_table.insertRow(row)
            self._kw_table.setItem(row, 0, QTableWidgetItem(str(kw.id)))
            self._kw_table.setItem(row, 1, QTableWidgetItem(kw.keyword))
            self._kw_table.setItem(row, 2, QTableWidgetItem(type_labels.get(kw.ktype, kw.ktype)))

    def _on_add_keyword(self) -> None:
        if not self._conn:
            return
        keyword = self._kw_input.text().strip()
        if not keyword:
            return
        ktype = self._kw_type_combo.currentData()
        from hcp_cms.core.release_manager import ReleaseManager
        ReleaseManager(self._conn).add_keyword(keyword, ktype)
        self._kw_input.clear()
        self._load_keywords()

    def _on_delete_keyword(self) -> None:
        if not self._conn:
            return
        rows = self._kw_table.selectionModel().selectedRows()
        if not rows:
            return
        kid = int(self._kw_table.item(rows[0].row(), 0).text())
        from hcp_cms.core.release_manager import ReleaseManager
        ReleaseManager(self._conn).delete_keyword(kid)
        self._load_keywords()
```

- [ ] **Step 4: 確認 `RulesView.__init__` 有 `self._conn` 參數**

查看 `rules_view.py` 的 `__init__`，若無 `conn` 參數則加入：
```python
def __init__(self, conn: sqlite3.Connection | None = None, ...):
    self._conn = conn
```

並確認 `main_window.py` 呼叫 `RulesView(conn=self._conn)` 時有傳入 conn。

- [ ] **Step 5: 啟動確認規則設定頁面顯示「待發關鍵字」區塊**

```bash
.venv/Scripts/python.exe -m hcp_cms
# 到 規則設定 → 確認底部有「待發關鍵字」管理區塊，預設關鍵字已載入
```

- [ ] **Step 6: Commit**

```bash
git add src/hcp_cms/ui/rules_view.py
git commit -m "feat(ui): 規則設定新增待發關鍵字管理區塊"
```

---

## Self-Review

### Spec Coverage

| 需求 | 對應 Task |
|------|-----------|
| 可自訂關鍵字（確認詞 + 出貨詞） | Task 1（DDL + 種子）、Task 3（偵測邏輯）、Task 6（UI 管理） |
| 月份分組對應 Patch | Task 1（month_str 欄位）、Task 5（月份篩選） |
| 解析「分配給: XXX」格式 | Task 3（`_ASSIGNEE_RE`） |
| 自動加入待發清單 | Task 4（import_email 整合） |
| Patch 整理結合 | Task 5（新增 Tab） |
| 標記已發布 | Task 5（UI 按鈕 + repo） |

### Placeholder Scan
無 TBD / TODO / 空佔位。

### Type Consistency
- `ReleaseItem` / `ReleaseKeyword` 在 Task 1 定義，Task 2-6 一致使用
- `ReleaseManager.detect_and_record()` 在 Task 3 定義，Task 4 呼叫簽名一致
- `ReleaseKeywordRepository.insert()` 回傳 `int`（lastrowid），Task 3 的 `add_keyword` 正確回傳
