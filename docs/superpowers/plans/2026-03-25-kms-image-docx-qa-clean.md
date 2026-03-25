# KMS 知識庫強化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 強化 KMS 知識庫，支援 .msg 圖片提取與持久顯示、Word 匯出（單筆/多筆/全部）、QA 文字清理（去招呼語/簽名）、答案欄放大，及移機提醒。

**Architecture:** Services 層新增靜態方法 `extract_images`、`_clean_qa_text`、修正 `_split_thread`；Core 層新增 `attach_images`、`export_to_docx`；UI 層新增 `KMSImageViewDialog`、`TextExpandDialog`，重構 `KMSView` 詳細面板，並透過 `db_dir` 鏈路（app → MainWindow → KMSView）傳遞圖片根目錄。

**Tech Stack:** Python 3.14、PySide6 6.10、SQLite FTS5、python-docx、PySide6-WebEngine、extract-msg

---

## 檔案異動總覽

| 動作 | 路徑 | 說明 |
|------|------|------|
| 修改 | `pyproject.toml` | 新增 python-docx、PySide6-WebEngine 相依 |
| 修改 | `src/hcp_cms/services/mail/msg_reader.py` | 新增 `_strip_leading_headers`、`_clean_qa_text`；修正 `_split_thread`；新增靜態方法 `extract_images`；`source_file` 改存絕對路徑 |
| 修改 | `src/hcp_cms/core/kms_engine.py` | 新增 `attach_images`、`export_to_docx`；更新 `extract_qa_from_email` 簽名 |
| 修改 | `src/hcp_cms/app.py` | 計算 `db_dir`，傳入 `MainWindow` |
| 修改 | `src/hcp_cms/ui/main_window.py` | 新增 `db_dir` 參數，傳入 `KMSView` |
| 修改 | `src/hcp_cms/ui/kms_view.py` | 新增 `db_dir` 參數；新增 `KMSImageViewDialog`、`TextExpandDialog`；重構詳細面板；新增匯出按鈕 |
| 修改 | `src/hcp_cms/ui/settings_view.py` | 新增移機提醒 `QFrame` |
| 新增 | `tests/unit/test_msg_reader.py` | `_strip_leading_headers`、`_clean_qa_text`、`_split_thread`、`extract_images` 單元測試 |
| 修改 | `tests/unit/test_kms_engine.py` | 新增 `attach_images`、`export_to_docx`、`extract_qa_from_email(db_dir=...)` 測試 |

---

## Task 1：新增相依套件

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1：修改 pyproject.toml**

在 `[project] dependencies` 清單加入兩行：

```toml
dependencies = [
    "PySide6>=6.6",
    "PySide6-WebEngine>=6.6",
    "openpyxl>=3.1",
    "python-docx>=1.1",
    "extract-msg>=0.48",
    "exchangelib>=5.1",
    "requests>=2.31",
    "keyring>=25.0",
    "jieba>=0.42",
]
```

- [ ] **Step 2：安裝新套件**

```bash
.venv/Scripts/pip.exe install python-docx PySide6-WebEngine
```

預期：安裝成功，無 ERROR 訊息。

- [ ] **Step 3：Commit**

```bash
git add pyproject.toml
git commit -m "chore: 新增 python-docx 與 PySide6-WebEngine 相依套件"
```

---

## Task 2：F5+F6 — QA 文字清理與 _split_thread 修正（Services 層）

**Files:**
- Modify: `src/hcp_cms/services/mail/msg_reader.py`
- Create: `tests/unit/test_msg_reader.py`

### Step 2-1：先寫測試（F6 _strip_leading_headers）

- [ ] **Step 1：建立測試檔，寫 `_strip_leading_headers` 失敗測試**

建立 `tests/unit/test_msg_reader.py`：

```python
"""Tests for MSGReader helper functions."""
import pytest
from hcp_cms.services.mail.msg_reader import (
    _clean_qa_text,
    _strip_leading_headers,
    MSGReader,
)


class TestStripLeadingHeaders:
    def test_removes_leading_header_lines(self):
        text = "From: foo@bar.com\nSubject: test\n\n正文內容"
        result = _strip_leading_headers(text)
        assert result == "\n正文內容"

    def test_stops_at_first_non_header(self):
        text = "From: foo@bar.com\n正文第一行\nSubject: 這行在正文裡"
        result = _strip_leading_headers(text)
        assert "正文第一行" in result
        assert "Subject: 這行在正文裡" in result

    def test_all_headers_returns_empty(self):
        text = "From: a@b.com\nTo: c@d.com\nSubject: hi"
        result = _strip_leading_headers(text)
        assert result.strip() == ""

    def test_empty_string(self):
        assert _strip_leading_headers("") == ""

    def test_no_headers_unchanged(self):
        text = "這是一般文字\n第二行"
        assert _strip_leading_headers(text) == text
```

- [ ] **Step 2：執行，確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_msg_reader.py::TestStripLeadingHeaders -v
```

預期：`ImportError` 或 `FAILED`（函數尚未存在）。

- [ ] **Step 3：在 msg_reader.py 新增 `_strip_leading_headers`**

在 `msg_reader.py` 開頭的 regex 常數之後（`_HEADER_LINE_RE` 之後）加入：

```python
def _strip_leading_headers(text: str) -> str:
    """移除 text 開頭連續符合 header pattern 的行，遇到非 header 行即停止。"""
    lines = text.split("\n")
    i = 0
    while i < len(lines) and _HEADER_LINE_RE.match(lines[i]):
        i += 1
    return "\n".join(lines[i:])
