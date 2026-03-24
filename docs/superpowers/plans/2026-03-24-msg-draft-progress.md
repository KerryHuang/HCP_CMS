# .msg 草稿寄件人補修與進度標記擷取 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 從 .msg 本文中自動擷取 `==進度:…==` 標記存入 `Case.progress`，並在草稿 .msg（`msg.sender` 為空）時從 body 搜尋 `From: name <email>` 補回正確寄件人。

**Architecture:** `RawEmail` 新增 `progress_note` 欄位；`MSGReader` 負責解析（Services 層）；`CaseManager.create_case()` 消費 `progress_note`（Core 層），body 標記優先於主旨/檔名標記；`EmailView` 補傳欄位（UI 層）。

**Tech Stack:** Python 3.14, re（標準庫）, extract-msg >= 0.48, pytest, PySide6 6.10

---

## 檔案異動清單

| 動作 | 檔案 | 說明 |
|------|------|------|
| 修改 | `src/hcp_cms/services/mail/base.py` | `RawEmail` 新增 `progress_note` |
| 修改 | `src/hcp_cms/services/mail/msg_reader.py` | 解析進度標記 + 草稿寄件人補修 |
| 修改 | `src/hcp_cms/core/case_manager.py` | `create_case()` + `import_email()` 新增 `progress_note` 參數 |
| 修改 | `src/hcp_cms/ui/email_view.py` | `_do_import_rows()` 補傳 `progress_note` |
| 修改 | `tests/unit/test_services.py` | MSGReader 新解析邏輯測試 |
| 修改 | `tests/unit/test_case_manager.py` | `create_case()` / `import_email()` progress_note 測試 |

---

## Task 1：RawEmail 新增欄位 + MSGReader 解析邏輯

**Files:**
- Modify: `src/hcp_cms/services/mail/base.py`
- Modify: `src/hcp_cms/services/mail/msg_reader.py`
- Test: `tests/unit/test_services.py`

### 1-A：RawEmail `progress_note` 欄位

- [ ] **Step 1：寫入失敗測試**

在 `tests/unit/test_services.py` 的 `TestRawEmail` 類別末尾加入：

```python
def test_raw_email_has_progress_note(self):
    email = RawEmail(progress_note="待確認需求")
    assert email.progress_note == "待確認需求"

def test_raw_email_progress_note_default_none(self):
    email = RawEmail()
    assert email.progress_note is None
```

- [ ] **Step 2：執行確認失敗**
```
.venv/Scripts/python.exe -m pytest tests/unit/test_services.py::TestRawEmail::test_raw_email_has_progress_note -v
```
期望：FAILED (TypeError: unexpected keyword argument)

- [ ] **Step 3：在 `src/hcp_cms/services/mail/base.py` 的 `RawEmail` 末尾新增欄位**

緊接在 `html_body: str | None = None` 之後加入：
```python
progress_note: str | None = None
```

- [ ] **Step 4：執行確認通過**
```
.venv/Scripts/python.exe -m pytest tests/unit/test_services.py::TestRawEmail -v
```
期望：全部 PASS

### 1-B：MSGReader 進度標記擷取

- [ ] **Step 5：寫入失敗測試**

在 `tests/unit/test_services.py` 的 `TestMSGReader` 類別末尾加入：

