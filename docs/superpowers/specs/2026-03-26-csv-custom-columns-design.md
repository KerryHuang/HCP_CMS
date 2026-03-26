# CSV 匯入精靈自訂欄位設計文件

**日期**：2026-03-26
**狀態**：已核准
**作者**：Jill / Claude

---

## 需求摘要

CSV 匯入精靈步驟 2（欄位對應）遇到資料庫無對應的 CSV 欄位時，允許使用者勾選「自動建立新欄位」，並輸入中文標籤。新欄位建立後，在以下所有 UI 呈現：

- 案件管理列表（CaseView）
- 案件詳情 Dialog（CaseDetailDialog Tab 1）
- 追蹤表報表（ReportEngine）
- CSV 匯入精靈右側下拉同時顯示中文標籤

不在此次範圍：欄位刪除、欄位改名、FTS5 搜尋整合、月報整合、`visible_in_list` 管理介面。

---

## 架構方案

採用 **ALTER TABLE + 中介資料表**：

1. `cs_cases` 直接 `ALTER TABLE ADD COLUMN cx_N TEXT`
2. `custom_columns` 中介資料表保存中文標籤與顯示設定
3. `Case` dataclass 加 `extra_fields: dict[str, str | None]`
4. 所有讀寫透過 Repository 層，Core 層封裝 DDL 操作，UI 層不直接存取 Repository

---

## 資料層設計

### 新表：`custom_columns`（加入 `_SCHEMA_SQL`）

```sql
CREATE TABLE IF NOT EXISTS custom_columns (
    col_key          TEXT PRIMARY KEY,   -- cx_1, cx_2, cx_3…
    col_label        TEXT NOT NULL,      -- 使用者輸入的中文標籤
    col_order        INTEGER NOT NULL,   -- 建立序號（= cx_ 後的數字）
    visible_in_list  INTEGER NOT NULL DEFAULT 1
);
```

`col_key` 命名規則：`cx_` + 下一個可用整數（從 `COALESCE(MAX(col_order), 0) + 1` 計算）。
例：第一個自訂欄 = `cx_1`，第二個 = `cx_2`。純整數序號完全避免中文 / 特殊字元轉換問題；`col_label` 儲存人類可讀中文標籤。

### Model：`CustomColumn`（加入 `models.py`，置於 `CaseLog` 之後）

```python
@dataclass
class CustomColumn:
    col_key: str           # cx_1, cx_2…
    col_label: str         # 中文顯示名稱
    col_order: int         # 顯示順序
    visible_in_list: bool = True
```

### `Case` dataclass 修改

```python
extra_fields: dict[str, str | None] = field(default_factory=dict)
```

加在最後一個欄位之後。`field(default_factory=dict)` 確保現有呼叫端不會因新增欄位而失效。

### 重要：所有 `CaseRepository` 查詢方法必須改用 `_row_to_case()`

現有程式碼使用 `Case(**dict(row))`。當 `cs_cases` 加入 `cx_1`、`cx_2` 等欄位後，`SELECT *` 回傳的 row 包含這些鍵，`Case(**dict(row))` 會因未知欄位名稱而拋 `TypeError`。

**修改範圍**：`CaseRepository` 中所有回傳 `Case` 物件的查詢方法，包含：
`get_by_id` / `list_all` / `list_by_status` / `list_by_month` / `list_by_date_range` / 其他現有查詢方法，全部改為：

```python
return self._row_to_case(row)
```

`_row_to_case(row: sqlite3.Row) -> Case` 實作：

```python
def _row_to_case(self, row: sqlite3.Row) -> Case:
    d = dict(row)
    static_fields = {k: v for k, v in d.items() if not k.startswith("cx_")}
    extra = {col.col_key: d.get(col.col_key) for col in self._custom_cols}
    return Case(**static_fields, extra_fields=extra)
```

### `CustomColumnRepository`（新增，加入 `repositories.py`）

| 方法 | 說明 |
|------|------|
| `next_col_key() -> str` | `SELECT COALESCE(MAX(col_order), 0) + 1`，組成 `cx_{n}` |
| `insert(col_key, col_label, col_order) -> None` | `INSERT OR IGNORE INTO custom_columns` |
| `list_all() -> list[CustomColumn]` | 依 col_order ASC，`visible_in_list` 欄位轉型為 `bool` |
| `add_column_to_cases(col_key: str) -> None` | ALTER TABLE（見安全說明）|

#### `list_all()` 型別轉換