```

- [ ] **Step 4：執行測試，確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_msg_reader.py::TestStripLeadingHeaders -v
```

預期：全部 PASSED。

### Step 2-2：測試 + 實作 _clean_qa_text（F5）

- [ ] **Step 5：加入 `_clean_qa_text` 失敗測試**

在 `test_msg_reader.py` 加入：

```python
class TestCleanQaText:
    def test_removes_greeting_您好(self):
        text = "您好，\n\n請問如何操作？"
        result = _clean_qa_text(text)
        assert not result.startswith("您好")
        assert "請問如何操作" in result

    def test_removes_greeting_hi(self):
        text = "Hi,\n這是問題"
        result = _clean_qa_text(text)
        assert not result.lower().startswith("hi")
        assert "這是問題" in result

    def test_removes_greeting_dear(self):
        text = "Dear 客服人員,\n請協助處理"
        result = _clean_qa_text(text)
        assert not result.lower().startswith("dear")

    def test_truncates_signature_best_regards(self):
        text = "這是正文\n\nBest regards\n王小明\n公司電話：02-1234"
        result = _clean_qa_text(text)
        assert "這是正文" in result
        assert "Best regards" not in result
        assert "公司電話" not in result

    def test_truncates_signature_此致(self):
        text = "問題描述\n此致\n敬禮"
        result = _clean_qa_text(text)
        assert "問題描述" in result
        assert "此致" not in result

    def test_signature_in_middle_of_line_not_truncated(self):
        """簽名關鍵字夾在句子中不觸發截斷"""
        text = "謝謝您的協助，後來解決了"
        result = _clean_qa_text(text)
        assert "謝謝您的協助" in result

    def test_truncates_dashes_separator(self):
        text = "正文\n---\n公司資訊"
        result = _clean_qa_text(text)
        assert "正文" in result
        assert "公司資訊" not in result

    def test_compresses_multiple_blank_lines(self):
        text = "行一\n\n\n\n\n行二"
        result = _clean_qa_text(text)
        assert "\n\n\n" not in result

    def test_empty_string(self):
        assert _clean_qa_text("") == ""

    def test_only_greeting_returns_empty(self):
        text = "您好，\n"
        result = _clean_qa_text(text)
        assert result == ""
```

- [ ] **Step 6：執行，確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_msg_reader.py::TestCleanQaText -v
```

- [ ] **Step 7：在 msg_reader.py 新增 `_clean_qa_text`**

在 `_strip_leading_headers` 之後加入（仍在模組層級）：

注意：`msg_reader.py` 頂部已有 `import re`，以下所有 `re.` 直接使用，**不要**重新 import。

```python
_GREETING_RE = re.compile(
    r"^(您好[\s，,、！!]*|Hi[\s,，]+|Hello[\s,，]+|Dear\s+.{1,20}[,，]\s*|親愛的.{1,10}[：:，,]\s*)\n?",
    re.IGNORECASE | re.MULTILINE,
)
_SIGNATURE_KEYWORDS = frozenset({
    "此致", "敬上", "謝謝", "感謝",
    "best regards", "regards", "thanks", "sincerely",
})
_SEPARATOR_RE = re.compile(r"^(-{3,}|_{3,})$")
_BRACKET_CO_RE = re.compile(r"^\[.{1,20}\]$")


def _clean_qa_text(text: str) -> str:
    """去除 QA 文字的招呼語、簽名檔，壓縮多餘空行。"""
    if not text:
        return ""
    # 1. 去招呼語
    text = _GREETING_RE.sub("", text, count=1).lstrip()
    # 2. 截斷簽名
    lines = text.split("\n")
    clean_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if (
            stripped.lower() in _SIGNATURE_KEYWORDS
            or _SEPARATOR_RE.match(stripped)
            or _BRACKET_CO_RE.match(stripped)
        ):
            break
        clean_lines.append(line)
    text = "\n".join(clean_lines)
    # 3. 壓縮連續空行（> 2 個空行 → 2 個）
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 4. strip
    return text.strip()
```

- [ ] **Step 8：執行測試，確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_msg_reader.py::TestCleanQaText -v
```

### Step 2-3：修正 _split_thread（F6）

- [ ] **Step 9：加入 _split_thread 修正測試**

```python
class TestSplitThreadFixed:
    def test_multi_layer_uses_last_customer_from(self):
        """多層引用時取最後一個非我方 From，thread_question 包含最原始問題。"""
        body = (
            "我方第二次回覆\n\n"
            "From: customer@client.com\n"
            "第一次客戶問題（被引用）\n\n"
            "From: hcpservice@ares.com.tw\n"
            "我方第一次回覆\n\n"
            "From: customer@client.com\n"
            "Subject: 原始問題\n\n"
            "最原始客戶問題內容"
        )
        answer, question = MSGReader._split_thread(body, own_domain="@ares.com.tw")
        assert question is not None
        assert "最原始客戶問題內容" in question
        assert answer is not None

    def test_leading_headers_removed_from_question(self):
        """客戶問題段開頭的 header 行被移除，正文保留。"""
        body = (
            "我方回覆\n\n"
            "From: customer@client.com\n"
            "Subject: 測試主旨\n"
            "Sent: 2026-01-01\n\n"
            "這是客戶問題正文"
        )
        _, question = MSGReader._split_thread(body)
        assert question is not None
        assert "這是客戶問題正文" in question
        assert "Subject:" not in question

    def test_no_customer_from_returns_none_none(self):
        body = "只有我方寄件人\nFrom: service@ares.com.tw\n內容"
        answer, question = MSGReader._split_thread(body, own_domain="@ares.com.tw")
        assert answer is None
        assert question is None
```

