# MSG QA 自動抽取 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 匯入 .MSG 信件時自動切割對話串、抽取問答，儲存為「待審核」KMS 條目，由人工在 KMSView 確認後才進入 FTS 搜尋索引。

**Architecture:** Services 層（MSGReader）切割 body 為 thread_question / thread_answer；Core 層（KMSEngine）以 status 欄位區分「待審核」／「已完成」並管制 FTS 寫入；UI 層（EmailView 呼叫 KMSEngine、KMSView 提供審核對話框）。

**Tech Stack:** Python 3.14、PySide6 6.10、SQLite FTS5、pytest、extract-msg

---

## 檔案異動總覽

| 動作 | 檔案路徑 |
|------|----------|
| 修改 | `src/hcp_cms/data/models.py` |
| 修改 | `src/hcp_cms/data/database.py` |
| 修改 | `src/hcp_cms/data/migration.py` |
| 修改 | `src/hcp_cms/data/repositories.py` |
| 修改 | `src/hcp_cms/services/mail/base.py` |
| 修改 | `src/hcp_cms/services/mail/msg_reader.py` |
| 修改 | `src/hcp_cms/core/kms_engine.py` |
| 修改 | `src/hcp_cms/ui/email_view.py` |
| 修改 | `src/hcp_cms/ui/kms_view.py` |
| 修改 | `src/hcp_cms/ui/main_window.py` |
| 修改 | `tests/unit/test_kms_engine.py` |
| 修改 | `tests/unit/test_repositories.py` |
| 修改 | `tests/unit/test_services.py` |
| 新增 | `tests/integration/test_msg_qa_extraction.py` |

**實作順序（Law 3 TDD 層次）：** data → services → core → ui

---

## Task 1：QAKnowledge 加入 status 欄位（Data Model + DDL + Migration）

**Files:**
- Modify: `src/hcp_cms/data/models.py`
- Modify: `src/hcp_cms/data/database.py`
- Modify: `src/hcp_cms/data/migration.py`
- Test: `tests/unit/test_models.py`
- Test: `tests/unit/test_database.py`
- Test: `tests/unit/test_migration.py`

- [ ] **Step 1：寫 model 欄位測試**

在 `tests/unit/test_models.py` 末尾加入：

```python
class TestQAKnowledgeStatus:
    def test_default_status_is_已完成(self):
        from hcp_cms.data.models import QAKnowledge
        qa = QAKnowledge(qa_id="QA-001", question="q", answer="a")
        assert qa.status == "已完成"

    def test_status_可設為待審核(self):
        from hcp_cms.data.models import QAKnowledge
        qa = QAKnowledge(qa_id="QA-001", question="q", answer="a", status="待審核")
        assert qa.status == "待審核"
```

- [ ] **Step 2：執行測試，確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_models.py::TestQAKnowledgeStatus -v
```

預期：`TypeError: QAKnowledge.__init__() got an unexpected keyword argument 'status'`

- [ ] **Step 3：在 `models.py` 的 QAKnowledge 加入 status 欄位**

在 `src/hcp_cms/data/models.py` 第 79 行（`notes` 欄位之前）插入：

```python
    status: str = "已完成"    # '待審核' | '已完成'
```

- [ ] **Step 4：執行測試，確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_models.py::TestQAKnowledgeStatus -v
```

- [ ] **Step 5：寫 DDL 測試**

在 `tests/unit/test_database.py` 末尾加入：

```python
class TestQAKnowledgeStatusColumn:
    def test_qa_knowledge_has_status_column(self, tmp_db_path):
        from hcp_cms.data.database import DatabaseManager
        db = DatabaseManager(tmp_db_path)
        db.initialize()
        cols = {row[1] for row in db.connection.execute("PRAGMA table_info(qa_knowledge)")}
        db.close()
        assert "status" in cols

    def test_status_default_is_已完成(self, tmp_db_path):
        from hcp_cms.data.database import DatabaseManager
        db = DatabaseManager(tmp_db_path)
        db.initialize()
        db.connection.execute(
            "INSERT INTO qa_knowledge (qa_id, question, answer) VALUES ('QA-T01', 'q', 'a')"
        )
        db.connection.commit()
        row = db.connection.execute(
            "SELECT status FROM qa_knowledge WHERE qa_id = 'QA-T01'"
        ).fetchone()
        db.close()
        assert row[0] == "已完成"
```

- [ ] **Step 6：執行測試，確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_database.py::TestQAKnowledgeStatusColumn -v
```

- [ ] **Step 7：修改 `database.py` DDL，在 `source` 欄位之後加入 `status`**

在 `src/hcp_cms/data/database.py` 找到 `qa_knowledge` DDL，將：
```sql
    source TEXT DEFAULT 'manual',
    created_by TEXT,
```
改為：
```sql
    source TEXT DEFAULT 'manual',
    status TEXT DEFAULT '已完成',
    created_by TEXT,
```

- [ ] **Step 8：執行測試，確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_database.py::TestQAKnowledgeStatusColumn -v
```

- [ ] **Step 9：寫 migration 冪等測試**

在 `tests/unit/test_migration.py` 末尾加入：

