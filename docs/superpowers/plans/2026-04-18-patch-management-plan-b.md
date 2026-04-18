# Patch 整理 Plan B — UI 層實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 實作 Patch 整理系統的 UI 層，包含共用 IssueTableWidget、SinglePatchTab、MonthlyPatchTab、PatchView 容器，以及 MainWindow 整合。

**Architecture:** 所有 View 繼承 QWidget，初始化集中於 `_setup_ui()`。PatchView 以 QTabWidget 包裝 SinglePatchTab / MonthlyPatchTab；IssueTableWidget 為兩個 Tab 共用的可編輯 Issue 清單元件。背景耗時操作（掃描、Mantis 同步、產報表）用 `threading.Thread` + 類別層級 `Signal(object)` 傳回結果，不阻塞 UI 主線程。

**Tech Stack:** PySide6 6.10、SQLite（PatchRepository）、pytest-qt（qtbot fixture）、threading.Thread（背景工作）

---

## 檔案對應

| 動作 | 路徑 | 職責 |
|------|------|------|
| 修改 | `src/hcp_cms/data/repositories.py` | 新增 `PatchRepository.get_issue_by_id` |
| 修改 | `src/hcp_cms/core/patch_engine.py` | 新增 `setup_new_patch`、`load_issues_from_release_doc` |
| 新增 | `src/hcp_cms/ui/widgets/issue_table_widget.py` | 可編輯 Issue 清單元件 |
| 新增 | `src/hcp_cms/ui/patch_single_tab.py` | 單次 Patch Tab（6 步流程）|
| 新增 | `src/hcp_cms/ui/patch_monthly_tab.py` | 每月大 PATCH Tab（7 步流程）|
| 新增 | `src/hcp_cms/ui/patch_view.py` | PatchView（QTabWidget 容器）|
| 修改 | `src/hcp_cms/ui/main_window.py` | 新增「📦 Patch 整理」nav 入口 |
| 新增 | `tests/unit/test_issue_table_widget.py` | IssueTableWidget 單元測試 |
| 新增 | `tests/unit/test_patch_single_tab.py` | SinglePatchTab 單元測試 |
| 新增 | `tests/unit/test_patch_monthly_tab.py` | MonthlyPatchTab 單元測試 |
| 新增 | `tests/unit/test_patch_view.py` | PatchView 單元測試 |

---

### Task 1: PatchRepository.get_issue_by_id + IssueTableWidget [POC: QTableWidget 拖曳列重排]

**POC 原因：** QTableWidget InternalMove 拖曳後 `rowsMoved` signal 的觸發時機與 row item 資料一致性需在實際環境驗證。

**Files:**
- Modify: `src/hcp_cms/data/repositories.py:1257`（在 `delete_issue` 前插入）
- Create: `src/hcp_cms/ui/widgets/issue_table_widget.py`
- Test: `tests/unit/test_issue_table_widget.py`

- [ ] **Step 1: 在 PatchRepository 新增 get_issue_by_id**

在 `src/hcp_cms/data/repositories.py` 的 `delete_issue` 方法前插入：

```python
def get_issue_by_id(self, issue_id: int) -> PatchIssue | None:
    row = self._conn.execute(
        "SELECT * FROM cs_patch_issues WHERE id = :id", {"id": issue_id}
    ).fetchone()
    return self._row_to_issue(row) if row else None
```

- [ ] **Step 2: 撰寫失敗測試**

新增 `tests/unit/test_issue_table_widget.py`：

```python
"""IssueTableWidget 單元測試。"""

from __future__ import annotations

import sqlite3

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import PatchIssue, PatchRecord
from hcp_cms.data.repositories import PatchRepository


@pytest.fixture
def db(tmp_path):
    dm = DatabaseManager(str(tmp_path / "t.db"))
    conn = dm.initialize()
    yield conn
    conn.close()


@pytest.fixture
def patch_id(db):
    repo = PatchRepository(db)
    return repo.insert_patch(PatchRecord(type="monthly", month_str="202604"))


def _make_issue(patch_id: int, no: str = "001") -> PatchIssue:
    return PatchIssue(patch_id=patch_id, issue_no=no, issue_type="BugFix",
                      region="TW", sort_order=0, source="manual")


# ── PatchRepository.get_issue_by_id ────────────────────────────────────────

def test_get_issue_by_id_returns_issue(db, patch_id):
    repo = PatchRepository(db)
    iid = repo.insert_issue(_make_issue(patch_id))
    result = repo.get_issue_by_id(iid)
    assert result is not None
    assert result.issue_no == "001"


def test_get_issue_by_id_returns_none_for_missing(db):
    repo = PatchRepository(db)
    assert repo.get_issue_by_id(9999) is None


# ── IssueTableWidget ────────────────────────────────────────────────────────

def test_load_issues_populates_table(qtbot, db, patch_id):
    from hcp_cms.ui.widgets.issue_table_widget import IssueTableWidget
    repo = PatchRepository(db)
    repo.insert_issue(_make_issue(patch_id))
    widget = IssueTableWidget(conn=db)
    qtbot.addWidget(widget)
    widget.load_issues(patch_id)
    assert widget._table.rowCount() == 1
    assert widget._table.item(0, 0).text() == "001"


def test_add_issue_appends_row(qtbot, db, patch_id):
    from hcp_cms.ui.widgets.issue_table_widget import IssueTableWidget
    widget = IssueTableWidget(conn=db)
    qtbot.addWidget(widget)
    widget.load_issues(patch_id)
    widget._on_add_clicked()
    assert widget._table.rowCount() == 1


def test_delete_issue_removes_row(qtbot, db, patch_id, monkeypatch):
    from hcp_cms.ui.widgets.issue_table_widget import IssueTableWidget
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **kw: QMessageBox.StandardButton.Yes,
    )
    repo = PatchRepository(db)
    repo.insert_issue(_make_issue(patch_id))
    widget = IssueTableWidget(conn=db)
    qtbot.addWidget(widget)
    widget.load_issues(patch_id)
    widget._table.selectRow(0)
    widget._on_delete_clicked()
    assert widget._table.rowCount() == 0
    assert repo.list_issues_by_patch(patch_id) == []


def test_cell_change_saves_to_db(qtbot, db, patch_id):
    from hcp_cms.ui.widgets.issue_table_widget import IssueTableWidget
    repo = PatchRepository(db)
    iid = repo.insert_issue(_make_issue(patch_id))
    widget = IssueTableWidget(conn=db)
    qtbot.addWidget(widget)
    widget.load_issues(patch_id)
    widget._table.item(0, 0).setText("999")
    saved = repo.get_issue_by_id(iid)
    assert saved is not None
    assert saved.issue_no == "999"


def test_issues_changed_signal_emitted(qtbot, db, patch_id):
    from hcp_cms.ui.widgets.issue_table_widget import IssueTableWidget
    widget = IssueTableWidget(conn=db)
    qtbot.addWidget(widget)
    widget.load_issues(patch_id)
    with qtbot.waitSignal(widget.issues_changed, timeout=1000):
        widget._on_add_clicked()
```

