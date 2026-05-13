# 桌面 App 加「推到 Mantis」批次按鈕 設計規格

**日期：** 2026-05-13
**狀態：** 待確認
**關聯：** [客服 Web Portal 設計規格 v2](./2026-05-12-cs-web-portal-design.md) — 本 spec 為其桌面端對等功能

## 背景與目標

客服 Web Portal v2 已實作「推到 Mantis」3 模式（單筆 / 批次 / bugnote），但目前 **僅 Web Portal 介面有此功能**，桌面 App（Jill 主要使用工具）的案件管理頁沒有。

**目標**：在桌面 App 的案件管理頁（CaseView）新增多選批次推送 Mantis 的能力，讓 Jill 一次選多筆案件後一鍵推送。

## 設計決策

- **僅做批次 + 略過已連結**：與 Web Portal v2 的批次邏輯一致（`push_cases_batch`），未連結 → 建新 ticket，已連結 → 自動略過。Jill 若要推 bugnote 仍走詳情視窗（後續可補）
- **MantisPushManager 搬到 Core 層**：由 `src/hcp_cms/web/mantis_push.py` 搬到 `src/hcp_cms/core/mantis_push.py`，符合 6 層架構 Law（業務邏輯歸 Core）
- **UI 整合點**：CaseView 工具列加「🚀 推到 Mantis」按鈕，旁邊現有篩選器 / 新增按鈕之後
- **多選模式**：確認 `QAbstractItemView.ExtendedSelection` 已啟用，支援 Ctrl+click 與 Shift+click 區間選取
- **確認對話框**：列出未連結（會建新）+ 已連結（會略過）的明細，使用者確認後才執行
- **結果顯示**：QMessageBox 顯示「成功 X / 失敗 Y / 略過 Z」，失敗筆可展開看每筆錯誤

## 架構搬移

```
變動前：
  src/hcp_cms/web/mantis_push.py   ← MantisPushManager
  src/hcp_cms/web/pages/case_*.py  ← import from hcp_cms.web.mantis_push

變動後：
  src/hcp_cms/core/mantis_push.py  ← MantisPushManager（搬過來）
  src/hcp_cms/web/pages/case_*.py  ← import from hcp_cms.core.mantis_push
  src/hcp_cms/ui/case_view.py      ← import from hcp_cms.core.mantis_push（新）
  tests/unit/test_mantis_push_manager.py  ← 既有 10+1 個測試，import 路徑更新
```

## UI 層改動

### CaseView 工具列

於現有工具列右側加 1 顆按鈕：

```
[ 搜尋... ] [ 篩選... ] [ 新增 ] ... [ 🚀 推到 Mantis ]
```

按鈕初始 disabled，listen `itemSelectionChanged` signal：
- 0 筆選取 → disabled
- ≥ 1 筆選取 → enabled，文字變「🚀 推到 Mantis (N 筆)」

### 確認對話框

點按鈕 → 自動分類選取案件：

```
┌─ 推到 Mantis 確認 ──────────────────────────┐
│                                                │
│ 將推送以下案件到 HCPSERVICE_測試 (project 218)：│
│                                                │
│ 未連結（將建立新 Mantis ticket）— 3 筆：       │
│   • C-2026-001  印表機異常       (客戶: ABC)   │
│   • C-2026-002  排程失敗         (客戶: XYZ)   │
│   • C-2026-003  錯誤 0x123       (客戶: DEF)   │
│                                                │
│ 已連結（自動略過）— 2 筆：                     │
│   • C-2026-004  → ticket #5678                 │
│   • C-2026-005  → ticket #5679                 │
│                                                │
│              [取消]  [確認推送]                │
└────────────────────────────────────────────────┘
```

### 結果對話框

執行完成後 QMessageBox：

```
✓ 成功 3 筆 / ✗ 失敗 0 筆 / ⊘ 略過 2 筆

[展開失敗詳情]  [關閉]
```

展開後顯示每筆失敗的 case_id + 錯誤訊息。

## Core 層

`MantisPushManager` 邏輯**完全不變**，只是位置從 `web/` 搬到 `core/`。介面：

```python
class MantisPushManager:
    def __init__(self, conn, client, project_id, category="General"): ...
    def push_case_as_new_ticket(self, case_id, operator_staff_id) -> tuple[bool, str]: ...
    def push_case_as_bugnote(self, case_id, operator_staff_id) -> tuple[bool, str]: ...
    def push_cases_batch(self, case_ids, operator_staff_id) -> list[tuple[str, str, str]]: ...
```

CaseView 直接使用 `push_cases_batch`，回傳值已含 success/failed/skipped 分類。

## 認證與權限

桌面 App 既有單一使用者模型（Jill），不需要 Web Portal 的 cookie 認證。`operator_staff_id` 傳入 Jill 的 staff_id（從現有 settings / config 取得）。

⚠ 若 Jill 沒設 staff_id，給預設值 `"jill"` 或從 staff 表查 `role='cs' AND name='jill'`。

## 測試策略

| 層 | 重點 |
|----|------|
| Core (`test_mantis_push_manager.py`) | 既有 11 個測試 import 路徑改 `hcp_cms.core.mantis_push`，邏輯不動 |
| UI (`test_case_view_mantis_push.py` 新) | 1-2 個 Qt smoke test：按鈕存在、disabled 狀態正確、signal 連對 |
| 整合 | 既有 web portal 整合測試（也用 core 的 MantisPushManager）通過 |

## 風險與緩解

| 風險 | 機率 | 緩解 |
|------|------|------|
| 既有 web portal 測試因 import 路徑改變而失敗 | 低 | 同時更新測試 import，全部跑一次驗證 |
| CaseView 工具列空間不足 | 低 | 必要時改用「批次操作」下拉選單，把推 Mantis 放進去 |
| 桌面 App Mantis credentials 取得方式不一致 | 低 | 重用既有 CredentialManager + keyring（Web Portal `__main__.py` 也走這個路徑）|
| 大量批次推送阻塞 UI | 中 | MVP 階段不用 QThread；改 UI 上加進度提示「處理中...」即可。每筆 SOAP < 3 秒，10 筆 < 30 秒可接受 |

## 工程量

**~1.5-2 小時，4 個 Tasks：**

1. 搬 MantisPushManager 到 core（含 import 更新 + 跑測試確認）
2. CaseView 啟用 multi-select + 加工具列按鈕（含 disabled 狀態）
3. 確認對話框（未連結 / 已連結明細分組顯示）
4. 執行批次 + 結果 QMessageBox（含展開失敗詳情）

## 後續事項

- 桌面 App 詳情視窗加「推 bugnote」按鈕（Phase 2）
- 桌面 App 詳情視窗加「建立新 Mantis ticket」按鈕（單筆，Phase 2）
- 批次推送加 QThread 避免 UI 阻塞（若實測 >30 秒才考慮）
