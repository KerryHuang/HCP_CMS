# 每月大 PATCH 資料夾掃描功能 設計規格

## 目標

在「每月大 PATCH」Tab 新增「掃描資料夾」來源選項，讓使用者選擇月份 Patch 頂層資料夾（如 `202412/`），系統自動掃描 11G/12C 子目錄、解壓縮封存、彙整所有 Issue，並產出符合現有規格的 `PATCH_LIST_YYYYMM_11G.xlsx` 與 `PATCH_LIST_YYYYMM_12C.xlsx`，每筆 Issue 含測試報告超連結。

---

## 資料夾結構假設

### 模式 A（主要模式）

```
202412/
├── 11G/
│   ├── 01.IP_YYYYMMDD_ISSUENUM_11G.7z
│   ├── 02.IP_YYYYMMDD_ISSUENUM_11G.7z
│   └── 測試報告/
│       ├── 01.IP_YYYYMMDD_ISSUENUM_TESTREPORT_11G.doc
│       └── 02.IP_YYYYMMDD_ISSUENUM_TESTREPORT_11G.docx
└── 12C/
    ├── 01.IP_YYYYMMDD_ISSUENUM_12C.7z
    └── 測試報告/
        └── ...
```

### 模式 B（亦支援）

```
202501/
├── 01.IP_YYYYMMDD_ISSUENUM_11G.7z
├── 01.IP_YYYYMMDD_ISSUENUM_12C.zip
├── 01.IP_YYYYMMDD_ISSUENUM_TESTREPORT_11G.doc
└── 01.IP_YYYYMMDD_ISSUENUM_TESTREPORT_12C.doc
```

系統自動偵測模式，兩種皆支援輸入；輸出均以模式 A 目錄結構存放。

---

## UI 變更：MonthlyPatchTab

### 新增來源選項

`_source_combo` 新增第三項：**「掃描資料夾」**，與現有「上傳 .txt / .json」、「Mantis 瀏覽器」共存。

### 來源切換行為

| 選項 | 顯示元件 |
|---|---|
| 上傳 .txt / .json | 檔案路徑欄 + 瀏覽按鈕（現有） |
| Mantis 瀏覽器 | 隱藏（現有） |
| 掃描資料夾 | 資料夾路徑欄 + 瀏覽按鈕（新增） |

### 掃描流程（點「📥 匯入 Issue」後）

Log 顯示順序：

```
📂 偵測結構：模式A（11G/12C 子目錄）
📦 解壓縮 11G/01.IP_...11G.7z → 完成
📦 解壓縮 11G/02.IP_...11G.7z → 完成
📖 讀取 ReleaseNote：11G N 筆 Issue
📦 解壓縮 12C/01.IP_...12C.7z → 完成
📖 讀取 ReleaseNote：12C N 筆 Issue
✅ 掃描完成：11G N 筆、12C N 筆
```

掃描完成後，Issue 表格顯示 11G Issues（預設），步驟推進至「④ 編輯」。

---

## Core 層變更：MonthlyPatchEngine

### 新增方法

#### `scan_monthly_dir(patch_dir: str) -> dict[str, int]`

掃描月份頂層資料夾，建立各版本的 Patch 記錄並匯入 Issues，回傳各版本的 `patch_id`。

**邏輯：**
1. 偵測模式：
   - 模式 A：`patch_dir/11G/` 或 `patch_dir/12C/` 子目錄存在
   - 模式 B：頂層有檔名含 `_11G` 或 `_12C` 的封存檔
2. 模式 B 時：將 11G 相關檔案（`.7z`、`.zip`、`.doc`、`.docx`）移至 `patch_dir/11G/`，12C 同理
3. 各版本目錄：
   - glob `*.7z` + `*.zip` 找所有封存檔
   - 用 `py7zr` / `zipfile` 各自解壓至同目錄下的 `IP_YYYYMMDD_ISSUENUM_{VER}/` 暫存資料夾
   - 用現有 `SinglePatchEngine.read_release_doc()` 讀取 ReleaseNote
   - 合併所有 Issue，建立 monthly `PatchRecord`（`type="monthly"`）並 insert
4. 回傳 `{"11G": patch_id_11g, "12C": patch_id_12c}`（若某版本不存在則無此 key）

#### `generate_patch_list_from_dir(patch_ids: dict[str, int], patch_dir: str, month_str: str) -> list[str]`

依 `patch_ids` 中每個版本產出 `PATCH_LIST_{month_str}_{VER}.xlsx`，存至對應的版本子目錄。

**回傳：** 產出的檔案完整路徑清單

**現有 `generate_patch_list()` 方法保持不動。**

---

## Excel 輸出格式

### 檔名與存放位置

- `{patch_dir}/11G/PATCH_LIST_{month_str}_11G.xlsx`
- `{patch_dir}/12C/PATCH_LIST_{month_str}_12C.xlsx`

### Sheet 1：清單整理

| 欄位 | 說明 |
|---|---|
| Issue No | 7 位數 Issue 編號（如 `0016552`） |
| 6I | 是否適用 6i 版本（初始空白，人工填寫） |
| 11G | V（若在 11G issues 中） |
| 12C | V（若在 12C issues 中） |
| （空白欄） | 保留 |
| Mantis 說明 | 格式：`{issue_no}: {description}` |

- Issue 列表取兩版本的聯集（以 Issue No 去重）
- 僅 11G 的 issue：11G 欄填 V，12C 空白；反之亦然；兩者皆有則均填 V

### Sheet 2：{VER}新項目說明

| 欄位 | 說明 |
|---|---|
| 區域 | region（預設「共用」） |
| 類別 | issue_type（BugFix → 修正；Enhancement → 改善） |
| 程式代碼 | program_code |
| 程式名稱 | program_name |
| 說明 | description |
| 測試報告 | 超連結至 `{VER}/測試報告/` 中對應檔案 |

**測試報告超連結對應規則：**
在 `{patch_dir}/{VER}/測試報告/` 搜尋檔名包含 Issue No（7 位數字）的 `.doc` / `.docx` 檔，找到則設為超連結（`file:///` 絕對路徑）；找不到則顯示 Issue No 純文字。

⚠ 若同一 Issue 有多個測試報告檔，取第一個（按檔名排序）——這屬於可接受誤差，實際應只有一個。

### Sheet 3：更新物件

| 欄位 | 說明 |
|---|---|
| 測試報告 | Issue No（純文字） |
| 資料庫物件 | SQL 目錄下的 `.sql` 檔名（去副檔名，逗號分隔） |
| 程式代碼 | FORM 目錄下的 `.fmb`/`.rdf` 檔名（去副檔名，逗號分隔） |
| 多語 | MUTI 目錄下的 `.sql` 檔名（含副檔名，逗號分隔） |

---

## Data 層

**不需異動。** 現有 `PatchRecord`（`type="monthly"`）與 `PatchIssue` 模型已足夠。

---

## 錯誤處理

- 解壓縮失敗：Log 顯示 `❌ 解壓縮失敗：{filename}：{error}`，跳過該封存，繼續其他
- ReleaseNote 不存在或無法解析：Log 顯示 `⚠️ 找不到 ReleaseNote：{path}`，Issue 數為 0
- 測試報告找不到：超連結欄顯示純文字 Issue No，不報錯

---

## 不在此次範圍

- ALERT清單 sheet（靜態資料，未來另行處理）
- 模式 B 自動整理後移動原始封存檔
- 多版本同時在 UI 切換顯示（11G/12C Issue 表格切換）
