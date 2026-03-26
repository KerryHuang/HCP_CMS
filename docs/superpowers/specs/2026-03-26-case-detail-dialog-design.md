# 案件詳情維護對話框 — 設計文件

**日期**：2026-03-26
**狀態**：已核准

---

## 背景

使用者雙擊案件管理列表的任一列，希望開啟可編輯的詳情視窗，支援：
1. 編輯案件所有欄位
2. 新增結構化補充記錄（客戶來信 / CS 回覆 / 內部討論）
3. 管理 Mantis ticket 關聯並手動同步最新狀態

---

## 架構

### 元件圖

```
CaseView（雙擊觸發 itemDoubleClicked）
  └─ CaseDetailDialog（QDialog，QTabWidget，3 分頁）
       ├─ Tab 1：案件資訊（可編輯表單）
       ├─ Tab 2：補充記錄（CaseLog 列表 + 新增對話框）
       └─ Tab 3：Mantis 關聯（ticket 列表 + 同步）

CaseDetailManager（Core 層）
  ├─ get_case(case_id: str) → Case | None
  ├─ update_case(case: Case) → None
  ├─ add_log(log: CaseLog) → None
  ├─ list_logs(case_id: str) → list[CaseLog]
  ├─ link_mantis(case_id: str, ticket_id: str) → None
  ├─ unlink_mantis(case_id: str, ticket_id: str) → None
  └─ sync_mantis_ticket(ticket_id: str) → MantisTicket | None

CaseLogRepository（Data 層）
  ├─ insert(log: CaseLog) → None
  ├─ list_by_case(case_id: str) → list[CaseLog]
  └─ delete(log_id: str) → None
```

---

## 資料模型

### 新增：`CaseLog` dataclass（`data/models.py`）

```python
@dataclass
class CaseLog:
    log_id: str               # LOG-YYYYMMDD-NNN
    case_id: str
    direction: str            # '客戶來信' | 'CS 回覆' | '內部討論'
    content: str
    mantis_ref: str | None    # Mantis Issue 編號（可空）
    logged_by: str | None     # 記錄人
    logged_at: str            # YYYY/MM/DD HH:MM:SS
```

### 新增資料表：`case_logs`（`data/database.py`）

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

migration（`_apply_pending_migrations`）加入：
```python
"CREATE TABLE IF NOT EXISTS case_logs (...)"
```

`case_mantis` 表（已存在）處理案件與 Mantis ticket 的 N:N 關聯，無需修改。

### log_id 產生規則

格式：`LOG-YYYYMMDD-NNN`（當日流水號，從現有最大值 +1）

---

## UI 設計

### 觸發

`CaseView._table.itemDoubleClicked` → `_on_row_double_clicked(item)` → 開啟 `CaseDetailDialog`

### CaseDetailDialog

- 繼承 `QDialog`
- `__init__(conn, case_id, parent)` — 接收主連線，不自建連線
- `setWindowTitle(f"案件詳情 — {case_id}")`
- `setMinimumSize(900, 650)`
- 關閉時發出 `case_updated = Signal()` 供 `CaseView.refresh()`

---

### Tab 1：案件資訊

兩欄式 `QFormLayout`（左右各一個 `QFormLayout`，水平排列）：

**左欄**
| 標籤 | Widget | 說明 |
|------|--------|------|
| 案件編號 | `QLabel` | 唯讀 |
| 主旨 | `QLineEdit` | |
| 公司 | `QLineEdit` | company_id |
| 聯絡人 | `QLineEdit` | |
| 寄件時間 | `QLineEdit` | |
| 聯絡方式 | `QComboBox` | Email / 電話 / 現場 |
| 來源 | `QLabel` | 唯讀 |

**右欄**
| 標籤 | Widget | 說明 |
|------|--------|------|
| 狀態 | `QComboBox` | 處理中/已回覆/已完成/Closed + 自由輸入 QComboBox(editable) |
| 優先 | `QComboBox` | 高/中/低 |
| 問題類型 | `QLineEdit` | issue_type |
| 功能模組 | `QLineEdit` | error_type |
| 系統產品 | `QLineEdit` | |
| 技術負責人 | `QLineEdit` | rd_assignee |
| 處理人員 | `QLineEdit` | handler |
| 回覆時間 | `QLineEdit` | reply_time |
| 影響期間 | `QLineEdit` | |

**下方全寬（各 QTextEdit，可調高度）**
- 處理進度（progress）
- 備註（notes）
- 實際回覆（actual_reply）

