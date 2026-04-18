# 批次指定公司 + 自動整併 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在案件管理選取多筆孤兒案件（company_id 為空），批次指定公司後自動執行 ThreadTracker 將同主旨案件整併為一個根案件。

**Architecture:** Data 層新增 `list_by_company_and_subject()`；Core 層的 `CaseManager` 新增 `batch_assign_company_and_merge()`；UI 層在 `CaseView` 新增「指定公司」按鈕，開啟新的 `AssignCompanyDialog` 讓使用者選擇公司，完成後刷新列表。

**Tech Stack:** PySide6 6.10.2、SQLite（已存在）、`ThreadTracker`（已存在）

---

## 檔案清單

| 動作 | 檔案 | 說明 |
|------|------|------|
| 修改 | `src/hcp_cms/data/repositories.py` | 新增 `CaseRepository.list_by_company_and_subject()` |
| 修改 | `src/hcp_cms/core/case_manager.py` | 新增 `CaseManager.batch_assign_company_and_merge()` |
| 新增 | `src/hcp_cms/ui/assign_company_dialog.py` | 公司選擇 Dialog |
| 修改 | `src/hcp_cms/ui/case_view.py` | 新增「指定公司」按鈕與 slot |
| 修改 | `tests/unit/test_repositories.py` | 測試 `list_by_company_and_subject()` |
| 修改 | `tests/unit/test_case_manager.py` | 測試 `batch_assign_company_and_merge()` |

---

### Task 1: Data 層 — `list_by_company_and_subject()`

**Files:**
- Modify: `src/hcp_cms/data/repositories.py`
- Test: `tests/unit/test_repositories.py`

- [ ] **Step 1: 寫失敗測試**

在 `tests/unit/test_repositories.py` 找到 `class TestCaseRepository`，新增：

```python
def test_list_by_company_and_subject_returns_all_matches(self, db):
    repo = CaseRepository(db.connection)
    comp_repo = CompanyRepository(db.connection)
    comp_repo.insert(Company(company_id="C-CHI", name="群光", domain="chicony.com"))

    from hcp_cms.data.models import Case
    for i, (cid, subj) in enumerate([
        ("CS-2026-001", "HCP 緊急聯絡人資訊 如何匯出"),
        ("CS-2026-002", "RE: HCP 緊急聯絡人資訊 如何匯出"),
        ("CS-2026-003", "HCP 緊急聯絡人資訊 如何匯出"),
        ("CS-2026-004", "完全不同的主旨"),
    ]):
        repo.insert(Case(case_id=cid, subject=subj, company_id="C-CHI",
                         sent_time=f"2026/04/0{i+1} 10:00:00"))

    results = repo.list_by_company_and_subject("C-CHI", "HCP 緊急聯絡人資訊 如何匯出")
    assert len(results) == 3
    assert all(c.company_id == "C-CHI" for c in results)
    case_ids = [c.case_id for c in results]
    assert "CS-2026-001" in case_ids
    assert "CS-2026-002" in case_ids
    assert "CS-2026-003" in case_ids
    assert "CS-2026-004" not in case_ids

def test_list_by_company_and_subject_sorted_by_sent_time(self, db):
    repo = CaseRepository(db.connection)
    CompanyRepository(db.connection).insert(
        Company(company_id="C-CHI", name="群光", domain="chicony.com")
    )
    from hcp_cms.data.models import Case
    for cid, t in [("CS-2026-010", "2026/04/03 10:00:00"),
                   ("CS-2026-011", "2026/04/01 10:00:00"),
                   ("CS-2026-012", "2026/04/02 10:00:00")]:
        repo.insert(Case(case_id=cid, subject="主旨 A", company_id="C-CHI", sent_time=t))

    results = repo.list_by_company_and_subject("C-CHI", "主旨 A")
    assert [c.case_id for c in results] == ["CS-2026-011", "CS-2026-012", "CS-2026-010"]
```

