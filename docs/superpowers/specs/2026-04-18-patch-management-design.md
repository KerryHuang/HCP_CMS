# Patch 整理系統設計規格

**日期：** 2026-04-18
**狀態：** 已確認

## 背景與目標

HCP 客服團隊每次收到新 Patch 及每月例行大 PATCH 時，需依照 SOP 執行以下作業：

- **單次 Patch**：掃描解壓縮資料夾 → 讀 ReleaseNote.doc → 同步 Mantis 狀態 → 產 3 份 Excel 報表 + 測試腳本
- **每月大 PATCH**：收集 Issue 清單 → 整理測試報告（含簡繁轉換）→ 產 PATCH_LIST Excel（11G / 12C）→ 產客戶通知 HTML

目標是將上述流程整合進現有 HCP CMS 桌面應用，讓 Jill 不需切換工具，在同一介面完成所有 Patch 整理作業。

## 設計決策

- **整合 vs 獨立工具**：整合進 HCP CMS。原因：CMS 已開著、可複用 CredentialManager / MantisClient / openpyxl 匯出慣例，統一維護成本低。
- **架構**：管線架構整合進 PySide6 GUI，遵循現有 6 層架構，新增 Patch 整理垂直切片。每個子流程（single / monthly）內部走固定管線，步驟順序固定，特例以參數或跳過旗標處理。
- **資料來源**：同時支援 Mantis 瀏覽器自動化（Playwright）與手動文字輸入（.txt / .json），無網路時可 fallback。
- **內容生成**：結構化欄位（格式、超連結、色彩）用 openpyxl 範本；說明文字、通知信文案呼叫 Claude API 生成。
- **錯誤原則**：所有錯誤為警告，不中止流程。能產出的先產出，問題欄位留佔位符，事後手動補正。

## 架構總覽

```
UI 層          PatchView
                ├── SinglePatchTab
                └── MonthlyPatchTab

Core 層        SinglePatchEngine
               MonthlyPatchEngine

Services 層    MantisClient（現有 SOAP，複用）
               PlaywrightMantisService（新增）
               ClaudeContentService（新增）

Data 層        PatchRepository（新增）

SQLite         cs_patches（新增）
               cs_patch_issues（新增）
```

## Data 層

### 資料表

**cs_patches**

| 欄位 | 型別 | 說明 |
|------|------|------|
| id | INTEGER PK | |
| type | TEXT | `single` / `monthly` |
| month_str | TEXT | 例：`202604`（monthly 專用）|
| patch_dir | TEXT | 作業資料夾路徑 |
| status | TEXT | `in_progress` / `completed` |
| created_at | TEXT | |
| updated_at | TEXT | |

**cs_patch_issues**

| 欄位 | 型別 | 說明 |
|------|------|------|
| id | INTEGER PK | |
| patch_id | INTEGER FK | → cs_patches.id |
| issue_no | TEXT | Mantis Issue 編號 |
| program_code | TEXT | 程式代號 |
| program_name | TEXT | 程式名稱 |
| issue_type | TEXT | `BugFix` / `Enhancement` |
| region | TEXT | `TW` / `CN` / `共用` |
| description | TEXT | 功能說明 |
| impact | TEXT | 影響說明 |
| test_direction | TEXT | 測試方向及注意事項 |
| mantis_detail | TEXT | Mantis 補充說明（JSON）|
| source | TEXT | `manual` / `mantis` |
| created_at | TEXT | |

### PatchRepository

標準 CRUD：`insert_patch()` / `get_patch_by_id()` / `list_patches()` / `update_patch_status()` / `insert_issue()` / `list_issues_by_patch()`。

## Core 層

### SinglePatchEngine(conn)

