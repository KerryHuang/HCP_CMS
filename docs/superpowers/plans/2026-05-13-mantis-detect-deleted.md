# Mantis 同步偵測已刪除 ticket → 自動 unlink Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 同步 Mantis ticket 時偵測「ticket 已不存在」，跳對話框徵詢使用者後解除本地連結並寫 case_log 紀錄。

**Architecture:** 純函數 keyword 比對 `client.last_error` 區分「ticket 不存在」與「連線失敗」。`sync_mantis_ticket` 返回值改為 `(SyncResult, MantisTicket|None)` tuple。新增 `unlink_mantis_with_audit` 含 case_log 紀錄。UI handler 三分支處理。

**Tech Stack:** Python 3.14、PySide6、SQLite、既有 `MantisSoapClient.last_error`

**Spec:** [`docs/superpowers/specs/2026-05-13-mantis-detect-deleted-design.md`](../specs/2026-05-13-mantis-detect-deleted-design.md)

---

## 檔案結構規劃

### 新增
```
src/hcp_cms/services/mantis/error_detector.py       # is_ticket_not_found 純函數
tests/unit/test_mantis_error_detector.py            # 7 個單元測試
```

### 修改
```
src/hcp_cms/core/case_detail_manager.py             # SyncResult enum
                                                    # sync_mantis_ticket 改 tuple 返回
                                                    # 新增 unlink_mantis_with_audit
src/hcp_cms/ui/case_detail_dialog.py:681-692        # _on_sync_mantis 改寫處理三分支
tests/unit/test_case_detail_manager_sync.py         # 既有 test 升級 tuple 返回 + 加 4 個新測試
```

---

## Task 1：`is_ticket_not_found` 純函數 + 7 個單元測試

**Files:**
- Create: `src/hcp_cms/services/mantis/error_detector.py`
- Create: `tests/unit/test_mantis_error_detector.py`

**目的：** 純函數 keyword 比對，將 SOAP `last_error` 字串分類為「ticket 不存在」與「其他錯誤」。

- [ ] **Step 1：寫失敗測試**

新增 `tests/unit/test_mantis_error_detector.py`：

```python
"""is_ticket_not_found 純函數單元測試。"""
from hcp_cms.services.mantis.error_detector import is_ticket_not_found


def test_detects_not_found_keyword_english() -> None:
    assert is_ticket_not_found("SOAP 錯誤：Issue #1234 not found") is True


def test_detects_does_not_exist_keyword() -> None:
    assert is_ticket_not_found("SOAP 錯誤：Issue does not exist") is True


def test_detects_chinese_not_exist() -> None:
    assert is_ticket_not_found("SOAP 錯誤：Issue 不存在") is True


def test_ignores_connection_error() -> None:
    assert is_ticket_not_found("連線失敗：HTTPSConnectionPool...") is False


def test_ignores_timeout_error() -> None:
    assert is_ticket_not_found("連線逾時（30 秒）") is False


def test_handles_none() -> None:
    assert is_ticket_not_found(None) is False


def test_handles_empty_string() -> None:
    assert is_ticket_not_found("") is False
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
cd /d/CMS/.claude/worktrees/mantis-detect-deleted
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_error_detector.py -v
```

預期：FAIL（module 不存在）

- [ ] **Step 3：實作**

新增 `src/hcp_cms/services/mantis/error_detector.py`：

```python
"""Mantis SOAP 錯誤訊息分類工具。"""
from __future__ import annotations

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

- [ ] **Step 4：跑測試驗證通過**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_error_detector.py -v
```

預期：7 個測試 PASS

- [ ] **Step 5：Lint**

```bash
/d/CMS/.venv/Scripts/ruff.exe check src/hcp_cms/services/mantis/error_detector.py tests/unit/test_mantis_error_detector.py
```

預期：All checks passed!

- [ ] **Step 6：Commit**

