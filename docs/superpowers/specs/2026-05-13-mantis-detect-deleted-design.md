# Mantis 同步偵測已刪除 ticket → 自動 unlink 設計規格

**日期：** 2026-05-13
**狀態：** 待確認

## 背景與目標

目前 HCP CMS 已連結 Mantis ticket 後，若該 ticket 在 Mantis 端被刪除：
- `CaseDetailManager.sync_mantis_ticket()` 呼叫 `client.get_issue()` 回 None
- UI 顯示「同步失敗，無法連線至 Mantis」— 與「真的連線失敗」訊息相同，使用者無法區分

Jill 反映應該明確偵測「ticket 已被刪」並徵詢是否解除連結。

**目標**：使用者點「🔄 同步選取」時，若 Mantis 回應為「ticket 不存在」（而非連線失敗），跳確認對話框讓使用者決定是否解除本地連結。

## 設計決策

- **觸發點**：**僅在「🔄 同步選取」按鈕點擊時偵測**（user 選 α）。不做開啟視窗時 / 排程背景檢查
- **偵測方式**：**字串比對 last_error**（user 選 a）。掃描 `not found / does not exist / 不存在` 三個 keyword
- **確認流程**：明確徵詢，不偷偷自動 unlink
- **解除連結時加 case_log**：留下「為何 unlink」紀錄，方便事後追溯
- **既有「🗑 取消連結」按鈕不變**：手動 unlink 維持原行為（無 audit）。新邏輯只走「同步偵測」這條路徑加紀錄
- **不改動 MantisClient ABC**：避免大範圍變更，純函數做 keyword 比對即可。Phase 2 若發現 keyword 偵測誤判過多再升級為 enum 返回

## Architecture

```
使用者點 「🔄 同步選取」
    ↓
CaseDetailDialog._on_sync_mantis()
    ↓
CaseDetailManager.sync_mantis_ticket() ──── tuple(SyncResult, MantisTicket|None)
    ↓                                            ↓
    │                                       SUCCESS → 既有同步流程
client.get_issue() 回 None                 NOT_FOUND → 觸發解除確認
    ↓                                       ERROR    → 顯示「同步失敗」
is_ticket_not_found(client.last_error)
    True → NOT_FOUND
    False → ERROR
```

## 元件分解

### 1. 新工具函數 `is_ticket_not_found`

**位置：** `src/hcp_cms/services/mantis/error_detector.py`（services 層，新檔）

```python
"""Mantis SOAP 錯誤訊息分類工具。"""

_NOT_FOUND_KEYWORDS = (
    "not found",        # "Issue #1234 not found"
    "does not exist",   # "Issue does not exist"
    "不存在",            # 中文 fault（少數版本）
)


def is_ticket_not_found(last_error: str | None) -> bool:
    """根據 SOAP last_error 字串判斷是否為 'ticket 不存在' 錯誤。

    用於區分「Mantis 連線失敗 / SOAP 一般錯誤」與「ticket 被刪除」兩種失敗情境。
    純字串比對，跨 Mantis 版本可能誤判 — Phase 2 可升級為 enum 返回。
    """
    if not last_error:
        return False
    lower = last_error.lower()
    return any(kw.lower() in lower for kw in _NOT_FOUND_KEYWORDS)
```

⚠ 純函數，無副作用，易測試。

### 2. `SyncResult` enum + `sync_mantis_ticket` 改返回值

**位置：** `src/hcp_cms/core/case_detail_manager.py`（修改既有）

```python
from enum import Enum


class SyncResult(Enum):
    """sync_mantis_ticket 三態返回。"""
    SUCCESS = "success"
    NOT_FOUND = "not_found"  # Mantis 找不到此 ticket（可能已被刪除）
    ERROR = "error"          # 連線失敗 / SOAP 一般錯誤 / client 未提供
```

`sync_mantis_ticket` 簽名變更：

```python
def sync_mantis_ticket(
    self,
    ticket_id: str,
    client: MantisClient | None = None,
) -> tuple[SyncResult, MantisTicket | None]:
    """呼叫 MantisClient 同步單一 ticket，更新本地快取。

    Returns:
        (SUCCESS, ticket) — 成功
        (NOT_FOUND, None) — Mantis 找不到此 ticket
        (ERROR, None) — 連線失敗或其他錯誤
    """
    if client is None:
        return SyncResult.ERROR, None
    issue = client.get_issue(ticket_id)
    if issue is None:
        last_err = getattr(client, "last_error", "")
        if is_ticket_not_found(last_err):
            return SyncResult.NOT_FOUND, None
        return SyncResult.ERROR, None
    # ... 既有 SUCCESS 流程（解析 issue、寫 mantis_tickets、回 MantisTicket）...
    return SyncResult.SUCCESS, ticket
```

⚠ **既有 callers 都返回 tuple**，需要修改 1 處（CaseDetailDialog 的 `_on_sync_mantis`，本 spec Section 4）。

### 3. `unlink_mantis_with_audit` 新方法

**位置：** `src/hcp_cms/core/case_detail_manager.py`（新增）

```python
def unlink_mantis_with_audit(
    self,
    case_id: str,
    ticket_id: str,
    reason: str,
) -> None:
    """解除 Mantis 連結並在 case_logs 留下紀錄。

    與既有 unlink_mantis 不同：本方法寫入 case_log 記錄 reason，
    用於同步偵測自動 unlink 等需要追溯的情境。
    """
    self._case_mantis_repo.unlink(case_id, ticket_id)
    now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    log = CaseLog(
        log_id=self._case_log_repo.next_log_id(),
        case_id=case_id,
        direction="內部討論",
        content=f"自動解除 Mantis 連結 #{ticket_id}：{reason}",
        mantis_ref=ticket_id,
        logged_by="system",
        logged_at=now,
    )
    self._case_log_repo.insert(log)
```

