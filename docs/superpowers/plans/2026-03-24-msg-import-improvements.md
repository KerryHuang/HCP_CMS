# .msg 匯入精準化三項改善 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 改善 .msg 匯入流程：(1) 公司識別改抓客戶而非我方、(2) 來回次數自動計算（區分 hcpservice 回覆 vs 客戶發信）、(3) 畫面直接顯示信件 HTML 內容。

**Architecture:** 在 `RawEmail` 新增 `to_recipients` 與 `html_body` 欄位供後續各層使用；`Classifier` 以 `OUR_DOMAIN = "ares.com.tw"` 識別我方寄件者，改抓收件人 domain 比對公司；`CaseManager` 新增 `import_email()` 智慧派送方法，自動區分「客戶來信（建立新案件）」與「我方回覆（標記父案件已回覆）」；`EmailView` 用 `QSplitter` 加入下半段 `QTextEdit` HTML 預覽。

**Tech Stack:** Python 3.14, PySide6 6.10, extract-msg >= 0.48, pytest, email.utils（標準庫）

---

## 檔案異動清單

| 動作 | 檔案 | 說明 |
|------|------|------|
| 修改 | `src/hcp_cms/services/mail/base.py` | RawEmail 新增 `to_recipients`, `html_body` |
| 修改 | `src/hcp_cms/services/mail/msg_reader.py` | 讀取 `msg.to` 與 `msg.htmlBody` |
| 修改 | `src/hcp_cms/core/classifier.py` | 新增 `OUR_DOMAIN`，`classify()` 接收 `to_recipients`，我方寄件改用收件人識別公司 |
| 修改 | `src/hcp_cms/core/case_manager.py` | 新增 `import_email()` 方法 |
| 修改 | `src/hcp_cms/ui/email_view.py` | 加入 HTML 預覽面板，儲存 RawEmail 列表，選取列時顯示內容 |
| 修改 | `tests/unit/test_services.py` | RawEmail 新欄位測試 + MSGReader mock 測試 |
| 修改 | `tests/unit/test_classifier.py` | 我方寄件人識別公司測試 |
| 修改 | `tests/unit/test_case_manager.py` | `import_email()` 測試 |
| 修改 | `tests/unit/test_ui.py` | EmailView 預覽欄位存在測試 |

---

## Task 1：RawEmail 新增欄位 + MSGReader 讀取

**Files:**
- Modify: `src/hcp_cms/services/mail/base.py`
- Modify: `src/hcp_cms/services/mail/msg_reader.py`
- Test: `tests/unit/test_services.py`

### 1-A：RawEmail 新欄位測試

- [ ] **Step 1：寫入失敗測試**

在 `tests/unit/test_services.py` 的 `TestRawEmail` 類別末尾加入：

```python
def test_raw_email_has_to_recipients(self):
    email = RawEmail(to_recipients=["a@foo.com", "b@bar.com"])
    assert email.to_recipients == ["a@foo.com", "b@bar.com"]

def test_raw_email_to_recipients_default_empty(self):
    email = RawEmail()
    assert email.to_recipients == []

def test_raw_email_has_html_body(self):
    email = RawEmail(html_body="<p>Hello</p>")
    assert email.html_body == "<p>Hello</p>"

def test_raw_email_html_body_default_none(self):
    email = RawEmail()
    assert email.html_body is None
```

- [ ] **Step 2：執行確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_services.py::TestRawEmail -v
```
期望：`FAILED` (AttributeError: unexpected keyword argument)

- [ ] **Step 3：修改 `base.py` 新增欄位**

在 `RawEmail` dataclass 末尾加入兩個欄位（`source_file` 之後）：

```python
to_recipients: list[str] = field(default_factory=list)
html_body: str | None = None
```

- [ ] **Step 4：執行確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_services.py::TestRawEmail -v
```
期望：全部 PASS

### 1-B：MSGReader 讀取 to_recipients 與 html_body

- [ ] **Step 5：寫入 MSGReader mock 測試**

在 `tests/unit/test_services.py` 的 `TestMSGReader` 類別末尾加入：

