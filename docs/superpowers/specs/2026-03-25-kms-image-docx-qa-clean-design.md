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
- `QAKnowledge.doc_name` 改用途：儲存來源 `.msg` 絕對路徑
- `QAKnowledge.has_image`：`"是"` 代表 `kms_attachments/{qa_id}/` 已有圖片檔案
- **不新增資料表、不做 DB migration**

### 層次分配

```
services/mail/msg_reader.py   → F1（提取）、F5/F6（清理與截斷修正）
core/kms_engine.py            → F1（attach_images）、F4（export_to_docx）
ui/kms_view.py                → F2、F3、F4（匯出按鈕）、F7
```

---

## F1：圖片提取與持久儲存

### `MSGReader.extract_images(msg_path, dest_dir) -> list[Path]`

- 接收 `.msg` 絕對路徑與目標目錄
- 提取對象：
  1. `htmlBody` 裡 `<img src="cid:...">` 對應的 attachment（CID 內嵌圖片）
  2. 副檔名為 `.png/.jpg/.jpeg/.gif/.bmp/.webp` 的一般附件
- 將圖片寫入 `dest_dir/`（目錄不存在時自動建立）
- 回傳已儲存的 `Path` 列表
- 若 `dest_dir` 已有同名檔案則跳過（冪等）

### `KMSEngine.attach_images(qa_id, msg_path, db_dir) -> int`

- `dest_dir = db_dir / "kms_attachments" / qa_id`
- 呼叫 `MSGReader.extract_images(msg_path, dest_dir)`
- 更新 DB：`has_image = "是"`、`doc_name = str(msg_path)`
- 回傳提取圖片數量

### 呼叫時機

- `KMSEngine.extract_qa_from_email()` 建立 QA 後，若 `raw_email.source_file` 存在，自動呼叫 `attach_images()`
- 也可從 UI 手動對既有 QA 執行（「重新提取圖片」按鈕，未來擴充）

---

## F2：查看完整回覆視窗

### `KMSImageViewDialog(QDialog)`

**位置**：`ui/kms_view.py`

**行為**：
- 標題：`完整回覆 — {qa_id}`
- 主體：`QWebEngineView`
- HTML 渲染策略：
  1. 優先使用 `doc_name` 指向的 `.msg` 檔重讀 `html_body`
  2. 若 `.msg` 不存在，用 `kms_attachments/{qa_id}/` 的圖片 + QA 文字欄位組合簡易 HTML
  3. 若兩者均無，以 `<pre>` 包純文字顯示
- CID 圖片替換：`cid:{name}` → `file:///{kms_attachments/{qa_id}/{name}}`
- 底部列出附件圖片縮圖列（`QScrollArea` 水平排列），點選放大
- 視窗初始大小：900×700，可調整

### `KMSView` 整合

- 詳細面板頂部固定顯示 `🖼️ 查看完整回覆` 按鈕
- 有圖片（`has_image == "是"`）時按鈕高亮；無圖片時仍可點選（僅顯示文字）

---

## F3：答案欄放大

### 詳細面板重構

- 問題 / 回覆 / 解決方案 三個 `QTextEdit` 改置於垂直 `QSplitter` 內，使用者可拖拉調整各欄位高度
- 預設比例：問題 25% / 回覆 50% / 解決方案 25%
- 每個欄位右上角加 `⛶` 按鈕，點選開啟 `TextExpandDialog`

### `TextExpandDialog(QDialog)`

- 標題顯示欄位名稱（問題 / 回覆 / 解決方案）
- 內容：單一 `QTextEdit`（唯讀、可選取複製）
- 視窗大小：700×500，可調整
- 底部：`關閉` 按鈕

---

## F4：Word 匯出

### `KMSEngine.export_to_docx(file_path, qa_list, db_dir) -> Path`

使用 `python-docx`，每筆 QA 格式如下：

