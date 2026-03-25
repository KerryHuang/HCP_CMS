# KMS 知識庫強化：圖片顯示、Word 匯出、QA 清理

**日期**：2026-03-25
**狀態**：已確認
**涵蓋功能**：圖片提取與持久儲存、完整回覆視窗、答案欄放大、Word 匯出、QA 內容清理、移機提醒

---

## 背景

KMS 知識庫目前有以下限制：

1. 圖片欄位（`has_image`、`doc_name`）存在但無實際提取與顯示機制
2. 詳細面板答案欄高度固定 80px，長文被截斷
3. `.msg` 匯入後 `thread_answer`/`thread_question` 含招呼語、簽名檔等雜訊，且 `_split_thread()` 有內容截斷 bug
4. 無法匯出 Word 文件

---

## 範圍

| 編號 | 功能 |
|------|------|
| F1 | .msg 圖片提取與持久儲存 |
| F2 | 查看完整回覆視窗（HTML + 圖片） |
| F3 | 答案欄放大（Splitter + 獨立視窗） |
| F4 | Word 匯出（單筆 / 多筆 / 全部） |
| F5 | QA 內容清理（招呼語、簽名檔） |
| F6 | `_split_thread()` 截斷修正 |
| F7 | 移機提醒（設定頁面） |

---

## 架構決策

### 圖片儲存路徑規則

```
{db所在目錄}/kms_attachments/{qa_id}/{原始檔名}
```

- 與 `.db` 檔案同目錄，整包複製即可移機
- `QAKnowledge.doc_name` 改用途：儲存來源 `.msg` **絕對路徑**
- `QAKnowledge.has_image`：`"是"` 代表 `kms_attachments/{qa_id}/` 已有圖片檔案
- **不新增資料表、不做 DB migration**

### `db_dir` 傳遞路徑（完整鏈路）

`KMSEngine` 建構子維持只接收 `conn: sqlite3.Connection`（符合現有慣例）。
`db_dir: Path` 由以下路徑傳遞：

1. `app.py`：`db_path = get_default_db_path()`，計算 `db_dir = db_path.parent`
2. `MainWindow.__init__` 新增 `db_dir: Path` 參數，`app.py` 建立 `MainWindow(conn, db_dir=db_dir)` 時傳入
3. `MainWindow` 建立 `KMSView(conn=conn, kms=kms, db_dir=db_dir)`
4. `KMSView.__init__` 新增 `db_dir: Path | None = None` 參數，儲存為 `self._db_dir`
5. `KMSImageViewDialog` 和匯出方法呼叫時使用 `self._db_dir`

### `RawEmail.source_file` 語義變更

**現況**：`source_file: str | None` 儲存 `.msg` 檔名（無目錄）。
**修改**：改為儲存 `.msg` **絕對路徑字串**。

**需修改位置（Breaking Change）**：
- `services/mail/msg_reader.py` `_read_msg_file()` 第 195 行：
  `source_file=file_path.name` → `source_file=str(file_path)`
- `case_manager.py` 的 `source_filename` 只取 stem 作標籤解析（`Path(source_filename).stem`）— 仍相容，`Path.stem` 對完整路徑同樣有效，無需修改。

### 層次分配

```
services/mail/msg_reader.py   → F1（extract_images）、F5/F6（清理與截斷修正）
core/kms_engine.py            → F1（attach_images）、F4（export_to_docx）
ui/kms_view.py                → F2、F3、F4（匯出按鈕）、F7
```

---

## F1：圖片提取與持久儲存

### `MSGReader.extract_images(msg_path: Path, dest_dir: Path) -> list[Path]`（靜態方法）

- 接收 `.msg` 絕對路徑與目標目錄
- 提取對象：
  1. `htmlBody` 裡 `<img src="cid:...">` 對應的 attachment（CID 內嵌圖片）
  2. 副檔名為 `.png/.jpg/.jpeg/.gif/.bmp/.webp` 的一般附件