```python
def test_read_msg_file_parses_to_recipients(self, tmp_path, monkeypatch):
    """_read_msg_file 應解析 msg.to 為 to_recipients list。"""
    import types

    fake_msg = types.SimpleNamespace(
        sender="hcpservice@ares.com.tw",
        subject="回覆：薪資問題",
        body="已處理",
        htmlBody=b"<p>\xe5\xb7\xb2\xe8\x99\x95\xe7\x90\x86</p>",
        date="2026/03/20 10:00",
        attachments=[],
        to="客戶 <user@customer.com>; other@customer.com",
    )

    def fake_Message(path):
        fake_msg.close = lambda: None
        return fake_msg

    import extract_msg
    monkeypatch.setattr(extract_msg, "Message", fake_Message)

    result = MSGReader._read_msg_file(tmp_path / "test.msg")
    assert result is not None
    assert "user@customer.com" in result.to_recipients
    assert "other@customer.com" in result.to_recipients

def test_read_msg_file_parses_html_body(self, tmp_path, monkeypatch):
    """_read_msg_file 應將 msg.htmlBody bytes 解碼為 html_body str。"""
    import types

    fake_msg = types.SimpleNamespace(
        sender="user@customer.com",
        subject="薪資問題",
        body="純文字",
        htmlBody=b"<p>HTML\xe5\x85\xa7\xe5\xae\xb9</p>",
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
    assert result.html_body is not None
    assert "<p>" in result.html_body

def test_read_msg_file_html_body_none_when_missing(self, tmp_path, monkeypatch):
    """msg.htmlBody 為 None 時，html_body 應為 None。"""
    import types

    fake_msg = types.SimpleNamespace(
        sender="user@customer.com",
        subject="Test",
        body="plain",
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
    assert result.html_body is None
```

- [ ] **Step 6：執行確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_services.py::TestMSGReader::test_read_msg_file_parses_to_recipients tests/unit/test_services.py::TestMSGReader::test_read_msg_file_parses_html_body tests/unit/test_services.py::TestMSGReader::test_read_msg_file_html_body_none_when_missing -v
```
期望：FAILED

- [ ] **Step 7：修改 `msg_reader.py` 的 `_read_msg_file()`**

在 `_read_msg_file()` 中，於 `import extract_msg` 後新增輔助 import，並修改回傳的 `RawEmail`：

```python
@staticmethod
def _read_msg_file(file_path: Path) -> RawEmail | None:
    """Parse a .msg file using extract-msg."""
    try:
        import extract_msg
        from email.utils import getaddresses

        msg = extract_msg.Message(file_path)

        # 解析收件人列表：msg.to 可能是 "Name <email>; email2" 格式
        raw_to = msg.to or ""
        # getaddresses 接受 list[str]，以 "," 或 ";" 分隔均可
        normalized = raw_to.replace(";", ",")
        to_recipients = [
            addr for _, addr in getaddresses([normalized]) if addr
        ]

        # 解析 HTML body（bytes → str，嘗試 UTF-8 後 fallback cp950）
        html_body: str | None = None
        raw_html = getattr(msg, "htmlBody", None)
        if raw_html:
            if isinstance(raw_html, bytes):
                try:
                    html_body = raw_html.decode("utf-8")
                except UnicodeDecodeError:
                    html_body = raw_html.decode("cp950", errors="replace")
            else:
                html_body = str(raw_html)

        email = RawEmail(
            sender=msg.sender or "",
            subject=msg.subject or "",
            body=msg.body or "",
            date=msg.date or None,
            attachments=[att.longFilename or "" for att in msg.attachments] if msg.attachments else [],
            source_file=file_path.name,
            to_recipients=to_recipients,
            html_body=html_body,
        )
        msg.close()
        return email
    except Exception:
        return None
```

- [ ] **Step 8：執行確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_services.py -v
```
期望：全部 PASS

- [ ] **Step 9：Commit**

```bash
git add src/hcp_cms/services/mail/base.py src/hcp_cms/services/mail/msg_reader.py tests/unit/test_services.py
git commit -m "feat: RawEmail 新增 to_recipients / html_body，MSGReader 讀取收件人與 HTML 內容"
```

---