- [ ] **Step 2: 執行測試確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_repositories.py -k "list_by_company_and_subject" -v
```

預期：`AttributeError: 'CaseRepository' object has no attribute 'list_by_company_and_subject'`

- [ ] **Step 3: 在 `CaseRepository` 新增方法**

在 `src/hcp_cms/data/repositories.py` 的 `find_by_company_and_subject()` 方法後面（約第 336 行）加入：

```python
def list_by_company_and_subject(self, company_id: str, clean_subject: str) -> list[Case]:
    """回傳同公司、同主旨（去前綴後）的所有案件，按 sent_time ASC 排序。"""
    rows = self._conn.execute(
        self._build_select() + " WHERE company_id = ? ORDER BY sent_time ASC, case_id ASC",
        (company_id,),
    ).fetchall()
    result = []
    for row in rows:
        case = self._row_to_case(row)
        if _clean_subject(case.subject) == clean_subject:
            result.append(case)
    return result
```

- [ ] **Step 4: 執行測試確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_repositories.py -k "list_by_company_and_subject" -v
```

預期：2 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/data/repositories.py tests/unit/test_repositories.py
git commit -m "feat(data): 新增 CaseRepository.list_by_company_and_subject() 供批次整併使用"
```

---

### Task 2: Core 層 — `batch_assign_company_and_merge()`

**Files:**
- Modify: `src/hcp_cms/core/case_manager.py`
- Test: `tests/unit/test_case_manager.py`

**整併邏輯說明：**
- 先把指定 case_ids 全部更新 company_id
- 以 `clean_subject` 分組
- 每組取 sent_time 最早（index 0）為根案件（root）
- 其餘案件若 `linked_case_id` 尚未設定，呼叫 `ThreadTracker.link_to_parent()` 連結至 root
- 回傳 `{"updated": N, "merged": M}`

- [ ] **Step 1: 寫失敗測試**

在 `tests/unit/test_case_manager.py` 的 `class TestCaseManager` 結尾新增：

```python
def test_batch_assign_company_and_merge_links_cases(self, seeded_db):
    """5 筆孤兒案件（無公司），批次指定公司後應整併為 1 根 + 4 子。"""
    CompanyRepository(seeded_db.connection).insert(
        Company(company_id="C-CHI", name="群光", domain="chicony.com")
    )
    mgr = CaseManager(seeded_db.connection)
    repo = CaseRepository(seeded_db.connection)

    # 建立 5 筆孤兒案件，主旨去前綴後相同
    case_ids = []
    subjects = [
        "HCP 緊急聯絡人資訊 如何匯出",
        "RE: HCP 緊急聯絡人資訊 如何匯出",
        "RE: HCP 緊急聯絡人資訊 如何匯出",
        "RE: HCP 緊急聯絡人資訊 如何匯出",
        "RE: HCP 緊急聯絡人資訊 如何匯出",
    ]
    for i, subj in enumerate(subjects):
        case = mgr.create_case(
            subject=subj,
            body="測試內容",
            sent_time=f"2026/04/0{i+1} 10:00:00",
        )
        case_ids.append(case.case_id)

    result = mgr.batch_assign_company_and_merge(case_ids, "C-CHI")

    assert result["updated"] == 5

    cases = [repo.get_by_id(cid) for cid in case_ids]
    assert all(c.company_id == "C-CHI" for c in cases)

    root = min(cases, key=lambda c: c.sent_time or "")
    linked = [c for c in cases if c.case_id != root.case_id]
    assert all(c.linked_case_id == root.case_id for c in linked)
    assert result["merged"] == 4

def test_batch_assign_company_and_merge_skips_already_linked(self, seeded_db):
    """已有 linked_case_id 的案件不重複連結。"""
    CompanyRepository(seeded_db.connection).insert(
        Company(company_id="C-CHI", name="群光", domain="chicony.com")
    )
    mgr = CaseManager(seeded_db.connection)
    repo = CaseRepository(seeded_db.connection)

    c1 = mgr.create_case(subject="問題 X", body="", sent_time="2026/04/01 10:00:00")
    c2 = mgr.create_case(subject="問題 X", body="", sent_time="2026/04/02 10:00:00")
    c3 = mgr.create_case(subject="問題 X", body="", sent_time="2026/04/03 10:00:00")

    # c3 已手動連結至 c2（非正常狀況，但要能容忍）
    c3_obj = repo.get_by_id(c3.case_id)
    c3_obj.linked_case_id = c2.case_id
    repo.update(c3_obj)

    result = mgr.batch_assign_company_and_merge([c1.case_id, c2.case_id, c3.case_id], "C-CHI")

    assert result["updated"] == 3
    c3_after = repo.get_by_id(c3.case_id)
    # c3 已有 linked_case_id，不應被覆蓋
    assert c3_after.linked_case_id == c2.case_id