- 將圖片寫入 `dest_dir/`（目錄不存在時自動 `mkdir(parents=True)`）
- 回傳已儲存的 `Path` 列表
- 若 `dest_dir` 已有同名檔案則跳過（冪等）
- 任何單張圖片提取失敗時 `continue`，不中斷整體流程

### `KMSEngine.attach_images(qa_id: str, msg_path: Path, db_dir: Path) -> int`

- `dest_dir = db_dir / "kms_attachments" / qa_id`
- 呼叫 `MSGReader.extract_images(msg_path, dest_dir)`
- 更新 DB：`has_image = "是"`、`doc_name = str(msg_path)`
- 回傳提取圖片數量（0 表示無圖片，`has_image` 仍更新為 `"是"` 以免重複嘗試）
- 若 `msg_path` 不存在：不拋例外，回傳 `0`，不更新 DB

### 呼叫時機

- `KMSEngine.extract_qa_from_email(raw_email, case_id, db_dir=None)` 建立 QA 後：
  若 `raw_email.source_file` 非空且 `db_dir` 非 `None`，自動呼叫 `attach_images()`
- `db_dir` 預設 `None`（向下相容，不傳則跳過圖片提取）

---

## F2：查看完整回覆視窗

### `KMSImageViewDialog(QDialog)`

**位置**：`ui/kms_view.py`

**行為**：
- 標題：`完整回覆 — {qa_id}`
- 主體：`QWebEngineView`
- HTML 渲染策略（依序 fallback）：
  1. 優先使用 `qa.doc_name` 指向的 `.msg` 絕對路徑重讀 `html_body`：建立 `MSGReader(directory=None).read_single_file(Path(qa.doc_name))`（`directory=None` 合法，`read_single_file` 僅需 `file_path`）；或將 `read_single_file` 改為靜態方法（F1 `extract_images` 同為靜態，風格一致，推薦）
  2. 若 `.msg` 不存在或無 `html_body`，從 `kms_attachments/{qa_id}/` 圖片 + QA 文字欄位組合簡易 HTML
  3. 若兩者均無，以 `<pre>` 包 `question + "\n\n" + answer` 純文字顯示
- CID 圖片替換：`cid:{name}` → `file:///{db_dir}/kms_attachments/{qa_id}/{name}`
- 底部附件縮圖列（`QScrollArea` 水平排列），點選開啟 `QDialog` 全尺寸顯示
- 視窗初始大小：900×700，可調整

### `KMSView` 整合

- 詳細面板頂部固定顯示 `🖼️ 查看完整回覆` 按鈕
- `has_image == "是"` 時按鈕樣式高亮（`color: #60a5fa`）；否則正常樣式
- 點選時傳入 `qa` 物件與 `db_dir`

---

## F3：答案欄放大

### 詳細面板重構

- 問題 / 回覆 / 解決方案 三個 `QTextEdit` 改置於垂直 `QSplitter` 內，使用者可拖拉調整各欄位高度
- 預設初始大小比例：問題 25% / 回覆 50% / 解決方案 25%（`setSizes([200, 400, 200])`）
- 移除 `setMaximumHeight(80)` 限制
- 每個欄位使用 `QWidget` 包裹（含標題 label + `⛶` 按鈕 + `QTextEdit`），方便 layout 管理

### `TextExpandDialog(QDialog)`

- 標題顯示欄位名稱（如「回覆 — 展開檢視」）
- 內容：單一 `QTextEdit`（`setReadOnly(True)`，可選取複製）
- 視窗大小：700×500，可調整
- 底部：`關閉` 按鈕

---

## F4：Word 匯出

### `KMSEngine.export_to_docx(file_path: Path, db_dir: Path, qa_list: list[QAKnowledge] | None = None) -> Path`