## Task 2：Classifier 識別我方寄件，改抓收件人公司

**Files:**
- Modify: `src/hcp_cms/core/classifier.py`
- Test: `tests/unit/test_classifier.py`

### 2-A：我方寄件人公司識別測試

- [ ] **Step 1：寫入失敗測試**

在 `tests/unit/test_classifier.py` 的 `TestClassifier` 類別末尾加入：

```python
def test_classify_our_side_sender_uses_recipient(self, seeded_db):
    """sender 為我方（ares.com.tw）時，公司應從 to_recipients 識別。"""
    c = Classifier(seeded_db.connection)
    result = c.classify(
        "RE: 薪資問題",
        "已處理",
        sender_email="hcpservice@ares.com.tw",
        to_recipients=["user@aseglobal.com"],
    )
    assert result["company_id"] == "C-ASE"
    assert result["company_display"] == "日月光集團"

def test_classify_our_side_sender_skips_ares_recipients(self, seeded_db):
    """to_recipients 中若有多個地址，應跳過 ares.com.tw，用第一個非我方地址。"""
    c = Classifier(seeded_db.connection)
    result = c.classify(
        "RE: 測試",
        "body",
        sender_email="hcpservice@ares.com.tw",
        to_recipients=["internal@ares.com.tw", "user@aseglobal.com"],
    )
    assert result["company_id"] == "C-ASE"

def test_classify_our_side_sender_no_usable_recipient(self, seeded_db):
    """我方寄件但收件人也全是我方時，company_id 應為 None。"""
    c = Classifier(seeded_db.connection)
    result = c.classify(
        "RE: 內部信",
        "body",
        sender_email="hcpservice@ares.com.tw",
        to_recipients=["other@ares.com.tw"],
    )
    assert result["company_id"] is None

def test_classify_our_side_sender_empty_recipients(self, seeded_db):
    """我方寄件但 to_recipients 為空時，company_id 應為 None。"""
    c = Classifier(seeded_db.connection)
    result = c.classify(
        "RE: 測試",
        "body",
        sender_email="hcpservice@ares.com.tw",
        to_recipients=[],
    )
    assert result["company_id"] is None

def test_classify_customer_sender_unchanged_behavior(self, seeded_db):
    """非我方寄件人時，行為與修改前一致，使用 sender_email。"""
    c = Classifier(seeded_db.connection)
    result = c.classify(
        "薪資問題",
        "body",
        sender_email="user@aseglobal.com",
        to_recipients=["hcpservice@ares.com.tw"],
    )
    assert result["company_id"] == "C-ASE"
```

- [ ] **Step 2：執行確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_classifier.py::TestClassifier::test_classify_our_side_sender_uses_recipient -v
```
期望：FAILED (TypeError: classify() got an unexpected keyword argument 'to_recipients')

- [ ] **Step 3：修改 `classifier.py`**

**重要約束：** `to_recipients` 必須放在 `sender_email` **之後**且有預設值，確保現有所有以位置參數呼叫 `classify("subj", "body")` 的舊測試不受影響。

在 `classifier.py` 頂部（`import re` 等 import 區塊之後）新增常數（**不可放在方法之間**）：
```python
OUR_DOMAIN = "ares.com.tw"
```

修改 `classify()` 簽章（`to_recipients` 在 `sender_email` 之後，兩者皆有預設值）：
```python
def classify(self, subject: str, body: str, sender_email: str = "", to_recipients: list[str] | None = None) -> dict:
```

修改 `classify()` 內部，將 `_resolve_company()` 呼叫改為：
```python
company_id, company_display = self._resolve_company(sender_email, to_recipients or [])
```

修改 `_resolve_company()` 簽章與邏輯：
```python
def _resolve_company(self, sender_email: str, to_recipients: list[str] | None = None) -> tuple[str | None, str | None]:
    """Resolve company from sender, or recipients if sender is our side."""
    # 判斷是否為我方寄件
    if sender_email and "@" in sender_email:
        from email.utils import parseaddr
        _, addr = parseaddr(sender_email)
        sender_domain = addr.split("@")[1].lower() if "@" in addr else ""
        if sender_domain == OUR_DOMAIN or sender_domain.endswith(f".{OUR_DOMAIN}"):
            # 我方寄件：委託公開方法從收件人解析公司
            return self.resolve_external_company(to_recipients or [])

    return self._lookup_by_email(sender_email)