| 方法 | 說明 |
|------|------|
| `scan_patch_dir(path)` | 掃描解壓縮資料夾，回傳結構摘要（form/sql/muti/setup.bat）|
| `read_release_doc(path)` | 用 oletools（.doc）或 python-docx（.docx）解析 ReleaseNote，識別 Issue 編號、類型、說明 |
| `sync_mantis(issue_nos)` | 呼叫 PlaywrightMantisService，填入客服驗證 / 客戶測試追蹤欄 |
| `generate_excel_reports(patch_id)` | 產 3 份 Excel：Issue清單整理、發行通知、IT/HR 清單 |
| `generate_test_scripts(patch_id)` | 產測試腳本_客服版.docx、客戶版.docx、測試追蹤表.xlsx（選用）|

### MonthlyPatchEngine(conn)

| 方法 | 說明 |
|------|------|
| `load_issues(source, month_str)` | `source='manual'` 讀 .txt/.json；`source='mantis'` 呼叫 PlaywrightMantisService |
| `prepare_test_reports(month_dir)` | 掃描測試報告資料夾，檢查命名格式，偵測簡體並用 opencc 轉繁體 |
| `generate_patch_list(patch_id)` | 產 PATCH_LIST_{YYYYMM}_11G.xlsx 與 12C.xlsx，各含 3 頁籤，Issue No 自動超連結測試報告 |
| `generate_notify_html(patch_id)` | 呼叫 ClaudeContentService 生成說明文字，Jinja2 填入 HTML 範本，產客戶通知信 |

## Services 層

### PlaywrightMantisService

- 使用 Playwright（Chromium）開啟 Mantis Issue 頁面
- 等待 Jill 手動登入後發出信號（UI 顯示「已登入，繼續」按鈕）
- 讀取 Issue 活動紀錄：客服驗證、客戶測試結果 / 日期、可納入大 Patch、備註
- 逾時 5 分鐘自動提示跳過

### ClaudeContentService

- 封裝 Anthropic SDK，讀取 `CredentialManager` 中的 API key
- `generate_description(issue_data)` → 產 HR 說明 / 影響說明文字
- `generate_notify_body(issues, month_str)` → 產客戶通知信主體段落
- 重試 2 次，仍失敗則回傳 `None`，由 Engine 填入佔位符 `【請手動填寫】`

## UI 層

### PatchView

- 左側導覽新增 `📦 Patch 整理` 入口
- 頂部 Tab：`單次 Patch` / `每月大 PATCH`

**共用 UI 元件：**
- 步驟進度列（① → ② → ③ → ④，依完成狀態高亮）
- 執行 Log 區域（即時串流每步結果，✅ / ⚠️ / ❌ 標示）
- 產出檔案區（完成後列出檔案路徑，[開啟] 按鈕）

**SinglePatchTab 操作流程：**
1. 選擇已解壓縮的資料夾
2. 點「▶ 開始執行」→ 自動掃描、讀 .doc
3. Mantis 同步：開啟 Chrome，Jill 登入後按「已登入，繼續」（可跳過）
4. Log 即時顯示進度
5. 完成後顯示 3 份 Excel 連結

**MonthlyPatchTab 操作流程：**
1. 選擇月份（月份選擇器，預設當月）
2. 選擇 Issue 來源（Mantis 瀏覽器 / 上傳 .txt 或 .json）
3. Issue 清單確認畫面（可編輯）
4. 點「產生 Excel」→ 產 PATCH_LIST 11G / 12C
5. 點「產生通知信」→ Claude 生成文字 → HTML 預覽
6. 所有產出集中顯示，[開啟資料夾] 按鈕

### Slot 命名規範

`_on_browse_clicked`、`_on_start_clicked`、`_on_mantis_login_confirmed`、`_on_issue_source_changed`、`_on_generate_excel_clicked`、`_on_generate_html_clicked`

## 輸出規格

### 單次 Patch — 3 份 Excel