SQLite 儲存 INTEGER（0/1），回傳前必須明確轉型：

```python
return [
    CustomColumn(
        col_key=row["col_key"],
        col_label=row["col_label"],
        col_order=row["col_order"],
        visible_in_list=bool(row["visible_in_list"]),
    )
    for row in rows
]
```

#### `add_column_to_cases` 安全規則

DDL 不支援 SQLite 參數化，`col_key` 必須在執行前通過嚴格白名單：

```python
import re
_COL_KEY_RE = re.compile(r'^cx_\d+$')

def add_column_to_cases(self, col_key: str) -> None:
    if not _COL_KEY_RE.match(col_key):
        raise ValueError(f"非法 col_key：{col_key!r}")
    cols = {row[1] for row in self._conn.execute("PRAGMA table_info(cs_cases)")}
    if col_key not in cols:
        self._conn.execute(f"ALTER TABLE cs_cases ADD COLUMN {col_key} TEXT")
        self._conn.commit()
```

#### 並發 / 重複呼叫

桌面單人應用不存在並發問題。`INSERT OR IGNORE` + `add_column_to_cases` 的冪等檢查確保重複呼叫安全。

### `CaseRepository` 修改

- 建構子中實例化 `CustomColumnRepository(self._conn)` 取得 `_custom_cols: list[CustomColumn]`
  （同一 `repositories.py` 檔案，無循環依賴）
- `_build_select() -> str`：`SELECT case_id, …靜態欄…, cx_1, cx_2, … FROM cs_cases`（依 `_custom_cols` 動態組成）
- **所有查詢方法**改用 `self._row_to_case(row)` 替換 `Case(**dict(row))`
- 新增 `reload_custom_columns() -> None`：重新讀取並更新 `_custom_cols`
- 新增 `update_extra_field(case_id: str, col_key: str, value: str | None) -> None`

#### `update_extra_field` 安全規則

col_key 由此方法內部驗證（呼叫方不需自行驗證）：

```python
def update_extra_field(self, case_id: str, col_key: str, value: str | None) -> None:
    if not _COL_KEY_RE.match(col_key):
        raise ValueError(f"非法 col_key：{col_key!r}")
    self._conn.execute(
        f"UPDATE cs_cases SET {col_key} = :v WHERE case_id = :id",
        {"v": value, "id": case_id},
    )
    self._conn.commit()
```

---

## Core 層設計

### `CustomColumnManager`（新增，`src/hcp_cms/core/custom_column_manager.py`）

UI 層所有自訂欄位操作一律透過此 Manager，不得直接存取 Repository。

| 方法 | 說明 |
|------|------|
| `list_columns() -> list[CustomColumn]` | 委託 `CustomColumnRepository.list_all()` |
| `create_column(col_label: str) -> CustomColumn` | next_col_key → add_column_to_cases → insert → 回傳 |
| `get_mappable_columns() -> list[tuple[str, str]]` | 靜態欄在前，自訂欄在後；格式 `(col_key, col_label)` |

靜態欄位的中文標籤常數（完整）：

```python
STATIC_COL_LABELS: dict[str, str] = {
    "case_id":        "案件編號",
    "company_id":     "公司 ID",
    "subject":        "主旨",
    "status":         "狀態",
    "priority":       "優先等級",
    "replied":        "是否已回覆",
    "sent_time":      "寄件時間",
    "contact_person": "聯絡人",
    "contact_method": "聯絡方式",
    "system_product": "系統／產品",
    "issue_type":     "問題類型",
    "error_type":     "錯誤類型",
    "impact_period":  "影響期間",
    "progress":       "處理進度",
    "handler":        "負責人",
    "actual_reply":   "實際回覆時間",
    "reply_time":     "預計回覆時間",
    "rd_assignee":    "RD 負責人",
    "notes":          "備註",
}
```

### `CsvImportEngine` 修改

- 建構子同時實例化 `CustomColumnManager(conn)`
- 新增 `create_custom_columns(requests: list[tuple[str, str]]) -> list[CustomColumn]`：
  接收 `[(csv_col_name, col_label), …]`，依序呼叫 `CustomColumnManager.create_column(col_label)`，
  回傳建立的 `CustomColumn` 清單（含 col_key，供 UI 更新 mapping 使用）
- `execute()` 執行完畢後，**內部**呼叫 `self._case_repo.reload_custom_columns()`（UI 無需另外呼叫）
- `_import_row()` 中，mapping 包含 `cx_N` 的項目透過 `CaseRepository.update_extra_field()` 寫入
  （col_key 由 `update_extra_field` 內部驗證，不需呼叫方驗證）

