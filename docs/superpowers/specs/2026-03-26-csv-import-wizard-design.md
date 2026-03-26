# CSV 歷史客服記錄匯入精靈 — 設計文件

**日期**：2026-03-26
**狀態**：已核准（v3，二次審查後修正）

---

## 背景

使用者手邊有一份歷史客服記錄 CSV（「202510開始客服問題記錄 - 202603問題記錄」），欄位為舊版 Excel 追蹤格式。需要一個匯入精靈，讓使用者可自行確認欄位對應後批次寫入 cs_cases / companies 資料表。

---

## 架構

### 元件圖

```
CaseView（UI 層）
  └─ 工具列「📥 匯入 CSV」按鈕
       └─ CsvImportDialog（3 步驟精靈，繼承 QDialog）
            ├─ Step 1：選擇檔案，解析標頭，顯示總筆數
            ├─ Step 2：欄位對應表（CSV 欄 → cs_cases 欄），預設值自動填入
            └─ Step 3：預覽（新增/衝突筆數），選衝突策略，執行，顯示結果

CsvImportEngine（Core 層）
  ├─ __init__(conn: sqlite3.Connection)
  │    內部建立：self._case_repo = CaseRepository(conn)
  │             self._company_repo = CompanyRepository(conn)
  ├─ parse_headers(path: Path) → list[str]
  ├─ preview(path: Path, mapping: Mapping) → ImportPreview
  └─ execute(path: Path, mapping: Mapping,
             strategy: ConflictStrategy,
             progress_cb: Callable[[int, int], None] | None = None) → ImportResult

CsvImportWorker(QThread)  ← UI 層，在 run() 內部建立自己的 conn
  signal: progress(current: int, total: int)
  signal: finished(result: ImportResult)
```

### 型別定義（`core/csv_import_engine.py`）

```python
@dataclass
class ImportPreview:
    total: int            # CSV 總列數（不含標頭）
    new_count: int        # 全新案件（case_id 不存在）
    conflict_count: int   # 衝突案件（case_id 已存在）

@dataclass
class ImportResult:
    success: int
    skipped: int
    overwritten: int
    failed: int
    errors: list[str]     # 格式："第 N 列：原因"

class ConflictStrategy(Enum):
    SKIP = "skip"
    OVERWRITE = "overwrite"

# mapping 方向：{csv_欄名: db_欄名} 或 {csv_欄名: "skip"}
Mapping = dict[str, str]
```

---

## 欄位對應（預設值）

### 使用者可對應的欄位（Step 2 下拉選單）

下拉選單只包含以下欄位（自動欄位不列入）：

`status`, `progress`, `sent_time`, `company_id`, `contact_person`, `subject`,
`system_product`, `issue_type`, `error_type`, `impact_period`, `actual_reply`,
`reply_time`, `notes`, `rd_assignee`, `handler`, `priority`, `contact_method`

| CSV 欄位 | 預設對應 | 備註 |
|----------|---------|------|
| 問題狀態 | `status` | |
| 處理進度 | `progress` | |
| 寄件時間 | `sent_time` | 標準化為 `YYYY/MM/DD HH:MM:SS` |
| 公司 | `company_id` | 見「公司處理規則」 |
| 聯絡人 | `contact_person` | |
| 主旨 | `subject` | |
| 對客服的難易度 | `priority` | |
| 技術協助人員1 | `rd_assignee` | |
| 技術協助人員2 | `notes` | 附加格式見下方說明 |
| 【Type】 | `issue_type` | |
| 問題分類 | `error_type` | |
| MANTIS建檔狀況 | `skip` | |
| 知識QA | `skip` | |
| 是否需要測試/查詢 | `skip` | |
| （其餘欄位） | `skip` | |

**技術協助人員2 附加規則**：
- 值不為空時，附加 `\n【技術協助2】{值}` 至 `notes` 尾端
- OVERWRITE 模式：先移除舊有 `\n【技術協助2】...` 行（regex），再重新附加