```python
class TestQAStatusMigration:
    def test_alter_table_冪等(self, tmp_path):
        import sqlite3
        from hcp_cms.data.migration import _add_qa_status_column
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.execute(
            "CREATE TABLE qa_knowledge (qa_id TEXT PRIMARY KEY, question TEXT, answer TEXT)"
        )
        conn.commit()
        _add_qa_status_column(conn)
        _add_qa_status_column(conn)   # 第二次不拋例外
        cols = {row[1] for row in conn.execute("PRAGMA table_info(qa_knowledge)")}
        conn.close()
        assert "status" in cols
```

- [ ] **Step 10：執行測試，確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_migration.py::TestQAStatusMigration -v
```

- [ ] **Step 11：在 `migration.py` 新增輔助函數並呼叫**

在 `src/hcp_cms/data/migration.py` 的 import 區確認有 `import sqlite3`。
在類別**外**（模組層）新增：

```python
def _add_qa_status_column(conn: sqlite3.Connection) -> None:
    """替既有 qa_knowledge 表加入 status 欄位，冪等（欄位已存在時跳過）。"""
    try:
        conn.execute("ALTER TABLE qa_knowledge ADD COLUMN status TEXT DEFAULT '已完成'")
        conn.commit()
    except sqlite3.OperationalError:
        pass
```

在 `MigrationManager._migrate()` 方法的 `self._new.commit()` 之前插入：

```python
        _add_qa_status_column(self._new)
```

- [ ] **Step 12：執行測試，確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_migration.py::TestQAStatusMigration -v
```

- [ ] **Step 13：執行全體測試，確認無回歸**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

- [ ] **Step 14：Commit**

```bash
git add src/hcp_cms/data/models.py src/hcp_cms/data/database.py src/hcp_cms/data/migration.py tests/unit/test_models.py tests/unit/test_database.py tests/unit/test_migration.py
git commit -m "feat: QAKnowledge 加入 status 欄位，DDL 與 migration 同步更新"
```

---

## Task 2：QARepository 支援 status 欄位

**Files:**
- Modify: `src/hcp_cms/data/repositories.py`
- Test: `tests/unit/test_repositories.py`

- [ ] **Step 1：寫 insert / update 持久化測試**

在 `tests/unit/test_repositories.py` 末尾加入（確認頂部已 import `QAKnowledge`、`QARepository`、`DatabaseManager`）：

```python
class TestQARepositoryStatus:
    @pytest.fixture
    def db(self, tmp_db_path):
        from hcp_cms.data.database import DatabaseManager
        db = DatabaseManager(tmp_db_path)
        db.initialize()
        yield db
        db.close()

    @pytest.fixture
    def repo(self, db):
        from hcp_cms.data.repositories import QARepository
        return QARepository(db.connection)

    def test_insert_status_待審核(self, repo):
        from hcp_cms.data.models import QAKnowledge
        qa = QAKnowledge(qa_id="QA-S01", question="q", answer="a", status="待審核")
        repo.insert(qa)
        assert repo.get_by_id("QA-S01").status == "待審核"

    def test_insert_status_default_已完成(self, repo):
        from hcp_cms.data.models import QAKnowledge
        qa = QAKnowledge(qa_id="QA-S02", question="q", answer="a")
        repo.insert(qa)
        assert repo.get_by_id("QA-S02").status == "已完成"

    def test_update_status_持久化(self, repo):
        from hcp_cms.data.models import QAKnowledge
        qa = QAKnowledge(qa_id="QA-S03", question="q", answer="a", status="待審核")
        repo.insert(qa)
        qa.status = "已完成"
        repo.update(qa)
        assert repo.get_by_id("QA-S03").status == "已完成"

    def test_list_by_status_待審核(self, repo):
        from hcp_cms.data.models import QAKnowledge
        repo.insert(QAKnowledge(qa_id="QA-S04", question="q1", answer="a", status="待審核"))
        repo.insert(QAKnowledge(qa_id="QA-S05", question="q2", answer="a", status="已完成"))
        pending = repo.list_by_status("待審核")
        assert len(pending) == 1
        assert pending[0].qa_id == "QA-S04"

    def test_list_approved(self, repo):
        from hcp_cms.data.models import QAKnowledge
        repo.insert(QAKnowledge(qa_id="QA-S06", question="q1", answer="a", status="待審核"))
        repo.insert(QAKnowledge(qa_id="QA-S07", question="q2", answer="a", status="已完成"))
        approved = repo.list_approved()
        assert len(approved) == 1
        assert approved[0].qa_id == "QA-S07"
```

- [ ] **Step 2：執行測試，確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_repositories.py::TestQARepositoryStatus -v
```

- [ ] **Step 3：修改 `QARepository.insert()` 加入 status**

在 `src/hcp_cms/data/repositories.py`，找到 `QARepository.insert()` 的 INSERT SQL。

欄位清單改為（在 `source` 之後加入 `status`）：
```python
            INSERT INTO qa_knowledge (
                qa_id, system_product, issue_type, error_type, question, answer,
                solution, keywords, has_image, doc_name, company_id, source_case_id,
                source, status, created_by, created_at, updated_at, notes
            ) VALUES (
                :qa_id, :system_product, :issue_type, :error_type, :question, :answer,
                :solution, :keywords, :has_image, :doc_name, :company_id, :source_case_id,
                :source, :status, :created_by, :created_at, :updated_at, :notes
            )