```

- [ ] **Step 2: 執行測試確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_case_manager.py -k "batch_assign" -v
```

預期：`AttributeError: 'CaseManager' object has no attribute 'batch_assign_company_and_merge'`

- [ ] **Step 3: 實作 `batch_assign_company_and_merge()`**

在 `src/hcp_cms/core/case_manager.py` 找到 `reopen_case()` 方法前，插入：

```python
def batch_assign_company_and_merge(
    self, case_ids: list[str], company_id: str
) -> dict[str, int]:
    """批次設定 company_id 並整併同公司同主旨的案件。

    1. 更新指定案件的 company_id。
    2. 以 clean_subject 分組，每組取最早案件為根，其餘設 linked_case_id。

    Returns:
        {"updated": 成功更新 company_id 筆數, "merged": 設定 linked_case_id 筆數}
    """
    updated = 0
    for cid in case_ids:
        self._case_repo.update_company_id(cid, company_id)
        updated += 1
    self._conn.commit()

    # 按 clean_subject 分組
    groups: dict[str, list[Case]] = {}
    for cid in case_ids:
        case = self._case_repo.get_by_id(cid)
        if not case:
            continue
        key = ThreadTracker.clean_subject(case.subject).lower()
        groups.setdefault(key, []).append(case)

    merged = 0
    for clean_subj, group_cases in groups.items():
        if len(group_cases) < 2:
            continue
        # 找同公司同主旨全部案件（含非選取的舊案件）
        all_matching = self._case_repo.list_by_company_and_subject(company_id, clean_subj)
        if not all_matching:
            all_matching = sorted(group_cases, key=lambda c: (c.sent_time or "", c.case_id))

        root = all_matching[0]
        for case in all_matching[1:]:
            if case.linked_case_id:
                continue  # 已連結，跳過
            self._tracker.link_to_parent(case.case_id, root.case_id)
            merged += 1

    return {"updated": updated, "merged": merged}
```

同時在 `case_manager.py` 頂部確認已有 `from hcp_cms.data.models import Case`（通常已存在）。確認 `self._tracker` 在 `__init__` 中存在（搜尋 `ThreadTracker`）。

- [ ] **Step 4: 確認 `__init__` 中有 `self._tracker`**

在 `case_manager.py` 找到 `class CaseManager` 的 `__init__`，確認有：

```python
self._tracker = ThreadTracker(conn)
```

若無，在 `self._case_repo = CaseRepository(conn)` 後加入：

```python
from hcp_cms.core.thread_tracker import ThreadTracker
self._tracker = ThreadTracker(conn)
```

（若已存在則略過）

- [ ] **Step 5: 執行測試確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_case_manager.py -k "batch_assign" -v
```

預期：2 tests PASSED

- [ ] **Step 6: 執行完整測試確認無回歸**

```
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

預期：所有原有測試 PASSED

- [ ] **Step 7: Commit**

```bash
git add src/hcp_cms/core/case_manager.py tests/unit/test_case_manager.py
git commit -m "feat(core): 新增 CaseManager.batch_assign_company_and_merge() 批次指定公司並整併案件"
```

---

### Task 3: UI 層 — AssignCompanyDialog + CaseView 按鈕

**Files:**
- Create: `src/hcp_cms/ui/assign_company_dialog.py`
- Modify: `src/hcp_cms/ui/case_view.py`

- [ ] **Step 1: 建立 `AssignCompanyDialog`**

新增 `src/hcp_cms/ui/assign_company_dialog.py`：

```python
"""Dialog for selecting a company to assign to selected cases."""

from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from hcp_cms.data.repositories import CompanyRepository


class AssignCompanyDialog(QDialog):
    """公司選擇對話框，供批次指定公司使用。"""

    def __init__(self, conn: sqlite3.Connection, case_count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("指定公司")
        self.setMinimumWidth(340)
        self._selected_company_id: str | None = None

        companies = CompanyRepository(conn).list_all()

        layout = QVBoxLayout(self)
        form = QFormLayout()

        info = QLabel(f"已選取 <b>{case_count}</b> 筆案件，請選擇要指定的公司：")
        info.setWordWrap(True)
        layout.addWidget(info)

        self._combo = QComboBox()
        self._combo.addItem("-- 請選擇 --", None)
        for company in sorted(companies, key=lambda c: c.name):
            self._combo.addItem(f"{company.name}（{company.domain}）", company.company_id)
        form.addRow("公司：", self._combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        company_id = self._combo.currentData()
        if not company_id:
            return  # 未選擇，不關閉
        self._selected_company_id = company_id
        self.accept()

    @property
    def selected_company_id(self) -> str | None:
        return self._selected_company_id
```