```

在 `Classifier` 類別中新增一個**公開**方法與一個私有輔助方法：
```python
def resolve_external_company(self, recipients: list[str]) -> tuple[str | None, str | None]:
    """從收件人列表中找第一個非我方地址，回傳其公司 (company_id, display)。
    供 CaseManager 等同層 Core 類別呼叫。
    """
    from email.utils import parseaddr
    for r in recipients:
        _, addr = parseaddr(r)
        if not addr:
            addr = r
        if "@" in addr:
            domain = addr.split("@")[1].lower()
            if domain != OUR_DOMAIN and not domain.endswith(f".{OUR_DOMAIN}"):
                return self._lookup_by_email(addr)
    return None, None

def _lookup_by_email(self, email_str: str) -> tuple[str | None, str | None]:
    """Look up company_id and display name from an email address string."""
    if not email_str or "@" not in email_str:
        return None, None
    from email.utils import parseaddr
    _, addr = parseaddr(email_str)
    if not addr or "@" not in addr:
        addr = email_str
    domain = addr.split("@")[1].lower().rstrip(">").strip()
    company = self._company_repo.get_by_domain(domain)
    if company:
        return company.company_id, company.name
    parts = domain.split(".")
    fallback_domain = domain
    if len(parts) > 2:
        fallback_domain = ".".join(parts[1:])
        company = self._company_repo.get_by_domain(fallback_domain)
        if company:
            return company.company_id, company.name
    return None, fallback_domain
```

並將舊的 `_resolve_company()` 方法中原本重複的 domain lookup 邏輯**全部移到 `_lookup_by_email()`**，舊方法改為呼叫新方法（DRY）。

- [ ] **Step 4：執行確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_classifier.py -v
```
期望：全部 PASS（含舊測試）

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/core/classifier.py tests/unit/test_classifier.py
git commit -m "feat: Classifier 識別我方寄件（ares.com.tw），改從收件人解析客戶公司"
```

---

## Task 3：CaseManager.import_email() 智慧派送

**Files:**
- Modify: `src/hcp_cms/core/case_manager.py`
- Test: `tests/unit/test_case_manager.py`

**邏輯說明：**
- sender domain 為 `ares.com.tw` → 我方回覆信：找父案件 → `mark_replied()` → 回傳 `(parent, "replied")`
- sender domain 非 `ares.com.tw` → 客戶來信：走原 `create_case()` → 回傳 `(case, "created")`
- 我方回覆但找不到父案件 → 回傳 `(None, "skipped")`

### 3-A：import_email() 測試

- [ ] **Step 1：寫入失敗測試**

在 `tests/unit/test_case_manager.py` 末尾加入新測試類別（`TestCaseManager` 類別之外）：

```python
class TestImportEmail:
    """測試 import_email() 智慧派送邏輯。"""

    @pytest.fixture
    def mgr(self, seeded_db):
        return CaseManager(seeded_db.connection)

    def test_customer_email_creates_case(self, mgr):
        """客戶發信 → 建立新案件，action 為 'created'。"""
        case, action = mgr.import_email(
            subject="薪資問題",
            body="員工薪資異常",
            sender_email="user@aseglobal.com",
            to_recipients=["hcpservice@ares.com.tw"],
            sent_time="2026/03/20 09:00",
        )
        assert action == "created"
        assert case is not None
        assert case.case_id.startswith("CS-")

    def test_our_reply_marks_parent_replied(self, mgr, seeded_db):
        """我方回覆 → 找到父案件並標記已回覆，action 為 'replied'。"""
        # 先建立父案件（客戶來信）
        parent, _ = mgr.import_email(
            subject="薪資計算問題",
            body="有異常",
            sender_email="user@aseglobal.com",
            to_recipients=["hcpservice@ares.com.tw"],
            sent_time="2026/03/20 09:00",
        )
        assert parent is not None

        # 我方回覆
        result_case, action = mgr.import_email(
            subject="RE: 薪資計算問題",
            body="已處理",
            sender_email="hcpservice@ares.com.tw",
            to_recipients=["user@aseglobal.com"],
            sent_time="2026/03/20 10:00",
        )
        assert action == "replied"
        assert result_case is not None
        assert result_case.case_id == parent.case_id

        # 確認父案件狀態更新
        from hcp_cms.data.repositories import CaseRepository
        updated = CaseRepository(seeded_db.connection).get_by_id(parent.case_id)
        assert updated.status == "已回覆"
        assert updated.reply_count == 1

    def test_our_reply_increments_reply_count(self, mgr, seeded_db):
        """我方每次回覆都應讓 reply_count +1。"""
        parent, _ = mgr.import_email(
            subject="問題追蹤",
            body="內容",
            sender_email="user@aseglobal.com",
            to_recipients=["hcpservice@ares.com.tw"],
            sent_time="2026/03/20 09:00",
        )

        mgr.import_email(
            subject="RE: 問題追蹤",
            body="第一次回覆",
            sender_email="hcpservice@ares.com.tw",
            to_recipients=["user@aseglobal.com"],
            sent_time="2026/03/20 10:00",
        )
        mgr.import_email(
            subject="RE: 問題追蹤",
            body="第二次回覆",
            sender_email="hcpservice@ares.com.tw",
            to_recipients=["user@aseglobal.com"],
            sent_time="2026/03/21 10:00",
        )

        from hcp_cms.data.repositories import CaseRepository
        updated = CaseRepository(seeded_db.connection).get_by_id(parent.case_id)
        assert updated.reply_count == 2

    def test_our_reply_no_parent_skipped(self, mgr):
        """我方回覆但找不到父案件 → action 為 'skipped'，case 為 None。"""
        case, action = mgr.import_email(
            subject="RE: 完全不存在的案件",
            body="回覆",
            sender_email="hcpservice@ares.com.tw",
            to_recipients=["user@aseglobal.com"],
            sent_time="2026/03/20 10:00",
        )
        assert action == "skipped"
        assert case is None