```bash
git add src/hcp_cms/services/mantis/error_detector.py tests/unit/test_mantis_error_detector.py
git commit -m "feat(mantis): is_ticket_not_found 偵測 ticket 已刪錯誤

Task 1 of Mantis 同步偵測已刪除 ticket 實作計畫。

純函數 keyword 比對 SOAP last_error 字串。
keyword: 'not found' / 'does not exist' / '不存在'。
跨 Mantis 版本可能誤判 — MVP 階段接受。

7 個單元測試覆蓋各 keyword + 連線錯誤 + None / empty。"
```

---

## Task 2：SyncResult enum + sync_mantis_ticket 改 tuple 返回 + unlink_mantis_with_audit

**Files:**
- Modify: `src/hcp_cms/core/case_detail_manager.py`（加 SyncResult enum、改 sync_mantis_ticket 返回、加 unlink_mantis_with_audit）
- Modify: `tests/unit/test_case_detail_manager_sync.py`（既有 test 升級 + 加 4 個新測試）

**目的：** Manager 層三態返回，UI 才能精確分支。新方法 unlink_mantis_with_audit 解除連結同時寫 case_log。

- [ ] **Step 1：先讀既有 test_case_detail_manager_sync.py，了解測試格式**

```bash
cat /d/CMS/.claude/worktrees/mantis-detect-deleted/tests/unit/test_case_detail_manager_sync.py
```

確認既有 fixture 與測試結構，避免新測試模式不一致。

- [ ] **Step 2：升級既有 1 個測試 + 加 5 個新測試**

修改 `tests/unit/test_case_detail_manager_sync.py`：

於 imports 區補：

```python
from hcp_cms.core.case_detail_manager import CaseDetailManager, SyncResult
from hcp_cms.data.repositories import CaseMantisRepository, CaseLogRepository
from hcp_cms.data.models import Case, CaseMantisLink, MantisTicket, Company
```

既有 1 個 success 測試的 assertion 改為 unpack tuple：

讀檔內容找到 `mgr.sync_mantis_ticket(...)` 那行，把 `result = ...` 改為 `result, _ticket = ...`，並補 `assert result == SyncResult.SUCCESS`。

於檔末加 4 個新測試：

```python
# ============= SyncResult 三態 =============


def test_sync_returns_not_found_when_last_error_says_not_found(
    db_with_case_and_ticket,
):
    """client.get_issue 回 None 且 last_error 含 'not found' → NOT_FOUND。"""
    db, _case, _link = db_with_case_and_ticket
    mgr = CaseDetailManager(db.connection)
    client = MagicMock()
    client.get_issue.return_value = None
    client.last_error = "SOAP 錯誤：Issue #9999 not found"

    result, ticket = mgr.sync_mantis_ticket("9999", client=client)

    assert result == SyncResult.NOT_FOUND
    assert ticket is None


def test_sync_returns_error_when_connection_fails(db_with_case_and_ticket):
    """client.get_issue 回 None 且 last_error 為連線錯誤 → ERROR。"""
    db, _case, _link = db_with_case_and_ticket
    mgr = CaseDetailManager(db.connection)
    client = MagicMock()
    client.get_issue.return_value = None
    client.last_error = "連線失敗：HTTPSConnectionPool..."

    result, ticket = mgr.sync_mantis_ticket("9999", client=client)

    assert result == SyncResult.ERROR
    assert ticket is None


def test_sync_returns_error_when_client_is_none(db_with_case_and_ticket):
    """client=None → ERROR。"""
    db, _case, _link = db_with_case_and_ticket
    mgr = CaseDetailManager(db.connection)
    result, ticket = mgr.sync_mantis_ticket("9999", client=None)
    assert result == SyncResult.ERROR
    assert ticket is None


# ============= unlink_mantis_with_audit =============


def test_unlink_mantis_with_audit_removes_link_and_logs(
    db_with_case_and_ticket,
):
    """解除連結 + case_log 寫入 reason。"""
    db, case, _link = db_with_case_and_ticket
    mgr = CaseDetailManager(db.connection)

    # 先確認連結存在
    links_before = CaseMantisRepository(db.connection).get_tickets_for_case(case.case_id)
    assert "9999" in links_before

    mgr.unlink_mantis_with_audit(
        case.case_id, "9999",
        reason="Mantis 找不到此 ticket（同步時偵測）",
    )

    # 連結移除
    links_after = CaseMantisRepository(db.connection).get_tickets_for_case(case.case_id)
    assert "9999" not in links_after

    # case_log 多一筆
    logs = CaseLogRepository(db.connection).list_by_case(case.case_id)
    sync_logs = [l for l in logs if "Mantis" in l.content and "找不到" in l.content]
    assert len(sync_logs) == 1
    assert sync_logs[0].mantis_ref == "9999"
    assert sync_logs[0].logged_by == "system"
```