```python
def test_read_msg_file_extracts_progress_note(self, tmp_path, monkeypatch):
    """body 含 ==進度:…== 時，progress_note 應正確擷取。"""
    import types
    fake_msg = types.SimpleNamespace(
        sender="user@customer.com",
        subject="薪資問題",
        body="說明內容\n==進度: 待與jacky確認事項==\n後續文字",
        htmlBody=None,
        date=None,
        attachments=[],
        to="",
    )
    def fake_Message(path):
        fake_msg.close = lambda: None
        return fake_msg
    import extract_msg
    monkeypatch.setattr(extract_msg, "Message", fake_Message)

    result = MSGReader._read_msg_file(tmp_path / "test.msg")
    assert result is not None
    assert result.progress_note == "待與jacky確認事項"

def test_read_msg_file_extracts_multiline_progress(self, tmp_path, monkeypatch):
    """==進度== 跨多行時應完整擷取（含換行）。"""
    import types
    fake_msg = types.SimpleNamespace(
        sender="user@customer.com",
        subject="問題",
        body="前文\n==進度: 第一行\n第二行\n第三行==\n後文",
        htmlBody=None,
        date=None,
        attachments=[],
        to="",
    )
    def fake_Message(path):
        fake_msg.close = lambda: None
        return fake_msg
    import extract_msg
    monkeypatch.setattr(extract_msg, "Message", fake_Message)

    result = MSGReader._read_msg_file(tmp_path / "test.msg")
    assert result is not None
    assert "第一行" in result.progress_note
    assert "第三行" in result.progress_note

def test_read_msg_file_extracts_progress_fullwidth_colon(self, tmp_path, monkeypatch):
    """全形冒號 ==進度：…== 也應正確擷取。"""
    import types
    fake_msg = types.SimpleNamespace(
        sender="user@customer.com",
        subject="問題",
        body="==進度：全形冒號測試==",
        htmlBody=None,
        date=None,
        attachments=[],
        to="",
    )
    def fake_Message(path):
        fake_msg.close = lambda: None
        return fake_msg
    import extract_msg
    monkeypatch.setattr(extract_msg, "Message", fake_Message)

    result = MSGReader._read_msg_file(tmp_path / "test.msg")
    assert result is not None
    assert result.progress_note == "全形冒號測試"

def test_read_msg_file_no_progress_marker_is_none(self, tmp_path, monkeypatch):
    """body 無 ==進度== 標記時，progress_note 應為 None。"""
    import types
    fake_msg = types.SimpleNamespace(
        sender="user@customer.com",
        subject="問題",
        body="正常信件內容，無任何進度標記",
        htmlBody=None,
        date=None,
        attachments=[],
        to="",
    )
    def fake_Message(path):
        fake_msg.close = lambda: None
        return fake_msg
    import extract_msg
    monkeypatch.setattr(extract_msg, "Message", fake_Message)

    result = MSGReader._read_msg_file(tmp_path / "test.msg")
    assert result is not None
    assert result.progress_note is None
```

- [ ] **Step 6：執行確認失敗**
```
.venv/Scripts/python.exe -m pytest tests/unit/test_services.py::TestMSGReader::test_read_msg_file_extracts_progress_note -v
```
期望：FAILED

### 1-C：MSGReader 草稿寄件人補修

- [ ] **Step 7：寫入失敗測試（草稿補修）**

在 `TestMSGReader` 末尾繼續加入：

```python
def test_read_msg_file_draft_sender_from_body_angle_bracket(self, tmp_path, monkeypatch):
    """msg.sender 空白，body 含 'From: Name <email>' → sender 補回。"""
    import types
    fake_msg = types.SimpleNamespace(
        sender="",
        subject="RE: 問題",
        body="From: Nicole_Chang(GLTTCL-張淑雅) <nicole_chang@glthome.com.tw>\n\n信件內容",
        htmlBody=None,
        date=None,
        attachments=[],
        to="",
    )
    def fake_Message(path):
        fake_msg.close = lambda: None
        return fake_msg
    import extract_msg
    monkeypatch.setattr(extract_msg, "Message", fake_Message)

    result = MSGReader._read_msg_file(tmp_path / "draft.msg")
    assert result is not None
    assert result.sender == "nicole_chang@glthome.com.tw"

def test_read_msg_file_draft_sender_from_body_plain_email(self, tmp_path, monkeypatch):
    """msg.sender 空白，body 含純 email 格式 'From: user@domain.com' → fallback regex 補回。"""
    import types
    fake_msg = types.SimpleNamespace(
        sender="",
        subject="RE: 問題",
        body="From: user@glthome.com.tw\n\n信件內容",
        htmlBody=None,
        date=None,
        attachments=[],
        to="",
    )
    def fake_Message(path):
        fake_msg.close = lambda: None
        return fake_msg
    import extract_msg
    monkeypatch.setattr(extract_msg, "Message", fake_Message)

    result = MSGReader._read_msg_file(tmp_path / "draft.msg")
    assert result is not None
    assert result.sender == "user@glthome.com.tw"

def test_read_msg_file_existing_sender_not_overridden(self, tmp_path, monkeypatch):
    """msg.sender 已有值時，body 的 From: 行不應覆蓋 sender。"""
    import types
    fake_msg = types.SimpleNamespace(
        sender="real@customer.com",
        subject="問題",
        body="From: other@example.com\n\n內容",
        htmlBody=None,
        date=None,
        attachments=[],
        to="",
    )
    def fake_Message(path):
        fake_msg.close = lambda: None
        return fake_msg
    import extract_msg
    monkeypatch.setattr(extract_msg, "Message", fake_Message)

    result = MSGReader._read_msg_file(tmp_path / "test.msg")
    assert result is not None
    assert result.sender == "real@customer.com"
```