```

在 dict 中加入（`"source"` 之後）：
```python
                "status": qa.status,
```

- [ ] **Step 4：修改 `QARepository.update()` 加入 status**

找到 `update()` 的 SQL SET 子句，在 `source = :source,` 之後插入：
```sql
                status = :status,
```

在 dict 中加入 `"status": qa.status,`。

- [ ] **Step 5：新增 `list_by_status()` 與 `list_approved()`**

在 `QARepository.list_all()` 之後加入：

```python
    def list_by_status(self, status: str) -> list[QAKnowledge]:
        rows = self._conn.execute(
            "SELECT * FROM qa_knowledge WHERE status = ?", (status,)
        ).fetchall()
        return [QAKnowledge(**dict(row)) for row in rows]

    def list_approved(self) -> list[QAKnowledge]:
        return self.list_by_status("已完成")
```

- [ ] **Step 6：執行測試，確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_repositories.py::TestQARepositoryStatus -v
```

- [ ] **Step 7：執行全體測試，確認無回歸**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

- [ ] **Step 8：Commit**

```bash
git add src/hcp_cms/data/repositories.py tests/unit/test_repositories.py
git commit -m "feat: QARepository 支援 status 欄位（insert/update/list_by_status/list_approved）"
```

---

## Task 3：RawEmail 新欄位 + MSGReader 對話串切割（Services 層）

> 此 Task 先於 Core 層（Task 4），因為 KMSEngine 需要使用 RawEmail 新欄位。

**Files:**
- Modify: `src/hcp_cms/services/mail/base.py`
- Modify: `src/hcp_cms/services/mail/msg_reader.py`
- Test: `tests/unit/test_services.py`

- [ ] **Step 1：寫 RawEmail 新欄位測試**

在 `tests/unit/test_services.py` 的 `TestRawEmail` 類別末尾加入：

```python
    def test_raw_email_thread_question_default_none(self):
        email = RawEmail()
        assert email.thread_question is None

    def test_raw_email_thread_answer_default_none(self):
        email = RawEmail()
        assert email.thread_answer is None

    def test_raw_email_thread_fields_settable(self):
        email = RawEmail(thread_question="客戶問題", thread_answer="我方回覆")
        assert email.thread_question == "客戶問題"
        assert email.thread_answer == "我方回覆"
```

- [ ] **Step 2：執行測試，確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_services.py::TestRawEmail -v
```

- [ ] **Step 3：在 `base.py` 的 RawEmail 新增兩個欄位**

在 `src/hcp_cms/services/mail/base.py` 的 `html_body` 欄位之後（`progress_note` 之前）加入：

```python
    thread_question: str | None = None  # 客戶問題段（清除 header 後，空字串轉 None）
    thread_answer: str | None = None    # HCPSERVICE 回覆段
```

- [ ] **Step 4：執行測試，確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_services.py::TestRawEmail -v
```

- [ ] **Step 5：寫 `_split_thread()` 測試**

在 `tests/unit/test_services.py` 末尾加入：

```python
class TestMSGReaderSplitThread:
    def test_英文_from_切割(self):
        body = (
            "HCPSERVICE 的回覆內容在這裡。\n\n"
            "From: customer@client.com\n"
            "Sent: 2026-01-01\n"
            "To: hcpservice@ares.com.tw\n"
            "Subject: 詢問\n\n"
            "客戶問題內容。"
        )
        ta, tq = MSGReader._split_thread(body)
        assert ta is not None and "HCPSERVICE" in ta
        assert tq is not None and "客戶問題" in tq
        assert "From:" not in tq
        assert "Sent:" not in tq

    def test_中文_寄件者_切割(self):
        body = (
            "我方回覆。\n\n"
            "寄件者: user@client.com.tw\n"
            "傳送時間: 2026-01-01\n"
            "收件者: hcpservice@ares.com.tw\n"
            "主旨: 問題\n\n"
            "客戶的問題。"
        )
        ta, tq = MSGReader._split_thread(body)
        assert ta is not None
        assert tq is not None and "客戶的問題" in tq

    def test_無客戶_From_行回傳_None_None(self):
        ta, tq = MSGReader._split_thread("這封信沒有嵌入的原始訊息。")
        assert ta is None and tq is None

    def test_全部_From_均為_ares_回傳_None_None(self):
        body = (
            "第一封回覆\n\n"
            "From: hcpservice@ares.com.tw\n"
            "Subject: Re: 問題\n\n"
            "原始我方訊息"
        )
        ta, tq = MSGReader._split_thread(body)
        assert ta is None and tq is None

    def test_own_domain_大小寫混用仍識別為我方(self):
        body = (
            "回覆\n\n"
            "From: User@ARES.COM.TW\n"
            "Subject: test\n\n"
            "另一封我方訊息"
        )
        ta, tq = MSGReader._split_thread(body)
        assert ta is None and tq is None

    def test_客戶段清除_header_後為空_回傳_None(self):
        body = (
            "我方回覆。\n\n"
            "From: customer@client.com\n"
            "Sent: 2026-01-01\n"
        )
        ta, tq = MSGReader._split_thread(body)
        assert tq is None

    def test_多層巢狀只取最外層客戶(self):
        body = (
            "最新回覆\n\n"
            "From: customer@abc.com\n"
            "Subject: 第一次詢問\n\n"
            "第一次問題\n\n"
            "From: another@xyz.com\n"
            "Subject: 更早的問題\n\n"
            "更早的問題"
        )
        ta, tq = MSGReader._split_thread(body)
        assert tq is not None and "第一次問題" in tq
```