⚠ Step 2 假設 fixture `db_with_case_and_ticket` 已存在於既有測試檔。**請先讀 Step 1 內容確認 fixture 名稱**。若名稱不同（如 `setup`、`db`），調整新測試的參數名 + 解構方式。

⚠ 若既有測試檔**沒有 fixture 提供「case + 連結 ticket」的設置**，需要新增：

```python
@pytest.fixture
def db_with_case_and_ticket(tmp_path):
    """提供：DB + 一個 Case（C-1） + 連結到 ticket #9999。"""
    db = DatabaseManager(tmp_path / "t.db")
    db.initialize()
    # 案件
    case = Case(
        case_id="C-1", subject="測試案件",
        company_id=None, sent_time="2026/05/04 10:00:00",
    )
    CaseRepository(db.connection).insert(case)
    # mantis_tickets（FK 依賴）
    MantisRepository(db.connection).upsert(MantisTicket(ticket_id="9999", summary=""))
    # 連結
    link = CaseMantisLink(case_id="C-1", ticket_id="9999")
    CaseMantisRepository(db.connection).insert(link)
    yield db, case, link
    db.close()
```

並補對應 import：`Company` 可移除（沒用到）；`CaseRepository`、`MantisRepository`、`CaseMantisLink` 確保都 import。

- [ ] **Step 3：跑測試驗證失敗**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_case_detail_manager_sync.py -v 2>&1 | tail -20
```

預期：所有測試 FAIL（SyncResult 不存在 / sync_mantis_ticket 返回單值不是 tuple / unlink_mantis_with_audit 不存在）

- [ ] **Step 4：實作 case_detail_manager.py**

開檔 `src/hcp_cms/core/case_detail_manager.py`。

**(4a) 加 enum：** 於檔頂 imports 後、`class CaseDetailManager` 前加：

```python
from enum import Enum


class SyncResult(Enum):
    """sync_mantis_ticket 三態返回。"""
    SUCCESS = "success"
    NOT_FOUND = "not_found"  # Mantis 找不到此 ticket（可能已被刪除）
    ERROR = "error"          # 連線失敗 / SOAP 一般錯誤 / client 未提供
```

**(4b) 改 sync_mantis_ticket 簽名 + 返回 tuple：**

讀既有 method body（約 line 115-157），把整段方法替換為：

```python
    def sync_mantis_ticket(
        self,
        ticket_id: str,
        client: MantisClient | None = None,
    ) -> tuple[SyncResult, MantisTicket | None]:
        """呼叫 MantisClient 同步單一 ticket，更新本地快取。

        Returns:
            (SUCCESS, ticket) — 成功
            (NOT_FOUND, None) — Mantis 找不到此 ticket（可能已被刪除）
            (ERROR, None) — 連線失敗 / 其他錯誤 / client=None
        """
        from hcp_cms.services.mantis.error_detector import is_ticket_not_found

        if client is None:
            return SyncResult.ERROR, None
        issue = client.get_issue(ticket_id)
        if issue is None:
            last_err = getattr(client, "last_error", "")
            if is_ticket_not_found(last_err):
                return SyncResult.NOT_FOUND, None
            return SyncResult.ERROR, None

        synced_at = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

        ticket = MantisTicket(
            ticket_id=issue.id,
            summary=issue.summary,
            status=issue.status,
            priority=issue.priority,
            handler=issue.handler,
            severity=issue.severity,
            reporter=issue.reporter,
            created_time=issue.date_submitted,
            planned_fix=issue.target_version,
            actual_fix=issue.fixed_in_version,
            description=issue.description,
            last_updated=issue.last_updated,
            notes_json=json.dumps(
                [
                    {
                        "reporter": n.reporter,
                        "text": n.text,
                        "date_submitted": n.date_submitted,
                    }
                    for n in issue.notes_list
                ],
                ensure_ascii=False,
            ),
            notes_count=issue.notes_count,
            synced_at=synced_at,
        )
        self._mantis_repo.upsert(ticket)
        return SyncResult.SUCCESS, self._mantis_repo.get_by_id(ticket_id)