```

- [ ] **Step 2：執行確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_case_manager.py::TestImportEmail -v
```
期望：FAILED (AttributeError: 'CaseManager' object has no attribute 'import_email')

- [ ] **Step 3：在 `case_manager.py` 新增 `import_email()` 方法**

首先，在 `case_manager.py` **檔案頂部的 import 區塊**新增（與其他 import 放在一起，不可放在方法之間）：
```python
from email.utils import parseaddr
from hcp_cms.core.classifier import OUR_DOMAIN
```

然後在 `CaseManager` 類別，`create_case()` 方法之前加入新方法：

```python
def import_email(
    self,
    subject: str,
    body: str,
    sender_email: str = "",
    to_recipients: list[str] | None = None,
    sent_time: str | None = None,
    source_filename: str | None = None,
) -> tuple["Case | None", str]:
    """智慧匯入：自動判斷客戶來信或我方回覆。

    Returns:
        (case, action) — action 為 'created' / 'replied' / 'skipped'
    """
    recipients = to_recipients or []

    # 判斷是否為我方寄件
    _, addr = parseaddr(sender_email)
    if not addr:
        addr = sender_email
    sender_domain = addr.split("@")[1].lower() if "@" in addr else ""
    is_our_side = sender_domain == OUR_DOMAIN or sender_domain.endswith(f".{OUR_DOMAIN}")

    if is_our_side:
        # 我方回覆：呼叫 Classifier 公開方法取得客戶公司，再比對父案件
        company_id, _ = self._classifier.resolve_external_company(recipients)
        parent = self._tracker.find_thread_parent(company_id, subject)
        if not parent:
            return None, "skipped"
        self.mark_replied(parent.case_id, sent_time)
        updated = self._case_repo.get_by_id(parent.case_id)
        return updated, "replied"

    # 客戶來信：走正常建案流程（帶 to_recipients 給 Classifier）
    case = self.create_case(
        subject=subject,
        body=body,
        sender_email=sender_email,
        to_recipients=recipients,
        sent_time=sent_time,
        source_filename=source_filename,
    )
    return case, "created"
```