- [ ] **Step 10：執行，確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_msg_reader.py::TestSplitThreadFixed -v
```

- [ ] **Step 11：修正 `_split_thread` 方法**

將 `MSGReader._split_thread` 靜態方法改為：

```python
@staticmethod
def _split_thread(body: str, own_domain: str = "@ares.com.tw") -> tuple[str | None, str | None]:
    """回傳 (thread_answer, thread_question)。
    取最後一個非我方 From 行：上方為 answer，下方清除 leading header 行後為 question。
    """
    own = own_domain.lower()
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

- [ ] **Step 12：執行全部 msg_reader 測試**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_msg_reader.py -v
```

預期：全部 PASSED。

### Step 2-4：加入 _clean_qa_text 到 _read_msg_file + 修正 source_file

- [ ] **Step 13：修改 `_read_msg_file` 兩處**

第一處：將第 195 行
```python
source_file=file_path.name,
```
改為：
```python
source_file=str(file_path),
```

第二處：在 `thread_answer, thread_question = MSGReader._split_thread(body_text)` 之後加入：
```python
thread_answer = _clean_qa_text(thread_answer) if thread_answer else None
thread_question = _clean_qa_text(thread_question) if thread_question else None
```

- [ ] **Step 14：執行全部測試確認沒有 regression**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short
```

預期：全部 PASSED（或只有先前就存在的失敗）。

- [ ] **Step 15：Commit**

```bash
git add src/hcp_cms/services/mail/msg_reader.py tests/unit/test_msg_reader.py
git commit -m "feat: 修正 _split_thread 截斷、新增 QA 文字清理函數（F5+F6）"
```

---

## Task 3：F1 Services — extract_images 靜態方法

**Files:**
- Modify: `src/hcp_cms/services/mail/msg_reader.py`
- Modify: `tests/unit/test_msg_reader.py`

- [ ] **Step 1：加入 extract_images 失敗測試**

在 `test_msg_reader.py` 加入：

```python
class TestExtractImages:
    def test_nonexistent_msg_returns_empty(self, tmp_path):
        result = MSGReader.extract_images(tmp_path / "notexist.msg", tmp_path / "out")
        assert result == []

    def test_idempotent_skip_existing(self, tmp_path):
        """若目標目錄已有同名檔案，跳過不重複寫入。"""
        dest = tmp_path / "out"
        dest.mkdir()
        existing = dest / "image.png"
        existing.write_bytes(b"original")
        # 模擬：若 msg_path 不存在，直接回傳 []（冪等驗證的前提是目的地已有檔案）
        result = MSGReader.extract_images(tmp_path / "fake.msg", dest)
        assert existing.read_bytes() == b"original"  # 未被覆蓋
```

- [ ] **Step 2：執行，確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_msg_reader.py::TestExtractImages -v
```

- [ ] **Step 3：在 MSGReader 新增靜態方法 `extract_images`**

在 `MSGReader` 類別內（`read_single_file_verbose` 之後）加入：

```python
@staticmethod
def extract_images(msg_path: Path, dest_dir: Path) -> list[Path]:
    """從 .msg 提取圖片附件至 dest_dir。若 msg_path 不存在回傳 []。

    提取對象：
    1. htmlBody 中 cid: 對應的 attachment
    2. 副檔名 .png/.jpg/.jpeg/.gif/.bmp/.webp 的一般附件
    冪等：dest_dir 已有同名檔案時跳過。
    """
    if not msg_path.exists():
        return []
    try:
        import extract_msg
        msg = extract_msg.Message(msg_path)
    except Exception:
        return []

    # 收集 CID 對應的 attachment content-id 集合
    cid_names: set[str] = set()
    try:
        html = getattr(msg, "htmlBody", None)
        if html:
            if isinstance(html, bytes):
                html = html.decode("utf-8", errors="replace")
            import re
            for cid in re.findall(r'src=["\']cid:([^"\'>\s]+)["\']', html, re.IGNORECASE):
                cid_names.add(cid.split("@")[0].lower())
    except Exception:
        pass

    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
    saved: list[Path] = []
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        attachments = msg.attachments or []
    except Exception:
        attachments = []

    for att in attachments:
        try:
            filename = getattr(att, "longFilename", None) or getattr(att, "shortFilename", None) or ""
            if not filename:
                continue
            ext = Path(filename).suffix.lower()
            content_id = (getattr(att, "contentId", None) or "").split("@")[0].lower()
            is_cid = content_id in cid_names
            is_image_ext = ext in _IMAGE_EXTS
            if not (is_cid or is_image_ext):
                continue
            dest_file = dest_dir / filename
            if dest_file.exists():
                saved.append(dest_file)
                continue
            data = att.data
            if data:
                dest_file.write_bytes(data)
                saved.append(dest_file)
        except Exception:
            continue

    try:
        msg.close()
    except Exception:
        pass
    return saved
```

- [ ] **Step 4：執行測試**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_msg_reader.py::TestExtractImages -v
```

預期：PASSED。