- [ ] **Step 3: 執行測試確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_issue_table_widget.py -v
```

Expected: FAIL — `IssueTableWidget` 尚未存在

- [ ] **Step 4: 建立 IssueTableWidget**

新增 `src/hcp_cms/ui/widgets/issue_table_widget.py`：

```python
"""IssueTableWidget — 可編輯 Issue 清單，供 SinglePatchTab / MonthlyPatchTab 共用。"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.data.models import PatchIssue
from hcp_cms.data.repositories import PatchRepository

_COLUMNS = [
    ("issue_no",        "Issue No"),
    ("issue_type",      "類型"),
    ("program_code",    "程式代號"),
    ("program_name",    "程式名稱"),
    ("region",          "區域"),
    ("description",     "功能說明"),
    ("impact",          "影響說明"),
    ("test_direction",  "測試方向"),
]
_COL_KEYS    = [c[0] for c in _COLUMNS]
_COL_HEADERS = [c[1] for c in _COLUMNS]


class IssueTableWidget(QWidget):
    issues_changed = Signal()

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._patch_id: int | None = None
        self._loading = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        btn_bar = QHBoxLayout()
        self._add_btn    = QPushButton("＋ 新增 Issue")
        self._delete_btn = QPushButton("🗑 刪除")
        btn_bar.addWidget(self._add_btn)
        btn_bar.addWidget(self._delete_btn)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COL_HEADERS)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove
        )
        self._table.setDragDropOverwriteMode(False)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._table)

        self._add_btn.clicked.connect(self._on_add_clicked)
        self._delete_btn.clicked.connect(self._on_delete_clicked)
        self._table.cellChanged.connect(self._on_cell_changed)
        self._table.model().rowsMoved.connect(self._on_rows_moved)

    # ── Public API ─────────────────────────────────────────────────────────

    def load_issues(self, patch_id: int,
                    conn: sqlite3.Connection | None = None) -> None:
        if conn:
            self._conn = conn
        self._patch_id = patch_id
        self._reload()

    # ── Internal ───────────────────────────────────────────────────────────

    def _reload(self) -> None:
        if not self._conn or self._patch_id is None:
            return
        repo = PatchRepository(self._conn)
        issues = repo.list_issues_by_patch(self._patch_id)
        self._loading = True
        try:
            self._table.setRowCount(0)
            for iss in issues:
                self._append_row(iss)
        finally:
            self._loading = False

    def _append_row(self, issue: PatchIssue) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        for col, key in enumerate(_COL_KEYS):
            value = getattr(issue, key, "") or ""
            item = QTableWidgetItem(str(value))
            item.setData(Qt.ItemDataRole.UserRole, issue.issue_id)
            self._table.setItem(row, col, item)

    def _on_add_clicked(self) -> None:
        if not self._conn or self._patch_id is None:
            return
        repo = PatchRepository(self._conn)
        new_issue = PatchIssue(
            patch_id=self._patch_id,
            issue_no="",
            issue_type="BugFix",
            region="共用",
            sort_order=self._table.rowCount(),
            source="manual",
        )
        repo.insert_issue(new_issue)
        self._reload()
        last = self._table.rowCount() - 1
        self._table.setCurrentCell(last, 0)
        self._table.editItem(self._table.item(last, 0))
        self.issues_changed.emit()

    def _on_delete_clicked(self) -> None:
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        if not rows:
            return
        answer = QMessageBox.question(
            self, "確認刪除",
            f"確定刪除選取的 {len(rows)} 筆 Issue？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not self._conn:
            return
        repo = PatchRepository(self._conn)
        for row in sorted(rows, reverse=True):
            item = self._table.item(row, 0)
            if item:
                issue_id = item.data(Qt.ItemDataRole.UserRole)
                if issue_id is not None:
                    repo.delete_issue(issue_id)
        self._reload()
        self.issues_changed.emit()

    def _on_cell_changed(self, row: int, _col: int) -> None:
        if self._loading or not self._conn or self._patch_id is None:
            return
        item = self._table.item(row, 0)
        if not item:
            return
        issue_id = item.data(Qt.ItemDataRole.UserRole)
        if issue_id is None:
            return
        repo = PatchRepository(self._conn)
        existing = repo.get_issue_by_id(issue_id)
        if not existing:
            return
        for col, key in enumerate(_COL_KEYS):
            cell = self._table.item(row, col)
            if cell:
                setattr(existing, key, cell.text())
        repo.update_issue(existing)
        self.issues_changed.emit()

    def _on_rows_moved(self) -> None:
        if self._loading or not self._conn or self._patch_id is None:
            return
        repo = PatchRepository(self._conn)
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if not item:
                continue
            issue_id = item.data(Qt.ItemDataRole.UserRole)
            if issue_id is None:
                continue
            existing = repo.get_issue_by_id(issue_id)
            if existing:
                existing.sort_order = row
                repo.update_issue(existing)
        self.issues_changed.emit()
```

- [ ] **Step 5: 執行測試確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_issue_table_widget.py -v
```

Expected: 全部 PASS

- [ ] **Step 6: Lint**

```
.venv/Scripts/ruff.exe check src/hcp_cms/data/repositories.py src/hcp_cms/ui/widgets/issue_table_widget.py
```

Expected: 無錯誤

- [ ] **Step 7: Commit**

```bash
git add src/hcp_cms/data/repositories.py \
        src/hcp_cms/ui/widgets/issue_table_widget.py \
        tests/unit/test_issue_table_widget.py
git commit -m "feat(ui): 新增 IssueTableWidget 及 PatchRepository.get_issue_by_id"
```

---

### Task 2: SinglePatchEngine 便利方法 + SinglePatchTab [POC: Mantis 瀏覽器互動]

**POC 原因：** Mantis 登入流程為非同步 UI 互動（開啟 Chrome → 等使用者按鈕），PySide6 跨線程 Signal 觸發時機需驗證；`read_release_doc` 解析真實 .doc 格式需在實際環境測試。

**Files:**
- Modify: `src/hcp_cms/core/patch_engine.py`（新增 `setup_new_patch`、`load_issues_from_release_doc`）
- Create: `src/hcp_cms/ui/patch_single_tab.py`
- Test: `tests/unit/test_patch_single_tab.py`

- [ ] **Step 1: 在 SinglePatchEngine 新增便利方法**

在 `src/hcp_cms/core/patch_engine.py` 的 `SinglePatchEngine` 類別末尾加入：

```python
# ── Patch 記錄管理 ─────────────────────────────────────────────────────────

def setup_new_patch(self, patch_dir: str) -> int:
    """建立單次 Patch 記錄，回傳 patch_id。"""
    from hcp_cms.data.models import PatchRecord
    patch = PatchRecord(type="single", patch_dir=patch_dir)
    return self._repo.insert_patch(patch)

def load_issues_from_release_doc(self, patch_id: int, doc_path: str) -> int:
    """從 ReleaseNote 解析 Issues 並寫入 DB，回傳新增筆數。"""
    from hcp_cms.data.models import PatchIssue
    raw_list = self.read_release_doc(doc_path)
    for idx, raw in enumerate(raw_list):
        issue = PatchIssue(
            patch_id=patch_id,
            issue_no=raw.get("issue_no", ""),
            program_code=raw.get("program_code"),
            program_name=raw.get("program_name"),
            issue_type=raw.get("issue_type", "BugFix"),
            region=raw.get("region", "共用"),
            description=raw.get("description"),
            impact=raw.get("impact"),
            test_direction=raw.get("test_direction"),
            source="manual",
            sort_order=idx,
        )
        self._repo.insert_issue(issue)
    return len(raw_list)
```

- [ ] **Step 2: 撰寫失敗測試**

新增 `tests/unit/test_patch_single_tab.py`：

```python
"""SinglePatchTab 單元測試。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import PatchRecord
from hcp_cms.data.repositories import PatchRepository