```

**(4c) 加 unlink_mantis_with_audit 方法：**

於既有 `unlink_mantis` 之後加：

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
            log_id=self._log_repo.next_log_id(),
            case_id=case_id,
            direction="內部討論",
            content=f"自動解除 Mantis 連結 #{ticket_id}：{reason}",
            mantis_ref=ticket_id,
            logged_by="system",
            logged_at=now,
        )
        self._log_repo.insert(log)
```

- [ ] **Step 5：跑測試驗證通過**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_case_detail_manager_sync.py -v 2>&1 | tail -15
```

預期：所有測試 PASS（既有 1 + 新 5 = 6 個）

- [ ] **Step 6：跑既有 CaseDetailManager 測試確認無回歸**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_case_detail_manager.py -v 2>&1 | tail -10
```

預期：全部 PASS（既有測試應該不直接呼叫 sync_mantis_ticket，只測其他方法）

- [ ] **Step 7：Lint**

```bash
/d/CMS/.venv/Scripts/ruff.exe check src/hcp_cms/core/case_detail_manager.py tests/unit/test_case_detail_manager_sync.py
```

預期：All checks passed!

- [ ] **Step 8：Commit**

```bash
git add src/hcp_cms/core/case_detail_manager.py tests/unit/test_case_detail_manager_sync.py
git commit -m "feat(core): SyncResult enum + sync_mantis_ticket 三態返回 + unlink_with_audit

Task 2 of Mantis 同步偵測已刪除 ticket 實作計畫。

- SyncResult enum: SUCCESS / NOT_FOUND / ERROR
- sync_mantis_ticket 返回 tuple[SyncResult, MantisTicket|None]
  - 偵測 last_error 含 'not found' / 'does not exist' / '不存在' → NOT_FOUND
  - 其他 None → ERROR
  - 成功 → SUCCESS + ticket
- unlink_mantis_with_audit: 解除連結 + case_log 寫 reason
  - 既有 unlink_mantis 維持原行為（手動取消無紀錄）

既有 success test 升級 tuple unpack + 加 4 個新測試"
```

---

## Task 3：UI 整合 + 手動 smoke test

**Files:**
- Modify: `src/hcp_cms/ui/case_detail_dialog.py:681-692`（`_on_sync_mantis` 改寫）

**目的：** UI 處理 SyncResult 三分支，NOT_FOUND 時跳確認對話框。

- [ ] **Step 1：替換 `_on_sync_mantis` method**

讀 `src/hcp_cms/ui/case_detail_dialog.py` 約 line 681-692，整段替換為：

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

- [ ] **Step 2：Import smoke test**

```bash
cd /d/CMS/.claude/worktrees/mantis-detect-deleted
PYTHONPATH=src /d/CMS/.venv/Scripts/python.exe -c "
from hcp_cms.ui.case_detail_dialog import CaseDetailDialog
import inspect
src = inspect.getsource(CaseDetailDialog._on_sync_mantis)
required = [
    'SyncResult.SUCCESS',
    'SyncResult.NOT_FOUND',
    'unlink_mantis_with_audit',
    'QMessageBox.question',
    '已不存在',
]
missing = [k for k in required if k not in src]
assert not missing, f'MISSING: {missing}'
print('All required pieces present')
"
```

