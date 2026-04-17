# HCP CMS PATCH 功能全面整合 設計規格

更新日期：2026-04-18

---

## 目標

將舊版手動 PATCH 工作流程（`hcp-issue-release` Skill、`patch-list-builder` Skill、`大PATCH月度整理助手.html`）全面整合進 HCP CMS，涵蓋兩個子系統：

- **子系統 A**：月 PATCH 強化（強化現有 `MonthlyPatchTab`）
- **子系統 B**：單次 Patch 整理（全新 Tab）
- **子系統 C**：Mantis 追蹤同步（延後，不在此次範圍）

---

## 子系統 A：月 PATCH 強化

### A-1. UI 層（`MonthlyPatchTab`）

#### 步驟條
擴展為 9 步：

```
① 選月份 → ② 選來源 → ③ 匯入 → ④ 編輯 → ⑤ S2T → ⑥ Excel → ⑦ 驗證 → ⑧ 通知信 → ⑨ 完成
```

#### 新增按鈕（插入現有按鈕列）
- `🔤 S2T 轉換`：匯入後自動觸發（見 A-3），可手動重跑
- `🔗 驗證超連結`：手動觸發（見 A-4）

#### 排班提醒區塊（常駐，位於 Log 上方）
- `QListWidget` 顯示提醒條目，每條右側有 `✕` 刪除按鈕
- `＋ 新增提醒` 按鈕：彈出 `QInputDialog` 輸入文字後加入列表
- 切換年份或月份時自動清空
- 僅用於 HTML 通知信產出，不儲存至 DB

#### 底圖上傳（常駐，位於月份選擇列右側）
- `🖼 上傳橫幅底圖` 按鈕：`QFileDialog` 選取 PNG/JPG，存為 `self._banner_image_bytes: bytes | None`
- 顯示已上傳檔名；再次上傳則覆蓋；無上傳時使用季節漸層色塊（fallback）
- 不隨月份切換清空，持久保留直到手動更換

---

### A-2. Excel 格式修正（`generate_patch_list_from_dir`）

#### 通用樣式
- 字型：微軟正黑體
- 本文：11pt
- 主標題列：15pt 白字，深藍底 `#1F3864`
- 副標題列：13pt 白字，中藍底 `#2E75B6`
- 發行日期欄：留空（人工填寫）

#### IT 發行通知（8 欄）

| # | 欄位名稱 | 格式說明 |
|---|----------|----------|
| 1 | Issue No | 藍色超連結 → 對應測試報告 (`file:///` 絕對路徑) |
| 2 | 類型 | BugFix = 淡橘底 `#FCE4D6`；Enhancement = 淡綠底 `#E2EFDA` |
| 3 | 程式代號 | |
| 4 | 說明 | 靠左對齊，自動換行 |
| 5 | FORM 目錄 | 逗號分隔，來自 `mantis_detail.form_files` |
| 6 | DB 物件 | 逗號分隔，來自 `mantis_detail.sql_files` |
| 7 | 多語更新 | 逗號分隔，來自 `mantis_detail.muti_files` |
| 8 | 備註 | |

#### HR 發行通知（11 欄）

| # | 欄位名稱 | 格式說明 |
|---|----------|----------|
| 1 | Issue No | 藍色超連結 → 對應測試報告 |
| 2 | 計區域 | CN = 淡橘黃 `#FFE0B2`；TW = 淡藍 `#DBEAFE`；共用 = 淡綠 `#DCFCE7` |
| 3 | 類型 | BugFix = 淡橘底；Enhancement = 淡綠底 |
| 4 | 程式代號 | |
| 5 | 程式名稱 | |
| 6 | 功能說明 | 靠左，自動換行 |
| 7 | 影響說明/用途 | 靠左，自動換行 |
| 8 | 相關程式(FORM) | 靠左，來自 `mantis_detail.form_files` |
| 9 | 上線所需動作 | 固定文字 + 淡黃底 `#FFF9C4`：「請與資訊單位確認是否已完成更新　確認更新完成再進行測試」 |
| 10 | 測試方向及注意事項 | 靠左，自動換行 |
| 11 | 備註 | |