**自動填入欄位（不可對應，程式內部設定）**：

| 欄位 | 值 |
|------|----|
| `case_id` | `CS-YYYYMM-NNN`（見「case_id 產生規則」） |
| `source` | `'csv_import'` |
| `created_at` | 匯入當下時間戳記 |
| `updated_at` | 匯入當下時間戳記 |
| `contact_method` | `'Email'`（若使用者未對應） |
| `replied` | `'否'`（預設，若使用者未對應） |

---

## 公司處理規則

與 `MigrationManager` 採用相同策略（`data/migration.py`）：

- `company_id = name = domain = company_name`
- 使用 `INSERT OR IGNORE`（冪等，相同公司多次出現只建立一筆）
- 公司欄空白 → `company_id = None`，不建立公司記錄

---

## case_id 產生規則

> **格式差異說明**：現有 `CaseRepository.next_case_id()` 產生 `CS-YYYY-NNN`。
> CSV 匯入使用新格式 `CS-YYYYMM-NNN`，由 Engine 內部方法獨立產生，流水號互不干擾。

**格式**：`CS-YYYYMM-NNN`

**流水號計算（批次開始時執行一次，不逐列查詢）**：

```python
# Engine 初始化匯入時，建立每月基數快取
_base: dict[str, int] = {}

def _next_case_id(self, year_month: str) -> str:
    if year_month not in self._base:
        # 查資料庫現有最大流水號
        row = conn.execute(
            "SELECT MAX(case_id) FROM cs_cases WHERE case_id LIKE ?",
            (f"CS-{year_month}-%",)
        ).fetchone()
        max_id = row[0]  # e.g. "CS-202510-007" or None
        self._base[year_month] = int(max_id[-3:]) if max_id else 0
    self._base[year_month] += 1
    return f"CS-{year_month}-{self._base[year_month]:03d}"
```

- `sent_time` 解析失敗時，`year_month` 使用匯入當下年月

---

## sent_time 格式標準化

目標格式：`YYYY/MM/DD HH:MM:SS`（與 `_now()` 一致）

支援輸入格式（依序嘗試）：

| 格式 | 範例 |
|------|------|
| `YYYY/MM/DD (週X) 上午/下午 HH:MM` | `2026/3/2 (週一) 上午 09:27` |
| `YYYY/MM/DD HH:MM:SS` | `2026/03/02 09:27:00` |
| `YYYY/MM/DD HH:MM` | `2026/03/02 09:27` |
| `YYYY/MM/DD` | `2026/03/02`（時間補 `00:00:00`） |

無法解析 → 該列跳過，記錄錯誤。
時間部分無秒數 → 補 `:00`。
上午/下午轉換：下午且小時 < 12 時 + 12；上午 12 時轉 0。

---

## OVERWRITE 覆寫範圍

OVERWRITE 模式覆寫 **所有 `mapping` 中指定的欄位**（不含自動欄位），
以 `UPDATE cs_cases SET col1=?, col2=? ... WHERE case_id=?` 實作。

`created_at` 保留原值不覆寫；`updated_at` 更新為匯入當下時間。

---

## preview() 衝突判斷

`preview()` 執行完整的 case_id 產生邏輯（呼叫 `_next_case_id()`），
對每列計算出 `case_id` 後查詢資料庫是否已存在。

> 注意：`preview()` 執行後會消耗月份計數器，`execute()` 需重新初始化 `_base`。
> 因此 `_base` 應為 `execute()` / `preview()` 各自獨立的區域變數，而非 instance 狀態。

---

## 執行緒設計（避免 UI 凍結）

```python
class CsvImportWorker(QThread):
    progress = Signal(int, int)          # (current, total)
    finished = Signal(object)            # ImportResult

    def __init__(self, db_path: Path, csv_path: Path,
                 mapping: Mapping, strategy: ConflictStrategy):
        ...

    def run(self):
        conn = sqlite3.connect(str(self._db_path))  # 在 worker 執行緒建立連線
        try:
            engine = CsvImportEngine(conn)
            result = engine.execute(
                self._csv_path, self._mapping, self._strategy,
                progress_cb=lambda c, t: self.progress.emit(c, t)
            )
            self.finished.emit(result)
        finally:
            conn.close()
```

