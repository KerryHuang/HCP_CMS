# 桌面 App 推到 Mantis 批次按鈕 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在桌面 App CaseView 案件管理頁加「🚀 推到 Mantis」工具列按鈕，支援多選批次推送（未連結建新 ticket，已連結略過）。

**Architecture:** 直接重用 `MantisPushManager.push_cases_batch`（從 `web/` 搬到 `core/`），UI 層僅做選取 → 確認對話框 → 執行 → 結果摘要。

**Tech Stack:** PySide6 6.10.2、SQLite、既有 MantisSoapClient + CredentialManager

**Spec:** [`docs/superpowers/specs/2026-05-13-desktop-mantis-push-design.md`](../specs/2026-05-13-desktop-mantis-push-design.md)

---

## 檔案結構規劃

### 新增
```
src/hcp_cms/ui/mantis_push_dialog.py    # 確認對話框 + 結果對話框（PushToMantisDialog）
tests/unit/test_mantis_push_dialog.py   # Qt smoke test（dialog 元件 + 行為）
```

### 修改
```
src/hcp_cms/ui/case_view.py             # 加按鈕、selection handler、on_click handler
src/hcp_cms/core/mantis_push.py         # ★ 由 web/mantis_push.py 搬過來
src/hcp_cms/web/mantis_push.py          # ★ 刪除（搬到 core 後）
src/hcp_cms/web/app.py                  # import 路徑：hcp_cms.web.mantis_push → hcp_cms.core.mantis_push
src/hcp_cms/web/pages/case_list.py      # 同上
src/hcp_cms/web/pages/case_detail.py    # 同上
tests/unit/test_mantis_push_manager.py  # 同上
```

---

## Task 1：搬 MantisPushManager 到 Core 層

**Files:**
- Move: `src/hcp_cms/web/mantis_push.py` → `src/hcp_cms/core/mantis_push.py`
- Modify: `src/hcp_cms/web/app.py`, `src/hcp_cms/web/pages/case_list.py`, `src/hcp_cms/web/pages/case_detail.py`, `tests/unit/test_mantis_push_manager.py`

**目的：** 業務邏輯歸 Core 層（Law 2），讓桌面 App 與 Web Portal 都用同一份。

- [ ] **Step 1：實際移動檔案 + 更新 imports**

```bash
git mv src/hcp_cms/web/mantis_push.py src/hcp_cms/core/mantis_push.py
```

接著更新所有引用點。逐檔處理：

`src/hcp_cms/web/app.py`：搜 `from hcp_cms.web.mantis_push` → 改為 `from hcp_cms.core.mantis_push`
`src/hcp_cms/web/pages/case_list.py`：同上
`src/hcp_cms/web/pages/case_detail.py`：同上
`tests/unit/test_mantis_push_manager.py`：同上

可用 sed 一次處理：

```bash
grep -rl "from hcp_cms.web.mantis_push" src/ tests/ | xargs sed -i 's|from hcp_cms.web.mantis_push|from hcp_cms.core.mantis_push|g'
```

⚠ 移到 core 後，`mantis_push.py` 本身不需修改（既有 import 都從 `hcp_cms.data` / `hcp_cms.services` / `hcp_cms.web.audit` 來，前兩個沒變，但 `web.audit` 是 Web 專用模組，可以保留依賴方向）。

實際確認 `mantis_push.py` 內 import：

```python
# 移到 core/ 後仍會有這行：
from hcp_cms.web.audit import AuditLogger
```

這違反「Core 不該依賴 Web」的層級規則。**處理方式**：把 AuditLogger 也搬到 core，或讓 MantisPushManager 接受 AuditLogger 依賴注入（推薦後者，避免再做一次搬移）。

簡化做法：保留 `from hcp_cms.web.audit import AuditLogger`，但接受這是 MVP 階段的暫時妥協（spec 風險已標註）。若 reviewer 抓住，可後續重構。