同時修改 `create_case()` 簽章加入 `to_recipients` 參數，並傳給 `classify()`：

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
) -> Case:
    # 修改 classify 呼叫：
    classification = self._classifier.classify(subject, body, sender_email, to_recipients or [])
    # ... 其餘不變
```

- [ ] **Step 4：執行確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_case_manager.py -v
```
期望：全部 PASS

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/core/case_manager.py tests/unit/test_case_manager.py
git commit -m "feat: CaseManager.import_email() 自動識別我方回覆，分別建案或標記已回覆"
```

---

## Task 4：EmailView HTML 預覽面板

**Files:**
- Modify: `src/hcp_cms/ui/email_view.py`
- Test: `tests/unit/test_ui.py`（基本存在性測試）

**設計說明：**
- 用 `QSplitter(Qt.Vertical)` 將現有列表（上）與新增預覽區（下）分開
- 預覽區使用 `QWebEngineView`（完整瀏覽器渲染），呼叫 `setHtml()` 顯示 HTML
- 信件有 HTML body → 直接 `setHtml()`，注入深色背景 CSS
- 信件無 HTML body → 將純文字包在 `<pre>` 標籤中，同樣套用深色 CSS
- 無選取 / 無法讀取 → 顯示佔位符 HTML
- `self._emails: list[RawEmail | None]` 與 `self._pending_files` 平行儲存
- 選取行時呼叫 `_on_row_selected()`

### 4-A：UI 存在性測試

- [ ] **Step 1：寫入失敗測試**

在 `tests/unit/test_ui.py` 末尾加入：

```python
class TestEmailView:
    def test_email_view_has_preview_widget(self, qapp):
        from hcp_cms.ui.email_view import EmailView
        from PySide6.QtWebEngineWidgets import QWebEngineView
        view = EmailView()
        # 確認預覽用 QWebEngineView 存在
        assert hasattr(view, "_preview")
        assert isinstance(view._preview, QWebEngineView)

    def test_email_view_has_emails_list(self, qapp):
        from hcp_cms.ui.email_view import EmailView
        view = EmailView()
        assert hasattr(view, "_emails")
        assert isinstance(view._emails, list)
```

- [ ] **Step 2：執行確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_ui.py::TestEmailView -v
```
期望：FAILED (AttributeError: 'EmailView' object has no attribute '_preview')

### 4-B：改寫 EmailView

- [ ] **Step 3：修改 `email_view.py`**

**改動一：新增 import**

在既有 `from PySide6.QtWidgets import ...` 區塊中加入 `QSplitter`，並在其下方新增一行：

```python
from PySide6.QtCore import QDate, Qt
from PySide6.QtWebEngineWidgets import QWebEngineView   # 新增
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,          # 新增
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
```

**改動二：`__init__` 新增 `_emails` 列表**
```python
def __init__(self, conn: sqlite3.Connection | None = None) -> None:
    super().__init__()
    self._conn = conn
    self._pending_files: list[Path] = []
    self._emails: list[RawEmail | None] = []   # 與 _pending_files 平行
    self._setup_ui()
```

**改動三：`_setup_ui()` 將列表和預覽包入 QSplitter**

將原本的：
```python
self._table = QTableWidget(0, 5)
...
layout.addWidget(self._table)
```

替換為：
```python
splitter = QSplitter(Qt.Orientation.Vertical)

# 上半：信件列表
self._table = QTableWidget(0, 5)
self._table.setHorizontalHeaderLabels(["✓", "寄件人", "主旨", "日期", "狀態"])
self._table.horizontalHeader().setStretchLastSection(True)
self._table.setColumnWidth(0, 30)
self._table.itemSelectionChanged.connect(self._on_row_selected)
splitter.addWidget(self._table)

# 下半：信件內容預覽（QWebEngineView 完整瀏覽器渲染）
self._preview = QWebEngineView()
self._preview.setHtml(self._placeholder_html())
splitter.addWidget(self._preview)

splitter.setSizes([300, 250])
layout.addWidget(splitter)
```

**改動四：新增兩個輔助方法**