#### 問題修正補充說明（7 欄）

| # | 欄位名稱 | 來源 |
|---|----------|------|
| 1 | Issue No | DB |
| 2 | 測試報告 | 超連結（現有邏輯保持不變） |
| 3 | 修改原因 | Claude 分析 Mantis 說明（見 A-5） |
| 4 | 原問題 | 同上 |
| 5 | 範例說明 | 同上 |
| 6 | 修正後 | 同上 |
| 7 | 注意事項 | 同上 |

---

### A-3. S2T 簡轉繁（新 `S2TConverter`）

**位置：** `src/hcp_cms/services/s2t/converter.py`

**依賴：** `opencc-python-reimplemented`（新增至 `pyproject.toml`）

**觸發時機：** 匯入（`_on_import_result`）成功後自動執行，可手動重跑

**邏輯：**
1. 掃描 `{scan_dir}/{VER}/測試報告/` 下所有 `.docx` 檔（⚠ `.doc` 格式不支援自動轉換，需使用者先手動另存為 `.docx`）
2. 以 `python-docx` 讀取每個 paragraph text，逐段用 `opencc.convert(text, config='s2t')` 轉換
3. 有變動才覆蓋存檔；無變動則跳過
4. Log 格式：
   - `🔤 01.IP_...11G.docx → 已轉換 87 字`
   - `🔤 02.IP_...11G.docx → 無需轉換`
   - `❌ S2T 失敗：{filename}：{error}`
5. 全部完成後步驟推進至 ⑤

**`S2TConverter` 介面：**
```python
class S2TConverter:
    def convert_docx(self, path: str) -> int:
        """回傳轉換字數，0 表示無需轉換"""
    def convert_directory(self, dir_path: str) -> dict[str, int]:
        """回傳 {filename: converted_count}"""
```

---

### A-4. 超連結驗證（`verify_patch_links`）

**位置：** `MonthlyPatchEngine.verify_patch_links(patch_dir: str) -> dict`

**觸發：** 手動點 `🔗 驗證超連結`

**邏輯：**
1. glob `{patch_dir}/11G/PATCH_LIST_*.xlsx` 與 `12C/PATCH_LIST_*.xlsx`
2. 用 `openpyxl` 讀取各 sheet，取 Issue No 欄的 `cell.hyperlink.target`
3. 將 `file:///` 路徑轉為本地路徑，`Path.exists()` 確認
4. 回傳 `{"11G": {"total": N, "ok": N, "failed": [...]}, "12C": {...}}`
5. Log 格式：
   - `✅ 11G：12/12 條超連結正常`
   - `❌ 11G：0016552 → 找不到 01.IP_20241128_0016552_TESTREPORT_11G.doc`

---

### A-5. Mantis + Claude 補充說明整合

**位置：** `MonthlyPatchEngine._fetch_supplement(issue_no: str) -> dict`

**流程：**
1. 呼叫現有 `MantisClient.get_issue(issue_no)` 取得 Mantis 說明文字
2. 呼叫 `ClaudeContentService.extract_supplement(mantis_text: str) -> dict` 分析
3. Claude prompt 要求輸出 JSON：`{"修改原因": "", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}`
4. 存入 `PatchIssue.mantis_detail`（擴展現有 JSON，加入 `supplement` key）
5. 若 Mantis 無法連線或 Issue 不存在：欄位留空，Log 警告

**`ClaudeContentService.extract_supplement` 介面：**
```python
def extract_supplement(self, mantis_text: str) -> dict[str, str]:
    """輸入 Mantis 說明文字，回傳五欄位 dict"""
```

---

### A-6. HTML 通知信強化（`generate_notify_html`）