- [ ] **Step 8：執行確認失敗**
```
.venv/Scripts/python.exe -m pytest tests/unit/test_services.py::TestMSGReader::test_read_msg_file_draft_sender_from_body_angle_bracket -v
```
期望：FAILED

- [ ] **Step 9：修改 `src/hcp_cms/services/mail/msg_reader.py` 的 `_read_msg_file()`**

在 `_read_msg_file()` 方法頂部，**`import extract_msg` 之前**，先在檔案頂部 import 區塊加入（與其他 import 並列）：
```python
import re
```

然後修改 `_read_msg_file()` 方法，在 `html_body` 解析邏輯**之後**、`email = RawEmail(...)` 建立**之前**加入以下兩段：

```python
# ── 進度標記擷取（==進度:…== 或 ==進度：…==，可跨行）──────────────────
body_text = msg.body or ""
_PROGRESS_RE = re.compile(r"==進度[:：]\s*(.*?)==", re.DOTALL | re.IGNORECASE)
_prog_match = _PROGRESS_RE.search(body_text)
progress_note: str | None = _prog_match.group(1).strip() if _prog_match else None

# ── 草稿寄件人補修（msg.sender 空白時從 body 搜尋 From: 行）────────────
sender = msg.sender or ""
if not sender:
    # 優先嘗試 "From: ... <email>" 格式
    _FROM_ANGLE_RE = re.compile(r"^From:\s*[^<\n]*<([^>]+)>", re.MULTILINE)
    _from_match = _FROM_ANGLE_RE.search(body_text)
    if _from_match:
        sender = _from_match.group(1).strip()
    else:
        # Fallback：純 email 格式 "From: user@domain.com"
        _FROM_PLAIN_RE = re.compile(r"^From:\s*(\S+@\S+)", re.MULTILINE)
        _plain_match = _FROM_PLAIN_RE.search(body_text)
        if _plain_match:
            sender = _plain_match.group(1).strip()
```

並修改 `RawEmail(...)` 建立，加入新欄位：
```python
email = RawEmail(
    sender=sender,                     # 改用 sender 變數（可能已補修）
    subject=msg.subject or "",
    body=body_text,                    # 改用 body_text 變數
    date=msg.date or None,
    attachments=[att.longFilename or "" for att in msg.attachments] if msg.attachments else [],
    source_file=file_path.name,
    to_recipients=to_recipients,
    html_body=html_body,
    progress_note=progress_note,       # 新增
)
```

- [ ] **Step 10：執行確認通過**
```
.venv/Scripts/python.exe -m pytest tests/unit/test_services.py -v
```
期望：全部 PASS

- [ ] **Step 11：全部測試回歸**
```
.venv/Scripts/python.exe -m pytest tests/ -v
```
期望：全部 PASS

- [ ] **Step 12：Commit**
```bash
git add src/hcp_cms/services/mail/base.py src/hcp_cms/services/mail/msg_reader.py tests/unit/test_services.py
git commit -m "feat: RawEmail 新增 progress_note，MSGReader 擷取進度標記與補修草稿寄件人"
```