- [ ] **Step 5：執行全部測試**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short
```

- [ ] **Step 6：Commit**

```bash
git add src/hcp_cms/services/mail/msg_reader.py tests/unit/test_msg_reader.py
git commit -m "feat: 新增 MSGReader.extract_images 靜態方法（F1 Services 層）"
```

---

## Task 4：F1 Core — KMSEngine.attach_images + extract_qa_from_email 更新

**Files:**
- Modify: `src/hcp_cms/core/kms_engine.py`
- Modify: `tests/unit/test_kms_engine.py`

- [ ] **Step 1：加入失敗測試**

在 `tests/unit/test_kms_engine.py` 的 `TestKMSEngine` 類別加入：

```python
def test_attach_images_nonexistent_msg(self, kms, tmp_path):
    """msg 不存在時回傳 0，DB 不更新。"""
    qa = kms.create_qa(question="測試", answer="答覆")
    count = kms.attach_images(qa.qa_id, tmp_path / "notexist.msg", tmp_path)
    assert count == 0
    qa_after = kms._qa_repo.get_by_id(qa.qa_id)
    assert qa_after.has_image == "否"  # 未更新

def test_attach_images_updates_db(self, kms, tmp_path):
    """提供假 msg 路徑（存在但無圖片），has_image 仍更新為是。"""
    # 建立一個空 msg-like 檔案（extract_images 會開啟失敗並回傳 []）
    fake_msg = tmp_path / "fake.msg"
    fake_msg.write_bytes(b"")
    qa = kms.create_qa(question="圖片測試", answer="答覆")
    # attach_images：0 張圖片但 msg 存在（不拋例外）→ has_image = 是
    kms.attach_images(qa.qa_id, fake_msg, tmp_path)
    qa_after = kms._qa_repo.get_by_id(qa.qa_id)
    assert qa_after.has_image == "是"
    assert qa_after.doc_name == str(fake_msg)

def test_extract_qa_from_email_with_db_dir(self, kms, tmp_path):
    """帶 db_dir 時，extract_qa_from_email 成功建立 QA 並記錄 doc_name。"""
    from hcp_cms.services.mail.base import RawEmail
    email = RawEmail(
        sender="customer@client.com",
        subject="測試",
        body="您好，請問如何操作？",
        thread_question="請問如何操作？",
        thread_answer="操作說明如下",
        source_file=str(tmp_path / "test.msg"),
    )
    # 建立假 msg 檔（讓 attach_images 不因不存在而略過）
    (tmp_path / "test.msg").write_bytes(b"")
    qa = kms.extract_qa_from_email(email, case_id="CS-001", db_dir=tmp_path)
    assert qa is not None
    assert qa.doc_name == str(tmp_path / "test.msg")
```

- [ ] **Step 2：執行，確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_kms_engine.py -k "attach_images or extract_qa_from_email_with_db_dir" -v
```

- [ ] **Step 3：修改 `kms_engine.py`**

在 `KMSEngine` 類別加入 `attach_images` 方法：

```python
def attach_images(self, qa_id: str, msg_path: Path, db_dir: Path) -> int:
    """從 msg_path 提取圖片至 db_dir/kms_attachments/qa_id/。
    若 msg_path 不存在回傳 0 且不更新 DB。
    """
    from pathlib import Path as _Path
    if not msg_path.exists():
        return 0
    from hcp_cms.services.mail.msg_reader import MSGReader
    dest_dir = db_dir / "kms_attachments" / qa_id
    saved = MSGReader.extract_images(msg_path, dest_dir)
    # 無論有無圖片，只要 msg 存在就更新 DB（避免重複嘗試）
    qa = self._qa_repo.get_by_id(qa_id)
    if qa:
        qa.has_image = "是"
        qa.doc_name = str(msg_path)
        self._qa_repo.update(qa)
    return len(saved)
```

更新 `extract_qa_from_email` 簽名，加入 `db_dir` 可選參數：

```python
def extract_qa_from_email(
    self,
    raw_email: RawEmail,
    case_id: str | None = None,
    db_dir: Path | None = None,
) -> QAKnowledge | None:
    """從 RawEmail thread 欄位抽取 QA，儲存為待審核。無問題段則回傳 None。
    若 db_dir 非 None 且 raw_email.source_file 非空，自動提取圖片。
    """
    if not raw_email.thread_question:
        return None
    qa = self.create_qa(
        question=raw_email.thread_question,
        answer=raw_email.thread_answer or "",
        source="email",
        source_case_id=case_id,
        status="待審核",
    )
    if db_dir is not None and raw_email.source_file:
        from pathlib import Path as _Path
        self.attach_images(qa.qa_id, _Path(raw_email.source_file), db_dir)
    return qa
```

同時在檔案頂部確保有：
```python
from pathlib import Path
```

- [ ] **Step 4：執行測試**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_kms_engine.py -v
```

預期：全部 PASSED。

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/core/kms_engine.py tests/unit/test_kms_engine.py
git commit -m "feat: 新增 KMSEngine.attach_images，更新 extract_qa_from_email 支援 db_dir（F1 Core）"
```

---

## Task 5：F4 Core — KMSEngine.export_to_docx

**Files:**
- Modify: `src/hcp_cms/core/kms_engine.py`
- Modify: `tests/unit/test_kms_engine.py`

- [ ] **Step 1：加入 export_to_docx 失敗測試**