@pytest.fixture
def db(tmp_path):
    dm = DatabaseManager(str(tmp_path / "t.db"))
    conn = dm.initialize()
    yield conn
    conn.close()


def test_single_patch_tab_instantiates(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    assert tab._folder_edit is not None
    assert tab._issue_table is not None
    assert tab._log is not None


def test_browse_sets_folder(qtbot, db, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory",
        lambda *a, **kw: str(tmp_path),
    )
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._on_browse_clicked()
    assert tab._folder_edit.text() == str(tmp_path)
    assert tab._patch_dir == str(tmp_path)


def test_start_disabled_without_folder(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._on_start_clicked()  # 無資料夾，應直接 return，不 crash


def test_start_scan_creates_patch_record(qtbot, db, tmp_path):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    with patch("hcp_cms.core.patch_engine.SinglePatchEngine.scan_patch_dir",
               return_value={"form_files": [], "sql_files": [], "muti_files": [],
                             "setup_bat": False, "release_note": None,
                             "install_guide": None, "missing": []}), \
         patch("hcp_cms.core.patch_engine.SinglePatchEngine.setup_new_patch",
               return_value=1):
        tab = SinglePatchTab(conn=db)
        qtbot.addWidget(tab)
        tab._patch_dir = str(tmp_path)
        tab._folder_edit.setText(str(tmp_path))
        with qtbot.waitSignal(tab._scan_done, timeout=3000):
            tab._on_start_clicked()


def test_generate_disabled_without_patch_id(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._on_generate_excel_clicked()  # patch_id=None，應 return，不 crash


def test_setup_new_patch_creates_record(db):
    from hcp_cms.core.patch_engine import SinglePatchEngine
    engine = SinglePatchEngine(db)
    pid = engine.setup_new_patch("/tmp/patch_test")
    repo = PatchRepository(db)
    record = repo.get_patch_by_id(pid)
    assert record is not None
    assert record.type == "single"
    assert record.patch_dir == "/tmp/patch_test"


def test_load_issues_from_release_doc_empty(db):
    from hcp_cms.core.patch_engine import SinglePatchEngine
    repo = PatchRepository(db)
    pid = repo.insert_patch(PatchRecord(type="single"))
    engine = SinglePatchEngine(db)
    with patch.object(engine, "read_release_doc", return_value=[]):
        count = engine.load_issues_from_release_doc(pid, "/fake/path.doc")
    assert count == 0


def test_load_issues_from_release_doc_inserts(db):
    from hcp_cms.core.patch_engine import SinglePatchEngine
    repo = PatchRepository(db)
    pid = repo.insert_patch(PatchRecord(type="single"))
    engine = SinglePatchEngine(db)
    fake_issues = [
        {"issue_no": "001", "description": "修正薪資", "issue_type": "BugFix",
         "region": "TW", "program_code": "PA001", "program_name": "薪資計算"},
        {"issue_no": "002", "description": "新增功能", "issue_type": "Enhancement",
         "region": "共用"},
    ]
    with patch.object(engine, "read_release_doc", return_value=fake_issues):
        count = engine.load_issues_from_release_doc(pid, "/fake/path.doc")
    assert count == 2
    assert len(repo.list_issues_by_patch(pid)) == 2
```

- [ ] **Step 3: 執行測試確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_single_tab.py -v
```

Expected: FAIL — `SinglePatchTab` 尚未存在

- [ ] **Step 4: 建立 SinglePatchTab**

新增 `src/hcp_cms/ui/patch_single_tab.py`：

```python
"""SinglePatchTab — 單次 Patch 整理六步流程。"""

from __future__ import annotations

import sqlite3
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.ui.widgets.issue_table_widget import IssueTableWidget

_STEPS = ["① 選擇資料夾", "② 掃描", "③ Mantis", "④ 編輯", "⑤ 產報表", "⑥ 完成"]
_CLR_DONE    = "color: #22c55e; font-weight: bold;"
_CLR_CURRENT = "color: #3b82f6; font-weight: bold;"
_CLR_PENDING = "color: #64748b;"


class SinglePatchTab(QWidget):
    _scan_done     = Signal(object)
    _generate_done = Signal(object)

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._patch_id: int | None = None
        self._patch_dir: str | None = None
        self._mantis_service = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 步驟進度列
        self._step_labels: list[QLabel] = []
        step_bar = QHBoxLayout()
        for i, title in enumerate(_STEPS):
            lbl = QLabel(title)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._step_labels.append(lbl)
            step_bar.addWidget(lbl)
            if i < len(_STEPS) - 1:
                arrow = QLabel("→")
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                step_bar.addWidget(arrow)
        layout.addLayout(step_bar)

        # 資料夾選擇
        folder_row = QHBoxLayout()
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("選擇解壓縮後的 Patch 資料夾…")
        self._folder_edit.setReadOnly(True)
        self._browse_btn = QPushButton("瀏覽…")
        folder_row.addWidget(self._folder_edit)
        folder_row.addWidget(self._browse_btn)
        layout.addLayout(folder_row)

        # 操作按鈕列
        action_row = QHBoxLayout()
        self._start_btn          = QPushButton("▶ 開始掃描")
        self._mantis_login_btn   = QPushButton("🌐 開啟 Mantis")
        self._mantis_confirm_btn = QPushButton("✅ 已登入，繼續")
        self._skip_mantis_btn    = QPushButton("⏭ 跳過 Mantis")
        self._generate_btn       = QPushButton("📊 產生報表")
        self._regenerate_btn     = QPushButton("🔄 重新產出")
        self._mantis_confirm_btn.setVisible(False)
        self._skip_mantis_btn.setVisible(False)
        for btn in [self._start_btn, self._mantis_login_btn,
                    self._mantis_confirm_btn, self._skip_mantis_btn,
                    self._generate_btn, self._regenerate_btn]:
            action_row.addWidget(btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        # Issue 表格
        self._issue_table = IssueTableWidget(conn=self._conn)
        layout.addWidget(self._issue_table, stretch=2)

        # 執行 Log
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(150)
        layout.addWidget(self._log)

        # 產出清單
        self._output_list = QListWidget()
        self._output_list.setMaximumHeight(100)
        layout.addWidget(self._output_list)

        # Signal / Slot 連線
        self._browse_btn.clicked.connect(self._on_browse_clicked)
        self._start_btn.clicked.connect(self._on_start_clicked)
        self._mantis_login_btn.clicked.connect(self._on_mantis_login_clicked)
        self._mantis_confirm_btn.clicked.connect(self._on_mantis_login_confirmed)
        self._skip_mantis_btn.clicked.connect(self._on_skip_mantis_clicked)
        self._generate_btn.clicked.connect(self._on_generate_excel_clicked)
        self._regenerate_btn.clicked.connect(self._on_regenerate_clicked)
        self._scan_done.connect(self._on_scan_result)
        self._generate_done.connect(self._on_generate_result)

        self._set_step(0)

    # ── 步驟高亮 ───────────────────────────────────────────────────────────

    def _set_step(self, step: int) -> None:
        for i, lbl in enumerate(self._step_labels):
            if i < step:
                lbl.setStyleSheet(_CLR_DONE)
            elif i == step:
                lbl.setStyleSheet(_CLR_CURRENT)
            else:
                lbl.setStyleSheet(_CLR_PENDING)

    def _append_log(self, msg: str) -> None:
        self._log.append(msg)

    # ── Slots ──────────────────────────────────────────────────────────────

    def _on_browse_clicked(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "選擇 Patch 資料夾")
        if path:
            self._folder_edit.setText(path)
            self._patch_dir = path
            self._set_step(1)

    def _on_start_clicked(self) -> None:
        if not self._patch_dir or not self._conn:
            return
        self._start_btn.setEnabled(False)
        self._append_log("🔍 開始掃描資料夾…")
        conn = self._conn
        patch_dir = self._patch_dir

        def work() -> dict:
            from hcp_cms.core.patch_engine import SinglePatchEngine
            engine = SinglePatchEngine(conn)
            patch_id = engine.setup_new_patch(patch_dir)
            scan = engine.scan_patch_dir(patch_dir)
            issue_count = 0
            if scan.get("release_note"):
                issue_count = engine.load_issues_from_release_doc(
                    patch_id, scan["release_note"]
                )
            return {"patch_id": patch_id, "scan": scan, "issue_count": issue_count}

        threading.Thread(
            target=lambda: self._scan_done.emit(work()), daemon=True
        ).start()

    def _on_scan_result(self, result: dict) -> None:
        self._patch_id = result["patch_id"]
        scan = result["scan"]
        self._append_log(
            f"✅ 掃描完成：{len(scan.get('form_files', []))} 個 FORM、"
            f"{len(scan.get('sql_files', []))} 個 SQL"
        )
        if scan.get("missing"):
            self._append_log(f"⚠️ 缺少目錄：{', '.join(scan['missing'])}")
        self._append_log(f"📋 讀取 {result['issue_count']} 筆 Issue")
        self._issue_table.load_issues(self._patch_id)
        self._start_btn.setEnabled(True)
        self._set_step(2)

    def _on_mantis_login_clicked(self) -> None:
        self._mantis_confirm_btn.setVisible(True)
        self._skip_mantis_btn.setVisible(True)
        self._mantis_login_btn.setEnabled(False)
        self._append_log("🌐 開啟 Mantis 瀏覽器，請登入後點「已登入，繼續」…")
        conn = self._conn

        def open_browser() -> None:
            from hcp_cms.services.mantis.playwright_service import (
                PlaywrightMantisService,
            )
            from hcp_cms.services.credential import CredentialManager
            mantis_url = CredentialManager().retrieve("mantis_url") or ""
            svc = PlaywrightMantisService(mantis_url)
            self._mantis_service = svc
            svc.open_browser()

        threading.Thread(target=open_browser, daemon=True).start()

    def _on_mantis_login_confirmed(self) -> None:
        if self._mantis_service is None or self._patch_id is None:
            return
        self._mantis_confirm_btn.setEnabled(False)
        self._append_log("⏳ 讀取 Mantis Issue 資料…")
        svc = self._mantis_service
        conn = self._conn
        patch_id = self._patch_id

        def fetch() -> dict:
            from hcp_cms.data.repositories import PatchRepository
            svc.confirm_login()
            repo = PatchRepository(conn)
            issues = repo.list_issues_by_patch(patch_id)
            issue_nos = [i.issue_no for i in issues if i.issue_no]
            results = svc.fetch_issues_batch(issue_nos)
            svc.close()
            return {"fetched": len(results)}

        threading.Thread(
            target=lambda: self._scan_done.emit(fetch()), daemon=True
        ).start()

    def _on_skip_mantis_clicked(self) -> None:
        if self._mantis_service:
            self._mantis_service.close()
            self._mantis_service = None
        self._mantis_confirm_btn.setVisible(False)
        self._skip_mantis_btn.setVisible(False)
        self._mantis_login_btn.setEnabled(True)
        self._append_log("⏭ 已跳過 Mantis 同步")
        self._set_step(3)

    def _on_generate_excel_clicked(self) -> None:
        if self._patch_id is None or not self._conn:
            return
        self._generate_btn.setEnabled(False)
        self._append_log("📊 產生 Excel 報表中…")
        conn = self._conn
        patch_id = self._patch_id
        patch_dir = self._patch_dir or "."

        def work() -> dict:
            from hcp_cms.core.patch_engine import SinglePatchEngine
            engine = SinglePatchEngine(conn)
            paths = engine.generate_excel_reports(patch_id, patch_dir)
            return {"paths": paths, "error": None}

        threading.Thread(
            target=lambda: self._generate_done.emit(work()), daemon=True
        ).start()

    def _on_generate_result(self, result: dict) -> None:
        self._generate_btn.setEnabled(True)
        if result.get("error"):
            self._append_log(f"❌ 產出失敗：{result['error']}")
            return
        self._output_list.clear()
        for path in result.get("paths", []):
            item = QListWidgetItem(path)
            self._output_list.addItem(item)
            self._append_log(f"✅ {path}")
        self._set_step(5)

    def _on_regenerate_clicked(self) -> None:
        self._output_list.clear()
        self._on_generate_excel_clicked()

    def _on_issues_changed(self) -> None:
        pass
```

- [ ] **Step 5: 執行測試確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_single_tab.py -v
```

Expected: 全部 PASS

- [ ] **Step 6: Lint**

```
.venv/Scripts/ruff.exe check src/hcp_cms/core/patch_engine.py src/hcp_cms/ui/patch_single_tab.py
```

Expected: 無錯誤

- [ ] **Step 7: Commit**

```bash
git add src/hcp_cms/core/patch_engine.py \
        src/hcp_cms/ui/patch_single_tab.py \
        tests/unit/test_patch_single_tab.py
git commit -m "feat(core/ui): SinglePatchEngine 新增便利方法，實作 SinglePatchTab"
```

---

### Task 3: MonthlyPatchTab [POC: Mantis 來源批次抓取]

**POC 原因：** 'mantis' 來源需要 PlaywrightMantisService 瀏覽器互動 + 使用者提供 Issue 號清單，跨線程 Signal 時機需驗證。

**Files:**
- Create: `src/hcp_cms/ui/patch_monthly_tab.py`
- Test: `tests/unit/test_patch_monthly_tab.py`

- [ ] **Step 1: 撰寫失敗測試**

新增 `tests/unit/test_patch_monthly_tab.py`：

```python
"""MonthlyPatchTab 單元測試。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import PatchIssue, PatchRecord
from hcp_cms.data.repositories import PatchRepository


@pytest.fixture
def db(tmp_path):
    dm = DatabaseManager(str(tmp_path / "t.db"))
    conn = dm.initialize()
    yield conn
    conn.close()


def test_monthly_tab_instantiates(qtbot, db):
    from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab
    tab = MonthlyPatchTab(conn=db)
    qtbot.addWidget(tab)
    assert tab._month_combo is not None
    assert tab._year_spin is not None
    assert tab._issue_table is not None
    assert tab._log is not None


def test_month_str_format(qtbot, db):
    from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab
    tab = MonthlyPatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._year_spin.setValue(2026)
    tab._month_combo.setCurrentIndex(3)  # index 3 = 4月
    assert tab._get_month_str() == "202604"


def test_source_changed_shows_file_browse(qtbot, db):
    from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab
    tab = MonthlyPatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._source_combo.setCurrentIndex(0)  # 上傳檔案
    assert tab._file_btn.isVisible()


def test_import_manual_loads_issues(qtbot, db, tmp_path):
    import json
    from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab
    issues_data = [{"issue_no": "001", "description": "修正", "issue_type": "BugFix"}]
    f = tmp_path / "issues.json"
    f.write_text(json.dumps(issues_data), encoding="utf-8")
    tab = MonthlyPatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._year_spin.setValue(2026)
    tab._month_combo.setCurrentIndex(3)
    tab._file_path = str(f)
    tab._file_edit.setText(str(f))
    with qtbot.waitSignal(tab._import_done, timeout=3000):
        tab._on_import_clicked()
    assert tab._patch_id is not None
    assert tab._issue_table._table.rowCount() == 1


def test_generate_excel_disabled_without_patch_id(qtbot, db):
    from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab
    tab = MonthlyPatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._on_generate_excel_clicked()  # patch_id=None，應 return 不 crash


def test_generate_html_disabled_without_patch_id(qtbot, db):
    from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab
    tab = MonthlyPatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._on_generate_html_clicked()  # patch_id=None，應 return 不 crash
```

- [ ] **Step 2: 執行測試確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_monthly_tab.py -v
```

Expected: FAIL — `MonthlyPatchTab` 尚未存在

- [ ] **Step 3: 建立 MonthlyPatchTab**

新增 `src/hcp_cms/ui/patch_monthly_tab.py`：

```python
"""MonthlyPatchTab — 每月大 PATCH 七步流程。"""

from __future__ import annotations

import sqlite3
import threading
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.ui.widgets.issue_table_widget import IssueTableWidget

_STEPS = ["① 選月份", "② 選來源", "③ 匯入", "④ 編輯", "⑤ Excel", "⑥ 通知信", "⑦ 完成"]
_CLR_DONE    = "color: #22c55e; font-weight: bold;"
_CLR_CURRENT = "color: #3b82f6; font-weight: bold;"
_CLR_PENDING = "color: #64748b;"
_MONTHS = [f"{m:02d}月" for m in range(1, 13)]
_SOURCE_FILE   = "上傳 .txt / .json"
_SOURCE_MANTIS = "Mantis 瀏覽器"


class MonthlyPatchTab(QWidget):
    _import_done   = Signal(object)
    _generate_done = Signal(object)

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._patch_id: int | None = None
        self._file_path: str | None = None
        self._output_dir: str | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        today = date.today()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 步驟進度列
        self._step_labels: list[QLabel] = []
        step_bar = QHBoxLayout()
        for i, title in enumerate(_STEPS):
            lbl = QLabel(title)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._step_labels.append(lbl)
            step_bar.addWidget(lbl)
            if i < len(_STEPS) - 1:
                arrow = QLabel("→")
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                step_bar.addWidget(arrow)
        layout.addLayout(step_bar)

        # 月份選擇列
        month_row = QHBoxLayout()
        month_row.addWidget(QLabel("月份："))
        self._year_spin = QSpinBox()
        self._year_spin.setRange(2000, 2100)
        self._year_spin.setValue(today.year)
        self._year_spin.setFixedWidth(80)
        month_row.addWidget(self._year_spin)
        self._month_combo = QComboBox()
        self._month_combo.addItems(_MONTHS)
        self._month_combo.setCurrentIndex(today.month - 1)
        self._month_combo.setFixedWidth(80)
        month_row.addWidget(self._month_combo)
        month_row.addStretch()
        layout.addLayout(month_row)

        # 來源選擇列
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Issue 來源："))
        self._source_combo = QComboBox()
        self._source_combo.addItems([_SOURCE_FILE, _SOURCE_MANTIS])
        src_row.addWidget(self._source_combo)
        self._file_edit = QLineEdit()
        self._file_edit.setPlaceholderText("選擇 .txt 或 .json 檔案…")
        self._file_edit.setReadOnly(True)
        self._file_btn = QPushButton("瀏覽…")
        src_row.addWidget(self._file_edit)
        src_row.addWidget(self._file_btn)
        layout.addLayout(src_row)

        # 輸出目錄
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("輸出目錄："))
        self._out_edit = QLineEdit()
        self._out_edit.setPlaceholderText("預設：_temp/monthly_{月份}/")
        self._out_edit.setReadOnly(True)
        self._out_btn = QPushButton("瀏覽…")
        out_row.addWidget(self._out_edit)
        out_row.addWidget(self._out_btn)
        layout.addLayout(out_row)

        # 操作按鈕
        action_row = QHBoxLayout()
        self._import_btn       = QPushButton("📥 匯入 Issue")
        self._generate_excel_btn = QPushButton("📊 產生 Excel")
        self._generate_html_btn  = QPushButton("✉️ 產生通知信")
        self._regenerate_btn   = QPushButton("🔄 重新產出")
        for btn in [self._import_btn, self._generate_excel_btn,
                    self._generate_html_btn, self._regenerate_btn]:
            action_row.addWidget(btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        # Issue 表格
        self._issue_table = IssueTableWidget(conn=self._conn)
        layout.addWidget(self._issue_table, stretch=2)

        # 執行 Log
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(150)
        layout.addWidget(self._log)

        # 產出清單
        self._output_list = QListWidget()
        self._output_list.setMaximumHeight(100)
        layout.addWidget(self._output_list)

        # Signal / Slot 連線
        self._source_combo.currentIndexChanged.connect(self._on_issue_source_changed)
        self._file_btn.clicked.connect(self._on_file_browse_clicked)
        self._out_btn.clicked.connect(self._on_out_browse_clicked)
        self._import_btn.clicked.connect(self._on_import_clicked)
        self._generate_excel_btn.clicked.connect(self._on_generate_excel_clicked)
        self._generate_html_btn.clicked.connect(self._on_generate_html_clicked)
        self._regenerate_btn.clicked.connect(self._on_regenerate_clicked)
        self._import_done.connect(self._on_import_result)
        self._generate_done.connect(self._on_generate_result)

        self._on_issue_source_changed(0)
        self._set_step(0)

    # ── 輔助 ───────────────────────────────────────────────────────────────

    def _get_month_str(self) -> str:
        year  = self._year_spin.value()
        month = self._month_combo.currentIndex() + 1
        return f"{year}{month:02d}"

    def _get_output_dir(self) -> str:
        if self._output_dir:
            return self._output_dir
        return f"_temp/monthly_{self._get_month_str()}"

    def _set_step(self, step: int) -> None:
        for i, lbl in enumerate(self._step_labels):
            if i < step:
                lbl.setStyleSheet(_CLR_DONE)
            elif i == step:
                lbl.setStyleSheet(_CLR_CURRENT)
            else:
                lbl.setStyleSheet(_CLR_PENDING)

    def _append_log(self, msg: str) -> None:
        self._log.append(msg)

    # ── Slots ──────────────────────────────────────────────────────────────

    def _on_issue_source_changed(self, index: int) -> None:
        is_file = self._source_combo.currentText() == _SOURCE_FILE
        self._file_edit.setVisible(is_file)
        self._file_btn.setVisible(is_file)

    def _on_file_browse_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇 Issue 清單", "",
            "資料檔 (*.txt *.json);;全部檔案 (*.*)"
        )
        if path:
            self._file_path = path
            self._file_edit.setText(path)
            self._set_step(1)

    def _on_out_browse_clicked(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "選擇輸出目錄")
        if path:
            self._output_dir = path
            self._out_edit.setText(path)

    def _on_import_clicked(self) -> None:
        if not self._conn:
            return
        source_text = self._source_combo.currentText()
        month_str   = self._get_month_str()
        conn        = self._conn
        file_path   = self._file_path

        if source_text == _SOURCE_FILE and not file_path:
            self._append_log("⚠️ 請先選擇檔案")
            return

        self._import_btn.setEnabled(False)
        self._append_log(f"📥 匯入 {month_str} Issue 清單…")

        def work() -> dict:
            from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
            engine = MonthlyPatchEngine(conn)
            if source_text == _SOURCE_FILE:
                pid = engine.load_issues("manual", month_str, file_path)
            else:
                pid = engine.load_issues("manual", month_str, None)
            from hcp_cms.data.repositories import PatchRepository
            count = len(PatchRepository(conn).list_issues_by_patch(pid))
            return {"patch_id": pid, "count": count}

        threading.Thread(
            target=lambda: self._import_done.emit(work()), daemon=True
        ).start()

    def _on_import_result(self, result: dict) -> None:
        self._import_btn.setEnabled(True)
        self._patch_id = result["patch_id"]
        self._append_log(f"✅ 匯入完成：{result['count']} 筆 Issue")
        self._issue_table.load_issues(self._patch_id)
        self._set_step(3)

    def _on_generate_excel_clicked(self) -> None:
        if self._patch_id is None or not self._conn:
            return
        self._generate_excel_btn.setEnabled(False)
        self._append_log("📊 產生 PATCH_LIST Excel…")
        conn       = self._conn
        patch_id   = self._patch_id
        month_str  = self._get_month_str()
        output_dir = self._get_output_dir()

        def work() -> dict:
            from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
            engine = MonthlyPatchEngine(conn)
            paths = engine.generate_patch_list(patch_id, output_dir, month_str)
            return {"paths": paths, "type": "excel"}

        threading.Thread(
            target=lambda: self._generate_done.emit(work()), daemon=True
        ).start()

    def _on_generate_html_clicked(self) -> None:
        if self._patch_id is None or not self._conn:
            return
        self._generate_html_btn.setEnabled(False)
        self._append_log("✉️ 產生客戶通知信（呼叫 Claude API）…")
        conn       = self._conn
        patch_id   = self._patch_id
        month_str  = self._get_month_str()
        output_dir = self._get_output_dir()

        def work() -> dict:
            from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
            from hcp_cms.data.repositories import PatchRepository
            from hcp_cms.services.claude_content import ClaudeContentService

            engine = MonthlyPatchEngine(conn)
            issues = PatchRepository(conn).list_issues_by_patch(patch_id)
            svc    = ClaudeContentService()
            notify_body = svc.generate_notify_body(
                [{"issue_no": i.issue_no, "description": i.description} for i in issues],
                month_str,
            )
            path = engine.generate_notify_html(
                patch_id, output_dir, month_str, notify_body=notify_body
            )
            return {"paths": [path], "type": "html"}

        threading.Thread(
            target=lambda: self._generate_done.emit(work()), daemon=True
        ).start()

    def _on_generate_result(self, result: dict) -> None:
        btn = (self._generate_excel_btn
               if result.get("type") == "excel"
               else self._generate_html_btn)
        btn.setEnabled(True)
        for path in result.get("paths", []):
            self._output_list.addItem(QListWidgetItem(path))
            self._append_log(f"✅ {path}")
        step = 5 if result.get("type") == "excel" else 6
        self._set_step(step)

    def _on_regenerate_clicked(self) -> None:
        self._output_list.clear()
        self._on_generate_excel_clicked()
```

- [ ] **Step 4: 執行測試確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_monthly_tab.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Lint**

```
.venv/Scripts/ruff.exe check src/hcp_cms/ui/patch_monthly_tab.py
```

Expected: 無錯誤

- [ ] **Step 6: Commit**

```bash
git add src/hcp_cms/ui/patch_monthly_tab.py \
        tests/unit/test_patch_monthly_tab.py
git commit -m "feat(ui): 新增 MonthlyPatchTab 每月大 PATCH 七步流程"
```

---

### Task 4: PatchView

**Files:**
- Create: `src/hcp_cms/ui/patch_view.py`
- Test: `tests/unit/test_patch_view.py`

- [ ] **Step 1: 撰寫失敗測試**

新增 `tests/unit/test_patch_view.py`：

```python
"""PatchView 單元測試。"""

from __future__ import annotations

import pytest

from hcp_cms.data.database import DatabaseManager


@pytest.fixture
def db(tmp_path):
    dm = DatabaseManager(str(tmp_path / "t.db"))
    conn = dm.initialize()
    yield conn
    conn.close()


def test_patch_view_instantiates(qtbot, db):
    from hcp_cms.ui.patch_view import PatchView
    view = PatchView(conn=db)
    qtbot.addWidget(view)
    assert view._tabs is not None


def test_patch_view_has_two_tabs(qtbot, db):
    from hcp_cms.ui.patch_view import PatchView
    view = PatchView(conn=db)
    qtbot.addWidget(view)
    assert view._tabs.count() == 2


def test_patch_view_tab_titles(qtbot, db):
    from hcp_cms.ui.patch_view import PatchView
    view = PatchView(conn=db)
    qtbot.addWidget(view)
    assert view._tabs.tabText(0) == "單次 Patch"
    assert view._tabs.tabText(1) == "每月大 PATCH"


def test_patch_view_without_conn(qtbot):
    from hcp_cms.ui.patch_view import PatchView
    view = PatchView(conn=None)
    qtbot.addWidget(view)
    assert view._tabs.count() == 2
```

- [ ] **Step 2: 執行測試確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_view.py -v
```

Expected: FAIL — `PatchView` 尚未存在

- [ ] **Step 3: 建立 PatchView**

新增 `src/hcp_cms/ui/patch_view.py`：

```python
"""PatchView — Patch 整理主頁，包含單次 Patch 與每月大 PATCH 兩個 Tab。"""

from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab
from hcp_cms.ui.patch_single_tab import SinglePatchTab
from hcp_cms.ui.theme import ThemeManager


class PatchView(QWidget):
    """Patch 整理頁面 — 頂部 Tab 切換 SinglePatchTab / MonthlyPatchTab。"""

    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        theme_mgr: ThemeManager | None = None,
    ) -> None:
        super().__init__()
        self._conn = conn
        self._theme_mgr = theme_mgr
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("📦 Patch 整理")
        layout.addWidget(title)

        self._tabs = QTabWidget()
        self._tabs.addTab(SinglePatchTab(conn=self._conn),  "單次 Patch")
        self._tabs.addTab(MonthlyPatchTab(conn=self._conn), "每月大 PATCH")
        layout.addWidget(self._tabs)
```

- [ ] **Step 4: 執行測試確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_view.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Lint**

```
.venv/Scripts/ruff.exe check src/hcp_cms/ui/patch_view.py
```

Expected: 無錯誤

- [ ] **Step 6: Commit**

```bash
git add src/hcp_cms/ui/patch_view.py tests/unit/test_patch_view.py
git commit -m "feat(ui): 新增 PatchView QTabWidget 容器"
```

---

### Task 5: MainWindow 整合

**Files:**
- Modify: `src/hcp_cms/ui/main_window.py`

- [ ] **Step 1: 撰寫失敗測試**

在 `tests/unit/test_patch_view.py` 末尾新增：

```python
def test_main_window_has_patch_nav(qtbot, db):
    from hcp_cms.ui.main_window import MainWindow
    win = MainWindow(db_connection=db)
    qtbot.addWidget(win)
    keys = [
        win._nav_list.item(i).data(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.ItemDataRole.UserRole)
        for i in range(win._nav_list.count())
    ]
    assert "patch" in keys


def test_main_window_patch_view_in_stack(qtbot, db):
    from hcp_cms.ui.main_window import MainWindow
    from hcp_cms.ui.patch_view import PatchView
    win = MainWindow(db_connection=db)
    qtbot.addWidget(win)
    assert "patch" in win._views
    assert isinstance(win._views["patch"], PatchView)
```

- [ ] **Step 2: 執行測試確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_view.py::test_main_window_has_patch_nav tests/unit/test_patch_view.py::test_main_window_patch_view_in_stack -v
```

Expected: FAIL — nav 清單中無 "patch"

- [ ] **Step 3: 修改 main_window.py — 新增 nav 項目**

在 `src/hcp_cms/ui/main_window.py` 中：

**3a. 新增 import（在現有 view imports 之後）：**

```python
from hcp_cms.ui.patch_view import PatchView
```

**3b. 在 `_setup_ui` 的 `nav_items` list 中，`("⚙️ 系統設定", "settings", "⇧S")` 之前插入：**

```python
("📦 Patch 整理", "patch", "⇧P"),
```

最終 nav_items 變為（共 10 項）：

```python
nav_items = [
    ("📊 儀表板",     "dashboard", "⇧H"),
    ("📋 案件管理",   "cases",     "⇧C"),
    ("🏢 客戶管理",   "customers", "⇧U"),
    ("📚 KMS 知識庫", "kms",       "⇧K"),
    ("📧 信件處理",   "email",     "⇧E"),
    ("🔧 Mantis 同步","mantis",    "⇧M"),
    ("📊 報表中心",   "reports",   "⇧R"),
    ("📦 Patch 整理", "patch",     "⇧P"),
    ("📏 規則設定",   "rules",     "⇧L"),
    ("⚙️ 系統設定",   "settings",  "⇧S"),
]
```

**3c. 在 `self._views` dict 中新增（`"rules"` 之前）：**

```python
"patch": PatchView(self._conn, theme_mgr=self._theme_mgr),
```

**3d. 在 `_setup_shortcuts` 的 shortcuts list 中更新索引（patch 插入後，rules/settings 索引各加 1）：**

```python
shortcuts = [
    ("Ctrl+Shift+H", 0),   # 儀表板
    ("Ctrl+Shift+C", 1),   # 案件管理
    ("Ctrl+Shift+U", 2),   # 客戶管理
    ("Ctrl+Shift+K", 3),   # KMS 知識庫
    ("Ctrl+Shift+E", 4),   # 信件處理
    ("Ctrl+Shift+M", 5),   # Mantis 同步
    ("Ctrl+Shift+R", 6),   # 報表中心
    ("Ctrl+Shift+P", 7),   # Patch 整理
    ("Ctrl+Shift+L", 8),   # 規則設定
    ("Ctrl+Shift+S", 9),   # 系統設定
]
```

**3e. 更新 `_on_nav_changed` 中的 index 硬編碼（信件處理 index 4 不變，其他依新順序更新）：**

```python
# 切到信件處理頁時自動連線（index 4 不變）
if index == 4:
    self._views["email"].try_auto_connect()
```

（此行不需修改，信件處理仍為 index 4）

**3f. 更新 `_on_navigate_to_recent_cases` 中的 index：**

```python
def _on_navigate_to_recent_cases(self) -> None:
    self._nav_list.setCurrentRow(1)  # 案件管理 = index 1（不變）
```

（此行不需修改）

- [ ] **Step 4: 執行測試確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_view.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: 執行全部測試確認無回歸**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: 所有測試 PASS

- [ ] **Step 6: Lint**

```
.venv/Scripts/ruff.exe check src/hcp_cms/ui/main_window.py
```

Expected: 無錯誤

- [ ] **Step 7: Commit**

```bash
git add src/hcp_cms/ui/main_window.py tests/unit/test_patch_view.py
git commit -m "feat(ui): MainWindow 整合 PatchView，新增「📦 Patch 整理」導覽入口"
```

---

## 完成條件

- [ ] 所有新增測試通過（`pytest tests/ -v` 全綠）
- [ ] `ruff check` 無錯誤
- [ ] `PatchView` 出現在 MainWindow 左側導覽，Ctrl+Shift+P 可切換
- [ ] `SinglePatchTab`：瀏覽資料夾 → 掃描 → 產報表 UI 流程可操作
- [ ] `MonthlyPatchTab`：選月份 → 上傳 JSON → 匯入 → 產 Excel / HTML 流程可操作
- [ ] `IssueTableWidget`：新增 / 修改 / 刪除 Issue 即時存入 DB

## 已知限制 / 後續 POC

- **拖曳列重排**：`rowsMoved` 連線已實作，需在真實 PySide6 環境確認 drag 後 sort_order 更新正確
- **Mantis 瀏覽器來源**：`SinglePatchTab` 的 Mantis 互動流程（開啟 Chrome → 等待登入 → 批次抓取）標記為 [POC]，需在有 Mantis 帳號的環境執行整合測試
- **Claude HTML 預覽**：`generate_notify_html` 產出的 HTML 目前僅存檔，可後續新增 QWebEngineView 預覽面板
