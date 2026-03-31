# Mantis 票號月報整合與同步頁面強化 — 設計規格

**日期**：2026-03-31
**狀態**：已核准

---

## 1. 背景與目標

目前月報（Excel）不包含 Mantis 票號資料，Mantis 同步頁面也缺乏視覺區分。本次設計目標：

1. 月報新增「📌 Mantis 追蹤」工作表，依未處理天數與分類顯示分色列表
2. Mantis 同步頁面新增頂部統計方塊 + 清單行分色
3. 分類邏輯集中於 `MantisClassifier`（Core 層），兩處共用

---

## 2. 分類規則（`MantisClassifier`）

### 2.1 分類類型

| 類型 | 顏色 | 優先序 |
|------|------|--------|
| `closed` | 灰色 | 1（最高，已結案直接灰化） |
| `salary` | 黃色 | 2 |
| `high` | 紅色 | 3 |
| `normal` | 預設 | 4 |

### 2.2 判斷條件

```
closed  → ticket.status in ("resolved", "closed", "已解決", "已關閉")
salary  → 任一關鍵字出現在 ticket.summary：("薪資", "薪水", "Payroll", "工資", "salary")
high    → ticket.priority in ("high", "urgent", "immediate")
normal  → 其他
```

⚠ **薪資關鍵字判斷僅比對 `summary` 欄位**，不檢查 `description`，避免因描述過長導致誤判。若未來需擴展比對範圍，修改 `MantisClassifier` 即可，不影響呼叫方。

⚠ **已結案優先於其他分類**：一張票若同時標記 urgent 且 status=closed，仍歸類為 `closed`（灰色），不顯示紅色。這是有意設計——已結案的票不應再吸引注意力。

### 2.3 介面

```python
class MantisClassifier:
    SALARY_KEYWORDS: tuple[str, ...] = ("薪資", "薪水", "Payroll", "工資", "salary")
    HIGH_PRIORITY:   tuple[str, ...] = ("high", "urgent", "immediate")
    CLOSED_STATUSES: tuple[str, ...] = ("resolved", "closed", "已解決", "已關閉")

    def classify(self, ticket: MantisTicket) -> str:
        """回傳 'closed' | 'salary' | 'high' | 'normal'"""
```

- 不依賴資料庫，不接收 `conn`
- 類別常數設為 `tuple`，子類可覆寫

---

## 3. 月報 Excel — 新增工作表

### 3.1 位置

在現有月報的第四個工作表，名稱「📌 Mantis 追蹤」，排在「客戶分析」之後。

### 3.2 欄位

| 欄 | 欄位名稱 | 來源 |
|----|----------|------|
| A | # | 序號 |
| B | 票號 | `MantisTicket.ticket_id` |
| C | 摘要 | `MantisTicket.summary` |
| D | 狀態 | `MantisTicket.status` |
| E | 優先 | `MantisTicket.priority` |
| F | 未處理天數 | 計算自 `last_updated`（已結案顯示 `—`） |
| G | 最後更新 | `MantisTicket.last_updated` |
| H | 負責人 | `MantisTicket.handler` |

### 3.3 資料範圍

取 `MantisRepository.list_all()` 的全部票號，不限月份。
⚠ **不限月份原因**：Mantis 票號為跨月持續追蹤，若只顯示當月建立的票，會遺漏舊票仍未結案的情況，屬可接受設計。

### 3.4 排序

依 `category` 優先序排列：`high` → `salary` → `normal` → `closed`

### 3.5 配色（Excel `PatternFill`）

| 分類 | 背景色 | 字體色 |
|------|--------|--------|
| `high` | `#450a0a` | `#ffffff` |
| `salary` | `#422006` | `#fef08a` |
| `normal` | `#111827` | `#e2e8f0` |
| `closed` | `#1a1a1a` | `#4b5563` |

### 3.6 新增方法

**`ReportEngine.build_mantis_sheet() -> list[dict]`**

```python
def build_mantis_sheet(self) -> list[dict]:
    """
    回傳 Mantis 追蹤工作表資料列，每列包含：
    ticket_id, summary, status, priority,
    unresolved_days, last_updated, handler, category
    """
```