SQLite 連線在 `run()` 內建立，避免跨執行緒共用（`check_same_thread` 預設行為）。

---

## 精靈步驟細節

### Step 1 — 選擇檔案

- `QFileDialog.getOpenFileName(filter="CSV (*.csv)")`
- 自動偵測編碼（UTF-8-BOM → UTF-8 → Big5）
- 顯示：檔名、偵測到的欄位清單、估計總筆數
- 編碼無法識別 → 顯示錯誤訊息，停留在 Step 1

### Step 2 — 欄位對應

- 表格：左欄 CSV 標頭、右欄下拉選單（可用 cs_cases 欄位清單 + 「略過」）
- 預設值依對應表自動填入
- 「下一步」驗證：`sent_time`、`subject`、`公司` 必須對應（非略過）

### Step 3 — 預覽 + 執行

- 呼叫 `preview()` 顯示：新增 N 筆 / 衝突 N 筆
- 衝突策略：`○ 略過` / `○ 覆蓋`
- 按「執行匯入」→ 啟動 `CsvImportWorker`，進度條即時更新
- 完成報告：成功 N、略過 N、覆蓋 N、失敗 N（附錯誤清單）

---

## 錯誤處理

| 情況 | 處理方式 |
|------|---------|
| `sent_time` 格式無法解析 | 跳過該列，記錄「第 N 列：sent_time 格式錯誤」 |
| `subject` 欄為空 | 跳過該列，記錄「第 N 列：subject 為空」 |
| 公司欄空白 | `company_id = None`，繼續寫入 |
| CSV 編碼無法識別 | Step 1 顯示錯誤 |
| 資料庫寫入異常 | 記錄錯誤，繼續下一列 |

---

## 測試策略（TDD）

### `tests/unit/test_csv_import_engine.py`

- `parse_headers`：UTF-8-BOM、UTF-8、Big5
- `sent_time` 標準化：上午/下午、無秒數補 `:00`、無法解析跳過
- `preview`：全新 / 部分衝突 / 全部衝突
- `execute`：
  - SKIP 模式：衝突列跳過，計入 `skipped`
  - OVERWRITE 模式：衝突列覆寫，`created_at` 保留，`updated_at` 更新
  - 公司自動建立（冪等：同名公司多次出現只建一筆）
  - 公司欄空白 → `company_id = None`
  - `技術協助人員2` 附加格式；OVERWRITE 時舊值先清除再附加
- `case_id` 產生：
  - 同月份流水號連續遞增（快取機制）
  - 跨月份各自計算
  - 資料庫已有 `CS-YYYY-NNN` 舊格式時，`CS-YYYYMM-NNN` 不受影響
  - 資料庫已有部分 `CS-YYYYMM-NNN` 時，新號接續最大值（MAX 非 COUNT）

### `tests/unit/test_csv_import_dialog.py`（Qt Test）

- Step 1 → Step 2 流程（mock `QFileDialog`）
- Step 2：必填欄位未對應時「下一步」禁用
- Step 3：preview 結果顯示、衝突策略切換
- Worker signal：mock `engine.execute`，驗證 `progress` / `finished` signal

---

## 異動檔案清單

| 檔案 | 動作 |
|------|------|
| `src/hcp_cms/core/csv_import_engine.py` | 新增 |
| `src/hcp_cms/ui/csv_import_dialog.py` | 新增（含 CsvImportWorker） |
| `src/hcp_cms/ui/case_view.py` | 修改（工具列加按鈕） |
| `tests/unit/test_csv_import_engine.py` | 新增 |
| `tests/unit/test_csv_import_dialog.py` | 新增 |
| `tests/conftest.py` | 可能修改（確認現有 db fixture 是否足夠） |