**底部按鈕列**
- 「💾 儲存」→ `CaseDetailManager.update_case()`，成功後 emit `case_updated`
- 「✅ 標記已回覆」→ `CaseManager.mark_replied()`，重新載入
- 「🔒 結案」→ `CaseManager.close_case()`，重新載入

---

### Tab 2：補充記錄

**工具列**：「➕ 新增記錄」按鈕

**記錄列表**（`QTableWidget`，唯讀）：

| 欄 | 內容 |
|----|------|
| 時間 | logged_at |
| 方向 | direction |
| 記錄人 | logged_by |
| Mantis 參照 | mantis_ref |
| 內容（摘要） | content 前 60 字 |

**新增記錄對話框**（`CaseLogAddDialog`，`QDialog`）：
- 方向：`QComboBox`（客戶來信 / CS 回覆 / 內部討論）
- 內容：`QTextEdit`（必填）
- Mantis Issue 編號：`QLineEdit`（可空）
- 記錄人：`QLineEdit`（可空）
- 按鈕：儲存 / 取消

---

### Tab 3：Mantis 關聯

**工具列**：
- 「🔗 連結 Ticket」：輸入 ticket_id（`QLineEdit`）+ 「連結」按鈕
- 「🔄 同步選取」：對選取列呼叫 `sync_mantis_ticket()`
- 「🗑 取消連結」：從 `case_mantis` 刪除關聯

**Ticket 列表**（`QTableWidget`，唯讀）：

| 欄 | 內容 |
|----|------|
| 票號 | ticket_id |
| 摘要 | summary |
| 狀態 | status |
| 優先 | priority |
| 處理人 | handler |
| 預計修復 | planned_fix |
| 最後同步 | synced_at |

---

## CaseDetailManager

```python
class CaseDetailManager:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._case_repo = CaseRepository(conn)
        self._log_repo = CaseLogRepository(conn)
        self._mantis_repo = MantisRepository(conn)

    def get_case(self, case_id: str) -> Case | None: ...
    def update_case(self, case: Case) -> None: ...     # UPDATE + updated_at
    def add_log(self, log: CaseLog) -> None: ...       # INSERT
    def list_logs(self, case_id: str) -> list[CaseLog]: ...
    def link_mantis(self, case_id: str, ticket_id: str) -> None: ...
    def unlink_mantis(self, case_id: str, ticket_id: str) -> None: ...
    def sync_mantis_ticket(self, ticket_id: str) -> MantisTicket | None: ...
    # sync_mantis_ticket 呼叫 MantisClient（已有）並更新 mantis_tickets
```

---

## 異動檔案清單

| 檔案 | 動作 | 說明 |
|------|------|------|
| `src/hcp_cms/data/models.py` | 修改 | 新增 `CaseLog` dataclass |
| `src/hcp_cms/data/database.py` | 修改 | 新增 `case_logs` 資料表（migration） |
| `src/hcp_cms/data/repositories.py` | 修改 | 新增 `CaseLogRepository` |
| `src/hcp_cms/core/case_detail_manager.py` | 新增 | `CaseDetailManager` |
| `src/hcp_cms/ui/case_detail_dialog.py` | 新增 | `CaseDetailDialog`、`CaseLogAddDialog` |
| `src/hcp_cms/ui/case_view.py` | 修改 | 雙擊觸發 + `case_updated` 接收後 refresh |
| `tests/unit/test_case_detail_manager.py` | 新增 | Core 層單元測試 |

---

## 錯誤處理

| 情況 | 處理方式 |
|------|----------|
| `update_case` 資料庫失敗 | QMessageBox.critical，不關閉 dialog |
| `link_mantis` ticket_id 不在本地 | 提示「找不到 Ticket，請先同步」 |
| `sync_mantis_ticket` 網路失敗 | QMessageBox.warning，保留舊快取 |
| `content` 為空新增記錄 | 「儲存」按鈕禁用，顯示提示 |

---

## 測試策略

### `tests/unit/test_case_detail_manager.py`

- `update_case`：欄位更新、`updated_at` 自動更新
- `add_log`：`log_id` 格式、所有欄位寫入正確
- `list_logs`：依 `case_id` 篩選、按 `logged_at` 排序
- `link_mantis` / `unlink_mantis`：`case_mantis` 關聯正確增刪
- `sync_mantis_ticket`：mock MantisClient，驗證本地 `mantis_tickets` 更新