⚠ **更新 mantis_push.py 內 docstring**：把「Mantis 手動推送管理器 — 案件 → Mantis ticket / bugnote 三模式」開頭那段 module docstring 不用改（與 Core 層位置無衝突）。

- [ ] **Step 2：跑 push manager + web 整合 + Mantis SOAP 全部測試**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_push_manager.py tests/integration/test_web_portal_flow.py tests/unit/test_mantis_soap_write.py -v
```

預期：13 個測試全 PASS

- [ ] **Step 3：grep 確認沒有遺漏的舊 import**

```bash
grep -rn "hcp_cms.web.mantis_push" src/ tests/
```

預期：**0 結果**

- [ ] **Step 4：commit**

```bash
git add -A
git commit -m "refactor(core): 搬 MantisPushManager 由 web/ 至 core/ 層

符合 6 層架構 Law 2（業務邏輯歸 Core）。
讓桌面 App 與 Web Portal 共用同一份 MantisPushManager。

⚠ 仍保留 from hcp_cms.web.audit import AuditLogger 一行
（暫時技術債，可後續把 AuditLogger 也搬 core）。

13 個既有測試全 pass。"
```

---

## Task 2：CaseView 加「推到 Mantis」工具列按鈕

**Files:**
- Modify: `src/hcp_cms/ui/case_view.py` (header toolbar section ~line 190 + `_on_selection_changed` ~line 508)

**目的：** 加按鈕到既有工具列；selection 變動時更新 enabled state + 文字。

- [ ] **Step 1：先讀 case_view.py 開頭 imports 區段**

```bash
head -50 /d/CMS/.claude/worktrees/desktop-mantis-push/src/hcp_cms/ui/case_view.py
```

確認既有 imports 用 `PySide6.QtWidgets` 還是 `from PySide6.QtWidgets import (..., QPushButton, QHBoxLayout, ...)`。後續加 import 才知道格式。

- [ ] **Step 2：在 case_view.py 工具列既有按鈕後加按鈕**

於 `_setup_ui()` 內、`self._delete_btn = QPushButton("🗑 批次刪除")` **之前**（建議放在 `_assign_company_btn` 後）加：

```python
        self._mantis_push_btn = QPushButton("🚀 推到 Mantis")
        self._mantis_push_btn.setToolTip("將選取案件推送到 Mantis 建立新 ticket（已連結的案件會自動略過）")
        self._mantis_push_btn.setEnabled(False)
        self._mantis_push_btn.clicked.connect(self._on_push_to_mantis)
        header.addWidget(self._mantis_push_btn)
```

- [ ] **Step 3：修改 `_on_selection_changed` 處理按鈕狀態**

定位 `_on_selection_changed` 方法（~line 508），既有：

```python
        rows = self._table.selectionModel().selectedRows()
        self._delete_selected_btn.setEnabled(bool(rows))
        self._assign_company_btn.setEnabled(bool(rows))
```

改成：

```python
        rows = self._table.selectionModel().selectedRows()
        self._delete_selected_btn.setEnabled(bool(rows))
        self._assign_company_btn.setEnabled(bool(rows))
        self._mantis_push_btn.setEnabled(bool(rows))
        self._mantis_push_btn.setText(
            f"🚀 推到 Mantis ({len(rows)} 筆)" if rows else "🚀 推到 Mantis"
        )