- [ ] **Step 2: 在 `CaseView` 新增「指定公司」按鈕**

開啟 `src/hcp_cms/ui/case_view.py`，在 `_delete_selected_btn` 的 `addWidget` 之後（約第 119 行）加入：

```python
self._assign_company_btn = QPushButton("🏢 指定公司")
self._assign_company_btn.setToolTip("為選取的案件批次指定公司，並自動整併同主旨案件")
self._assign_company_btn.setEnabled(False)
self._assign_company_btn.clicked.connect(self._on_assign_company)
header.addWidget(self._assign_company_btn)
```

- [ ] **Step 3: 在 `_on_selection_changed` 中連動按鈕啟用狀態**

找到 `_on_selection_changed()` 方法（約第 273 行），在 `self._delete_selected_btn.setEnabled(bool(rows))` 那行之後加入：

```python
self._assign_company_btn.setEnabled(bool(rows))
```

- [ ] **Step 4: 在 `_clear_detail()` 中重設按鈕狀態**

找到 `_clear_detail()` 方法（約第 260 行），在 `self._delete_selected_btn.setEnabled(False)` 之後加入：

```python
self._assign_company_btn.setEnabled(False)
```

- [ ] **Step 5: 實作 `_on_assign_company()` slot**

在 `case_view.py` 的 `_on_delete_single_case()` 方法前插入：

```python
def _on_assign_company(self) -> None:
    """批次指定公司並整併同主旨案件。"""
    if not self._conn:
        return
    rows = self._table.selectionModel().selectedRows()
    if not rows:
        return

    case_ids = []
    for idx in rows:
        row = idx.row()
        if 0 <= row < len(self._cases):
            case_ids.append(self._cases[row].case_id)
    if not case_ids:
        return

    from hcp_cms.ui.assign_company_dialog import AssignCompanyDialog
    dlg = AssignCompanyDialog(self._conn, len(case_ids), parent=self)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return

    company_id = dlg.selected_company_id
    if not company_id:
        return

    result = CaseManager(self._conn).batch_assign_company_and_merge(case_ids, company_id)

    updated = result["updated"]
    merged = result["merged"]
    QMessageBox.information(
        self,
        "完成",
        f"已更新 {updated} 筆案件的公司。\n成功整併 {merged} 筆為同主旨根案件的子案件。",
    )
    self.refresh()
    self.cases_changed.emit()
```

- [ ] **Step 6: 啟動應用程式手動驗證**

```
.venv/Scripts/python.exe -m hcp_cms
```

驗證步驟：
1. 前往「案件管理」
2. 選取多筆相同主旨的孤兒案件（公司欄位空白）
3. 點選「🏢 指定公司」按鈕
4. 在 Dialog 選擇 chicony.com 的公司 → 按確定
5. 確認訊息顯示更新/整併數量
6. 列表刷新後，案件數量應減少（或可見 linked_case_id 已填入）

- [ ] **Step 7: Commit**

```bash
git add src/hcp_cms/ui/assign_company_dialog.py src/hcp_cms/ui/case_view.py
git commit -m "feat(ui): 新增批次指定公司並自動整併同主旨案件功能"
```

---

## Self-Review

**Spec 覆蓋度：**
- ✅ 選取多筆案件 → Task 3（按鈕 + selectionModel）
- ✅ 批次設定 company_id → Task 2（batch_assign_company_and_merge）
- ✅ ThreadTracker 整併 → Task 2（呼叫 link_to_parent）
- ✅ 結果反饋 → Task 3（QMessageBox）

**Placeholder 掃描：** 無 TBD / TODO / 省略

**型別一致性：**
- `list_by_company_and_subject(company_id: str, clean_subject: str) -> list[Case]` — Task 1 定義，Task 2 使用 ✅
- `batch_assign_company_and_merge(case_ids: list[str], company_id: str) -> dict[str, int]` — Task 2 定義，Task 3 使用 ✅
- `AssignCompanyDialog.selected_company_id: str | None` — Task 3 定義與使用 ✅