| 檔案 | 用途 | 特點 |
|------|------|------|
| Issue清單整理.xlsx | 內部追蹤 | 含客服 / 客戶測試追蹤欄（色彩規範）|
| 發行通知.xlsx | 對客戶 | 不含追蹤欄，測試完成後才發出 |
| Issue清單_IT_HR.xlsx | 角色分流 | IT 頁籤（深藍）+ HR 頁籤（深綠）|

### 單次 Patch — 測試腳本（選用）

| 檔案 | 用途 |
|------|------|
| 測試腳本_客服版.docx | 詳細步驟、簽名欄 |
| 測試腳本_客戶版.docx | 簡化勾選、客戶回填 |
| 測試追蹤表.xlsx | PASS/FAIL 追蹤 |

### 每月大 PATCH — 產出

| 檔案 | 用途 |
|------|------|
| PATCH_LIST_{YYYYMM}_11G.xlsx | IT + HR + 問題修正補充說明（3 頁籤）|
| PATCH_LIST_{YYYYMM}_12C.xlsx | 同上，12C 版本 |
| 【HCP11G維護客戶】{YYYYMM}月份大PATCH更新通知.html | 客戶通知信（貼入 Outlook）|

### Excel 色彩規範（Issue清單整理）

| 色彩 | 用途 |
|------|------|
| #D5F5E3 淡綠 | 客服驗證 / 客服測試結果 / 日期 |
| #D6EAF8 淡藍 | 客戶測試結果 / 日期 |
| #FEF9E7 淡黃 | 可納入每月大 Patch |
| #F5EEF8 淡紫 | 備註 |
| #E2EFDA 淡綠2 | Enhancement 類型列 |
| #FCE4D6 淡橘 | Bug Fix 類型列 |
| #FFF3CD 警告黃 | 待確認 / 尚未完成（自動標色）|

### PATCH_LIST Excel 規範

**IT 發行通知頁籤（8 欄）**：Issue No（藍色超連結）/ 類型 / 程式代號 / 說明 / FORM目錄 / DB物件 / 多語更新 / 備註

**HR 發行通知頁籤（11 欄）**：Issue No / 計區域 / 類型 / 程式代號 / 程式名稱 / 功能說明 / 影響說明 / 相關程式(FORM) / 上線所需動作 / 測試方向及注意事項 / 備註

**通用樣式**：微軟正黑體 11pt；主標題 15pt 白字 #1F3864；副標題 13pt 白字 #2E75B6；CN=淡橘黃 / TW=淡藍 / 共用=淡綠；上線所需動作固定文字「請與資訊單位確認是否已完成更新，確認更新完成再進行測試」

## 錯誤處理

| 情況 | 處理方式 |
|------|----------|
| .doc（非 .docx）| oletools 提取文字；無法解析時提示手動貼入 |
| Excel 已開啟中 | 自動存為 `_v2` 版本，Log 提示 |
| 資料夾結構不符 | 列出缺少項目，讓 Jill 確認後繼續 |
| 測試報告命名不規範 | 標示警告但不中止，超連結留空 |
| Mantis 未登入 / 逾時 | 等待「已登入」按鈕，逾時 5 分鐘後提示跳過 |
| Mantis Issue 欄位讀不到 | 跳過該 Issue，Log 標記，手動補填 |
| SOAP 連線失敗 | Fallback 到瀏覽器模式，再失敗則手動輸入 |
| Claude API key 未設定 | 提示在 CredentialManager 設定，欄位留空 |
| Claude API 逾時 | 重試 2 次，仍失敗用範本填入，Log 標記 |
| Claude 回應空白 | 保留佔位符 `【請手動填寫】`，不中止流程 |

## 依賴套件（新增）

| 套件 | 用途 |
|------|------|
| `playwright` | Mantis 瀏覽器自動化 |
| `oletools` | 讀取 .doc（非 .docx）|
| `opencc-python-reimplemented` | 簡體→繁體轉換 |
| `jinja2` | HTML 通知信範本 |
| `anthropic` | Claude API（說明文字生成）|

`openpyxl`、`python-docx` 已在現有專案中使用。