**`ReportWriter._write_mantis_sheet(ws, rows: list[dict])`**

- 寫入欄位標頭 + 資料列
- 依 `row["category"]` 套用 `PatternFill` 與 `Font` 色彩
- 凍結首列（`ws.freeze_panes = "A2"`）
- 自動調整欄寬（最大 50 字元）

`ReportEngine.build_monthly_report()` 新增呼叫 `build_mantis_sheet()`，並在 `ReportWriter.write_excel()` 中新增對應工作表寫入。

---

## 4. Mantis 同步頁面（`MantisView`）強化

### 4.1 頂部統計方塊

在現有「同步全部」按鈕列下方新增一排四個統計 `QFrame`：

| 方塊 | 顯示內容 | 背景色 |
|------|----------|--------|
| 高優先度 | N 件 | `#450a0a` |
| 薪資相關 | N 件 | `#422006` |
| 處理中 | N 件 | `#1e3a5f` |
| 已結案 | N 件 | `#1a1a1a` |

數字由 `refresh()` 載入清單後統計，不額外查詢資料庫。

### 4.2 清單行分色

`refresh()` 填入 `QTableWidget` 後，對每行：

1. 建立 `MantisClassifier` 實例
2. 呼叫 `classify(ticket)` 取得分類
3. 對該行所有欄位設定 `setBackground(QColor)` / `setForeground(QColor)`

配色與 Excel 相同（見 3.5）。

---

## 5. 架構層次與依賴

```
MantisView (UI)
  └─ MantisClassifier (Core)   ← 分類邏輯唯一來源
  └─ MantisRepository (Data)

ReportEngine (Core)
  └─ MantisClassifier (Core)
  └─ MantisRepository (Data)

ReportWriter (Core)
  └─ [純資料寫入，不依賴 Classifier]
```

---

## 6. 測試計畫

### `tests/unit/test_mantis_classifier.py`

| 測試方法 | 驗證內容 |
|----------|----------|
| `test_classify_closed_status` | status=resolved → `closed` |
| `test_classify_closed_beats_high` | status=closed + priority=urgent → `closed` |
| `test_classify_salary_keyword` | summary 含「薪資」→ `salary` |
| `test_classify_salary_english` | summary 含「Payroll」→ `salary` |
| `test_classify_high_priority` | priority=urgent → `high` |
| `test_classify_high_immediate` | priority=immediate → `high` |
| `test_classify_normal` | 無任何觸發條件 → `normal` |
| `test_classify_empty_summary` | summary=None → 不拋例外，`normal` |

### `tests/unit/test_report_engine.py`（新增）

| 測試方法 | 驗證內容 |
|----------|----------|
| `test_build_mantis_sheet_returns_rows` | 有票號時回傳非空 list |
| `test_build_mantis_sheet_category_field` | 每列含 `category` 欄位 |
| `test_build_mantis_sheet_sorting` | high 排在 normal 之前 |

### `tests/unit/test_report_writer.py`（新增）

| 測試方法 | 驗證內容 |
|----------|----------|
| `test_write_mantis_sheet_headers` | 工作表首列含正確欄位標頭 |
| `test_write_mantis_sheet_high_fill` | high 列的 fill.fgColor 正確 |

---

## 7. 改動範圍

| 檔案 | 動作 | 說明 |
|------|------|------|
| `src/hcp_cms/core/mantis_classifier.py` | **新增** | 分類邏輯集中管理 |
| `src/hcp_cms/core/report_engine.py` | 修改 | 新增 `build_mantis_sheet()` |
| `src/hcp_cms/core/report_writer.py` | 修改 | 新增 `_write_mantis_sheet()` |
| `src/hcp_cms/ui/mantis_view.py` | 修改 | 統計方塊 + 行分色 |
| `tests/unit/test_mantis_classifier.py` | **新增** | 8 個測試案例 |
| `tests/unit/test_report_engine.py` | 修改 | 新增 3 個測試案例 |
| `tests/unit/test_report_writer.py` | 修改 | 新增 2 個測試案例 |

**不改動**：`data/` 層（不需新增欄位）、`services/` 層、`scheduler/` 層。