- [ ] **Step 6：執行測試，確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_services.py::TestMSGReaderSplitThread -v
```

- [ ] **Step 7：在 `msg_reader.py` 加入正則與 `_split_thread()` 方法**

在 `src/hcp_cms/services/mail/msg_reader.py` 的現有正則常數之後加入：

```python
_THREAD_FROM_RE = re.compile(
    r"^(?:From|寄件者)\s*:\s*.*?([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})",
    re.MULTILINE | re.IGNORECASE,
)
_HEADER_LINE_RE = re.compile(
    r"^(?:From|To|Sent|Subject|寄件者|收件者|傳送時間|主旨)\s*:.*$",
    re.MULTILINE | re.IGNORECASE,
)
```

在 `MSGReader` 類別中（`_safe_str` 靜態方法之後）加入：

```python
    @staticmethod
    def _split_thread(body: str, own_domain: str = "@ares.com.tw") -> tuple[str | None, str | None]:
        """回傳 (thread_answer, thread_question)。
        找到第一個非我方 From 行：上方為 answer，下方清除 header 行後為 question。
        strip 後為空字串一律轉 None。own_domain 比對大小寫不敏感。
        """
        own = own_domain.lower()
        for match in _THREAD_FROM_RE.finditer(body):
            addr = match.group(1).lower()
            if own not in addr:
                split_pos = match.start()
                answer = body[:split_pos].strip() or None
                question_raw = body[split_pos:]
                question = _HEADER_LINE_RE.sub("", question_raw).strip() or None
                return answer, question
        return None, None