---

## Task 2：CaseManager 消費 progress_note

**Files:**
- Modify: `src/hcp_cms/core/case_manager.py`
- Test: `tests/unit/test_case_manager.py`

**邏輯：** `create_case()` 新增 `progress_note` 參數；body 標記優先於主旨/檔名標記（`progress_note` 有值時覆蓋 `classification["progress"]`）。`import_email()` 同步新增參數並傳遞。

- [ ] **Step 1：寫入失敗測試**

在 `tests/unit/test_case_manager.py` 的 `TestCaseManager` 類別末尾加入：

```python
def test_create_case_with_progress_note(self, seeded_db):
    """create_case(progress_note=…) → case.progress 應寫入 progress_note。"""
    mgr = CaseManager(seeded_db.connection)
    case = mgr.create_case(
        subject="薪資問題",
        body="員工薪資異常",
        sender_email="user@aseglobal.com",
        progress_note="待與jacky確認組織代號",
    )
    assert case.progress == "待與jacky確認組織代號"

def test_create_case_progress_note_overrides_subject_tag(self, seeded_db):
    """body 進度標記應優先於主旨解析出的進度。"""
    mgr = CaseManager(seeded_db.connection)
    # 主旨含 (RD_JACKY)(待確認) 標記
    case = mgr.create_case(
        subject="問題(RD_JACKY)(待確認主旨進度)",
        body="內容",
        sender_email="user@aseglobal.com",
        progress_note="body進度優先",
    )
    assert case.progress == "body進度優先"

def test_create_case_no_progress_note_uses_subject_tag(self, seeded_db):
    """progress_note 為 None 時，仍使用主旨/檔名解析的進度。"""
    mgr = CaseManager(seeded_db.connection)
    case = mgr.create_case(
        subject="問題(RD_JACKY)(待確認)",
        body="內容",
        sender_email="user@aseglobal.com",
        progress_note=None,
    )
    assert case.progress == "待確認"
```

- [ ] **Step 2：執行確認失敗**
```
.venv/Scripts/python.exe -m pytest tests/unit/test_case_manager.py::TestCaseManager::test_create_case_with_progress_note -v
```
期望：FAILED (TypeError: create_case() got an unexpected keyword argument 'progress_note')

- [ ] **Step 3：修改 `src/hcp_cms/core/case_manager.py` 的 `create_case()`**

**3-a：在 `create_case()` 的參數清單加入 `progress_note`（放在 `source_filename` 之後）：**
```python
def create_case(
    self,
    subject: str,
    body: str,
    sender_email: str = "",
    to_recipients: list[str] | None = None,
    sent_time: str | None = None,
    contact_person: str | None = None,
    handler: str | None = None,
    source_filename: str | None = None,
    progress_note: str | None = None,       # 新增
) -> Case:
```

**3-b：在 `Case(...)` 建立之前（`case_id = self._case_repo.next_case_id()` 那塊之後），修改 `progress` 的決策邏輯**

找到現有的：
```python
case = Case(
    ...
    progress=classification.get("progress"),
    ...
)
```

在 `case = Case(...)` 之前加入：
```python
# body ==進度== 標記優先；若無則用主旨/檔名解析結果
final_progress = progress_note.strip() if progress_note else classification.get("progress")
```

並將 `Case(...)` 中的 `progress=classification.get("progress")` 改為：
```python
progress=final_progress,
```

- [ ] **Step 4：修改 `import_email()` 同步新增 `progress_note` 參數並傳遞**

**4-a：在 `import_email()` 參數清單加入 `progress_note`（放在 `source_filename` 之後）：**
```python
def import_email(
    self,
    subject: str,
    body: str,
    sender_email: str = "",
    to_recipients: list[str] | None = None,
    sent_time: str | None = None,
    source_filename: str | None = None,
    progress_note: str | None = None,       # 新增
) -> tuple[Case | None, str]:
```

**4-b：在客戶來信分支的 `create_case()` 呼叫加入 `progress_note`：**