```
[標題] {qa_id}｜{system_product}
問題：{question}
回覆：{answer}
        [圖片：從 kms_attachments/{qa_id}/ 依序插入，寬度上限 14cm]
解決方案：{solution}（若有）
────────────────────────（分隔線，非最後一筆）
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

`python-docx` 已在需求清單中（`openpyxl` 現有，`python-docx` 需新增至 `pyproject.toml`）

---

## F5：QA 內容清理

### `MSGReader._clean_qa_text(text: str) -> str`

套用順序：

1. **開頭招呼語去除**（case-insensitive）
   - 模式：`^(您好[\s，,、！!]*|Hi[\s,，]*|Hello[\s,，]*|Dear\s+.{1,20}[,，]\s*|親愛的.{1,10}[：:，,]\s*)\n?`
   - 去除後再次 `lstrip()`

2. **結尾簽名截斷**
   - 遇到以下任一獨立行即截斷（含之後全部內容）：
     - `--`、`___`（三個以上底線）
     - `此致`、`敬上`、`謝謝`（獨立行）
     - `Best regards`、`Regards,`、`Thanks,`、`Sincerely`（不分大小寫）
     - `[公司名稱]`（形如 `[Ares]`、`[亞利斯]` 等方括號包覆）

3. **連續空行壓縮**：三行以上空行 → 兩行

4. **頭尾 strip**

### 呼叫位置

`_read_msg_file()` 內，`_split_thread()` 之後：

```python
thread_answer = _clean_qa_text(thread_answer) if thread_answer else None
thread_question = _clean_qa_text(thread_question) if thread_question else None
```

---

## F6：`_split_thread()` 截斷修正

### 問題一：`_HEADER_LINE_RE` 過於激進

**現況**：全文刪除所有 `From:|To:|Subject:` 等開頭的行，會誤刪內文說明。
**修正**：只刪除「緊接在 thread 分割點之後的連續 header 行區塊」，不影響客戶問題正文。

```python
# 修正前：對全 question_raw 套用
question = _HEADER_LINE_RE.sub("", question_raw).strip() or None

# 修正後：只清除分割點後的 header 區塊（連續行）
question = _strip_leading_headers(question_raw).strip() or None
```

新增 `_strip_leading_headers(text)` — 逐行掃描，移除開頭連續符合 header pattern 的行，遇到非 header 行即停止。

### 問題二：取第一個 vs 最後一個 From 分割點

**現況**：找到第一個非我方 `From:` 就切割，多層引用時客戶原始問題被截斷。
**修正**：改取**最後一個**非我方 `From:` 作為 `thread_question` 起點，確保保留最原始的客戶問題。

```python
# 修正前
for match in _THREAD_FROM_RE.finditer(body):
    ...
    return answer, question   # 第一個就回傳

# 修正後
last_match = None
for match in _THREAD_FROM_RE.finditer(body):
    addr = match.group(1).lower()
    if own not in addr:
        last_match = match      # 持續更新，取最後一個
if last_match:
    ...
    return answer, question
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

樣式：黃色提示背景（`#fef3c7`），文字 `#92400e`，與深色主題形成對比。

---

## 測試計畫

### 單元測試（`tests/unit/`）

| 測試檔案 | 測試項目 |
|---------|---------|
| `test_msg_reader.py` | `extract_images()` 提取 CID 圖片、一般附件；冪等性 |
| `test_msg_reader.py` | `_clean_qa_text()` 招呼語去除、簽名截斷、空行壓縮 |
| `test_msg_reader.py` | `_split_thread()` 多層引用取最後 From；leading headers 只清頭部 |
| `test_kms_engine.py` | `attach_images()` 正確更新 `has_image`、`doc_name` |
| `test_kms_engine.py` | `export_to_docx()` 輸出檔案存在、含正確 QA 數量 |

### 整合測試（`tests/integration/`）

- 從真實 `.msg` 檔匯入 → QA 建立 → 圖片出現在 `kms_attachments/` → 匯出 docx 含圖片

---

## 相依套件異動

| 套件 | 異動 |
|------|------|
| `python-docx` | 新增至 `pyproject.toml` |
| `PySide6.QtWebEngineWidgets` | 已存在（需確認已安裝） |

---

## 不在範圍內

- 圖片 OCR 或文字識別
- 線上雲端儲存同步
- 圖片版本管理
- 手動上傳圖片至既有 QA（未來擴充）