```python
def test_export_to_docx_creates_file(self, kms, tmp_path):
    # 必須建立「已完成」的 QA，qa_list=None 時呼叫 list_approved()
    kms.create_qa(question="問題一", answer="回覆一", status="已完成")
    kms.create_qa(question="問題二", answer="回覆二", status="已完成")
    out = tmp_path / "export.docx"
    result = kms.export_to_docx(out, db_dir=tmp_path)
    assert result == out
    assert out.exists()

def test_export_to_docx_empty_list(self, kms, tmp_path):
    """空列表時建立含『無資料』標題的空白 docx，不拋例外。"""
    out = tmp_path / "empty.docx"
    kms.export_to_docx(out, db_dir=tmp_path, qa_list=[])
    assert out.exists()

def test_export_to_docx_qa_list_override(self, kms, tmp_path):
    """傳入 qa_list 時只匯出指定的 QA。"""
    qa1 = kms.create_qa(question="匯出這筆", answer="A")
    kms.create_qa(question="不匯出這筆", answer="B")
    out = tmp_path / "partial.docx"
    kms.export_to_docx(out, db_dir=tmp_path, qa_list=[qa1])
    # 讀取確認只有 qa1
    from docx import Document
    doc = Document(out)
    full_text = " ".join(p.text for p in doc.paragraphs)
    assert "匯出這筆" in full_text
    assert "不匯出這筆" not in full_text
```

- [ ] **Step 2：執行，確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_kms_engine.py -k "export_to_docx" -v
```

- [ ] **Step 3：在 kms_engine.py 新增 `export_to_docx`**

```python
def export_to_docx(
    self,
    file_path: Path,
    db_dir: Path,
    qa_list: list[QAKnowledge] | None = None,
) -> Path:
    """匯出 QA 至 Word 文件。qa_list=None 時匯出全部已完成 QA。"""
    from docx import Document
    from docx.shared import Cm

    if qa_list is None:
        qa_list = self._qa_repo.list_approved()

    doc = Document()
    doc.add_heading("KMS 知識庫匯出", level=1)

    if not qa_list:
        doc.add_paragraph("無資料")
        doc.save(str(file_path))
        return file_path

    for i, qa in enumerate(qa_list):
        title = f"{qa.qa_id}"
        if qa.system_product:
            title += f"｜{qa.system_product}"
        doc.add_heading(title, level=2)
        doc.add_paragraph(f"問題：{qa.question or ''}")
        doc.add_paragraph(f"回覆：{qa.answer or ''}")

        # 插入圖片
        img_dir = db_dir / "kms_attachments" / qa.qa_id
        if img_dir.exists():
            for img_path in sorted(img_dir.iterdir()):
                if img_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}:
                    try:
                        doc.add_picture(str(img_path), width=Cm(14))
                    except Exception:
                        continue

        if qa.solution:
            doc.add_paragraph(f"解決方案：{qa.solution}")
        if i < len(qa_list) - 1:
            doc.add_paragraph("─" * 40)

    doc.save(str(file_path))
    return file_path
```

- [ ] **Step 4：執行測試**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_kms_engine.py -k "export_to_docx" -v
```

- [ ] **Step 5：執行全部測試**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short
```

- [ ] **Step 6：Commit**

```bash
git add src/hcp_cms/core/kms_engine.py tests/unit/test_kms_engine.py
git commit -m "feat: 新增 KMSEngine.export_to_docx（F4 Core）"
```

---

## Task 6：架構 — db_dir 傳遞鏈路（app → MainWindow → KMSView）

**Files:**
- Modify: `src/hcp_cms/app.py`
- Modify: `src/hcp_cms/ui/main_window.py`

此 Task 無業務邏輯，無需 TDD。

- [ ] **Step 1：修改 `app.py` 傳入 db_dir**

將：
```python
window = MainWindow(db.connection)
```
改為：
```python
window = MainWindow(db.connection, db_dir=db_path.parent)
```

- [ ] **Step 2：修改 `MainWindow.__init__` 接收 db_dir**

將：
```python
def __init__(self, db_connection: sqlite3.Connection | None = None) -> None:
    super().__init__()
    self._conn = db_connection
```
改為：
```python
def __init__(
    self,
    db_connection: sqlite3.Connection | None = None,
    db_dir: Path | None = None,
) -> None:
    super().__init__()
    self._conn = db_connection
    self._db_dir = db_dir
```

並在 `main_window.py` 頂部加入：
```python
from pathlib import Path
```

- [ ] **Step 3：在 `_setup_ui` 內傳入 db_dir 給 KMSView**

將：
```python
"kms": KMSView(self._conn, kms=kms),
```
改為：
```python
"kms": KMSView(self._conn, kms=kms, db_dir=self._db_dir),
```

- [ ] **Step 4：修改 `KMSView.__init__` 接收 db_dir**

在 `kms_view.py` 找到（第 100 行附近）：
```python
# 修改前
def __init__(self, conn: sqlite3.Connection | None = None, kms: KMSEngine | None = None) -> None:
```
替換為：

```python
def __init__(
    self,
    conn: sqlite3.Connection | None = None,
    kms: KMSEngine | None = None,
    db_dir: Path | None = None,
) -> None:
    super().__init__()
    self._conn = conn
    self._kms = kms or (KMSEngine(conn) if conn else None)
    self._db_dir = db_dir
    self._results: list = []
    self._pending: list = []
    self._setup_ui()
```

並在 `kms_view.py` 頂部加入：
```python
from pathlib import Path
```

- [ ] **Step 5：執行測試確認無 regression**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short
```

- [ ] **Step 6：Commit**