預期輸出：`All required pieces present`

- [ ] **Step 3：Lint**

```bash
/d/CMS/.venv/Scripts/ruff.exe check src/hcp_cms/ui/case_detail_dialog.py
```

預期：All checks passed!

- [ ] **Step 4：跑既有 case_detail_dialog 相關測試**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_case_detail_dialog.py -v 2>&1 | tail -10
```

⚠ 既有 UI 測試可能 mock 過 `sync_mantis_ticket` 返回單值。若有 test 失敗，找到對應 mock 改成回 tuple `(SyncResult.SUCCESS, ticket)` 或 `(SyncResult.ERROR, None)`。

```bash
grep -n "sync_mantis_ticket" tests/unit/test_case_detail_dialog.py
```

逐個檢查 mock setup，調整。

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/ui/case_detail_dialog.py tests/unit/test_case_detail_dialog.py
git commit -m "feat(ui): _on_sync_mantis 處理 NOT_FOUND 三分支

Task 3 of Mantis 同步偵測已刪除 ticket 實作計畫。

UI 互動：
- SUCCESS → 重新整理表格
- NOT_FOUND → QMessageBox.question 徵詢「是否解除連結？」
  - Yes → unlink_mantis_with_audit + 顯示「已解除連結」
  - No → 保留連結
- ERROR → 顯示「同步失敗」（既有行為）

既有 test_case_detail_dialog mock 同步升級 tuple 返回。"
```

- [ ] **Step 6（選做）：手動 Live test**

需要實際開啟桌面 App 測試：

1. 找一個本地連結但 Mantis 端不存在的 ticket（可故意連結到不存在的 ID）：
   - 在桌面 App 詳情視窗 → Mantis 分頁 → 輸入 ticket id `99999999` → 按「🔗 連結」
2. 選取該 ticket → 按「🔄 同步選取」
3. 預期：彈出對話框「Mantis ticket #99999999 已不存在...」
4. 點「是」→ 連結消失 + case_log 多一筆「自動解除 Mantis 連結 #99999999」

⚠ 此 step 為選做。Task 1/2 既有測試已充分驗證邏輯。

---

## 完工檢查

- [ ] **跑全部相關測試**

```bash
cd /d/CMS/.claude/worktrees/mantis-detect-deleted
/d/CMS/.venv/Scripts/python.exe -m pytest \
  tests/unit/test_mantis_error_detector.py \
  tests/unit/test_case_detail_manager_sync.py \
  tests/unit/test_case_detail_manager.py \
  tests/unit/test_mantis_push_manager.py \
  tests/unit/test_mantis_soap_write.py \
  -q 2>&1 | tail -5
```

預期：全部 PASS

- [ ] **Lint**

```bash
/d/CMS/.venv/Scripts/ruff.exe check \
  src/hcp_cms/services/mantis/error_detector.py \
  src/hcp_cms/core/case_detail_manager.py \
  src/hcp_cms/ui/case_detail_dialog.py \
  tests/unit/test_mantis_error_detector.py \
  tests/unit/test_case_detail_manager_sync.py
```

預期：All checks passed!

---

## 風險與處理

| 風險 | 處理方式 |
|------|------|
| 既有 fixture `db_with_case_and_ticket` 名稱不同 | Step 1 先 cat 既有檔，新測試對齊既有命名 |
| 既有 test_case_detail_dialog mock 改變 sync_mantis_ticket 返回會破測試 | Step 4 grep 找到 mock，調整為 tuple 返回 |
| Live test 連結到不存在 ticket 時可能因 link FK 限制失敗 | mantis_tickets 表的 FK 預先 upsert，如同 push manager test 的 `_link_with_ticket` helper |
| `keyword "Issue" 太通用` 不在 _NOT_FOUND_KEYWORDS 是故意的 | 避免「Issue field required」等也誤判，保守只用 "not found" / "does not exist" / "不存在" 三組 |