#### Header 區塊（對應截圖深藍橫幅）
- 有上傳底圖：圖片 base64 嵌入為 `<img>` 標籤，用 CSS `position:relative/absolute` 疊加文字；使用者從瀏覽器全選複製貼入 Outlook 時，`<img>` 內容會隨剪貼板保留（比 CSS background-image 更可靠）
- 無上傳底圖：依月份自動套用漸層色塊：
  - 1–3 月 🌸 春：`#1F4E79` → `#2E75B6`
  - 4–6 月 🌿 夏：`#1B5E20` → `#2E7D32`
  - 7–9 月 🌻 秋：`#E65100` → `#F57C00`
  - 10–12 月 ❄️ 冬：`#263238` → `#37474F`
- 疊加固定文字（硬編碼，不需每次填寫）：
  - 標題：`【HCP{VER}維護客戶】{YYYYMM}月份大PATCH更新通知`
  - 副標題：`資通電腦 HCP 人力資源管理系統 / 系統維護更新公告`
  - 重要提醒 checklist（固定 5 條，與截圖一致）

#### 主體佈局（左右分欄）
- **左欄（flex:2）**：Issue 清單表格（現有邏輯）
- **右欄（flex:1）**：排班提醒列表
  - 有提醒條目：顯示黃底卡片，每條一行
  - 無提醒條目：右欄不顯示，左欄佔全寬

#### 函式簽名更新
```python
def generate_notify_html(
    self,
    patch_id: int,
    output_dir: str,
    month_str: str,
    notify_body: str | None = None,
    version: str = "11G",
    banner_image_bytes: bytes | None = None,
    schedule_reminders: list[str] | None = None,
) -> str:
```

---

## 子系統 B：單次 Patch 整理

### B-1. UI 層（新 `SinglePatchTab`）

**位置：** `src/hcp_cms/ui/single_patch_tab.py`

**步驟條（5 步）：**
```
① 選 .7z → ② 解壓匯入 → ③ 編輯 → ④ 產報表 → ⑤ 完成
```

**UI 元件：**
- `.7z` 路徑欄 + 瀏覽按鈕
- 輸出目錄欄 + 瀏覽按鈕
- Issue 版本標籤（預設從 .7z 檔名解析，格式 `IP_合併_{YYYYMMDD}`，如 `IP_合併_20261101`，可手動修改）
- `📥 解壓匯入` 按鈕
- Issue 表格（`IssueTableWidget`，可編輯）
- 產報表按鈕群：`📊 Issue清單整理` / `📄 發行通知` / `📋 Issue清單` / `📝 測試腳本`
- Log 區域 + 產出清單

### B-2. Core 層（新 `SinglePatchEngine`）

⚠ 若專案已有 `SinglePatchEngine`，擴展其方法；否則新建。

**位置：** `src/hcp_cms/core/single_patch_engine.py`

**主要方法：**

```python
class SinglePatchEngine:
    def __init__(self, conn: sqlite3.Connection) -> None: ...

    def load_from_archive(self, archive_path: str, month_str: str) -> int:
        """解壓 .7z，讀 ReleaseNote，匯入 DB，回傳 patch_id"""

    def generate_issue_list(self, patch_id: int, output_dir: str) -> str:
        """產 IP_合併_XXXX_Issue清單整理.xlsx（3 頁籤）"""

    def generate_release_notice(self, patch_id: int, output_dir: str) -> str:
        """產 IP_合併_XXXX_發行通知.xlsx（1 頁籤）"""

    def generate_issue_split(self, patch_id: int, output_dir: str) -> str:
        """產 IP_合併_XXXX_Issue清單.xlsx（IT/HR 2 頁籤）"""

    def generate_test_scripts(self, patch_id: int, output_dir: str) -> list[str]:
        """產測試腳本（2 Word + 1 Excel），回傳路徑列表"""
```

### B-3. Excel 輸出規格

#### `IP_合併_XXXX_Issue清單整理.xlsx`（3 頁籤）