- `qa_list=None` 時匯出全部已完成 QA（與 `export_to_excel` 一致）
- `qa_list=[]`（空列表）時：建立含標題「無資料」的空白 docx 並儲存，不拋例外
- 每筆 QA 格式：

```
[標題 Heading2] {qa_id}｜{system_product}
問題：{question}
回覆：{answer}
[圖片：從 kms_attachments/{qa_id}/ 依序插入，寬度上限 14cm，若無圖片則略過]
解決方案：{solution}（若有）
────────────（分隔線，非最後一筆）
```

### `KMSView` 新增按鈕

位置：搜尋列右側按鈕區

| 按鈕 | 觸發條件 | 行為 |
|------|---------|------|
| `💾 匯出選取` | 有勾選列 | 匯出勾選的 QA |
| `📄 匯出全部` | 隨時可用 | 匯出目前搜尋結果全部 QA |

詳細面板底部新增：
- `💾 另存 .docx`（僅匯出當前選取的單筆）

匯出完成後以 `QMessageBox.information` 顯示儲存路徑。
檔案選擇使用 `QFileDialog.getSaveFileName`，預設檔名 `KMS匯出_{日期}.docx`。

### 相依套件

`python-docx` 需新增至 `pyproject.toml` `[project.dependencies]`。

---

## F5：QA 內容清理

### `_clean_qa_text(text: str) -> str`（模組層級函數，非方法）

套用順序：

1. **開頭招呼語去除**（case-insensitive，MULTILINE）
   - 模式：`^(您好[\s，,、！!]*|Hi[\s,，]+|Hello[\s,，]+|Dear\s+.{1,20}[,，]\s*|親愛的.{1,10}[：:，,]\s*)\n?`
   - 去除後再次 `lstrip()`

2. **結尾簽名截斷**
   - 逐行掃描，遇到以下任一**獨立行**（`strip()` 後完全符合）即截斷（含之後全部）：
     - `--`、三個以上 `_` 或 `-`
     - `此致`、`敬上`、`謝謝`、`感謝`
     - `Best regards`、`Regards`、`Thanks`、`Sincerely`（不分大小寫）
     - 符合 `^\[.{1,20}\]$` 的方括號公司名稱行
   - **注意**：簽名關鍵字若出現在非獨立行（夾在其他文字中），不觸發截斷

3. **連續空行壓縮**：三行以上連續空行 → 兩行

4. **頭尾 strip**

5. **邊界情況**：
   - 輸入為空字串 `""` → 回傳 `""`（呼叫端負責轉 `None`）
   - 去除招呼語後內容為空 → 回傳 `""`

### 呼叫位置（`_read_msg_file()` 內，`_split_thread()` 之後）

```python
# 模組層級函數，直接呼叫
thread_answer = _clean_qa_text(thread_answer) if thread_answer else None
thread_question = _clean_qa_text(thread_question) if thread_question else None
```

---

## F6：`_split_thread()` 截斷修正

### 問題一：`_HEADER_LINE_RE` 過於激進

**現況**：`_HEADER_LINE_RE.sub("", question_raw)` 全文刪除所有符合 header pattern 的行，會誤刪客戶問題正文。

**修正**：新增模組層級函數 `_strip_leading_headers(text: str) -> str`：
- 逐行掃描，移除**開頭連續**符合 `_HEADER_LINE_RE` 的行
- 遇到第一個不符合的行即停止，後續全部保留
- 邊界情況：全部都是 header 行 → 回傳 `""`

```python
# 修正前
question = _HEADER_LINE_RE.sub("", question_raw).strip() or None

# 修正後
question = _strip_leading_headers(question_raw).strip() or None
```

### 問題二：多層引用取最後一個非我方 From

**現況**：找到第一個非我方 `From:` 就切割，多層引用時截掉後面的客戶原始問題。

**預期行為**：`thread_question` = 最原始（最早）的客戶問題；`thread_answer` = 我方最新回覆（分割點之前的全部內容）。多層引用時同一客戶可能出現多次，取最後一個非我方 From 確保客戶原始問題完整。