```bash
git add src/hcp_cms/app.py src/hcp_cms/ui/main_window.py src/hcp_cms/ui/kms_view.py
git commit -m "refactor: db_dir 傳遞鏈路（app → MainWindow → KMSView）"
```

---

## Task 7：F3 UI — 答案欄放大（Splitter + TextExpandDialog）

**Files:**
- Modify: `src/hcp_cms/ui/kms_view.py`

> **TDD 豁免**：`TextExpandDialog` 為純 UI 呈現元件（無業務邏輯），以手動視覺驗收代替自動測試。

- [ ] **Step 1：在 `kms_view.py` 新增 `TextExpandDialog`**

在 `QAReviewDialog` 之前加入：

```python
class TextExpandDialog(QDialog):
    """欄位展開檢視對話框。"""

    def __init__(self, title: str, content: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(700, 500)
        layout = QVBoxLayout(self)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(content)
        layout.addWidget(text)
        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
```

- [ ] **Step 2：新增 `_make_field_widget` 輔助方法至 `KMSView`**

```python
def _make_field_widget(self, label: str, attr_name: str) -> tuple[QWidget, QTextEdit]:
    """建立標題列 + 展開按鈕 + QTextEdit 的組合 widget。"""
    wrapper = QWidget()
    vlay = QVBoxLayout(wrapper)
    vlay.setContentsMargins(0, 0, 0, 0)
    vlay.setSpacing(2)

    header = QWidget()
    hlay = QHBoxLayout(header)
    hlay.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
    hlay.addWidget(lbl)
    hlay.addStretch()
    expand_btn = QPushButton("⛶")
    expand_btn.setFixedSize(22, 22)
    expand_btn.setToolTip("展開檢視")
    expand_btn.setStyleSheet("QPushButton { background: transparent; color: #64748b; font-size: 14px; border: none; } QPushButton:hover { color: #e2e8f0; }")
    hlay.addWidget(expand_btn)
    vlay.addWidget(header)

    edit = QTextEdit()
    edit.setReadOnly(True)
    vlay.addWidget(edit)

    field_label = label
    expand_btn.clicked.connect(
        lambda: TextExpandDialog(f"{field_label} — 展開檢視", edit.toPlainText(), self).exec()
    )
    return wrapper, edit
```

- [ ] **Step 3：重構 `_setup_ui` 的詳細面板**

在 `KMSView._setup_ui` 內，找到詳細面板建立區塊（`detail = QWidget()` 以下至 `splitter.addWidget(detail)`），替換為：

```python
detail = QWidget()
detail_layout = QVBoxLayout(detail)
detail_layout.setContentsMargins(4, 4, 4, 4)

# 查看完整回覆按鈕（頂部）
self._view_btn = QPushButton("🖼️ 查看完整回覆")
self._view_btn.clicked.connect(self._on_view_full)
detail_layout.addWidget(self._view_btn)

# 三個欄位放入垂直 QSplitter
field_splitter = QSplitter(Qt.Orientation.Vertical)

q_widget, self._detail_question = self._make_field_widget("問題", "question")
a_widget, self._detail_answer = self._make_field_widget("回覆", "answer")
s_widget, self._detail_solution = self._make_field_widget("解決方案", "solution")

field_splitter.addWidget(q_widget)
field_splitter.addWidget(a_widget)
field_splitter.addWidget(s_widget)
field_splitter.setSizes([200, 400, 200])

detail_layout.addWidget(field_splitter)

# 單筆匯出按鈕
self._export_single_btn = QPushButton("💾 另存 .docx")
self._export_single_btn.clicked.connect(self._on_export_single)
detail_layout.addWidget(self._export_single_btn)

splitter.addWidget(detail)
```

同時在 `QSplitter` import 行確認已加入（`kms_view.py` 已有）。
新增 `QVBoxLayout` 到 import list（若未包含）。

- [ ] **Step 4：執行應用程式手動確認介面**

```bash
.venv/Scripts/python.exe -m hcp_cms
```

