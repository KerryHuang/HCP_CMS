# 報表中心 — 檢視與下載分離設計

狀態：已核准
日期：2026-03-29

## 概述

將報表中心的單一「產生並下載」按鈕拆為「檢視」和「下載」兩個獨立動作。使用者先在 app 內以 QTabWidget 預覽多 sheet 報表資料，滿意後再下載成 Excel。

## 架構變更

### Core 層 — ReportEngine 重構

新增兩個方法，回傳結構化資料（不寫檔案）：

- `build_tracking_table(start: str, end: str) -> dict[str, list[list]]`
- `build_monthly_report(start: str, end: str) -> dict[str, list[list]]`

回傳格式：`{sheet_name: [[header_cell, ...], [row_cell, ...], ...]}`，每個 sheet 的第一列為表頭。

原有的 `generate_tracking_table` / `generate_monthly_report` 改為內部呼叫 `build_*` 取得資料後再寫 Excel。產生邏輯只維護一份。

### Core 層 — ReportWriter（新增）

從 ReportEngine 抽出 Excel 寫入邏輯，獨立為 `ReportWriter`：

- `write_excel(data: dict[str, list[list]], path: Path) -> None`
- 負責樣式（表頭深藍背景白字粗體、交替行色、邊框）、超連結、欄寬等格式化

ReportEngine 的 `generate_*` 方法改為呼叫 `ReportWriter.write_excel`。

### UI 層 — ReportView 改造

- 移除原「產生並下載」按鈕
- 新增「檢視」按鈕：呼叫 `build_*` 取得資料 → 填入 QTabWidget 預覽
- 新增「下載」按鈕：初始停用，有預覽資料後啟用 → 呼叫 `ReportWriter.write_excel` 寫檔
- 切換報表類型或日期範圍時，自動清空預覽區、停用下載按鈕
- `self._preview_data: dict[str, list[list]] | None` 暫存當前預覽資料

## UI 佈局

```
控制列: [報表類型 ▼] [起始日期] ～ [結束日期]  [🔍 檢視]  [📥 下載(停用)]

預覽區: QTabWidget
  ├─ Tab "客戶索引"    → QTableWidget
  ├─ Tab "問題追蹤總表" → QTableWidget
  └─ ... 每個 sheet 一個 tab

狀態列: 就緒 / ⏳ 載入中 / ✅ 預覽完成 / ✅ 已下載
```

## 互動流程

1. 使用者選擇報表類型與日期範圍
2. 按「檢視」→ 狀態顯示載入中 → 預覽區填入多 sheet 資料 → 下載按鈕啟用
3. 切換報表類型或日期範圍 → 預覽區清空、下載按鈕停用
4. 按「下載」→ QFileDialog 選路徑 → 寫檔 → 詢問是否開啟
5. 查詢結果為空 → 預覽區顯示空狀態，下載按鈕不啟用

## 資料流

```
UI (檢視) → ReportEngine.build_*() → dict[str, list[list]] → UI 填 QTabWidget
                                            ↓ (暫存 self._preview_data)
UI (下載) → ReportWriter.write_excel(self._preview_data, path) → .xlsx
```

## 錯誤處理

- 日期範圍不合法（起始 > 結束）→ QMessageBox 警告，不執行查詢
- 查詢結果為空（所有 sheet 皆無資料列）→ 預覽區顯示空狀態，下載按鈕不啟用
- Excel 寫檔失敗 → QMessageBox 錯誤提示，狀態列顯示失敗訊息

## 檔案影響

| 檔案 | 動作 | 說明 |
|------|------|------|
| `src/hcp_cms/core/report_engine.py` | 修改 | 抽出 `build_*` 方法，寫入邏輯委託 ReportWriter |
| `src/hcp_cms/core/report_writer.py` | 新增 | Excel 寫入與格式化 |
| `src/hcp_cms/ui/report_view.py` | 修改 | 拆為檢視/下載按鈕，加入 QTabWidget 預覽 |
| `tests/unit/test_report_engine.py` | 修改 | 補充 `build_*` 方法測試 |
| `tests/unit/test_report_writer.py` | 新增 | ReportWriter 單元測試 |