找到：
```python
case = self.create_case(
    subject=subject,
    body=body,
    sender_email=sender_email,
    to_recipients=recipients,
    sent_time=sent_time,
    source_filename=source_filename,
)
```

改為：
```python
case = self.create_case(
    subject=subject,
    body=body,
    sender_email=sender_email,
    to_recipients=recipients,
    sent_time=sent_time,
    source_filename=source_filename,
    progress_note=progress_note,
)
```

- [ ] **Step 5：`TestImportEmail` 補一個整合測試**

在 `tests/unit/test_case_manager.py` 的 `TestImportEmail` 類別末尾加入：

```python
def test_import_email_passes_progress_note_to_case(self, mgr, seeded_db):
    """import_email(progress_note=…) → 建案後 case.progress 正確。"""
    case, action = mgr.import_email(
        subject="組織異動問題",
        body="說明",
        sender_email="user@aseglobal.com",
        to_recipients=["hcpservice@ares.com.tw"],
        progress_note="待確認人天費用",
    )
    assert action == "created"
    assert case is not None
    assert case.progress == "待確認人天費用"
```

- [ ] **Step 6：執行確認通過**
```
.venv/Scripts/python.exe -m pytest tests/unit/test_case_manager.py -v
```
期望：全部 PASS

- [ ] **Step 7：全部測試回歸**
```
.venv/Scripts/python.exe -m pytest tests/ -v
```
期望：全部 PASS

- [ ] **Step 8：Lint**
```
.venv/Scripts/ruff.exe check src/ tests/
```
期望：All checks passed

- [ ] **Step 9：Commit**
```bash
git add src/hcp_cms/core/case_manager.py tests/unit/test_case_manager.py
git commit -m "feat: create_case() / import_email() 新增 progress_note，body 標記優先寫入 case.progress"
```

---

## Task 3：EmailView 補傳 progress_note

**Files:**
- Modify: `src/hcp_cms/ui/email_view.py`

**說明：** `_do_import_rows()` 中呼叫 `manager.import_email()` 時，補傳 `progress_note=email.progress_note`。此為單行修改，不需要新測試（UI 層的 progress_note 傳遞已由 Task 2 的整合測試覆蓋）。

- [ ] **Step 1：修改 `src/hcp_cms/ui/email_view.py`**

找到 `_do_import_rows()` 中的 `manager.import_email(...)` 呼叫（目前約第 272-279 行）：

```python
case, action = manager.import_email(
    subject=email.subject,
    body=email.body,
    sender_email=email.sender,
    to_recipients=email.to_recipients,
    sent_time=str(email.date) if email.date else None,
    source_filename=email.source_file,
)
```

加入 `progress_note` 參數：

```python
case, action = manager.import_email(
    subject=email.subject,
    body=email.body,
    sender_email=email.sender,
    to_recipients=email.to_recipients,
    sent_time=str(email.date) if email.date else None,
    source_filename=email.source_file,
    progress_note=email.progress_note,      # 新增
)
```

- [ ] **Step 2：全部測試確認無回歸**
```
.venv/Scripts/python.exe -m pytest tests/ -v
```
期望：全部 PASS

- [ ] **Step 3：Lint**
```
.venv/Scripts/ruff.exe check src/ tests/
```
期望：All checks passed

- [ ] **Step 4：Commit**
```bash
git add src/hcp_cms/ui/email_view.py
git commit -m "feat: EmailView._do_import_rows() 補傳 progress_note 至 import_email()"
```

---

## 驗收清單

- [ ] 匯入含 `==進度: 文字==` 的 .msg → `case.progress` 顯示該文字
- [ ] 全形冒號 `==進度：文字==` 也能正確擷取
- [ ] 跨行進度標記完整保留換行內容
- [ ] `msg.sender` 為空白的草稿 .msg，body 有 `From: Name <email>` → 公司識別正確
- [ ] 純 email 格式 `From: user@domain.com` 也能補修 sender
- [ ] body 進度標記優先於主旨標記（兩者同時存在時，body 贏）
- [ ] 全部測試通過 `pytest tests/ -v`，lint 無誤