**ReleaseNote 頁籤：**
- Bug Fix 節（紅色標籤）+ Enhancement 節（綠色標籤）
- 欄位：Issue No / 類型 / 程式代號 / 程式名稱 / 說明
- 追蹤欄（留空待日後 Mantis 同步）：
  - 綠底：客服驗證 / 測試結果(客服) / 測試日期(客服)
  - 藍底：提供客戶驗證 / 測試結果(客戶) / 測試日期(客戶)
  - 黃底：可納入大PATCH
  - 紫底：備註

**安裝說明頁籤：**
- 欄位：Issue No（相同步驟則合併）/ 安裝步驟
- 步驟來自 ReleaseNote 安裝說明段落

**檔案清單頁籤：**
- 僅列子資料夾（`form/`、`sql/`、`muti/`）程式檔，不含根目錄

#### `IP_合併_XXXX_發行通知.xlsx`（1 頁籤）
- 欄位：Issue No / 類型 / 說明 / 相關程式 / 安裝步驟
- 不含任何追蹤欄位

#### `IP_合併_XXXX_Issue清單.xlsx`（2 頁籤）
- IT 頁籤：深藍 `#1F4E79`，同月 PATCH IT 8 欄格式
- HR 頁籤：深綠 `#1E5631`，同月 PATCH HR 11 欄格式

### B-4. 測試腳本輸出規格

#### `IP_合併_XXXX_測試腳本_客服版.docx`
- 每個 Issue 一節：問題說明 / 前置條件 / 測試步驟（含預期結果）/ 測試人員簽名欄

#### `IP_合併_XXXX_測試腳本_客戶版.docx`
- 每個 Issue 一節：簡化步驟 / □ 正常 □ 異常 / 備註欄

#### `IP_合併_XXXX_測試追蹤表.xlsx`（2 頁籤）
- 客服驗證頁籤：Issue No / 測試日期 / PASS / FAIL / 說明
- 客戶驗證頁籤：Issue No / 回覆日期 / 正常 / 異常 / 說明

---

## 架構影響（檔案變動清單）

### 修改
| 檔案 | 變動說明 |
|------|----------|
| `src/hcp_cms/ui/patch_monthly_tab.py` | 步驟條擴展、新增按鈕、排班提醒區塊、底圖上傳 |
| `src/hcp_cms/core/monthly_patch_engine.py` | Excel 格式修正、`verify_patch_links()`、`_fetch_supplement()`、`generate_notify_html()` 簽名擴展 |
| `src/hcp_cms/services/claude_content.py` | 新增 `extract_supplement()` 方法 |
| `src/hcp_cms/data/models.py` | `PatchIssue.mantis_detail` JSON 擴展加入 `supplement` key（無需 migration，向下相容） |
| `src/hcp_cms/ui/main_window.py` | 新增 `SinglePatchTab` |
| `pyproject.toml` | 新增 `opencc-python-reimplemented`、`python-docx`（若尚未有） |

### 新建
| 檔案 | 說明 |
|------|------|
| `src/hcp_cms/services/s2t/converter.py` | `S2TConverter` — opencc 封裝 |
| `src/hcp_cms/services/s2t/__init__.py` | |
| `src/hcp_cms/ui/single_patch_tab.py` | 單次 Patch 整理 Tab |
| `src/hcp_cms/core/single_patch_engine.py` | 單次 Patch Core 邏輯 |
| `tests/unit/test_s2t_converter.py` | S2T 單元測試 |
| `tests/unit/test_single_patch_engine.py` | 單次 Patch Engine 測試 |

---

## 不在此次範圍

- 子系統 C：Mantis 追蹤同步（客服/客戶驗證狀態回寫），延後另行規劃
- ALERT 清單 sheet
- 多版本 Issue 表格切換（11G/12C 分頁顯示）
- Mantis 瀏覽器來源（現有功能，不動）