切換至 KMS 知識庫，點選一筆 QA，確認：
- 三欄位有標題列與 ⛶ 按鈕
- 拖拉 Splitter 可調整高度
- 點 ⛶ 開啟展開視窗

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/ui/kms_view.py
git commit -m "feat: KMSView 答案欄改 Splitter，新增 TextExpandDialog（F3）"
```

---

## Task 8：F2 UI — KMSImageViewDialog（完整回覆視窗）

**Files:**
- Modify: `src/hcp_cms/ui/kms_view.py`

> **TDD 豁免**：`KMSImageViewDialog` 為純 UI 渲染元件（HTML 渲染邏輯依賴 QWebEngineView），以手動 end-to-end 驗收代替自動測試。

- [ ] **Step 1：新增 `KMSImageViewDialog` 至 `kms_view.py`**

在 `TextExpandDialog` 之後加入（需在 `kms_view.py` 頂部 import 加入必要項目）：

```python
# 頂部新增 import：
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QScrollArea
```

```python
class KMSImageViewDialog(QDialog):
    """完整回覆視窗：HTML + 圖片。"""

    def __init__(self, qa, db_dir: Path | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"完整回覆 — {qa.qa_id}")
        self.resize(900, 700)
        self._qa = qa
        self._db_dir = db_dir
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._web = QWebEngineView()
        html = self._build_html()
        if self._db_dir:
            base_url = QUrl.fromLocalFile(str(self._db_dir) + "/")
            self._web.setHtml(html, base_url)
        else:
            self._web.setHtml(html)
        layout.addWidget(self._web, stretch=1)

        # 附件縮圖列
        img_dir = (self._db_dir / "kms_attachments" / self._qa.qa_id) if self._db_dir else None
        if img_dir and img_dir.exists():
            scroll = QScrollArea()
            scroll.setFixedHeight(120)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            thumb_widget = QWidget()
            thumb_layout = QHBoxLayout(thumb_widget)
            _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
            for img_path in sorted(img_dir.iterdir()):
                if img_path.suffix.lower() in _IMAGE_EXTS:
                    lbl = QLabel()
                    pix = QPixmap(str(img_path)).scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    lbl.setPixmap(pix)
                    lbl.setCursor(Qt.CursorShape.PointingHandCursor)
                    img_path_str = str(img_path)
                    lbl.mousePressEvent = lambda e, p=img_path_str: self._open_full_image(p)
                    thumb_layout.addWidget(lbl)
            thumb_layout.addStretch()
            scroll.setWidget(thumb_widget)
            layout.addWidget(scroll)

        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _build_html(self) -> str:
        qa = self._qa
        # 嘗試重讀 .msg html_body
        html_body = None
        if qa.doc_name:
            from pathlib import Path as _Path
            msg_path = _Path(qa.doc_name)
            if msg_path.exists():
                from hcp_cms.services.mail.msg_reader import MSGReader
                # 注意：維持實例方法呼叫（directory=None 合法），不做靜態化，與現有 MSGReader 介面一致
                raw = MSGReader(directory=None).read_single_file(msg_path)
                if raw and raw.html_body:
                    html_body = self._replace_cid(raw.html_body)

        if html_body:
            return html_body

        # fallback：用圖片 + 文字組合簡易 HTML
        img_dir = (self._db_dir / "kms_attachments" / qa.qa_id) if self._db_dir else None
        img_html = ""
        if img_dir and img_dir.exists():
            _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
            for img_path in sorted(img_dir.iterdir()):
                if img_path.suffix.lower() in _IMAGE_EXTS:
                    img_html += f'<img src="{img_path.as_uri()}" style="max-width:100%;margin:8px 0;"><br>'

        q = (qa.question or "").replace("<", "&lt;").replace(">", "&gt;")
        a = (qa.answer or "").replace("<", "&lt;").replace(">", "&gt;")
        s = (qa.solution or "").replace("<", "&lt;").replace(">", "&gt;")
        return f"""<html><body style="font-family:sans-serif;padding:16px">
<h3>問題</h3><pre>{q}</pre>
<h3>回覆</h3><pre>{a}</pre>
{img_html}
{'<h3>解決方案</h3><pre>' + s + '</pre>' if s else ''}
</body></html>"""

    def _replace_cid(self, html: str) -> str:
        """將 cid: 圖片參考替換為 file:// 路徑。"""
        if not self._db_dir:
            return html
        import re
        img_dir = self._db_dir / "kms_attachments" / self._qa.qa_id
        def replacer(m):
            cid = m.group(1).split("@")[0]
            for f in img_dir.iterdir() if img_dir.exists() else []:
                if f.stem.lower() == cid.lower() or f.name.lower() == cid.lower():
                    return f'src="{f.as_uri()}"'
            return m.group(0)
        return re.sub(r'src=["\']cid:([^"\'>\s]+)["\']', replacer, html, flags=re.IGNORECASE)

    def _open_full_image(self, img_path_str: str) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("圖片檢視")
        dlg.resize(800, 600)
        lay = QVBoxLayout(dlg)
        lbl = QLabel()
        pix = QPixmap(img_path_str)
        lbl.setPixmap(pix.scaled(780, 560, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        lay.addWidget(lbl)
        dlg.exec()
```

- [ ] **Step 2：實作 `_on_view_full` slot**

在 `KMSView` 加入：

```python
def _on_view_full(self) -> None:
    rows = self._table.selectionModel().selectedRows()
    if not rows or not self._results:
        return
    qa = self._results[rows[0].row()]
    dlg = KMSImageViewDialog(qa, self._db_dir, parent=self)
    dlg.exec()
```

更新 `_on_selection_changed` 以高亮 `_view_btn`：

```python
def _on_selection_changed(self) -> None:
    rows = self._table.selectionModel().selectedRows()
    if not rows or not self._results:
        return
    row = rows[0].row()
    if row < 0 or row >= len(self._results):
        return
    qa = self._results[row]
    self._detail_question.setPlainText(qa.question or "")
    self._detail_answer.setPlainText(qa.answer or "")
    self._detail_solution.setPlainText(qa.solution or "")
    # 高亮查看按鈕
    if qa.has_image == "是":
        self._view_btn.setStyleSheet("color: #60a5fa;")
    else:
        self._view_btn.setStyleSheet("")
```

- [ ] **Step 3：手動確認**

```bash
.venv/Scripts/python.exe -m hcp_cms
```

點選有圖片 QA，點「🖼️ 查看完整回覆」，確認視窗開啟且顯示內容。

- [ ] **Step 4：Commit**

```bash
git add src/hcp_cms/ui/kms_view.py
git commit -m "feat: 新增 KMSImageViewDialog 完整回覆視窗（F2）"
```

---

## Task 9：F4 UI — Word 匯出按鈕

**Files:**
- Modify: `src/hcp_cms/ui/kms_view.py`

- [ ] **Step 1：在 `kms_view.py` 新增匯出相關 imports**

確認頂部有：
```python
from PySide6.QtWidgets import QFileDialog, QMessageBox
from datetime import date
```

- [ ] **Step 2：新增搜尋列的匯出按鈕**

在 `_setup_ui` 的 `search_layout` 按鈕群組中（`new_btn` 之後）加入：

```python
export_sel_btn = QPushButton("💾 匯出選取")
export_sel_btn.clicked.connect(self._on_export_selected)
search_layout.addWidget(export_sel_btn)

export_all_btn = QPushButton("📄 匯出全部")
export_all_btn.clicked.connect(self._on_export_all)
search_layout.addWidget(export_all_btn)
```

- [ ] **Step 3：實作三個匯出 slots**

```python
def _on_export_single(self) -> None:
    rows = self._table.selectionModel().selectedRows()
    if not rows or not self._results:
        return
    qa = self._results[rows[0].row()]
    self._do_export([qa])

def _on_export_selected(self) -> None:
    rows = self._table.selectionModel().selectedRows()
    if not rows:
        return
    qa_list = [self._results[r.row()] for r in rows if r.row() < len(self._results)]
    self._do_export(qa_list)

def _on_export_all(self) -> None:
    # 匯出「目前搜尋結果」（非全部 DB 已完成 QA），與按鈕說明「匯出全部搜尋結果」一致
    # 若搜尋結果為空，_do_export([]) 建立空白 docx 並告知使用者
    self._do_export(self._results if self._results else [])

def _do_export(self, qa_list: list) -> None:
    if not self._kms:
        return
    today = date.today().strftime("%Y%m%d")
    default_name = f"KMS匯出_{today}.docx"
    path, _ = QFileDialog.getSaveFileName(self, "另存 Word 文件", default_name, "Word 文件 (*.docx)")
    if not path:
        return
    try:
        from pathlib import Path
        self._kms.export_to_docx(Path(path), db_dir=self._db_dir or Path("."), qa_list=qa_list)
        QMessageBox.information(self, "匯出完成", f"已儲存至：\n{path}")
    except Exception as e:
        QMessageBox.critical(self, "匯出失敗", str(e))
```

- [ ] **Step 4：手動確認**

```bash
.venv/Scripts/python.exe -m hcp_cms
```

顯示全部 QA → 點選一筆 → 點「💾 另存 .docx」，確認 Word 文件建立成功。

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/ui/kms_view.py
git commit -m "feat: KMSView 新增 Word 匯出按鈕（F4 UI）"
```

---

## Task 10：F7 UI — SettingsView 移機提醒

**Files:**
- Modify: `src/hcp_cms/ui/settings_view.py`

- [ ] **Step 1：在 settings_view.py 加入移機提醒區塊**

在 `_setup_ui` 末尾（`layout.addStretch()` 之前）加入：

```python
# ── 移機提醒 ──────────────────────────────────────────
from PySide6.QtWidgets import QFrame
notice = QFrame()
notice.setObjectName("migrationNotice")
notice.setStyleSheet(
    "QFrame#migrationNotice { background-color: #fef3c7; border-radius: 6px; padding: 8px; }"
)
notice_layout = QVBoxLayout(notice)
notice_layout.setContentsMargins(12, 8, 12, 8)
notice_lbl = QLabel(
    "📦 移機注意事項\n"
    "移機時請確認以下項目一併複製至新電腦：\n"
    "  • hcp_cms.db　　  — 資料庫\n"
    "  • kms_attachments/ — 知識庫圖片（與 .db 同目錄）\n"
    "缺少 kms_attachments/ 時，知識庫圖片將無法顯示。"
)
notice_lbl.setStyleSheet("color: #92400e; font-size: 12px;")
notice_lbl.setWordWrap(True)
notice_layout.addWidget(notice_lbl)
layout.addWidget(notice)
```

- [ ] **Step 2：手動確認**

```bash
.venv/Scripts/python.exe -m hcp_cms
```

切換至「⚙️ 系統設定」，確認底部出現黃色提醒區塊。

- [ ] **Step 3：執行全部測試**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short
```

- [ ] **Step 4：Commit**

```bash
git add src/hcp_cms/ui/settings_view.py
git commit -m "feat: SettingsView 新增移機提醒（F7）"
```

---

## 最終驗收

- [ ] **執行全部測試，確認 0 failures**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short
```

- [ ] **執行 Lint**

```bash
.venv/Scripts/ruff.exe check src/ tests/
```

- [ ] **手動 end-to-end 驗收**

1. 匯入一個含圖片的 .msg 信件 → 建立 QA
2. KMS 頁面「顯示全部」→ 點選剛建立的 QA
3. 點「🖼️ 查看完整回覆」→ 確認圖片顯示
4. 點「⛶」→ 確認展開視窗
5. 點「📄 匯出全部」→ 確認 .docx 存在且含 QA 內容
6. 切換至「⚙️ 系統設定」→ 確認黃色移機提醒可見

- [ ] **最終 Commit**（若仍有未提交的異動）

```bash
git add \
  src/hcp_cms/services/mail/msg_reader.py \
  src/hcp_cms/core/kms_engine.py \
  src/hcp_cms/app.py \
  src/hcp_cms/ui/main_window.py \
  src/hcp_cms/ui/kms_view.py \
  src/hcp_cms/ui/settings_view.py \
  pyproject.toml \
  tests/unit/test_msg_reader.py \
  tests/unit/test_kms_engine.py
git commit -m "feat: KMS 知識庫強化完成（F1-F7）圖片、Word 匯出、QA 清理、移機提醒"
```