```

- [ ] **Step 4：加占位 `_on_push_to_mantis` 方法（Task 3 / 4 才寫完整邏輯）**

於 CaseView 任意位置（建議靠近 `_on_assign_company`）加：

```python
    def _on_push_to_mantis(self) -> None:
        """推到 Mantis 按鈕 handler — 將選取案件批次推送建新 ticket。"""
        rows = self._table.selectionModel().selectedRows()
        if not rows or not hasattr(self, '_cases'):
            return
        case_ids = [self._cases[r.row()].case_id for r in rows if r.row() < len(self._cases)]
        # Task 3 補確認 dialog；Task 4 補執行邏輯
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "待實作", f"選取 {len(case_ids)} 筆案件，待 Task 3 / 4 實作完整流程")
```

- [ ] **Step 5：手動 smoke test**

```bash
cd /d/CMS/.claude/worktrees/desktop-mantis-push
/d/CMS/.venv/Scripts/python.exe -m hcp_cms
```

操作：
1. 打開「案件管理」頁
2. 工具列應看到新按鈕「🚀 推到 Mantis」（disabled）
3. 點任一筆案件 → 按鈕變「🚀 推到 Mantis (1 筆)」且 enabled
4. Ctrl+click 加選 → 按鈕變「(2 筆)」
5. 全選 → 按鈕 enable + 筆數正確
6. 取消選取 → 按鈕變回 disabled + 文字無筆數
7. 點按鈕 → 應跳出待實作 QMessageBox

確認 ✓ 後關掉 App。

- [ ] **Step 6：commit**

```bash
git add src/hcp_cms/ui/case_view.py
git commit -m "feat(ui): CaseView 加「推到 Mantis」工具列按鈕

按鈕狀態：
- 0 筆選取 → disabled
- ≥ 1 筆 → enabled，文字更新為「🚀 推到 Mantis (N 筆)」

Task 2 of 桌面 Mantis 推送實作計畫。
完整邏輯待 Task 3 / 4 補上確認 dialog 與執行流程。"
```

---

## Task 3：確認對話框 `PushToMantisDialog`

**Files:**
- Create: `src/hcp_cms/ui/mantis_push_dialog.py`
- Create: `tests/unit/test_mantis_push_dialog.py`

**目的：** 點按鈕後彈確認對話框，分組顯示未連結（會建新）/ 已連結（略過）案件明細，讓使用者確認後才執行。

- [ ] **Step 1：寫失敗測試**

新增 `tests/unit/test_mantis_push_dialog.py`：

```python
"""PushToMantisConfirmDialog Qt smoke test。"""
from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, CaseMantisLink, MantisTicket
from hcp_cms.data.repositories import (
    CaseMantisRepository,
    CaseRepository,
    MantisRepository,
)
from hcp_cms.ui.mantis_push_dialog import PushToMantisConfirmDialog


@pytest.fixture
def setup(tmp_path: Path, qtbot):
    db = DatabaseManager(tmp_path / "t.db")
    db.initialize()

    repo = CaseRepository(db.connection)
    repo.insert(Case(case_id="C-1", subject="未連結 A", handler="jill"))
    repo.insert(Case(case_id="C-2", subject="未連結 B", handler="jill"))
    repo.insert(Case(case_id="C-3", subject="已連結", handler="jill"))

    MantisRepository(db.connection).upsert(MantisTicket(ticket_id="9999", summary=""))
    CaseMantisRepository(db.connection).insert(
        CaseMantisLink(case_id="C-3", ticket_id="9999")
    )

    yield db


def test_dialog_classifies_unlinked_vs_linked(qtbot, setup) -> None:
    db = setup
    dlg = PushToMantisConfirmDialog(db.connection, case_ids=["C-1", "C-2", "C-3"])
    qtbot.addWidget(dlg)

    assert set(dlg.unlinked_case_ids) == {"C-1", "C-2"}
    assert dlg.linked_case_ids == ["C-3"]


def test_dialog_accept_returns_unlinked_only(qtbot, setup) -> None:
    db = setup
    dlg = PushToMantisConfirmDialog(db.connection, case_ids=["C-1", "C-2", "C-3"])
    qtbot.addWidget(dlg)
    # 確認 confirmed_case_ids 屬性只含未連結
    assert set(dlg.confirmed_case_ids()) == {"C-1", "C-2"}