#### `_import_row` 自訂欄流程

```
1. 組靜態欄 dict → insert / overwrite Case（現有邏輯不變）
2. for (csv_col, col_key) in mapping 中 col_key.startswith("cx_") 的項目：
   case_repo.update_extra_field(case_id, col_key, row[csv_col])
```

### `CaseDetailManager` 修改

新增：
```python
def update_extra_field(self, case_id: str, col_key: str, value: str | None) -> None:
    """委託 CaseRepository.update_extra_field()。"""
```

---

## UI 層設計

### 步驟 2：欄位對應頁面

`CsvImportDialog` 持有 `CustomColumnManager` 實例。

**右側下拉改動**：
- 資料來源改用 `custom_col_manager.get_mappable_columns()`
- 選項格式：`中文標籤 (col_key)`，例：`主旨 (subject)`、`自訂欄A (cx_1)`

**底部「未對應欄位」區塊**：
- 條件出現：有 CSV 欄位未對應任何 DB 欄位
- 標題：`尚未對應的 CSV 欄位 — 勾選可自動建立新欄位：`
- 每列：`☑ {csv_col_name}　中文標籤：[QLineEdit，預填 csv_col_name]`
- 預設全部勾選

**步驟 3 執行流程**：
1. 收集勾選列 → 呼叫 `engine.create_custom_columns(requests)`
2. 用回傳的 `CustomColumn` 更新 mapping dict（csv_col → cx_N）
3. 呼叫 `engine.execute()`（內部自動 reload CaseRepository，UI 無需另行呼叫）

### `CaseView`（案件管理列表）

- 持有 `CustomColumnManager` 實例
- `refresh()` 呼叫 `custom_col_manager.list_columns()`
- `visible_in_list=True` 的欄位動態附加於固定欄位之後，欄標題顯示 `col_label`
- 讀取 `case.extra_fields[col_key]` 填入儲存格

### `CaseDetailDialog` Tab 1

- `_load_case()` 後呼叫 `CustomColumnManager.list_columns()`
- 動態加 `QLabel(col_label) + QLineEdit(value)` 於「備註」欄位之後
- `_save_case()` 時對每個自訂欄呼叫 `case_detail_manager.update_extra_field(case_id, col_key, value)`

### `ReportEngine`（追蹤表）

- 建構子同時實例化 `CustomColumnManager(conn)`
- `generate_tracking_table()` 取得 `custom_cols = custom_col_manager.list_columns()`
- 問題追蹤總表（ws2）：`main_headers` 尾端追加各 `col.col_label`，資料列追加 `case.extra_fields.get(col.col_key, "")`
- 個別公司頁籤：同上邏輯

---

## 測試計畫

### 單元測試

| 測試檔案 | 涵蓋範圍 |
|----------|----------|
| `tests/unit/test_custom_column_repository.py` | next_col_key / insert 冪等 / list_all（visible_in_list bool 轉型）/ add_column_to_cases 正常 + 重複（冪等）+ 非法 col_key 拋 ValueError |
| `tests/unit/test_custom_column_manager.py` | create_column / list_columns / get_mappable_columns（靜態欄在前、自訂欄在後）|
| `tests/unit/test_csv_import_engine_custom.py` | create_custom_columns / 匯入含自訂欄資料後 extra_fields 正確 / execute() 後 CaseRepository reload 已觸發 |
| `tests/unit/test_case_repository_extra_fields.py` | 有自訂欄時 list_all / get_by_id / list_by_status 等全部查詢方法均正確填入 extra_fields / update_extra_field 正常 + 非法 col_key 拋 ValueError |
| `tests/unit/test_case_detail_manager_extra.py` | update_extra_field 委託正確 |
| `tests/unit/test_report_engine_custom_cols.py` | generate_tracking_table 含自訂欄標題與值 |

### 整合測試

- `tests/integration/test_csv_wizard_custom_columns.py`：完整流程 — 建立自訂欄 → 匯入 → 驗證 DB 欄位存在 / Case.extra_fields / 報表輸出含自訂欄

---

## 不在此次範圍

- 欄位刪除（SQLite DROP COLUMN 需重建表）
- 欄位改名
- 自訂欄位 FTS5 搜尋整合
- 自訂欄位顯示於「月報」
- `visible_in_list` 的 UI 管理介面