```python
# 修正後：取最後一個非我方 From
last_match = None
for match in _THREAD_FROM_RE.finditer(body):
    addr = match.group(1).lower()
    if own not in addr:
        last_match = match
if last_match:
    split_pos = last_match.start()
    answer = body[:split_pos].strip() or None
    question = _strip_leading_headers(body[split_pos:]).strip() or None
    return answer, question
return None, None
```

---

## F7：移機提醒

### `SettingsView` 新增備份提示區塊

位置：設定頁面底部「系統資訊」或「備份」分區

顯示文字：

```
📦 移機注意事項
移機時請確認以下項目一併複製至新電腦：
  • hcp_cms.db         — 資料庫
  • kms_attachments/   — 知識庫圖片（與 .db 同目錄）
缺少 kms_attachments/ 時，知識庫圖片將無法顯示。
```

**樣式**：使用深色主題相容的警告色塊（刻意與主題對比以引起注意）：
- 背景 `#fef3c7`（淡黃）、文字 `#92400e`（深橘棕）
- 以 `QFrame` 包裹，`setStyleSheet` 明確指定以避免被全域 dark stylesheet 覆蓋：`QFrame#migrationNotice { background-color: #fef3c7; border-radius: 6px; padding: 8px; }`
- `objectName = "migrationNotice"`

---

## 測試計畫

### 單元測試（`tests/unit/`）

| 測試檔案 | 測試項目 |
|---------|---------|
| `test_msg_reader.py` | `extract_images()` 提取 CID 圖片、一般附件；冪等性（重複呼叫不重複寫檔） |
| `test_msg_reader.py` | `extract_images()` msg 不存在時回傳空列表不拋例外 |
| `test_msg_reader.py` | `_clean_qa_text()` 招呼語去除（各模式）；簽名截斷（獨立行觸發、非獨立行不截）；空行壓縮 |
| `test_msg_reader.py` | `_clean_qa_text()` 空字串輸入 → 回傳空字串 |
| `test_msg_reader.py` | `_strip_leading_headers()` 只清頭部 header 區塊；全部是 header → 空字串 |
| `test_msg_reader.py` | `_split_thread()` 多層引用取最後非我方 From（`thread_question` 完整）；無非我方 From → 兩者均 `None` |
| `test_kms_engine.py` | `attach_images()` 正確更新 `has_image = "是"`、`doc_name` = 絕對路徑 |
| `test_kms_engine.py` | `attach_images()` msg 不存在時回傳 0、DB 不更新 |
| `test_kms_engine.py` | `export_to_docx()` 輸出檔案存在、含正確 QA 數量（段落數） |
| `test_kms_engine.py` | `export_to_docx()` 空列表 → 建立含「無資料」的空白 docx |
| `test_kms_engine.py` | `extract_qa_from_email()` 帶 `db_dir` 時自動呼叫 `attach_images()` |

### 整合測試（`tests/integration/`）

- 從真實 `.msg` 檔匯入（`source_file` 存絕對路徑）→ QA 建立 → `kms_attachments/{qa_id}/` 有圖片 → 匯出 docx 含圖片段落

---

## 相依套件異動

| 套件 | 異動 | 說明 |
|------|------|------|
| `python-docx` | **新增**至 `pyproject.toml [project.dependencies]` | Word 匯出 |
| `PySide6-WebEngine` | **新增**至 `pyproject.toml [project.dependencies]`（目前未列，需補上） | `QWebEngineView` 渲染 HTML（`email_view.py` 已使用但未在依賴中聲明） |

---

## 不在範圍內

- 圖片 OCR 或文字識別
- 線上雲端儲存同步
- 圖片版本管理
- 手動上傳圖片至既有 QA（未來擴充）
- 圖片備援機制（若 `.msg` 刪除則圖片以已提取版本為準）