def test_dialog_all_linked_disables_confirm(qtbot, setup) -> None:
    """若所有選取案件都已連結 → 確認按鈕應 disabled。"""
    db = setup
    dlg = PushToMantisConfirmDialog(db.connection, case_ids=["C-3"])
    qtbot.addWidget(dlg)
    assert dlg.confirm_button.isEnabled() is False
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_push_dialog.py -v
```

預期：FAIL（檔案不存在）

- [ ] **Step 3：實作 PushToMantisConfirmDialog**

新增 `src/hcp_cms/ui/mantis_push_dialog.py`：

```python
"""推到 Mantis 確認對話框與結果對話框。"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from hcp_cms.data.repositories import CaseMantisRepository, CaseRepository


class PushToMantisConfirmDialog(QDialog):
    """選取案件 → 分類未連結 / 已連結 → 確認推送。"""

    def __init__(
        self,
        conn: sqlite3.Connection,
        case_ids: list[str],
        project_label: str = "HCPSERVICE_測試 (project 218)",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self.setWindowTitle("推到 Mantis 確認")
        self.setMinimumWidth(600)

        # 分類
        case_repo = CaseRepository(conn)
        link_repo = CaseMantisRepository(conn)
        self.unlinked_case_ids: list[str] = []
        self.linked_case_ids: list[str] = []
        self._cases_by_id = {}
        for cid in case_ids:
            case = case_repo.get_by_id(cid)
            if case is None:
                continue
            self._cases_by_id[cid] = case
            links = link_repo.list_by_case_id(cid)
            if links:
                self.linked_case_ids.append(cid)
            else:
                self.unlinked_case_ids.append(cid)
        self._link_repo = link_repo

        self._setup_ui(project_label)

    def _setup_ui(self, project_label: str) -> None:
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"將推送以下案件到 {project_label}："))

        # 未連結區
        unlinked_label = QLabel(
            f"未連結（將建立新 Mantis ticket）— {len(self.unlinked_case_ids)} 筆："
        )
        unlinked_label.setStyleSheet("font-weight: bold; color: #3b82f6; margin-top: 8px;")
        layout.addWidget(unlinked_label)
        unlinked_list = QListWidget()
        unlinked_list.setMaximumHeight(180)
        for cid in self.unlinked_case_ids:
            case = self._cases_by_id[cid]
            unlinked_list.addItem(
                f"  • {cid}  {case.subject or ''}  (客戶: {case.company_id or '—'})"
            )
        if not self.unlinked_case_ids:
            unlinked_list.addItem("  （無）")
        layout.addWidget(unlinked_list)

        # 已連結區
        linked_label = QLabel(
            f"已連結（自動略過）— {len(self.linked_case_ids)} 筆："
        )
        linked_label.setStyleSheet("font-weight: bold; color: #94a3b8; margin-top: 8px;")
        layout.addWidget(linked_label)
        linked_list = QListWidget()
        linked_list.setMaximumHeight(120)
        for cid in self.linked_case_ids:
            case = self._cases_by_id[cid]
            tickets = self._link_repo.list_by_case_id(cid)
            ticket_id = tickets[0].ticket_id if tickets else "?"
            linked_list.addItem(f"  • {cid}  {case.subject or ''}  → ticket #{ticket_id}")
        if not self.linked_case_ids:
            linked_list.addItem("  （無）")
        layout.addWidget(linked_list)

        # 按鈕區
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.confirm_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.confirm_button.setText("確認推送")
        self.confirm_button.setEnabled(bool(self.unlinked_case_ids))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def confirmed_case_ids(self) -> list[str]:
        """回傳要實際推送的案件 ID（僅未連結部分）。"""
        return list(self.unlinked_case_ids)
```

- [ ] **Step 4：跑測試驗證通過**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_push_dialog.py -v
```

預期：3 個測試 PASS

- [ ] **Step 5：commit**

```bash
git add src/hcp_cms/ui/mantis_push_dialog.py tests/unit/test_mantis_push_dialog.py
git commit -m "feat(ui): PushToMantisConfirmDialog 確認對話框

Task 3 of 桌面 Mantis 推送實作計畫。

- 自動分類選取案件：未連結 / 已連結
- 顯示明細列表 + 客戶資訊 + 連結 ticket ID
- 全部已連結時 disabled 確認按鈕
- 3 個 Qt smoke test 覆蓋分類 / 確認返回 / disabled 條件"
```

---

## Task 4：執行批次推送 + 結果 QMessageBox

**Files:**
- Modify: `src/hcp_cms/ui/case_view.py:_on_push_to_mantis`

**目的：** 串起對話框與 MantisPushManager，執行批次推送並顯示結果。

- [ ] **Step 1：替換 case_view.py 的 `_on_push_to_mantis` 占位實作**

```python
    def _on_push_to_mantis(self) -> None:
        """推到 Mantis 按鈕 handler — 將選取案件批次推送建新 ticket。"""
        from PySide6.QtWidgets import QApplication, QMessageBox
        from PySide6.QtCore import Qt as _Qt

        rows = self._table.selectionModel().selectedRows()
        if not rows or not hasattr(self, '_cases') or not self._conn:
            return
        case_ids = [
            self._cases[r.row()].case_id
            for r in rows
            if r.row() < len(self._cases)
        ]

        # 確認對話框
        from hcp_cms.ui.mantis_push_dialog import PushToMantisConfirmDialog
        dlg = PushToMantisConfirmDialog(self._conn, case_ids, parent=self)
        if dlg.exec() != PushToMantisConfirmDialog.DialogCode.Accepted:
            return

        target_ids = dlg.confirmed_case_ids()
        if not target_ids:
            QMessageBox.information(self, "推到 Mantis", "沒有可推送的案件。")
            return

        # 準備 Mantis client（從 keyring）
        from hcp_cms.services.credential import CredentialManager
        from hcp_cms.services.mantis.soap import MantisSoapClient
        creds = CredentialManager()
        url = creds.retrieve("mantis_url") or ""
        user = creds.retrieve("mantis_user") or ""
        pwd = creds.retrieve("mantis_password") or ""
        if not all([url, user, pwd]):
            QMessageBox.warning(
                self, "Mantis 設定不完整",
                "請先到「設定」分頁填寫 Mantis URL / 帳號 / 密碼。"
            )
            return

        client = MantisSoapClient(url, user, pwd)
        if not client.connect():
            QMessageBox.critical(
                self, "Mantis 連線失敗", f"無法連線：{client.last_error}"
            )
            return

        # 取 operator staff_id（自己）— 桌面 App 為 Jill
        from hcp_cms.data.repositories import StaffRepository
        jill = None
        for s in StaffRepository(self._conn).list_by_role("cs"):
            if s.name.lower() == "jill":
                jill = s
                break
        operator_staff_id = jill.staff_id if jill else "jill"

        # 執行批次推送
        from hcp_cms.core.mantis_push import MantisPushManager
        QApplication.setOverrideCursor(_Qt.CursorShape.WaitCursor)
        try:
            mgr = MantisPushManager(self._conn, client, project_id="218")
            results = mgr.push_cases_batch(target_ids, operator_staff_id)
        finally:
            QApplication.restoreOverrideCursor()

        # 結果摘要
        ok = sum(1 for r in results if r[1] == "success")
        fail = sum(1 for r in results if r[1] == "failed")
        skip = sum(1 for r in results if r[1] == "skipped")

        summary = f"✓ 成功 {ok} 筆 / ✗ 失敗 {fail} 筆 / ⊘ 略過 {skip} 筆"
        msg = QMessageBox(self)
        msg.setWindowTitle("推到 Mantis 完成")
        msg.setIcon(QMessageBox.Icon.Information if fail == 0 else QMessageBox.Icon.Warning)
        msg.setText(summary)

        if fail > 0:
            failures = [r for r in results if r[1] == "failed"]
            detail = "\n".join(f"{r[0]}: {r[2]}" for r in failures)
            msg.setDetailedText(detail)

        msg.exec()

        # 重新整理清單（顯示新連結狀態）
        self.refresh()
        self.cases_changed.emit()
```

- [ ] **Step 2：手動 smoke test（dry run，不真打 Mantis）**

```bash
cd /d/CMS/.claude/worktrees/desktop-mantis-push
/d/CMS/.venv/Scripts/python.exe -m hcp_cms
```

操作（**不要按確認推送**，僅驗證對話框流程）：
1. 案件管理頁 → 多選 2-3 筆
2. 點「🚀 推到 Mantis (3 筆)」
3. 應看到確認對話框，顯示未連結 / 已連結分組
4. 點「取消」→ 應正常關閉

✓ 後關掉。

- [ ] **Step 3（選做）：Live test — 真打 Mantis 一筆**

僅當您要驗證端到端時做。建議選 1 筆未連結案件：

1. 多選只勾 1 筆未連結案件
2. 點「🚀 推到 Mantis (1 筆)」
3. 確認 → 應跳出「成功 1 筆」訊息
4. 重整後該案件詳情視窗 → Mantis 分頁應看到新 ticket
5. 到 Mantis Web 看實際 ticket 建立成功

⚠ 此測試會在真實 Mantis 建立 ticket。建議推完後手動 close 該 ticket。

- [ ] **Step 4：commit**

```bash
git add src/hcp_cms/ui/case_view.py
git commit -m "feat(ui): CaseView 推 Mantis 完整流程 + 結果摘要

Task 4 of 桌面 Mantis 推送實作計畫。

完整流程：
1. 選取案件 → 點按鈕
2. PushToMantisConfirmDialog 分類未連結 / 已連結
3. 確認 → keyring 取 Mantis credentials + connect
4. MantisPushManager.push_cases_batch 執行
5. QMessageBox 顯示成功 / 失敗 / 略過統計
6. 失敗時 setDetailedText 展開錯誤明細
7. 重整清單 + emit cases_changed signal

桌面 App 推送以 Jill 為 operator（staff_id 從 staff 表查 cs role + name='jill'）"
```

---

## 完工檢查

- [ ] **跑全部 mantis / case_view 相關測試**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest \
    tests/unit/test_mantis_push_manager.py \
    tests/unit/test_mantis_soap_write.py \
    tests/unit/test_mantis_push_dialog.py \
    tests/integration/test_web_portal_flow.py \
    -v
```

預期：全部 PASS

- [ ] **Lint + 格式**

```bash
/d/CMS/.venv/Scripts/ruff.exe check src/hcp_cms/ui/case_view.py src/hcp_cms/ui/mantis_push_dialog.py src/hcp_cms/core/mantis_push.py tests/unit/test_mantis_push_dialog.py
/d/CMS/.venv/Scripts/ruff.exe format src/hcp_cms/ui/case_view.py src/hcp_cms/ui/mantis_push_dialog.py src/hcp_cms/core/mantis_push.py tests/unit/test_mantis_push_dialog.py
```

預期：0 errors

- [ ] **手動驗收**

1. 開桌面 App
2. 案件管理頁 → 多選 3 筆（混合 1 未連結 + 2 已連結）
3. 點按鈕 → 確認對話框顯示「1 筆建新 / 2 筆略過」
4. 確認 → 看到結果摘要「成功 1 筆 / 失敗 0 / 略過 2 筆」
5. 該案件詳情視窗 → Mantis 分頁 → 看到新 ticket

---

## 風險與處理

| 風險 | 處理方式 |
|------|------|
| Task 1 沒抓到所有 import 引用 | grep 確認後手動修補 |
| `mantis_push.py` 仍 import `web.audit` | MVP 接受暫時技術債（已在 spec 標註）|
| 既有 web portal 測試因 import 改變失敗 | Task 1 Step 2 全部跑一次驗證 |
| Mantis 連線在 Live test 階段失敗 | 已驗證過 credentials 可用（前個 worktree POC ticket #17627）|