```

- [ ] **Step 8：修改 `_read_msg_file()` 呼叫 `_split_thread()` 並寫入 RawEmail**

在 `src/hcp_cms/services/mail/msg_reader.py` 的 `_read_msg_file()` 中，找到 `email = RawEmail(` 建構式之前，加入：

```python
        thread_answer, thread_question = MSGReader._split_thread(body_text)
```

在 `RawEmail(...)` 建構式中，在 `html_body=html_body,` 之後加入：

```python
            thread_question=thread_question,
            thread_answer=thread_answer,
```

- [ ] **Step 9：執行測試，確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_services.py::TestMSGReaderSplitThread -v
```

- [ ] **Step 10：執行全體測試，確認無回歸**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

- [ ] **Step 11：Commit**

```bash
git add src/hcp_cms/services/mail/base.py src/hcp_cms/services/mail/msg_reader.py tests/unit/test_services.py
git commit -m "feat: RawEmail 新增 thread_question/thread_answer；MSGReader 加入對話串切割邏輯"
```

---

## Task 4：KMSEngine — status 管制、新方法、export 修正（Core 層）

**Files:**
- Modify: `src/hcp_cms/core/kms_engine.py`
- Test: `tests/unit/test_kms_engine.py`

- [ ] **Step 1：寫 status 管制與新方法測試**

在 `tests/unit/test_kms_engine.py` 末尾加入：

```python
class TestKMSEngineStatus:
    def test_create_qa_待審核_不進_FTS(self, kms):
        qa = kms.create_qa(question="問題A", answer="回覆A", status="待審核")
        results = kms.search("問題A")
        assert all(r.qa_id != qa.qa_id for r in results)

    def test_create_qa_已完成_進_FTS(self, kms):
        kms.create_qa(question="問題B", answer="回覆B", status="已完成")
        results = kms.search("問題B")
        assert len(results) > 0

    def test_update_qa_待審核_不更新_FTS(self, kms):
        qa = kms.create_qa(question="問題C", answer="回覆C", status="待審核")
        kms.update_qa(qa.qa_id, answer="新回覆C")
        results = kms.search("問題C")
        assert all(r.qa_id != qa.qa_id for r in results)

    def test_update_qa_已完成_更新_FTS(self, kms):
        qa = kms.create_qa(question="問題D", answer="回覆D")
        kms.update_qa(qa.qa_id, answer="新回覆D")
        results = kms.search("問題D")
        assert len(results) > 0

    def test_update_qa_降級被拒絕(self, kms):
        qa = kms.create_qa(question="問題E", answer="回覆E", status="已完成")
        result = kms.update_qa(qa.qa_id, status="待審核")
        assert result is None
        from hcp_cms.data.repositories import QARepository
        assert QARepository(kms._conn).get_by_id(qa.qa_id).status == "已完成"

    def test_extract_qa_from_email_有_thread_question(self, kms):
        from hcp_cms.services.mail.base import RawEmail
        raw = RawEmail(thread_question="客戶詢問問題", thread_answer="我方回覆")
        qa = kms.extract_qa_from_email(raw, case_id="CS-001")
        assert qa is not None
        assert qa.status == "待審核"
        assert qa.question == "客戶詢問問題"
        assert qa.source_case_id == "CS-001"

    def test_extract_qa_from_email_無_thread_question(self, kms):
        from hcp_cms.services.mail.base import RawEmail
        raw = RawEmail(thread_question=None, thread_answer=None)
        qa = kms.extract_qa_from_email(raw)
        assert qa is None

    def test_approve_qa_更新_status_且_FTS_索引建立(self, kms):
        from hcp_cms.services.mail.base import RawEmail
        raw = RawEmail(thread_question="問題F", thread_answer="回覆F")
        qa = kms.extract_qa_from_email(raw)
        approved = kms.approve_qa(qa.qa_id, answer="修改後回覆F")
        assert approved is not None
        assert approved.status == "已完成"
        results = kms.search("問題F")
        assert len(results) > 0

    def test_list_pending(self, kms):
        kms.create_qa(question="待審1", answer="a", status="待審核")
        kms.create_qa(question="已完成1", answer="b", status="已完成")
        pending = kms.list_pending()
        assert len(pending) == 1
        assert pending[0].question == "待審1"

    def test_search_不返回待審核(self, kms):
        kms.create_qa(question="共同關鍵字", answer="a", status="待審核")
        kms.create_qa(question="共同關鍵字", answer="b", status="已完成")
        results = kms.search("共同關鍵字")
        assert all(r.status == "已完成" for r in results)

    def test_delete_待審核_QA_無害(self, kms):
        from hcp_cms.services.mail.base import RawEmail
        raw = RawEmail(thread_question="刪除測試", thread_answer="a")
        qa = kms.extract_qa_from_email(raw)
        kms.delete_qa(qa.qa_id)
        assert kms._qa_repo.get_by_id(qa.qa_id) is None

    def test_export_to_excel_排除待審核(self, kms, tmp_path):
        kms.create_qa(question="已完成QA", answer="a", status="已完成")
        kms.create_qa(question="待審核QA", answer="b", status="待審核")
        path = kms.export_to_excel(tmp_path / "out.xlsx")
        import openpyxl
        wb = openpyxl.load_workbook(str(path))
        rows = list(wb.active.iter_rows(min_row=2, values_only=True))
        questions = [r[1] for r in rows if r[1]]
        assert "已完成QA" in questions
        assert "待審核QA" not in questions
```

- [ ] **Step 2：執行測試，確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_kms_engine.py::TestKMSEngineStatus -v
```

- [ ] **Step 3：修改 `KMSEngine.create_qa()`，加入 status 參數與 FTS 守衛**

在 `src/hcp_cms/core/kms_engine.py` 的 `create_qa()` signature 末尾加入 `status: str = "已完成",`。

在 `QAKnowledge(...)` 建構中加入 `status=status`。

將 `self._fts.index_qa(...)` 改為：
```python
        if status == "已完成":
            self._fts.index_qa(qa_id, question, answer, solution, keywords)
```

- [ ] **Step 4：修改 `KMSEngine.update_qa()`，加入降級守衛與 FTS 守衛**

在 `update_qa()` 中，`qa = self._qa_repo.get_by_id(qa_id)` 之後、`for key, value in fields.items()` 之前，插入降級守衛：

```python
        incoming_status = fields.get("status")
        if qa.status == "已完成" and incoming_status == "待審核":
            return None
```

將 `self._fts.update_qa_index(...)` 改為（setattr 迴圈執行後）：

```python
        if qa.status == "已完成":
            self._fts.update_qa_index(qa_id, qa.question, qa.answer, qa.solution, qa.keywords)
```

- [ ] **Step 5：修改 `KMSEngine.search()`，過濾待審核**

在 `search()` 的 `if qa:` 區塊內，加入：

```python
                if qa.status != "已完成":
                    continue
```

- [ ] **Step 6：修改 `KMSEngine.export_to_excel()` 改用 `list_approved()`**

找到 `export_to_excel()` 方法中：
```python
            qa_list = self._qa_repo.list_all()
```
改為：
```python
            qa_list = self._qa_repo.list_approved()
```

- [ ] **Step 7：在 KMSEngine 加入新方法與 import**

在 `kms_engine.py` 頂部確認有（若無則加入）：
```python
from hcp_cms.services.mail.base import RawEmail
```

在 `delete_qa()` 之後加入：

```python
    def extract_qa_from_email(self, raw_email: RawEmail, case_id: str | None = None) -> QAKnowledge | None:
        """從 RawEmail thread 欄位抽取 QA，儲存為待審核。無問題段則回傳 None。"""
        if not raw_email.thread_question:
            return None
        return self.create_qa(
            question=raw_email.thread_question,
            answer=raw_email.thread_answer or "",
            source="email",
            source_case_id=case_id,
            status="待審核",
        )

    def approve_qa(self, qa_id: str, **updated_fields) -> QAKnowledge | None:
        """單一入口：更新欄位 → status='已完成' → FTS 索引建立。"""
        updated_fields["status"] = "已完成"
        return self.update_qa(qa_id, **updated_fields)

    def list_pending(self) -> list[QAKnowledge]:
        """列出所有待審核 QA。"""
        return self._qa_repo.list_by_status("待審核")

    def list_approved(self) -> list[QAKnowledge]:
        """列出所有已完成 QA（供 UI 層顯示全部使用）。"""
        return self._qa_repo.list_approved()
```

並在 `auto_extract_qa()` docstring 第一行加入：
```python
        """.. deprecated:: 由 extract_qa_from_email() 取代。"""
```

- [ ] **Step 8：執行測試，確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_kms_engine.py -v
```

- [ ] **Step 9：執行全體測試，確認無回歸**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

- [ ] **Step 10：Commit**

```bash
git add src/hcp_cms/core/kms_engine.py tests/unit/test_kms_engine.py
git commit -m "feat: KMSEngine 加入 status 管制、approve_qa、extract_qa_from_email、list_pending；export 排除待審核"
```

---

## Task 5：EmailView 注入 KMSEngine + MainWindow 共用實例

**Files:**
- Modify: `src/hcp_cms/ui/email_view.py`
- Modify: `src/hcp_cms/ui/main_window.py`

- [ ] **Step 1：修改 `EmailView.__init__` 加入 kms 參數**

在 `src/hcp_cms/ui/email_view.py` 第 47 行，將：
```python
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
```
改為：
```python
    def __init__(self, conn: sqlite3.Connection | None = None, kms=None) -> None:
        super().__init__()
        self._conn = conn
        self._kms = kms
```

在頂部 import 區加入：
```python
from hcp_cms.core.kms_engine import KMSEngine
```

- [ ] **Step 2：在 `_do_import_rows()` 的匯入成功後加入 KMS 抽取**

在 `src/hcp_cms/ui/email_view.py` 的 `_do_import_rows()` 中，找到：
```python
                    label = label_map.get(action, "已匯入")
                    self._table.setItem(row, 4, QTableWidgetItem(label))
                    success += 1
```

在 `success += 1` 之前插入：
```python
                    if email.thread_question and self._kms:
                        self._kms.extract_qa_from_email(email, case.case_id if case else None)
```

- [ ] **Step 3：修改 `MainWindow._setup_ui()` 共用 KMSEngine**

在 `src/hcp_cms/ui/main_window.py` 頂部加入：
```python
from hcp_cms.core.kms_engine import KMSEngine
```

在 `_setup_ui()` 的 `self._views` dict 之前（第 96 行附近）加入：
```python
        kms = KMSEngine(self._conn) if self._conn else None
```

將 `"kms": KMSView(self._conn)` 改為：
```python
            "kms": KMSView(self._conn, kms=kms),
```

將 `"email": EmailView(self._conn)` 改為：
```python
            "email": EmailView(self._conn, kms=kms),
```

- [ ] **Step 4：執行全體測試，確認無回歸**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/ui/email_view.py src/hcp_cms/ui/main_window.py
git commit -m "feat: EmailView 注入 KMSEngine，匯入時自動呼叫 extract_qa_from_email"
```

---

## Task 6：KMSView — 待審核分頁與 QAReviewDialog

**Files:**
- Modify: `src/hcp_cms/ui/kms_view.py`

- [ ] **Step 1：改寫 `kms_view.py`**

將 `src/hcp_cms/ui/kms_view.py` 完整替換為：

```python
"""KMS knowledge base view — search, CRUD, 待審核審核。"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.kms_engine import KMSEngine


class QAReviewDialog(QDialog):
    """待審核 QA 編輯對話框。"""

    def __init__(self, qa, parent=None) -> None:
        super().__init__(parent)
        self.qa = qa
        self._result_action: str | None = None
        self.setWindowTitle(f"QA 審核編輯 — {qa.qa_id}")
        self.setMinimumWidth(600)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._question = QTextEdit(self.qa.question or "")
        self._question.setFixedHeight(80)
        self._answer = QTextEdit(self.qa.answer or "")
        self._answer.setFixedHeight(80)
        self._solution = QTextEdit(self.qa.solution or "")
        self._solution.setFixedHeight(60)
        self._keywords = QLineEdit(self.qa.keywords or "")
        self._product = QLineEdit(self.qa.system_product or "")

        form.addRow("問題：", self._question)
        form.addRow("回覆：", self._answer)
        form.addRow("解決方案：", self._solution)
        form.addRow("關鍵字：", self._keywords)
        form.addRow("產品：", self._product)
        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        draft_btn = QPushButton("💾 儲存草稿")
        draft_btn.clicked.connect(self._on_draft)
        approve_btn = QPushButton("✅ 確認完成")
        approve_btn.clicked.connect(self._on_approve)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(draft_btn)
        btn_layout.addWidget(approve_btn)
        layout.addLayout(btn_layout)

    def _collect_fields(self) -> dict:
        return {
            "question": self._question.toPlainText().strip(),
            "answer": self._answer.toPlainText().strip(),
            "solution": self._solution.toPlainText().strip() or None,
            "keywords": self._keywords.text().strip() or None,
            "system_product": self._product.text().strip() or None,
        }

    def _on_draft(self) -> None:
        self._result_action = "draft"
        self._result_fields = self._collect_fields()
        self.accept()

    def _on_approve(self) -> None:
        self._result_action = "approve"
        self._result_fields = self._collect_fields()
        self.accept()

    def result_action(self) -> str | None:
        return self._result_action

    def result_fields(self) -> dict:
        return getattr(self, "_result_fields", {})


class KMSView(QWidget):
    """KMS knowledge base page."""

    def __init__(self, conn: sqlite3.Connection | None = None, kms: KMSEngine | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._kms = kms or (KMSEngine(conn) if conn else None)
        self._results: list = []
        self._pending: list = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("📚 KMS 知識庫")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f1f5f9;")
        layout.addWidget(title)

        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # ── 全部 tab ──────────────────────────────────────────────────
        all_tab = QWidget()
        all_layout = QVBoxLayout(all_tab)

        search_layout = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜尋知識庫（支援同義詞擴展）...")
        self._search_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self._search_input)
        search_btn = QPushButton("🔍 搜尋")
        search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(search_btn)
        show_all_btn = QPushButton("📋 顯示全部")
        show_all_btn.clicked.connect(self._on_show_all)
        search_layout.addWidget(show_all_btn)
        new_btn = QPushButton("➕ 新增 QA")
        new_btn.clicked.connect(self._on_new_qa)
        search_layout.addWidget(new_btn)
        all_layout.addLayout(search_layout)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["QA 編號", "問題", "產品", "類型", "來源"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self._table)

        detail = QWidget()
        detail_layout = QFormLayout(detail)
        self._detail_question = QTextEdit()
        self._detail_question.setMaximumHeight(80)
        self._detail_question.setReadOnly(True)
        self._detail_answer = QTextEdit()
        self._detail_answer.setMaximumHeight(80)
        self._detail_answer.setReadOnly(True)
        self._detail_solution = QTextEdit()
        self._detail_solution.setMaximumHeight(80)
        self._detail_solution.setReadOnly(True)
        detail_layout.addRow("問題:", self._detail_question)
        detail_layout.addRow("回覆:", self._detail_answer)
        detail_layout.addRow("解決方案:", self._detail_solution)
        splitter.addWidget(detail)
        all_layout.addWidget(splitter)
        self._tabs.addTab(all_tab, "全部")

        # ── 待審核 tab ────────────────────────────────────────────────
        pending_tab = QWidget()
        pending_layout = QVBoxLayout(pending_tab)

        self._pending_table = QTableWidget(0, 3)
        self._pending_table.setHorizontalHeaderLabels(["QA 編號", "問題預覽", "來源案件"])
        self._pending_table.horizontalHeader().setStretchLastSection(True)
        self._pending_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._pending_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        pending_layout.addWidget(self._pending_table)

        pending_btn_layout = QHBoxLayout()
        review_btn = QPushButton("✏️ 編輯審核")
        review_btn.clicked.connect(self._on_review)
        delete_btn = QPushButton("🗑️ 刪除")
        delete_btn.clicked.connect(self._on_delete_pending)
        pending_btn_layout.addWidget(review_btn)
        pending_btn_layout.addWidget(delete_btn)
        pending_btn_layout.addStretch()
        pending_layout.addLayout(pending_btn_layout)
        self._tabs.addTab(pending_tab, "待審核")

        layout.addWidget(self._tabs)

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            self._refresh_pending()

    def _refresh_pending(self) -> None:
        if not self._kms:
            return
        self._pending = self._kms.list_pending()
        count = len(self._pending)
        self._tabs.setTabText(1, f"待審核{'  🔴' + str(count) if count else ''}")
        self._pending_table.setRowCount(count)
        for i, qa in enumerate(self._pending):
            self._pending_table.setItem(i, 0, QTableWidgetItem(qa.qa_id))
            self._pending_table.setItem(i, 1, QTableWidgetItem((qa.question or "")[:50]))
            self._pending_table.setItem(i, 2, QTableWidgetItem(qa.source_case_id or ""))

    def _on_show_all(self) -> None:
        """載入所有已完成 QA 顯示於全部 tab。"""
        if not self._kms:
            return
        self._results = self._kms.list_approved()
        self._table.setRowCount(len(self._results))
        for i, qa in enumerate(self._results):
            self._table.setItem(i, 0, QTableWidgetItem(qa.qa_id))
            self._table.setItem(i, 1, QTableWidgetItem(qa.question or ""))
            self._table.setItem(i, 2, QTableWidgetItem(qa.system_product or ""))
            self._table.setItem(i, 3, QTableWidgetItem(qa.issue_type or ""))
            self._table.setItem(i, 4, QTableWidgetItem(qa.source or ""))

    def _on_search(self) -> None:
        query = self._search_input.text().strip()
        if not query or not self._kms:
            return
        self._results = self._kms.search(query)
        self._table.setRowCount(len(self._results))
        for i, qa in enumerate(self._results):
            self._table.setItem(i, 0, QTableWidgetItem(qa.qa_id))
            self._table.setItem(i, 1, QTableWidgetItem(qa.question or ""))
            self._table.setItem(i, 2, QTableWidgetItem(qa.system_product or ""))
            self._table.setItem(i, 3, QTableWidgetItem(qa.issue_type or ""))
            self._table.setItem(i, 4, QTableWidgetItem(qa.source or ""))

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

    def _on_new_qa(self) -> None:
        pass  # 預留給新增 QA 對話框

    def _on_review(self) -> None:
        if not self._kms:
            return
        rows = self._pending_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if row >= len(self._pending):
            return
        qa = self._pending[row]
        dlg = QAReviewDialog(qa, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dlg.result_fields()
        if dlg.result_action() == "draft":
            self._kms.update_qa(qa.qa_id, **fields)
        elif dlg.result_action() == "approve":
            self._kms.approve_qa(qa.qa_id, **fields)
        self._refresh_pending()

    def _on_delete_pending(self) -> None:
        if not self._kms:
            return
        rows = self._pending_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if row >= len(self._pending):
            return
        qa = self._pending[row]
        self._kms.delete_qa(qa.qa_id)
        self._refresh_pending()
```

- [ ] **Step 2：執行全體測試，確認無回歸**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

- [ ] **Step 3：Commit**

```bash
git add src/hcp_cms/ui/kms_view.py
git commit -m "feat: KMSView 加入待審核分頁、QAReviewDialog 與顯示全部按鈕"
```

---

## Task 7：整合測試

**Files:**
- Create: `tests/integration/test_msg_qa_extraction.py`

- [ ] **Step 1：撰寫整合測試**

建立 `tests/integration/test_msg_qa_extraction.py`：

```python
"""整合測試：.MSG 對話串 → KMS 待審核 → 審核通過 → 搜尋可找到。"""

from pathlib import Path

import pytest

from hcp_cms.core.kms_engine import KMSEngine
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.repositories import QARepository
from hcp_cms.services.mail.base import RawEmail
from hcp_cms.services.mail.msg_reader import MSGReader


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def kms(db: DatabaseManager) -> KMSEngine:
    return KMSEngine(db.connection)


class TestMsgQAExtractionIntegration:
    def test_完整流程_匯入到搜尋(self, kms):
        body = (
            "感謝您的詢問，薪資計算方式請參考系統設定中的薪資模組。\n\n"
            "From: customer@clientco.com\n"
            "Sent: 2026-03-20\n"
            "To: hcpservice@ares.com.tw\n"
            "Subject: 請問薪資如何計算\n\n"
            "請問薪資如何計算？"
        )
        ta, tq = MSGReader._split_thread(body)
        raw = RawEmail(
            sender="hcpservice@ares.com.tw",
            subject="Re: 請問薪資如何計算",
            body=body,
            thread_answer=ta,
            thread_question=tq,
        )

        # 1. 抽取 → 待審核，不進 FTS
        qa = kms.extract_qa_from_email(raw, case_id="CS-202603-001")
        assert qa is not None and qa.status == "待審核"
        assert all(r.qa_id != qa.qa_id for r in kms.search("薪資"))

        # 2. 出現在待審核列表
        assert any(p.qa_id == qa.qa_id for p in kms.list_pending())

        # 3. 儲存草稿不進 FTS
        kms.update_qa(qa.qa_id, question="薪資如何計算")
        assert all(r.qa_id != qa.qa_id for r in kms.search("薪資"))
        assert QARepository(kms._conn).get_by_id(qa.qa_id).status == "待審核"

        # 4. 審核通過
        approved = kms.approve_qa(qa.qa_id, answer="請參考薪資模組")
        assert approved is not None and approved.status == "已完成"

        # 5. 搜尋可找到
        assert any(r.qa_id == qa.qa_id for r in kms.search("薪資"))

        # 6. 不再在待審核列表
        assert all(p.qa_id != qa.qa_id for p in kms.list_pending())

    def test_無_thread_question_不建立_QA(self, kms):
        raw = RawEmail(sender="user@ares.com.tw", subject="test", body="沒有對話串")
        assert kms.extract_qa_from_email(raw) is None
        assert len(kms.list_pending()) == 0

    def test_export_excel_排除待審核(self, kms, tmp_path):
        raw = RawEmail(thread_question="待審問題", thread_answer="待審回覆")
        kms.extract_qa_from_email(raw)
        kms.create_qa(question="已完成問題", answer="已完成回覆", status="已完成")
        path = kms.export_to_excel(tmp_path / "out.xlsx")
        import openpyxl
        wb = openpyxl.load_workbook(str(path))
        questions = [r[1] for r in wb.active.iter_rows(min_row=2, values_only=True) if r[1]]
        assert "已完成問題" in questions
        assert "待審問題" not in questions
```

- [ ] **Step 2：執行整合測試**

```
.venv/Scripts/python.exe -m pytest tests/integration/test_msg_qa_extraction.py -v
```

預期：全部 PASS

- [ ] **Step 3：執行全體測試**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

- [ ] **Step 4：Commit**

```bash
git add tests/integration/test_msg_qa_extraction.py
git commit -m "test: 新增 MSG QA 抽取整合測試（含 export 排除待審核驗證）"
```

---

## 驗收清單

完成所有 Task 後，手動確認以下項目：

- [ ] 選擇含有客戶原始問題的 .MSG 匯入 → 信件處理頁面匯入成功
- [ ] 切換至 KMS 知識庫 → 「待審核」tab 顯示 🔴N，出現該 QA
- [ ] 點選 QA → 「✏️ 編輯審核」開啟對話框，問題與回覆已預填
- [ ] 修改內容後按「💾 儲存草稿」→ 條目仍在待審核，搜尋不到
- [ ] 重新開啟，按「✅ 確認完成」→ 條目移至「全部」tab（按「📋 顯示全部」可見）
- [ ] 搜尋關鍵字 → 找到審核通過的 QA
- [ ] 匯入不含對話串的 .MSG → KMS 待審核數量不增加
- [ ] 匯出 Excel → 待審核 QA 不出現在匯出檔案中