```python
# ── 預覽輔助 ──────────────────────────────────────────────
_BASE_STYLE = (
    "body{margin:16px;font-family:'Segoe UI',Arial,sans-serif;"
    "font-size:13px;background:#1e293b;color:#e2e8f0;}"
    "pre{white-space:pre-wrap;word-break:break-word;}"
    "a{color:#60a5fa;}"
    "blockquote{border-left:3px solid #4b5563;margin:0;padding-left:12px;color:#94a3b8;}"
)

def _placeholder_html(self) -> str:
    return f"<html><head><style>{self._BASE_STYLE}</style></head><body><p style='color:#64748b'>點選信件以預覽內容…</p></body></html>"

def _wrap_plain(self, text: str) -> str:
    from html import escape
    return f"<html><head><style>{self._BASE_STYLE}</style></head><body><pre>{escape(text)}</pre></body></html>"

def _inject_style(self, html: str) -> str:
    """在信件 HTML 中注入深色背景 CSS（插入 <head>，若無則包一層）。"""
    tag = f"<style>{self._BASE_STYLE}</style>"
    lower = html.lower()
    if "<head>" in lower:
        pos = lower.index("<head>") + len("<head>")
        return html[:pos] + tag + html[pos:]
    return f"<html><head>{tag}</head><body>{html}</body></html>"
```

**改動五：`_on_import_msg()` 同步維護 `_emails`**

在方法開頭清空列表時一起清空：
```python
self._emails = []
```

在解析每個檔案後，同步 append：
```python
email = reader.read_single_file(file_path)
self._emails.append(email)   # 與 _pending_files 平行，可為 None
```

**改動六：新增 `_on_row_selected()` slot**

```python
def _on_row_selected(self) -> None:
    """顯示選中行的信件內容（HTML 優先，fallback 純文字 → 包入 pre）。"""
    selected = self._table.selectedItems()
    if not selected:
        return
    row = self._table.row(selected[0])
    if row >= len(self._emails):
        return
    email = self._emails[row]
    if email is None:
        self._preview.setHtml(self._wrap_plain("（無法讀取信件內容）"))
        return
    if email.html_body:
        self._preview.setHtml(self._inject_style(email.html_body))
    else:
        self._preview.setHtml(self._wrap_plain(email.body))
```

**改動六：`_do_import_rows()` 改用 `import_email()`**

將原本：
```python
manager.create_case(
    subject=email.subject,
    body=email.body,
    sender_email=email.sender,
    sent_time=str(email.date) if email.date else None,
    source_filename=email.source_file,
)
self._table.setItem(row, 4, QTableWidgetItem("已匯入"))
```

替換為：
```python
case, action = manager.import_email(
    subject=email.subject,
    body=email.body,
    sender_email=email.sender,
    to_recipients=email.to_recipients,
    sent_time=str(email.date) if email.date else None,
    source_filename=email.source_file,
)
label = {"created": "已匯入", "replied": "已回覆標記", "skipped": "略過（找不到父案件）"}.get(action, "已匯入")
self._table.setItem(row, 4, QTableWidgetItem(label))
```

- [ ] **Step 4：執行確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_ui.py::TestEmailView -v
```
期望：全部 PASS

- [ ] **Step 5：完整測試回歸**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```
期望：全部 PASS，無回歸

- [ ] **Step 6：Commit**

```bash
git add src/hcp_cms/ui/email_view.py tests/unit/test_ui.py
git commit -m "feat: EmailView 加入 HTML 信件預覽面板，匯入時區分建案/回覆標記/略過"
```

---

## 驗收清單

- [ ] 匯入客戶 .msg → 公司顯示客戶公司名稱（非 hcpservice 的 ares.com.tw）
- [ ] 匯入 hcpservice 的回覆 .msg → 狀態欄顯示「已回覆標記」，父案件 reply_count +1
- [ ] 匯入 hcpservice 的回覆但找不到父案件 → 狀態欄顯示「略過（找不到父案件）」
- [ ] 點選信件列表 → 下方預覽顯示 HTML 格式信件內容
- [ ] 無 HTML body 的信件 → 預覽顯示純文字 body
- [ ] 全部測試通過 `pytest tests/ -v`