⚠ 不取代既有 `unlink_mantis`。手動「🗑 取消連結」維持原行為（即時生效、無 log）。新方法只給「同步偵測自動 unlink」使用。

### 4. UI 互動 `_on_sync_mantis` 改寫

**位置：** `src/hcp_cms/ui/case_detail_dialog.py:681-692`（修改既有）

```python
def _on_sync_mantis(self) -> None:
    from hcp_cms.core.case_detail_manager import SyncResult

    rows = self._mantis_table.selectionModel().selectedRows()
    if not rows:
        QMessageBox.information(self, "提示", "請先選取要同步的 Ticket。")
        return
    ticket_id = self._mantis_table.item(rows[0].row(), 0).text()
    client = self._build_mantis_client()
    result, _ticket = self._manager.sync_mantis_ticket(ticket_id, client=client)

    if result == SyncResult.SUCCESS:
        self._refresh_mantis_table()
    elif result == SyncResult.NOT_FOUND:
        reply = QMessageBox.question(
            self,
            "Ticket 已不存在",
            f"Mantis ticket #{ticket_id} 已不存在（可能已被刪除）。\n\n"
            "是否要從本案件解除連結？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._manager.unlink_mantis_with_audit(
                self._case_id, ticket_id,
                reason="Mantis 找不到此 ticket（同步時偵測）",
            )
            self._refresh_mantis_table()
            QMessageBox.information(
                self, "已解除連結", f"Ticket #{ticket_id} 連結已移除。"
            )
    else:  # SyncResult.ERROR
        QMessageBox.warning(self, "同步失敗", "無法連線至 Mantis，或 Mantis 設定未完成。")
```

## 測試策略

### `tests/unit/test_mantis_error_detector.py`（新檔）

| 測試 | 覆蓋 |
|------|------|
| `test_detects_not_found_keyword_english` | `"Issue #1234 not found"` |
| `test_detects_does_not_exist_keyword` | `"Issue does not exist"` |
| `test_detects_chinese_not_exist` | `"...不存在..."` |
| `test_ignores_connection_error` | `"連線失敗：..."` → False |
| `test_ignores_timeout_error` | `"連線逾時"` → False |
| `test_handles_none` | None → False |
| `test_handles_empty_string` | `""` → False |

### `tests/unit/test_case_detail_manager_sync.py`（新檔 / 加到既有）

| 測試 | 覆蓋 |
|------|------|
| `test_sync_returns_success_when_issue_found` | 既有 SUCCESS 路徑回 tuple |
| `test_sync_returns_not_found_when_last_error_says_not_found` | mock client get_issue 回 None + last_error 含 "not found" |
| `test_sync_returns_error_when_connection_fails` | mock client get_issue 回 None + last_error 為連線失敗訊息 |
| `test_sync_returns_error_when_client_is_none` | 不傳 client → ERROR |
| `test_unlink_mantis_with_audit_removes_link_and_logs` | 驗證 case_mantis 移除 + case_log 寫入 reason |

### UI 層（手動 smoke test）

PySide6 UI 測試成本高（既有測試多用 monkeypatch）。本次新邏輯純走 manager 層，UI 改動小（替換 sync handler 內 5 行邏輯），靠手動測試：

1. 詳情視窗連結一個假 ticket（如 `99999999`）
2. 點「🔄 同步選取」→ 應跳「Ticket 已不存在」對話框
3. 點「是」→ 連結移除 + case_log 多一筆紀錄
4. 點「否」→ 連結保留

## 風險與緩解

| 風險 | 緩解 |
|------|------|
| 不同 Mantis 版本 fault 訊息不同 → keyword 沒命中 | MVP 用 3 個 keyword 覆蓋常見格式；Live 測試發現新訊息再擴充 _NOT_FOUND_KEYWORDS 即可 |
| 誤判：某個 SOAP 錯誤訊息恰好含 "not found"（如 "field not found"）→ 誤刪連結 | 確認對話框是 user-driven，不會自動刪 |
| 既有 sync_mantis_ticket 改返回值 → 其他 caller 壞掉 | grep 全 repo 確認只有 case_detail_dialog 一處呼叫，本 spec 同步修改 |
| `unlink_mantis_with_audit` 與既有 `unlink_mantis` 容易混淆 | 在兩個方法 docstring 註明差異；未來考慮合併為單一方法接 optional reason |

## 工程量

**~1-1.5 小時**，3 個 Tasks：

1. `is_ticket_not_found` 純函數 + 7 個單元測試（30 分鐘）
2. `SyncResult` enum + sync_mantis_ticket 改返回值 + `unlink_mantis_with_audit` + 5 個 manager 測試（30 分鐘）
3. UI `_on_sync_mantis` 改寫 + 手動 smoke test + commit（30 分鐘）

## 後續事項（不在本次範圍）

- 把 keyword 偵測升級為 `MantisClient.get_issue()` 返回 enum，徹底擺脫字串比對
- 排程定期掃所有 case_mantis link 偵測孤兒（user 之前選 α 拒絕，但若 Mantis 端常清資料可能需要）
- 推到 Mantis 後 ticket 被立刻刪除的 race condition 處理（極端少見）
- Web Portal 端對應 UI（目前 Web Portal 也有 sync，需同樣加偵測）
