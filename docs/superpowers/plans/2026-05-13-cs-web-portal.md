# 客服 Web Portal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建置 NiceGUI Web Portal 讓 3 位客服共用瀏覽器維護案件，並新增「推到 Mantis」手動按鈕（單筆 / 批次 / 推 bugnote 三模式），加入「已結案」狀態鎖定不重開。

**Architecture:** Companion Server — NiceGUI Web Server 跑在 Jill PC 與桌面 App 共用同一 SQLite 檔（WAL）。新增 4 個 Core Manager（WebAuthManager / CaseVisibilityFilter / AuditLogger / MantisPushManager）、1 個資料表（web_audit_log）、擴充 MantisClient ABC 加寫入方法。

**Tech Stack:** Python 3.14、PySide6 6.10.2、SQLite + FTS5、NiceGUI（新增）、Mantis SOAP API

**Spec:** [`docs/superpowers/specs/2026-05-13-cs-web-portal-design.md`](../specs/2026-05-13-cs-web-portal-design.md)

---

## 檔案結構規劃

### 新增檔案

```
src/hcp_cms/
├── web/                                ★ 新增整個 Web Portal 子模組
│   ├── __init__.py
│   ├── __main__.py                     # python -m hcp_cms.web 入口
│   ├── app.py                          # NiceGUI app + 路由註冊
│   ├── auth.py                         # WebAuthManager（cookie + pick-from-list）
│   ├── audit.py                        # AuditLogger
│   ├── visibility.py                   # CaseVisibilityFilter（B+A + G-3）
│   ├── mantis_push.py                  # MantisPushManager
│   └── pages/
│       ├── __init__.py
│       ├── login.py                    # /login
│       ├── case_list.py                # /cases
│       ├── case_detail.py              # /cases/{id}
│       └── audit.py                    # /audit
├── data/
│   └── repositories.py                 # ＋ WebAuditLogRepository
└── services/mantis/
    ├── base.py                         # ＋ create_issue / add_note 抽象方法
    └── soap.py                         # ＋ create_issue / add_note 實作

tests/
├── unit/
│   ├── test_web_audit_log_repository.py    # 新
│   ├── test_web_auth_manager.py            # 新
│   ├── test_case_visibility_filter.py      # 新
│   ├── test_audit_logger.py                # 新
│   ├── test_mantis_push_manager.py         # 新
│   ├── test_mantis_soap_write.py           # 新
│   └── test_thread_tracker_closed_case.py  # 新（D-2）
└── integration/
    └── test_web_portal_flow.py             # 新

docs/
└── 客服 Web Portal 使用說明.md             # 新
```

### 修改檔案

```
src/hcp_cms/
├── data/database.py                    # ＋ web_audit_log migration
├── core/
│   ├── case_manager.py                 # ＋ 已結案 case 客戶回信改加 case_log（D-2）
│   └── thread_tracker.py               # ＋ find_thread_parent 加搜尋 已結案
└── services/mantis/base.py             # 既有 ABC 改為含新方法
```

### 不修改

- 桌面 App 全部 PySide6 UI 不動（沿用現有「未指派案件」處理流程，G-3）
- Email Scheduler 不動
- 報表 / KMS / Patch 不動

---

## Phase 1：Data 層（Migration + Repository）

### Task 1：新增 `已結案` 狀態值域（無 schema 變動）

**Files:**
- Modify: `src/hcp_cms/data/models.py:46-48`（`Case.is_open` property 排除已結案）

**目的：** `cs_cases.status` 為 TEXT 欄位，狀態 enum 在應用層維護。擴增至 4 個值：`處理中` / `已回覆` / `已完成` / `已結案`。`is_open` property 排除「已結案」。

- [ ] **Step 1：寫失敗測試**

新增 `tests/unit/test_case_model_closed.py`：

```python
"""Case dataclass 對 已結案 狀態的處理。"""
from hcp_cms.data.models import Case


def test_closed_case_is_not_open() -> None:
    case = Case(case_id="C-1", subject="test", status="已結案")
    assert case.is_open is False


def test_completed_case_is_not_open() -> None:
    case = Case(case_id="C-2", subject="test", status="已完成")
    assert case.is_open is False


def test_processing_case_is_open() -> None:
    case = Case(case_id="C-3", subject="test", status="處理中")
    assert case.is_open is True
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_case_model_closed.py -v
```

預期：`test_closed_case_is_not_open` FAIL（因為 `is_open` 目前只排除 「已完成」/「Closed」）

- [ ] **Step 3：修改 `Case.is_open`**

`src/hcp_cms/data/models.py:46-48` 改成：

```python
    @property
    def is_open(self) -> bool:
        return self.status not in ("已完成", "Closed", "已結案")
```

- [ ] **Step 4：跑測試驗證通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_case_model_closed.py -v
```

預期：3 個測試 PASS

- [ ] **Step 5：跑全部既有測試確認無回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short
```

預期：所有既有測試仍 PASS

- [ ] **Step 6：commit**

```bash
git add src/hcp_cms/data/models.py tests/unit/test_case_model_closed.py
git commit -m "feat(model): Case.is_open 排除 已結案 狀態（D-2 基礎）"
```

---

### Task 2：新增 `web_audit_log` 表 + Migration

**Files:**
- Modify: `src/hcp_cms/data/database.py`（_SCHEMA_SQL 加新表 + Migration list 加冪等 ALTER）

**目的：** 新增稽核 log 表，記錄 Web Portal 操作（欄位變更、Mantis 推送）。

- [ ] **Step 1：閱讀既有 database.py 結構**

```bash
.venv/Scripts/python.exe -c "from hcp_cms.data.database import DatabaseManager; import inspect; print(inspect.getsourcefile(DatabaseManager))"
```

讀檔以了解 `_SCHEMA_SQL` 與 `_apply_pending_migrations()` 的寫法。

- [ ] **Step 2：寫失敗測試**

新增 `tests/unit/test_web_audit_log_schema.py`：

```python
"""驗證 web_audit_log 表結構（Migration 後存在且結構正確）。"""
import sqlite3
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager


@pytest.fixture
def db_conn(tmp_path: Path) -> sqlite3.Connection:
    db = DatabaseManager(tmp_path / "test.db")
    db.initialize()
    yield db.conn
    db.close()


def test_web_audit_log_table_exists(db_conn: sqlite3.Connection) -> None:
    cur = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='web_audit_log'"
    )
    assert cur.fetchone() is not None


def test_web_audit_log_columns(db_conn: sqlite3.Connection) -> None:
    cur = db_conn.execute("PRAGMA table_info(web_audit_log)")
    cols = {row[1]: row[2] for row in cur.fetchall()}
    assert cols == {
        "id": "INTEGER",
        "staff_id": "TEXT",
        "occurred_at": "TEXT",
        "case_id": "TEXT",
        "field_name": "TEXT",
    }


def test_web_audit_log_indexes(db_conn: sqlite3.Connection) -> None:
    cur = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='web_audit_log'"
    )
    names = {row[0] for row in cur.fetchall()}
    assert "idx_audit_case" in names
    assert "idx_audit_staff" in names
```

- [ ] **Step 3：跑測試驗證失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_web_audit_log_schema.py -v
```

預期：3 個測試全 FAIL

- [ ] **Step 4：在 `_SCHEMA_SQL` 加 CREATE TABLE**

於 `src/hcp_cms/data/database.py` 的 `_SCHEMA_SQL` 字串末段（既有 CREATE TABLE 之後、最後一個 `);` 之前）加入：

```sql
CREATE TABLE IF NOT EXISTS web_audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id    TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    case_id     TEXT NOT NULL,
    field_name  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_case  ON web_audit_log(case_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_staff ON web_audit_log(staff_id, occurred_at);
```

- [ ] **Step 5：跑測試驗證通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_web_audit_log_schema.py -v
```

預期：3 個測試 PASS

- [ ] **Step 6：跑全部既有測試確認無回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ --tb=short
```

預期：既有測試全 PASS

- [ ] **Step 7：commit**

```bash
git add src/hcp_cms/data/database.py tests/unit/test_web_audit_log_schema.py
git commit -m "feat(data): 新增 web_audit_log 表（稽核 Web Portal 操作）"
```

---

### Task 3：新增 `WebAuditLogRepository`

**Files:**
- Modify: `src/hcp_cms/data/repositories.py`（加 class，附在檔末或 `CaseLogRepository` 後）
- Create: `tests/unit/test_web_audit_log_repository.py`

**目的：** 提供 web_audit_log CRUD。

- [ ] **Step 1：寫失敗測試**

新增 `tests/unit/test_web_audit_log_repository.py`：

```python
"""WebAuditLogRepository CRUD 測試。"""
import sqlite3
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.repositories import WebAuditLogRepository


@pytest.fixture
def repo(tmp_path: Path) -> WebAuditLogRepository:
    db = DatabaseManager(tmp_path / "test.db")
    db.initialize()
    yield WebAuditLogRepository(db.conn)
    db.close()


def test_insert_and_list_by_case(repo: WebAuditLogRepository) -> None:
    repo.insert(staff_id="S001", case_id="C-1", field_name="status")
    repo.insert(staff_id="S002", case_id="C-1", field_name="handler")
    repo.insert(staff_id="S001", case_id="C-2", field_name="status")

    rows = repo.list_by_case_id("C-1")
    assert len(rows) == 2
    assert {r.staff_id for r in rows} == {"S001", "S002"}
    assert {r.field_name for r in rows} == {"status", "handler"}


def test_list_by_staff_id(repo: WebAuditLogRepository) -> None:
    repo.insert(staff_id="S001", case_id="C-1", field_name="status")
    repo.insert(staff_id="S001", case_id="C-2", field_name="progress")
    repo.insert(staff_id="S002", case_id="C-1", field_name="handler")

    rows = repo.list_by_staff_id("S001")
    assert len(rows) == 2


def test_list_all_ordered_desc(repo: WebAuditLogRepository) -> None:
    repo.insert(staff_id="S001", case_id="C-1", field_name="first")
    repo.insert(staff_id="S001", case_id="C-1", field_name="second")
    repo.insert(staff_id="S001", case_id="C-1", field_name="third")

    rows = repo.list_all(limit=10)
    assert [r.field_name for r in rows] == ["third", "second", "first"]


def test_occurred_at_format(repo: WebAuditLogRepository) -> None:
    repo.insert(staff_id="S001", case_id="C-1", field_name="status")
    rows = repo.list_by_case_id("C-1")
    # 格式 YYYY/MM/DD HH:MM:SS（依專案慣例）
    import re
    assert re.match(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}$", rows[0].occurred_at)
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_web_audit_log_repository.py -v
```

預期：FAIL（`WebAuditLogRepository` 與 `WebAuditLog` model 不存在）

- [ ] **Step 3：在 `models.py` 新增 dataclass**

於 `src/hcp_cms/data/models.py` 末段加：

```python
@dataclass
class WebAuditLog:
    """Web Portal 操作稽核紀錄 — web_audit_log table."""
    id: int | None = None
    staff_id: str = ""
    occurred_at: str = ""
    case_id: str = ""
    field_name: str = ""
```

- [ ] **Step 4：在 `repositories.py` 新增 Repository**

於 `src/hcp_cms/data/repositories.py` 末段加：

```python
class WebAuditLogRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_model(self, row: sqlite3.Row) -> WebAuditLog:
        d = dict(row)
        return WebAuditLog(
            id=d["id"],
            staff_id=d["staff_id"],
            occurred_at=d["occurred_at"],
            case_id=d["case_id"],
            field_name=d["field_name"],
        )

    def insert(self, staff_id: str, case_id: str, field_name: str) -> None:
        self._conn.execute(
            """
            INSERT INTO web_audit_log (staff_id, occurred_at, case_id, field_name)
            VALUES (:staff_id, :occurred_at, :case_id, :field_name)
            """,
            {
                "staff_id": staff_id,
                "occurred_at": _now(),
                "case_id": case_id,
                "field_name": field_name,
            },
        )
        self._conn.commit()

    def list_by_case_id(self, case_id: str) -> list[WebAuditLog]:
        rows = self._conn.execute(
            "SELECT * FROM web_audit_log WHERE case_id = ? ORDER BY occurred_at DESC",
            (case_id,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def list_by_staff_id(self, staff_id: str) -> list[WebAuditLog]:
        rows = self._conn.execute(
            "SELECT * FROM web_audit_log WHERE staff_id = ? ORDER BY occurred_at DESC",
            (staff_id,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def list_all(self, limit: int = 100) -> list[WebAuditLog]:
        rows = self._conn.execute(
            "SELECT * FROM web_audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]
```

⚠ 確認檔頭已 import `WebAuditLog`（與其他 model 同樣 from `.models`）。`_now()` 與其他 repo 共用既有 helper。

- [ ] **Step 5：跑測試驗證通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_web_audit_log_repository.py -v
```

預期：4 個測試 PASS

- [ ] **Step 6：跑全部測試**

```bash
.venv/Scripts/python.exe -m pytest tests/ --tb=short
```

- [ ] **Step 7：commit**

```bash
git add src/hcp_cms/data/repositories.py src/hcp_cms/data/models.py tests/unit/test_web_audit_log_repository.py
git commit -m "feat(data): WebAuditLogRepository + WebAuditLog model"
```

---

## Phase 2：Services 層 — Mantis SOAP 寫入

### Task 4：POC — 5 分鐘驗證 `mc_issue_add` SOAP 可用

**目的：** 確認貴公司 Mantis 版本支援 `mc_issue_add` / `mc_issue_note_add` SOAP method，**避免 Day 5 才發現不行**。

- [ ] **Step 1：取得 Mantis 測試 credentials**

從專案設定檔或 keyring 取得 base_url / username / password（請 Jill 提供）。

- [ ] **Step 2：用 curl 試打 `mc_issue_add`**

```bash
curl -k -X POST "https://<your-mantis-host>/api/soap/mantisconnect.php" \
  -H "Content-Type: text/xml; charset=utf-8" \
  -d '<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:man="http://futureware.biz/mantisconnect">
    <soapenv:Body>
        <man:mc_issue_add>
            <man:username>YOUR_USER</man:username>
            <man:password>YOUR_PASS</man:password>
            <man:issue>
                <man:project><man:id>1</man:id></man:project>
                <man:summary>POC 測試 ticket</man:summary>
                <man:description>HCP CMS POC，可刪除</man:description>
                <man:category>General</man:category>
                <man:priority><man:name>normal</man:name></man:priority>
                <man:severity><man:name>minor</man:name></man:severity>
            </man:issue>
        </man:mc_issue_add>
    </soapenv:Body>
</soapenv:Envelope>'
```

- [ ] **Step 3：驗證回應**

預期：HTTP 200 + 回應 XML 含 `<id>` 標籤回傳新 ticket id（如 `<id xsi:type="xsd:integer">5678</id>`）。

成功 → 進 Task 5
失敗 → 記錄 `<faultstring>` 內容，回報 Jill 決定：
- (a) 用 REST API 替代
- (b) Phase 2 再做 Mantis 寫入功能
- (c) 升級 Mantis 版本

- [ ] **Step 4：手動清理 POC ticket**

到 Mantis Web 介面 close 或 delete 剛剛建立的 POC ticket，避免污染。

- [ ] **Step 5：記錄結果到 plan**

於本文件 Task 4 末段加 `**POC 結果：** ✅ 可用 / ❌ 不可用 + 原因`。

---

### Task 5：擴充 `MantisClient` ABC — 加 `create_issue` / `add_note` 抽象方法

**Files:**
- Modify: `src/hcp_cms/services/mantis/base.py:39-48`

**目的：** ABC 加寫入抽象方法，但 REST 子類別 MVP 先 raise NotImplementedError（不阻擋 SOAP MVP）。

- [ ] **Step 1：寫失敗測試**

新增 `tests/unit/test_mantis_client_abc.py`：

```python
"""驗證 MantisClient ABC 含 create_issue / add_note 抽象方法。"""
import inspect

import pytest

from hcp_cms.services.mantis.base import MantisClient


def test_create_issue_is_abstract() -> None:
    assert "create_issue" in MantisClient.__abstractmethods__


def test_add_note_is_abstract() -> None:
    assert "add_note" in MantisClient.__abstractmethods__


def test_create_issue_signature() -> None:
    sig = inspect.signature(MantisClient.create_issue)
    params = list(sig.parameters.keys())
    assert "project_id" in params
    assert "summary" in params
    assert "description" in params
    # 帶有預設值的選用參數
    assert sig.parameters["priority"].default == "normal"
    assert sig.parameters["severity"].default == "minor"


def test_add_note_signature() -> None:
    sig = inspect.signature(MantisClient.add_note)
    params = list(sig.parameters.keys())
    assert "issue_id" in params
    assert "text" in params
    assert sig.parameters["view_state"].default == "public"
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_client_abc.py -v
```

預期：FAIL

- [ ] **Step 3：修改 `base.py`**

`src/hcp_cms/services/mantis/base.py` 的 `MantisClient` 改為：

```python
class MantisClient(ABC):
    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def get_issue(self, issue_id: str) -> MantisIssue | None: ...

    @abstractmethod
    def get_issues(self, project_id: str | None = None) -> list[MantisIssue]: ...

    @abstractmethod
    def create_issue(
        self,
        project_id: str,
        summary: str,
        description: str,
        category: str = "",
        priority: str = "normal",
        severity: str = "minor",
        handler: str | None = None,
    ) -> str | None:
        """建立新 issue，成功回傳 ticket_id，失敗回 None（self.last_error 含原因）。"""

    @abstractmethod
    def add_note(
        self,
        issue_id: str,
        text: str,
        view_state: str = "public",
    ) -> str | None:
        """加 bugnote，成功回傳 note_id，失敗回 None。"""
```

- [ ] **Step 4：REST client 加 stub（先 raise NotImplementedError）**

於 `src/hcp_cms/services/mantis/rest.py` 末加 2 方法（MVP 不實作）：

```python
    def create_issue(
        self,
        project_id: str,
        summary: str,
        description: str,
        category: str = "",
        priority: str = "normal",
        severity: str = "minor",
        handler: str | None = None,
    ) -> str | None:
        raise NotImplementedError("REST create_issue 未實作；MVP 僅支援 SOAP")

    def add_note(
        self,
        issue_id: str,
        text: str,
        view_state: str = "public",
    ) -> str | None:
        raise NotImplementedError("REST add_note 未實作；MVP 僅支援 SOAP")
```

- [ ] **Step 5：跑測試驗證通過 + 既有 Mantis 測試不破**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_client_abc.py tests/unit/test_mantis_soap_fields.py tests/unit/test_mantis_classifier.py -v
```

預期：新測試 PASS；既有測試仍 PASS。

- [ ] **Step 6：commit**

```bash
git add src/hcp_cms/services/mantis/base.py src/hcp_cms/services/mantis/rest.py tests/unit/test_mantis_client_abc.py
git commit -m "feat(mantis): MantisClient ABC 加 create_issue / add_note 抽象方法"
```

---

### Task 6：`MantisSoapClient.create_issue` 實作

**Files:**
- Modify: `src/hcp_cms/services/mantis/soap.py`（class 內加方法）

**目的：** 透過 SOAP `mc_issue_add` 建立新 Mantis ticket。

- [ ] **Step 1：寫失敗測試（mock requests.post）**

新增 `tests/unit/test_mantis_soap_write.py`：

```python
"""MantisSoapClient.create_issue / add_note 測試（mock 網路）。"""
from unittest.mock import patch, MagicMock

import pytest

from hcp_cms.services.mantis.soap import MantisSoapClient


@pytest.fixture
def client() -> MantisSoapClient:
    c = MantisSoapClient("http://mantis.test", "user", "pass")
    c._connected = True
    return c


def _mock_response(text: str, status: int = 200) -> MagicMock:
    m = MagicMock()
    m.status_code = status
    m.text = text
    return m


def test_create_issue_success_returns_ticket_id(client: MantisSoapClient) -> None:
    response_xml = """<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<m:mc_issue_addResponse><return xsi:type="xsd:integer">12345</return></m:mc_issue_addResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    with patch("hcp_cms.services.mantis.soap.requests.post") as mock_post:
        mock_post.return_value = _mock_response(response_xml)
        ticket_id = client.create_issue(
            project_id="1",
            summary="測試案件",
            description="本文",
        )
    assert ticket_id == "12345"


def test_create_issue_soap_fault_returns_none(client: MantisSoapClient) -> None:
    fault_xml = """<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<SOAP-ENV:Fault><faultstring>Access denied</faultstring></SOAP-ENV:Fault>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    with patch("hcp_cms.services.mantis.soap.requests.post") as mock_post:
        mock_post.return_value = _mock_response(fault_xml)
        result = client.create_issue(
            project_id="1",
            summary="x",
            description="y",
        )
    assert result is None
    assert "Access denied" in client.last_error


def test_create_issue_http_error_returns_none(client: MantisSoapClient) -> None:
    with patch("hcp_cms.services.mantis.soap.requests.post") as mock_post:
        mock_post.return_value = _mock_response("Server Error", status=500)
        result = client.create_issue(
            project_id="1",
            summary="x",
            description="y",
        )
    assert result is None
    assert "500" in client.last_error


def test_create_issue_includes_handler_when_provided(client: MantisSoapClient) -> None:
    response_xml = '<return xsi:type="xsd:integer">99</return>'
    with patch("hcp_cms.services.mantis.soap.requests.post") as mock_post:
        mock_post.return_value = _mock_response(response_xml)
        client.create_issue(
            project_id="1",
            summary="x",
            description="y",
            handler="YOGA",
        )
        sent_body = mock_post.call_args.kwargs.get("data", b"").decode("utf-8")
    assert "<man:handler>" in sent_body
    assert "<man:name>YOGA</man:name>" in sent_body


def test_create_issue_omits_handler_when_none(client: MantisSoapClient) -> None:
    response_xml = '<return xsi:type="xsd:integer">99</return>'
    with patch("hcp_cms.services.mantis.soap.requests.post") as mock_post:
        mock_post.return_value = _mock_response(response_xml)
        client.create_issue(
            project_id="1",
            summary="x",
            description="y",
            handler=None,
        )
        sent_body = mock_post.call_args.kwargs.get("data", b"").decode("utf-8")
    assert "<man:handler>" not in sent_body
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_soap_write.py -v
```

預期：FAIL

- [ ] **Step 3：實作 `create_issue`**

於 `src/hcp_cms/services/mantis/soap.py` 的 `MantisSoapClient` 內加：

```python
    def create_issue(
        self,
        project_id: str,
        summary: str,
        description: str,
        category: str = "",
        priority: str = "normal",
        severity: str = "minor",
        handler: str | None = None,
    ) -> str | None:
        if not self._connected:
            self.last_error = "尚未連線，請先呼叫 connect()"
            return None

        handler_block = (
            f"<man:handler><man:name>{self._escape_xml(handler)}</man:name></man:handler>"
            if handler else ""
        )
        category_block = (
            f"<man:category>{self._escape_xml(category)}</man:category>"
            if category else ""
        )

        soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:man="http://futureware.biz/mantisconnect">
    <soapenv:Body>
        <man:mc_issue_add>
            <man:username>{self._escape_xml(self._username)}</man:username>
            <man:password>{self._escape_xml(self._password)}</man:password>
            <man:issue>
                <man:project><man:id>{self._escape_xml(project_id)}</man:id></man:project>
                <man:summary>{self._escape_xml(summary)}</man:summary>
                <man:description>{self._escape_xml(description)}</man:description>
                {category_block}
                <man:priority><man:name>{self._escape_xml(priority)}</man:name></man:priority>
                <man:severity><man:name>{self._escape_xml(severity)}</man:name></man:severity>
                {handler_block}
            </man:issue>
        </man:mc_issue_add>
    </soapenv:Body>
</soapenv:Envelope>"""

        try:
            resp = requests.post(
                f"{self._base_url}/api/soap/mantisconnect.php",
                data=soap_body.encode("utf-8"),
                headers={"Content-Type": "text/xml; charset=utf-8"},
                timeout=30,
                verify=False,
            )
            if resp.status_code != 200:
                self.last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                return None
            text = resp.text
            if "<faultstring>" in text:
                fault = self._extract_xml(text, "faultstring") or "未知錯誤"
                self.last_error = f"SOAP 錯誤：{fault}"
                return None
            # 抓 <return> 內的數字
            ticket_id = self._extract_xml(text, "return")
            if not ticket_id or not ticket_id.strip().isdigit():
                self.last_error = f"回應解析失敗：{text[:200]}"
                return None
            return ticket_id.strip()
        except requests.exceptions.ConnectionError as e:
            self.last_error = f"連線失敗：{e}"
            return None
        except requests.exceptions.Timeout:
            self.last_error = "連線逾時（30 秒）"
            return None
        except Exception as e:
            self.last_error = f"未知錯誤：{e}"
            return None

    @staticmethod
    def _escape_xml(value: str) -> str:
        """XML escape: &, <, >, ", '"""
        if value is None:
            return ""
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )
```

- [ ] **Step 4：跑測試驗證通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_soap_write.py -v
```

預期：5 個測試 PASS

- [ ] **Step 5：commit**

```bash
git add src/hcp_cms/services/mantis/soap.py tests/unit/test_mantis_soap_write.py
git commit -m "feat(mantis): MantisSoapClient.create_issue 實作（mc_issue_add）"
```

---

### Task 7：`MantisSoapClient.add_note` 實作

**Files:**
- Modify: `src/hcp_cms/services/mantis/soap.py`

**目的：** 透過 SOAP `mc_issue_note_add` 加 bugnote。

- [ ] **Step 1：在既有 test 檔加新測試**

於 `tests/unit/test_mantis_soap_write.py` 末加：

```python
def test_add_note_success_returns_note_id(client: MantisSoapClient) -> None:
    response_xml = """<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<m:mc_issue_note_addResponse><return xsi:type="xsd:integer">789</return></m:mc_issue_note_addResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    with patch("hcp_cms.services.mantis.soap.requests.post") as mock_post:
        mock_post.return_value = _mock_response(response_xml)
        note_id = client.add_note(issue_id="1234", text="客服更新")
    assert note_id == "789"


def test_add_note_fault_returns_none(client: MantisSoapClient) -> None:
    fault_xml = "<SOAP-ENV:Fault><faultstring>Issue not found</faultstring></SOAP-ENV:Fault>"
    with patch("hcp_cms.services.mantis.soap.requests.post") as mock_post:
        mock_post.return_value = _mock_response(fault_xml)
        result = client.add_note(issue_id="999", text="x")
    assert result is None
    assert "Issue not found" in client.last_error


def test_add_note_escapes_xml(client: MantisSoapClient) -> None:
    response_xml = '<return xsi:type="xsd:integer">1</return>'
    with patch("hcp_cms.services.mantis.soap.requests.post") as mock_post:
        mock_post.return_value = _mock_response(response_xml)
        client.add_note(issue_id="1", text="A & B <tag>")
        sent_body = mock_post.call_args.kwargs.get("data", b"").decode("utf-8")
    assert "A &amp; B &lt;tag&gt;" in sent_body
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_soap_write.py::test_add_note_success_returns_note_id -v
```

預期：FAIL

- [ ] **Step 3：實作 `add_note`**

於 `MantisSoapClient` 內加：

```python
    def add_note(
        self,
        issue_id: str,
        text: str,
        view_state: str = "public",
    ) -> str | None:
        if not self._connected:
            self.last_error = "尚未連線，請先呼叫 connect()"
            return None

        soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:man="http://futureware.biz/mantisconnect">
    <soapenv:Body>
        <man:mc_issue_note_add>
            <man:username>{self._escape_xml(self._username)}</man:username>
            <man:password>{self._escape_xml(self._password)}</man:password>
            <man:issue_id>{self._escape_xml(issue_id)}</man:issue_id>
            <man:note>
                <man:text>{self._escape_xml(text)}</man:text>
                <man:view_state><man:name>{self._escape_xml(view_state)}</man:name></man:view_state>
            </man:note>
        </man:mc_issue_note_add>
    </soapenv:Body>
</soapenv:Envelope>"""

        try:
            resp = requests.post(
                f"{self._base_url}/api/soap/mantisconnect.php",
                data=soap_body.encode("utf-8"),
                headers={"Content-Type": "text/xml; charset=utf-8"},
                timeout=30,
                verify=False,
            )
            if resp.status_code != 200:
                self.last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                return None
            text_resp = resp.text
            if "<faultstring>" in text_resp:
                fault = self._extract_xml(text_resp, "faultstring") or "未知錯誤"
                self.last_error = f"SOAP 錯誤：{fault}"
                return None
            note_id = self._extract_xml(text_resp, "return")
            if not note_id or not note_id.strip().isdigit():
                self.last_error = f"回應解析失敗：{text_resp[:200]}"
                return None
            return note_id.strip()
        except requests.exceptions.ConnectionError as e:
            self.last_error = f"連線失敗：{e}"
            return None
        except requests.exceptions.Timeout:
            self.last_error = "連線逾時（30 秒）"
            return None
        except Exception as e:
            self.last_error = f"未知錯誤：{e}"
            return None
```

- [ ] **Step 4：跑測試驗證通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_soap_write.py -v
```

預期：8 個測試全 PASS

- [ ] **Step 5：commit**

```bash
git add src/hcp_cms/services/mantis/soap.py tests/unit/test_mantis_soap_write.py
git commit -m "feat(mantis): MantisSoapClient.add_note 實作（mc_issue_note_add）"
```

---

## Phase 3：Core 層

### Task 8：D-2 — `已結案` 案件客戶回信不重開、加 case_log

**Files:**
- Modify: `src/hcp_cms/core/thread_tracker.py:88-92`（find_thread_parent 加搜尋 已結案）
- Modify: `src/hcp_cms/core/case_manager.py:354-358`（match 到已結案 parent 時改加 case_log 不建子案件）

**目的：** 已結案案件被客戶回信時，不建子案件、不重開、只在原案件加一筆 case_log。

- [ ] **Step 1：寫失敗測試**

新增 `tests/unit/test_thread_tracker_closed_case.py`：

```python
"""D-2：已結案案件客戶回信時的行為。"""
import sqlite3
from pathlib import Path

import pytest

from hcp_cms.core.case_manager import CaseManager
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.repositories import (
    CaseRepository,
    CaseLogRepository,
    CompanyRepository,
)
from hcp_cms.data.models import Case, Company


@pytest.fixture
def db(tmp_path: Path):
    d = DatabaseManager(tmp_path / "t.db")
    d.initialize()
    yield d
    d.close()


def _make_closed_parent_case(conn: sqlite3.Connection) -> str:
    """準備一個 已結案 parent case。"""
    CompanyRepository(conn).insert(Company(company_id="CO-1", name="ABC", domain="abc.com"))
    repo = CaseRepository(conn)
    case = Case(
        case_id="C-PARENT",
        subject="印表機異常",
        company_id="CO-1",
        status="已結案",
        message_id="<msg-001@abc.com>",
        sent_time="2026/05/01 10:00:00",
    )
    repo.insert(case)
    return case.case_id


def test_thread_tracker_finds_closed_parent(db) -> None:
    """ThreadTracker 必須能找到 已結案 case 作為 parent。"""
    from hcp_cms.core.thread_tracker import ThreadTracker
    _make_closed_parent_case(db.conn)
    tracker = ThreadTracker(db.conn)
    parent = tracker.find_thread_parent(
        company_id="CO-1",
        subject="Re: 印表機異常",
        in_reply_to=None,
    )
    assert parent is not None
    assert parent.case_id == "C-PARENT"


def test_customer_reply_to_closed_does_not_create_new_case(db) -> None:
    """已結案 parent 收客戶回信時，不建新子案件。"""
    _make_closed_parent_case(db.conn)
    mgr = CaseManager(db.conn)
    classification = {"company_id": "CO-1"}
    result = mgr.create_case(
        subject="Re: 印表機異常",
        body="客戶再次來信",
        sender="customer@abc.com",
        message_id="<msg-002@abc.com>",
        in_reply_to="<msg-001@abc.com>",
        sent_time="2026/05/13 10:00:00",
        classification=classification,
    )
    # 不應建子案件 — 應回傳 parent 本身
    assert result.case_id == "C-PARENT"


def test_customer_reply_to_closed_adds_case_log(db) -> None:
    """已結案 parent 收客戶回信時，加一筆 case_log。"""
    _make_closed_parent_case(db.conn)
    mgr = CaseManager(db.conn)
    mgr.create_case(
        subject="Re: 印表機異常",
        body="客戶補充：依然有問題",
        sender="customer@abc.com",
        message_id="<msg-002@abc.com>",
        in_reply_to="<msg-001@abc.com>",
        sent_time="2026/05/13 10:00:00",
        classification={"company_id": "CO-1"},
    )
    logs = CaseLogRepository(db.conn).list_by_case_id("C-PARENT")
    # 至少有一筆「客戶回信到已結案」的 case_log
    matching = [
        log for log in logs
        if log.direction == "客戶來信" and "依然有問題" in (log.content or "")
    ]
    assert len(matching) >= 1


def test_customer_reply_to_closed_does_not_change_status(db) -> None:
    """已結案 parent 收客戶回信後，狀態仍為 已結案。"""
    _make_closed_parent_case(db.conn)
    mgr = CaseManager(db.conn)
    mgr.create_case(
        subject="Re: 印表機異常",
        body="再次回信",
        sender="customer@abc.com",
        message_id="<msg-003@abc.com>",
        in_reply_to="<msg-001@abc.com>",
        sent_time="2026/05/13 10:00:00",
        classification={"company_id": "CO-1"},
    )
    parent = CaseRepository(db.conn).get_by_id("C-PARENT")
    assert parent.status == "已結案"
```

⚠ 如果 `CaseManager.create_case` 的簽名與上述不符，依實際簽名調整測試（先讀 case_manager.py 開頭）。

- [ ] **Step 2：讀 CaseManager.create_case 實際簽名**

```bash
.venv/Scripts/python.exe -c "from hcp_cms.core.case_manager import CaseManager; import inspect; print(inspect.signature(CaseManager.create_case))"
```

依實際簽名修正 Step 1 測試（測試中 `classification` 參數應符合既有用法）。

- [ ] **Step 3：跑測試驗證失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_thread_tracker_closed_case.py -v
```

預期：4 個測試 FAIL

- [ ] **Step 4：修改 `thread_tracker.py:88-92` — 加搜尋已結案**

`src/hcp_cms/core/thread_tracker.py` 內既有：

```python
            from datetime import datetime, timedelta
            cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y/%m/%d")
            for case in self._case_repo.list_by_status("已完成"):
                if case.company_id == company_id and case.subject:
                    if (case.sent_time or "") >= cutoff:
                        if self.subjects_match(case.subject, subject):
                            return self._find_root(case)
```

改成同時搜尋「已完成」與「已結案」：

```python
            from datetime import datetime, timedelta
            cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y/%m/%d")
            for status in ("已完成", "已結案"):
                for case in self._case_repo.list_by_status(status):
                    if case.company_id == company_id and case.subject:
                        if (case.sent_time or "") >= cutoff:
                            if self.subjects_match(case.subject, subject):
                                return self._find_root(case)
```

⚠ 已結案案件**不受 90 天限制**？依專案決策；MVP 暫沿用 90 天 cutoff，與已完成一致。

- [ ] **Step 5：修改 `case_manager.py:354-358` — match 到已結案改加 case_log**

讀 `src/hcp_cms/core/case_manager.py` Line 320-360 區段，定位現有 parent-match 邏輯後，改成：

```python
        # link_to_parent 需要子案件已在 DB 中才能更新，故在 insert 後執行
        if parent:
            # D-2：已結案 parent 不建子案件、不重開，只加 case_log
            if parent.status == "已結案":
                # 不要 insert 新案件，反而把剛才已 insert 的子案件刪掉，加 log 到 parent
                self._case_repo.delete(case_id)
                # 將內容存為 parent 的客戶來信 log
                from hcp_cms.data.models import CaseLog
                log = CaseLog(
                    log_id=self._log_repo.next_log_id(),
                    case_id=parent.case_id,
                    direction="客戶來信",
                    content=body,
                    logged_at=log_time,
                )
                self._log_repo.insert(log)
                return parent

            self._tracker.link_to_parent(case_id, parent.case_id)
            # Reopen parent if it was replied
            if parent.status == "已回覆":
                self.reopen_case(parent.case_id, f"後續來信: {subject}")

        return case
```

⚠ 此修改假設 `CaseRepository` 有 `delete(case_id)` 方法。先確認：

```bash
.venv/Scripts/python.exe -c "from hcp_cms.data.repositories import CaseRepository; print('delete' in dir(CaseRepository))"
```

若無 `delete`：改用「不要先 insert 子案件，而是在 match 後判斷 parent.status」重構策略——將 insert 移到 if/else 分支內。具體做法：

讀現有 case_manager.py 邏輯，重構 create_case 使得：
1. 先計算 parent (透過 ThreadTracker)
2. 若 parent.status == "已結案" → 直接加 log 到 parent，不 insert 新案，回傳 parent
3. 否則 → 既有流程（insert 子案件 + link_to_parent + 可能 reopen）

- [ ] **Step 6：跑測試驗證通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_thread_tracker_closed_case.py -v
```

預期：4 個測試 PASS

- [ ] **Step 7：跑全部既有測試確認無回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ --tb=short
```

預期：既有測試全 PASS。**特別注意** thread_tracker / case_manager 相關測試。

- [ ] **Step 8：commit**

```bash
git add src/hcp_cms/core/thread_tracker.py src/hcp_cms/core/case_manager.py tests/unit/test_thread_tracker_closed_case.py
git commit -m "feat(core): D-2 已結案 case 收客戶回信時不建新案，只加 case_log"
```

---

### Task 9：`WebAuthManager`（點名 + cookie）

**Files:**
- Create: `src/hcp_cms/web/__init__.py`（空）
- Create: `src/hcp_cms/web/auth.py`
- Create: `tests/unit/test_web_auth_manager.py`

**目的：** 管理 Web Portal 認證（pick-from-list + HttpOnly cookie）。

- [ ] **Step 1：寫失敗測試**

新增 `tests/unit/test_web_auth_manager.py`：

```python
"""WebAuthManager 測試。"""
import sqlite3
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.repositories import StaffRepository
from hcp_cms.data.models import Staff
from hcp_cms.web.auth import WebAuthManager


@pytest.fixture
def auth(tmp_path: Path):
    db = DatabaseManager(tmp_path / "t.db")
    db.initialize()
    sr = StaffRepository(db.conn)
    sr.insert(Staff(staff_id="S001", name="jill", role="cs"))
    sr.insert(Staff(staff_id="S002", name="YOGA", role="cs"))
    sr.insert(Staff(staff_id="S003", name="Rebecca", role="cs"))
    sr.insert(Staff(staff_id="S004", name="老闆", role="admin"))  # 非 cs
    yield WebAuthManager(db.conn)
    db.close()


def test_list_cs_staff_returns_only_cs_role(auth: WebAuthManager) -> None:
    staff = auth.list_cs_staff()
    names = {s.name for s in staff}
    assert names == {"jill", "YOGA", "Rebecca"}


def test_get_staff_by_id_existing(auth: WebAuthManager) -> None:
    s = auth.get_staff_by_id("S001")
    assert s is not None
    assert s.name == "jill"


def test_get_staff_by_id_missing(auth: WebAuthManager) -> None:
    assert auth.get_staff_by_id("S999") is None


def test_get_staff_by_id_non_cs_returns_none(auth: WebAuthManager) -> None:
    """非 cs role 的 staff 不可透過此方法登入。"""
    assert auth.get_staff_by_id("S004") is None
```

⚠ 確認 `Staff` model 有 `role` 欄位。先查：

```bash
.venv/Scripts/python.exe -c "from hcp_cms.data.models import Staff; from dataclasses import fields; print([f.name for f in fields(Staff)])"
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_web_auth_manager.py -v
```

預期：FAIL（auth module 不存在）

- [ ] **Step 3：建立 `src/hcp_cms/web/__init__.py`**

```bash
mkdir -p src/hcp_cms/web/pages
```

```python
# src/hcp_cms/web/__init__.py
"""HCP CMS Web Portal — NiceGUI-based browser client for 3-CS team."""
```

```python
# src/hcp_cms/web/pages/__init__.py
"""Page modules for Web Portal."""
```

- [ ] **Step 4：寫 `WebAuthManager`**

新增 `src/hcp_cms/web/auth.py`：

```python
"""Web Portal 認證管理 — 點名登入 + cookie 裝置綁定。"""
from __future__ import annotations

import sqlite3

from hcp_cms.data.models import Staff
from hcp_cms.data.repositories import StaffRepository

COOKIE_NAME = "cms_staff"
COOKIE_MAX_AGE_SECONDS = 365 * 24 * 60 * 60  # 1 年


class WebAuthManager:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._staff_repo = StaffRepository(conn)

    def list_cs_staff(self) -> list[Staff]:
        """列出 role='cs' 的 staff（登入頁顯示用）。"""
        return [s for s in self._staff_repo.list_all() if s.role == "cs"]

    def get_staff_by_id(self, staff_id: str) -> Staff | None:
        """依 staff_id 取 staff，僅回傳 role='cs' 者。"""
        s = self._staff_repo.get_by_id(staff_id)
        if s is None or s.role != "cs":
            return None
        return s
```

⚠ 若 `StaffRepository.list_all` 不存在，改用相對應的既有方法（如 `list_by_role` 或直接 SQL）。

- [ ] **Step 5：跑測試驗證通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_web_auth_manager.py -v
```

預期：4 個測試 PASS

- [ ] **Step 6：commit**

```bash
git add src/hcp_cms/web/__init__.py src/hcp_cms/web/auth.py src/hcp_cms/web/pages/__init__.py tests/unit/test_web_auth_manager.py
git commit -m "feat(web): WebAuthManager 點名登入 + cookie 設定常數"
```

---

### Task 10：`CaseVisibilityFilter`（B+A + G-3）

**Files:**
- Create: `src/hcp_cms/web/visibility.py`
- Create: `tests/unit/test_case_visibility_filter.py`

**目的：** 依登入客服身分過濾可視案件。規則：`(handler = 我 OR company.cs_staff_id = 我) AND handler IS NOT NULL`。

- [ ] **Step 1：寫失敗測試**

新增 `tests/unit/test_case_visibility_filter.py`：

```python
"""CaseVisibilityFilter B+A 聯集 + G-3 排除未指派。"""
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, Company, Staff
from hcp_cms.data.repositories import (
    CaseRepository,
    CompanyRepository,
    StaffRepository,
)
from hcp_cms.web.visibility import CaseVisibilityFilter


@pytest.fixture
def setup(tmp_path: Path):
    db = DatabaseManager(tmp_path / "t.db")
    db.initialize()

    StaffRepository(db.conn).insert(Staff(staff_id="S-YOGA", name="YOGA", role="cs"))
    StaffRepository(db.conn).insert(Staff(staff_id="S-REBECCA", name="Rebecca", role="cs"))

    co_repo = CompanyRepository(db.conn)
    co_repo.insert(Company(company_id="CO-A", name="A 公司", domain="a.com", cs_staff_id="S-YOGA"))
    co_repo.insert(Company(company_id="CO-B", name="B 公司", domain="b.com", cs_staff_id="S-REBECCA"))
    co_repo.insert(Company(company_id="CO-X", name="X 公司", domain="x.com"))  # 無 cs_staff

    case_repo = CaseRepository(db.conn)
    # YOGA 是 handler
    case_repo.insert(Case(case_id="C-1", subject="A1", handler="YOGA", company_id="CO-A"))
    # YOGA 是 cs_staff 透過公司
    case_repo.insert(Case(case_id="C-2", subject="A2", handler="Rebecca", company_id="CO-A"))
    # Rebecca 應該看到
    case_repo.insert(Case(case_id="C-3", subject="B1", handler="Rebecca", company_id="CO-B"))
    # 未指派（G-3 應排除）
    case_repo.insert(Case(case_id="C-4", subject="A3", handler=None, company_id="CO-A"))
    case_repo.insert(Case(case_id="C-5", subject="A4", handler="", company_id="CO-A"))
    # 沒人管的孤兒
    case_repo.insert(Case(case_id="C-6", subject="X1", handler=None, company_id="CO-X"))

    yield db, CaseVisibilityFilter(db.conn)
    db.close()


def test_yoga_sees_handler_and_company_cases(setup) -> None:
    _, vf = setup
    yoga = Staff(staff_id="S-YOGA", name="YOGA", role="cs")
    ids = {c.case_id for c in vf.visible_cases(yoga)}
    # C-1（handler=YOGA）+ C-2（CO-A → YOGA）
    assert ids == {"C-1", "C-2"}


def test_rebecca_sees_only_her_cases(setup) -> None:
    _, vf = setup
    rebecca = Staff(staff_id="S-REBECCA", name="Rebecca", role="cs")
    ids = {c.case_id for c in vf.visible_cases(rebecca)}
    # C-2 (handler=Rebecca, 公司=CO-A 雖然不是 Rebecca 但 handler 是 Rebecca)
    # C-3 (handler=Rebecca + 公司=CO-B)
    assert ids == {"C-2", "C-3"}


def test_unassigned_cases_excluded(setup) -> None:
    _, vf = setup
    yoga = Staff(staff_id="S-YOGA", name="YOGA", role="cs")
    ids = {c.case_id for c in vf.visible_cases(yoga)}
    # C-4 (handler=None)、C-5 (handler='') 即使屬於 CO-A 也不顯示
    assert "C-4" not in ids
    assert "C-5" not in ids


def test_handler_case_insensitive(setup) -> None:
    """既有資料有 ~7 筆 JILL 大寫，比對需大小寫不敏感。"""
    db, vf = setup
    case_repo = CaseRepository(db.conn)
    case_repo.insert(Case(case_id="C-7", subject="legacy", handler="YOGA", company_id="CO-A"))
    case_repo.insert(Case(case_id="C-8", subject="legacy", handler="yoga", company_id="CO-A"))
    yoga = Staff(staff_id="S-YOGA", name="YOGA", role="cs")
    ids = {c.case_id for c in vf.visible_cases(yoga)}
    assert "C-7" in ids
    assert "C-8" in ids
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_case_visibility_filter.py -v
```

預期：FAIL

- [ ] **Step 3：實作 `CaseVisibilityFilter`**

新增 `src/hcp_cms/web/visibility.py`：

```python
"""案件可視性過濾 — B+A 聯集 + G-3 排除未指派。"""
from __future__ import annotations

import sqlite3

from hcp_cms.data.models import Case, Staff
from hcp_cms.data.repositories import CaseRepository


class CaseVisibilityFilter:
    """依登入客服身分過濾可視案件。

    規則 (B+A 聯集 + G-3)：
        (LOWER(handler) = LOWER(staff.name)
         OR company_id IN (companies where cs_staff_id = staff.staff_id))
        AND handler IS NOT NULL AND handler != ''
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._case_repo = CaseRepository(conn)

    def visible_cases(self, staff: Staff) -> list[Case]:
        rows = self._conn.execute(
            """
            SELECT c.* FROM cs_cases c
            WHERE (
                LOWER(c.handler) = LOWER(?)
                OR c.company_id IN (
                    SELECT company_id FROM companies WHERE cs_staff_id = ?
                )
            )
            AND c.handler IS NOT NULL
            AND c.handler != ''
            ORDER BY c.updated_at DESC
            """,
            (staff.name, staff.staff_id),
        ).fetchall()
        # 重用 CaseRepository._row_to_case 反序列化
        return [self._case_repo._row_to_case(r) for r in rows]
```

⚠ 若 `CaseRepository._row_to_case` 命名不同（如 `_to_case` 或公開方法），依實際調整。

- [ ] **Step 4：跑測試驗證通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_case_visibility_filter.py -v
```

預期：4 個測試 PASS

- [ ] **Step 5：commit**

```bash
git add src/hcp_cms/web/visibility.py tests/unit/test_case_visibility_filter.py
git commit -m "feat(web): CaseVisibilityFilter B+A 聯集 + G-3 排除未指派"
```

---

### Task 11：`AuditLogger`（雙寫 web_audit_log + case_logs for mantis_push）

**Files:**
- Create: `src/hcp_cms/web/audit.py`
- Create: `tests/unit/test_audit_logger.py`

**目的：** 提供統一介面記錄稽核事件。`log_field_change` 寫單一 `web_audit_log`；`log_mantis_push` 雙寫 `web_audit_log` + `case_logs`。

- [ ] **Step 1：寫失敗測試**

新增 `tests/unit/test_audit_logger.py`：

```python
"""AuditLogger 雙寫測試。"""
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.repositories import (
    WebAuditLogRepository,
    CaseLogRepository,
    CaseRepository,
)
from hcp_cms.data.models import Case
from hcp_cms.web.audit import AuditLogger


@pytest.fixture
def setup(tmp_path: Path):
    db = DatabaseManager(tmp_path / "t.db")
    db.initialize()
    CaseRepository(db.conn).insert(Case(case_id="C-1", subject="test"))
    yield db
    db.close()


def test_log_field_change_writes_audit_log(setup) -> None:
    db = setup
    logger = AuditLogger(db.conn)
    logger.log_field_change(staff_id="S001", case_id="C-1", field_name="status")
    rows = WebAuditLogRepository(db.conn).list_by_case_id("C-1")
    assert len(rows) == 1
    assert rows[0].field_name == "status"


def test_log_field_change_does_not_write_case_log(setup) -> None:
    db = setup
    logger = AuditLogger(db.conn)
    logger.log_field_change(staff_id="S001", case_id="C-1", field_name="status")
    logs = CaseLogRepository(db.conn).list_by_case_id("C-1")
    assert len(logs) == 0


def test_log_mantis_push_writes_both(setup) -> None:
    db = setup
    logger = AuditLogger(db.conn)
    logger.log_mantis_push(
        staff_id="S001",
        case_id="C-1",
        ticket_id="9999",
        mode="new_ticket",
    )

    audit_rows = WebAuditLogRepository(db.conn).list_by_case_id("C-1")
    assert len(audit_rows) == 1
    assert audit_rows[0].field_name == "mantis_push"

    case_logs = CaseLogRepository(db.conn).list_by_case_id("C-1")
    assert len(case_logs) == 1
    assert case_logs[0].direction == "Mantis 推送"
    assert case_logs[0].mantis_ref == "9999"
    assert "9999" in (case_logs[0].content or "")
    assert "new_ticket" in (case_logs[0].content or "")


def test_log_mantis_push_bugnote_mode(setup) -> None:
    db = setup
    logger = AuditLogger(db.conn)
    logger.log_mantis_push(
        staff_id="S001",
        case_id="C-1",
        ticket_id="9999",
        mode="bugnote",
    )
    case_logs = CaseLogRepository(db.conn).list_by_case_id("C-1")
    assert "bugnote" in (case_logs[0].content or "")
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_audit_logger.py -v
```

預期：FAIL（AuditLogger 不存在）

- [ ] **Step 3：實作 `AuditLogger`**

新增 `src/hcp_cms/web/audit.py`：

```python
"""稽核紀錄 — 雙寫 web_audit_log + case_logs（Mantis 推送）。"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from hcp_cms.data.models import CaseLog
from hcp_cms.data.repositories import CaseLogRepository, WebAuditLogRepository


class AuditLogger:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._audit_repo = WebAuditLogRepository(conn)
        self._log_repo = CaseLogRepository(conn)

    def log_field_change(self, staff_id: str, case_id: str, field_name: str) -> None:
        """記錄欄位變更到 web_audit_log。"""
        self._audit_repo.insert(staff_id=staff_id, case_id=case_id, field_name=field_name)

    def log_mantis_push(
        self,
        staff_id: str,
        case_id: str,
        ticket_id: str,
        mode: str,
    ) -> None:
        """記錄 Mantis 推送 — 雙寫。

        1. web_audit_log: field_name='mantis_push'（追蹤誰何時推）
        2. case_logs: direction='Mantis 推送' + content 含 ticket_id + mode
        """
        self._audit_repo.insert(
            staff_id=staff_id,
            case_id=case_id,
            field_name="mantis_push",
        )

        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        log = CaseLog(
            log_id=self._log_repo.next_log_id(),
            case_id=case_id,
            direction="Mantis 推送",
            content=f"{staff_id} 於 {now} 推送為 {mode}: ticket #{ticket_id}",
            mantis_ref=ticket_id,
            logged_by=staff_id,
            logged_at=now,
        )
        self._log_repo.insert(log)
```

- [ ] **Step 4：跑測試驗證通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_audit_logger.py -v
```

預期：4 個測試 PASS

- [ ] **Step 5：commit**

```bash
git add src/hcp_cms/web/audit.py tests/unit/test_audit_logger.py
git commit -m "feat(web): AuditLogger 欄位變更 + Mantis 推送雙寫"
```

---

### Task 12：`MantisPushManager` — 模式 (a) 單筆建新 ticket

**Files:**
- Create: `src/hcp_cms/web/mantis_push.py`
- Create: `tests/unit/test_mantis_push_manager.py`

**目的：** Core 層編排「案件 → Mantis ticket」的轉換 + push + 寫入 case_mantis + audit。

- [ ] **Step 1：寫失敗測試**

新增 `tests/unit/test_mantis_push_manager.py`：

```python
"""MantisPushManager 三模式測試（mock MantisClient）。"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, CaseMantisLink
from hcp_cms.data.repositories import (
    CaseRepository,
    CaseMantisRepository,
    CaseLogRepository,
)
from hcp_cms.web.mantis_push import MantisPushManager


@pytest.fixture
def setup(tmp_path: Path):
    db = DatabaseManager(tmp_path / "t.db")
    db.initialize()
    CaseRepository(db.conn).insert(
        Case(
            case_id="C-1",
            subject="印表機異常",
            progress="已聯絡客戶確認",
            priority="高",
            handler="YOGA",
        )
    )
    yield db
    db.close()


def test_push_case_as_new_ticket_success(setup) -> None:
    db = setup
    client = MagicMock()
    client.create_issue.return_value = "12345"

    mgr = MantisPushManager(db.conn, client=client, project_id="1")
    success, payload = mgr.push_case_as_new_ticket(
        case_id="C-1",
        operator_staff_id="S-YOGA",
    )
    assert success is True
    assert payload == "12345"

    # 確認寫入 case_mantis
    links = CaseMantisRepository(db.conn).list_by_case_id("C-1")
    assert len(links) == 1
    assert links[0].ticket_id == "12345"

    # 確認 SOAP 帶入正確欄位
    call_kwargs = client.create_issue.call_args.kwargs
    assert call_kwargs["project_id"] == "1"
    assert call_kwargs["summary"] == "印表機異常"
    assert "[HCP-CMS: C-1]" in call_kwargs["description"]
    assert "已聯絡客戶確認" in call_kwargs["description"]
    assert call_kwargs["priority"] == "high"  # 高→high
    assert call_kwargs["handler"] == "YOGA"


def test_push_case_as_new_ticket_priority_mapping(setup) -> None:
    db = setup
    client = MagicMock()
    client.create_issue.return_value = "1"
    mgr = MantisPushManager(db.conn, client=client, project_id="1")

    # 中
    CaseRepository(db.conn).insert(Case(case_id="C-M", subject="中", priority="中", handler="YOGA"))
    mgr.push_case_as_new_ticket("C-M", "S-YOGA")
    assert client.create_issue.call_args.kwargs["priority"] == "normal"

    # 低
    CaseRepository(db.conn).insert(Case(case_id="C-L", subject="低", priority="低", handler="YOGA"))
    mgr.push_case_as_new_ticket("C-L", "S-YOGA")
    assert client.create_issue.call_args.kwargs["priority"] == "low"


def test_push_case_as_new_ticket_already_linked_fails(setup) -> None:
    db = setup
    # 預先建立連結
    CaseMantisRepository(db.conn).insert(
        CaseMantisLink(case_id="C-1", ticket_id="9999")
    )
    client = MagicMock()
    mgr = MantisPushManager(db.conn, client=client, project_id="1")
    success, payload = mgr.push_case_as_new_ticket("C-1", "S-YOGA")
    assert success is False
    assert "已連結" in payload
    # 不該打 SOAP
    client.create_issue.assert_not_called()


def test_push_case_as_new_ticket_case_not_found(setup) -> None:
    db = setup
    client = MagicMock()
    mgr = MantisPushManager(db.conn, client=client, project_id="1")
    success, payload = mgr.push_case_as_new_ticket("C-NONEXIST", "S-YOGA")
    assert success is False
    assert "不存在" in payload
    client.create_issue.assert_not_called()


def test_push_case_as_new_ticket_soap_failure_does_not_write_link(setup) -> None:
    db = setup
    client = MagicMock()
    client.create_issue.return_value = None
    client.last_error = "Mantis 拒絕連線"

    mgr = MantisPushManager(db.conn, client=client, project_id="1")
    success, payload = mgr.push_case_as_new_ticket("C-1", "S-YOGA")
    assert success is False
    assert "Mantis 拒絕連線" in payload

    # case_mantis 不該有記錄
    links = CaseMantisRepository(db.conn).list_by_case_id("C-1")
    assert len(links) == 0
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_push_manager.py -v
```

預期：FAIL

- [ ] **Step 3：實作 `MantisPushManager.push_case_as_new_ticket`**

新增 `src/hcp_cms/web/mantis_push.py`：

```python
"""Mantis 手動推送管理器 — 案件 → Mantis ticket / bugnote 三模式。"""
from __future__ import annotations

import sqlite3

from hcp_cms.data.models import Case, CaseMantisLink
from hcp_cms.data.repositories import (
    CaseRepository,
    CaseMantisRepository,
    CaseLogRepository,
)
from hcp_cms.services.mantis.base import MantisClient
from hcp_cms.web.audit import AuditLogger

_PRIORITY_MAP = {"高": "high", "中": "normal", "低": "low"}


class MantisPushManager:
    def __init__(
        self,
        conn: sqlite3.Connection,
        client: MantisClient,
        project_id: str,
    ) -> None:
        self._conn = conn
        self._client = client
        self._project_id = project_id
        self._case_repo = CaseRepository(conn)
        self._link_repo = CaseMantisRepository(conn)
        self._log_repo = CaseLogRepository(conn)
        self._auditor = AuditLogger(conn)

    # ---- 模式 (a) 單筆建新 ticket ----

    def push_case_as_new_ticket(
        self,
        case_id: str,
        operator_staff_id: str,
    ) -> tuple[bool, str]:
        """單筆推：建新 Mantis ticket。

        Returns:
            (True, ticket_id) on success
            (False, error_message) on failure
        """
        case = self._case_repo.get_by_id(case_id)
        if case is None:
            return False, f"案件 {case_id} 不存在"

        existing_links = self._link_repo.list_by_case_id(case_id)
        if existing_links:
            return False, f"案件已連結 Mantis ticket #{existing_links[0].ticket_id}，請改用 push_as_bugnote"

        ticket_id = self._client.create_issue(
            project_id=self._project_id,
            summary=case.subject,
            description=self._build_description(case),
            priority=_PRIORITY_MAP.get(case.priority, "normal"),
            severity="minor",
            handler=case.handler if case.handler else None,
        )
        if ticket_id is None:
            return False, getattr(self._client, "last_error", "未知 Mantis SOAP 錯誤")

        self._link_repo.insert(
            CaseMantisLink(
                case_id=case_id,
                ticket_id=ticket_id,
                summary=case.subject,
            )
        )
        self._auditor.log_mantis_push(
            staff_id=operator_staff_id,
            case_id=case_id,
            ticket_id=ticket_id,
            mode="new_ticket",
        )
        return True, ticket_id

    def _build_description(self, case: Case) -> str:
        """組裝 Mantis description：[HCP-CMS] header + 主旨 + 本文 + 進度。"""
        parts = [f"[HCP-CMS: {case.case_id}]"]
        if case.subject:
            parts.append(f"【主旨】{case.subject}")
        if case.progress:
            parts.append("【處理進度】\n" + case.progress)
        if case.company_id:
            parts.append(f"【客戶】{case.company_id}")
        if case.contact_person:
            parts.append(f"【聯絡人】{case.contact_person}")
        return "\n\n".join(parts)
```

- [ ] **Step 4：跑測試驗證通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_push_manager.py -v
```

預期：5 個測試 PASS

- [ ] **Step 5：commit**

```bash
git add src/hcp_cms/web/mantis_push.py tests/unit/test_mantis_push_manager.py
git commit -m "feat(web): MantisPushManager.push_case_as_new_ticket (模式 a)"
```

---

### Task 13：`MantisPushManager.push_case_as_bugnote`（模式 c）

**Files:**
- Modify: `src/hcp_cms/web/mantis_push.py`（加方法）
- Modify: `tests/unit/test_mantis_push_manager.py`

- [ ] **Step 1：在 test 檔加新測試**

於 `tests/unit/test_mantis_push_manager.py` 末加：

```python
def test_push_case_as_bugnote_success(setup) -> None:
    db = setup
    # 預先建立 case_mantis 連結
    CaseMantisRepository(db.conn).insert(
        CaseMantisLink(case_id="C-1", ticket_id="9999")
    )
    client = MagicMock()
    client.add_note.return_value = "note-456"

    mgr = MantisPushManager(db.conn, client=client, project_id="1")
    success, payload = mgr.push_case_as_bugnote("C-1", "S-YOGA")

    assert success is True
    assert payload == "note-456"
    # 確認 add_note 內含案件最新內容
    call_kwargs = client.add_note.call_args.kwargs
    assert call_kwargs["issue_id"] == "9999"
    assert "已聯絡客戶確認" in call_kwargs["text"]  # progress 內容


def test_push_case_as_bugnote_not_linked_fails(setup) -> None:
    db = setup
    client = MagicMock()
    mgr = MantisPushManager(db.conn, client=client, project_id="1")
    success, payload = mgr.push_case_as_bugnote("C-1", "S-YOGA")
    assert success is False
    assert "尚未連結" in payload
    client.add_note.assert_not_called()


def test_push_case_as_bugnote_soap_failure(setup) -> None:
    db = setup
    CaseMantisRepository(db.conn).insert(
        CaseMantisLink(case_id="C-1", ticket_id="9999")
    )
    client = MagicMock()
    client.add_note.return_value = None
    client.last_error = "Issue locked"

    mgr = MantisPushManager(db.conn, client=client, project_id="1")
    success, payload = mgr.push_case_as_bugnote("C-1", "S-YOGA")
    assert success is False
    assert "Issue locked" in payload
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_push_manager.py -v
```

預期：新測試 FAIL

- [ ] **Step 3：實作 `push_case_as_bugnote`**

於 `MantisPushManager` 內加：

```python
    # ---- 模式 (c) 推為 bugnote ----

    def push_case_as_bugnote(
        self,
        case_id: str,
        operator_staff_id: str,
    ) -> tuple[bool, str]:
        """模式 (c)：若案件已連結某 ticket，把最新內容推為 bugnote。"""
        case = self._case_repo.get_by_id(case_id)
        if case is None:
            return False, f"案件 {case_id} 不存在"

        links = self._link_repo.list_by_case_id(case_id)
        if not links:
            return False, "案件尚未連結 Mantis ticket，請改用建新 ticket"

        # MVP：若多筆連結，取第一筆
        ticket_id = links[0].ticket_id

        note_id = self._client.add_note(
            issue_id=ticket_id,
            text=self._build_bugnote_text(case),
        )
        if note_id is None:
            return False, getattr(self._client, "last_error", "未知 Mantis SOAP 錯誤")

        self._auditor.log_mantis_push(
            staff_id=operator_staff_id,
            case_id=case_id,
            ticket_id=ticket_id,
            mode="bugnote",
        )
        return True, note_id

    def _build_bugnote_text(self, case: Case) -> str:
        """組裝 bugnote 文字：含當前狀態 + 進度 + 最新 case_log。"""
        parts = [f"[HCP-CMS: {case.case_id}] 更新"]
        if case.status:
            parts.append(f"【當前狀態】{case.status}")
        if case.progress:
            parts.append("【最新進度】\n" + case.progress)

        # 抓最新的非 Mantis 推送 case_log
        logs = self._log_repo.list_by_case_id(case.case_id)
        non_push_logs = [l for l in logs if l.direction != "Mantis 推送"]
        if non_push_logs:
            latest = non_push_logs[0]  # 假設依 logged_at desc 排序
            parts.append(f"【最新記錄 ({latest.direction})】\n{latest.content or ''}")

        return "\n\n".join(parts)
```

- [ ] **Step 4：跑測試驗證通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_push_manager.py -v
```

預期：8 個測試（5 既有 + 3 新）全 PASS

- [ ] **Step 5：commit**

```bash
git add src/hcp_cms/web/mantis_push.py tests/unit/test_mantis_push_manager.py
git commit -m "feat(web): MantisPushManager.push_case_as_bugnote (模式 c)"
```

---

### Task 14：`MantisPushManager.push_cases_batch`（模式 b）

**Files:**
- Modify: `src/hcp_cms/web/mantis_push.py`（加方法）
- Modify: `tests/unit/test_mantis_push_manager.py`

- [ ] **Step 1：加測試**

於 test 檔末加：

```python
def test_push_cases_batch_mixed_results(setup) -> None:
    db = setup
    CaseRepository(db.conn).insert(Case(case_id="C-2", subject="A", handler="YOGA"))
    CaseRepository(db.conn).insert(Case(case_id="C-3", subject="B", handler="YOGA"))

    # C-3 已連結 → 應 skip
    CaseMantisRepository(db.conn).insert(
        CaseMantisLink(case_id="C-3", ticket_id="EXISTING-1")
    )

    client = MagicMock()
    # C-1 成功，C-2 失敗，C-3 略過
    client.create_issue.side_effect = ["111", None]
    client.last_error = "SOAP 錯誤"

    mgr = MantisPushManager(db.conn, client=client, project_id="1")
    results = mgr.push_cases_batch(
        case_ids=["C-1", "C-2", "C-3"],
        operator_staff_id="S-YOGA",
    )

    by_id = {r[0]: r for r in results}
    # (case_id, status, payload)
    assert by_id["C-1"][1] == "success"
    assert by_id["C-1"][2] == "111"
    assert by_id["C-2"][1] == "failed"
    assert "SOAP 錯誤" in by_id["C-2"][2]
    assert by_id["C-3"][1] == "skipped"
    assert "已連結" in by_id["C-3"][2]


def test_push_cases_batch_empty_list(setup) -> None:
    db = setup
    client = MagicMock()
    mgr = MantisPushManager(db.conn, client=client, project_id="1")
    results = mgr.push_cases_batch([], "S-YOGA")
    assert results == []
    client.create_issue.assert_not_called()
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_push_manager.py -v
```

預期：新測試 FAIL

- [ ] **Step 3：實作 `push_cases_batch`**

於 `MantisPushManager` 內加：

```python
    # ---- 模式 (b) 批次建新 ticket ----

    def push_cases_batch(
        self,
        case_ids: list[str],
        operator_staff_id: str,
    ) -> list[tuple[str, str, str]]:
        """模式 (b)：批次推。每筆獨立。

        Returns:
            list of (case_id, status, payload) where:
              status in ('success', 'failed', 'skipped')
              payload = ticket_id on success, error on failed, reason on skipped
        """
        results: list[tuple[str, str, str]] = []
        for case_id in case_ids:
            # 先檢查是否已連結（skip）
            if self._link_repo.list_by_case_id(case_id):
                results.append((case_id, "skipped", "案件已連結 Mantis ticket"))
                continue
            success, payload = self.push_case_as_new_ticket(case_id, operator_staff_id)
            status = "success" if success else "failed"
            results.append((case_id, status, payload))
        return results
```

- [ ] **Step 4：跑測試驗證通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_push_manager.py -v
```

預期：10 個測試全 PASS

- [ ] **Step 5：commit**

```bash
git add src/hcp_cms/web/mantis_push.py tests/unit/test_mantis_push_manager.py
git commit -m "feat(web): MantisPushManager.push_cases_batch (模式 b)"
```

---

## Phase 4：UI 層（NiceGUI Web Portal）

### Task 15：NiceGUI 環境建立 + 入口 + 登入頁 `/login`

**Files:**
- Modify: `pyproject.toml`（加 nicegui 依賴）
- Create: `src/hcp_cms/web/__main__.py`
- Create: `src/hcp_cms/web/app.py`
- Create: `src/hcp_cms/web/pages/login.py`

**目的：** 可以 `python -m hcp_cms.web` 啟動 server，瀏覽器看到登入頁。

- [ ] **Step 1：加 NiceGUI 依賴**

於 `pyproject.toml` 的 `dependencies` 或 `[project.dependencies]` 加：

```toml
"nicegui>=2.0.0",
```

- [ ] **Step 2：安裝**

```bash
.venv/Scripts/pip.exe install "nicegui>=2.0.0"
```

- [ ] **Step 3：寫 `__main__.py`**

新增 `src/hcp_cms/web/__main__.py`：

```python
"""HCP CMS Web Portal entry point.

啟動：python -m hcp_cms.web
"""
import os
from pathlib import Path

from hcp_cms.data.database import DatabaseManager
from hcp_cms.web.app import create_app


def main() -> None:
    db_path = Path(os.environ.get("HCP_CMS_DB", Path.home() / ".hcp_cms" / "cs_tracker.db"))
    db = DatabaseManager(db_path)
    db.initialize()

    create_app(conn=db.conn, db_dir=db_path.parent)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4：寫 `app.py` 骨架**

新增 `src/hcp_cms/web/app.py`：

```python
"""NiceGUI Web Portal app factory."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from nicegui import app, ui

from hcp_cms.web.auth import COOKIE_NAME, WebAuthManager
from hcp_cms.web.pages.login import build_login_page


def create_app(conn: sqlite3.Connection, db_dir: Path) -> None:
    """建立 NiceGUI app 並註冊所有路由。"""
    auth = WebAuthManager(conn)

    @ui.page("/")
    def home():
        staff_id = app.storage.user.get("staff_id")
        if not staff_id or auth.get_staff_by_id(staff_id) is None:
            return ui.navigate.to("/login")
        return ui.navigate.to("/cases")

    @ui.page("/login")
    def login_page():
        build_login_page(auth)

    @ui.page("/logout")
    def logout_page():
        app.storage.user.clear()
        ui.navigate.to("/login")

    ui.run(
        host="0.0.0.0",
        port=8080,
        title="HCP CMS 客服 Portal",
        favicon="🛟",
        dark=True,
        storage_secret="hcp-cms-secret-change-me",
        reload=False,
        show=False,
    )
```

- [ ] **Step 5：寫 login 頁面**

新增 `src/hcp_cms/web/pages/login.py`：

```python
"""Login page — pick-from-list."""
from __future__ import annotations

from nicegui import app, ui

from hcp_cms.web.auth import WebAuthManager


def build_login_page(auth: WebAuthManager) -> None:
    with ui.column().classes("w-full h-screen items-center justify-center"):
        ui.label("HCP CMS 客服 Portal").classes("text-3xl font-bold mb-4")
        ui.label("請點選您的身分").classes("text-lg mb-8 text-slate-400")

        cs_staff = auth.list_cs_staff()
        with ui.column().classes("gap-2 w-64"):
            for staff in cs_staff:
                _build_staff_button(staff)


def _build_staff_button(staff) -> None:
    def on_click() -> None:
        app.storage.user["staff_id"] = staff.staff_id
        ui.navigate.to("/cases")

    ui.button(staff.name, on_click=on_click).classes("w-full")
```

- [ ] **Step 6：本機啟動測試**

```bash
.venv/Scripts/python.exe -m hcp_cms.web
```

預期：終端顯示 `NiceGUI ready to go on http://localhost:8080`

開瀏覽器 `http://localhost:8080`，應看到登入頁列出 3 個客服按鈕。點任一個 → 應跳到 `/cases`（此時還沒實作會 404，正常）。

⚠ 終端按 `Ctrl+C` 結束。

- [ ] **Step 7：commit**

```bash
git add pyproject.toml src/hcp_cms/web/__main__.py src/hcp_cms/web/app.py src/hcp_cms/web/pages/login.py
git commit -m "feat(web): NiceGUI 環境 + 入口 + 登入頁 (pick from list)"
```

---

### Task 16：案件清單頁 `/cases` + B+A + G-3 過濾

**Files:**
- Modify: `src/hcp_cms/web/app.py`（註冊 /cases 路由）
- Create: `src/hcp_cms/web/pages/case_list.py`

- [ ] **Step 1：寫頁面 module**

新增 `src/hcp_cms/web/pages/case_list.py`：

```python
"""案件清單頁 — /cases。"""
from __future__ import annotations

import sqlite3

from nicegui import app, ui

from hcp_cms.data.models import Staff
from hcp_cms.web.auth import WebAuthManager
from hcp_cms.web.visibility import CaseVisibilityFilter


def build_case_list_page(conn: sqlite3.Connection, staff: Staff) -> None:
    visibility = CaseVisibilityFilter(conn)
    cases = visibility.visible_cases(staff)

    # 頂部 nav
    with ui.row().classes("w-full items-center p-4 bg-slate-900"):
        ui.label("我的案件").classes("text-2xl font-bold")
        ui.space()
        ui.label(f"身分：{staff.name}").classes("text-slate-300")
        ui.button("登出", on_click=lambda: ui.navigate.to("/logout")).props("flat")

    with ui.column().classes("p-4 w-full"):
        if not cases:
            ui.label("目前沒有指派給您的案件").classes("text-slate-500 italic")
            return

        # 批次選取 state
        selected_ids: set[str] = set()
        batch_button = ui.button("推到 Mantis（0 筆）").props("disabled")

        def _on_select_change(case_id: str, is_selected: bool) -> None:
            if is_selected:
                selected_ids.add(case_id)
            else:
                selected_ids.discard(case_id)
            batch_button.text = f"推到 Mantis（{len(selected_ids)} 筆）"
            if selected_ids:
                batch_button.props(remove="disabled")
            else:
                batch_button.props("disabled")

        with ui.grid(columns="50px 200px 1fr 100px 100px 120px").classes("w-full gap-1"):
            ui.label("選").classes("font-bold")
            ui.label("案件編號").classes("font-bold")
            ui.label("主旨").classes("font-bold")
            ui.label("狀態").classes("font-bold")
            ui.label("優先度").classes("font-bold")
            ui.label("更新時間").classes("font-bold")

            for c in cases:
                cb = ui.checkbox(value=False)
                cb.on(
                    "update:model-value",
                    lambda e, cid=c.case_id: _on_select_change(cid, e.args),
                )
                ui.link(c.case_id, f"/cases/{c.case_id}")
                ui.label(c.subject or "")
                _render_status_chip(c.status)
                ui.label(c.priority or "")
                ui.label(c.updated_at or "")
```

⚠ `_render_status_chip` 暫時 placeholder：

```python
def _render_status_chip(status: str) -> None:
    color_map = {
        "處理中": "amber",
        "已回覆": "blue",
        "已完成": "green",
        "已結案": "slate",
    }
    color = color_map.get(status, "neutral")
    ui.label(status or "").classes(f"px-2 py-1 rounded text-{color}-700 bg-{color}-100")
```

- [ ] **Step 2：在 app.py 註冊路由**

於 `src/hcp_cms/web/app.py` 加 import + 路由：

```python
from hcp_cms.web.pages.case_list import build_case_list_page


# 在 create_app 內加：
    @ui.page("/cases")
    def case_list_page():
        staff_id = app.storage.user.get("staff_id")
        if not staff_id:
            return ui.navigate.to("/login")
        staff = auth.get_staff_by_id(staff_id)
        if staff is None:
            app.storage.user.clear()
            return ui.navigate.to("/login")
        build_case_list_page(conn, staff)
```

- [ ] **Step 3：手動測試**

```bash
.venv/Scripts/python.exe -m hcp_cms.web
```

開 `http://localhost:8080`，登入後應看到 `/cases` 頁面（清單或「沒有指派」訊息）。

- [ ] **Step 4：commit**

```bash
git add src/hcp_cms/web/app.py src/hcp_cms/web/pages/case_list.py
git commit -m "feat(web): /cases 清單頁 + B+A + G-3 可視過濾"
```

---

### Task 17：案件詳情頁 `/cases/{case_id}` + 5 欄位編輯 + 已結案 UI

**Files:**
- Modify: `src/hcp_cms/web/app.py`（註冊路由）
- Create: `src/hcp_cms/web/pages/case_detail.py`

**目的：** 編輯 status / progress / handler / priority / rd_assignee；「已結案」狀態用顯著 UI 標示。

- [ ] **Step 1：寫詳情頁**

新增 `src/hcp_cms/web/pages/case_detail.py`：

```python
"""案件詳情頁 — /cases/{case_id}。"""
from __future__ import annotations

import sqlite3

from nicegui import app, ui

from hcp_cms.data.models import Staff
from hcp_cms.data.repositories import (
    CaseRepository,
    CaseLogRepository,
    CaseMantisRepository,
    StaffRepository,
)
from hcp_cms.web.audit import AuditLogger
from hcp_cms.web.visibility import CaseVisibilityFilter


STATUS_OPTIONS = ["處理中", "已回覆", "已完成", "已結案"]
PRIORITY_OPTIONS = ["高", "中", "低"]


def build_case_detail_page(conn: sqlite3.Connection, staff: Staff, case_id: str) -> None:
    case_repo = CaseRepository(conn)
    log_repo = CaseLogRepository(conn)
    link_repo = CaseMantisRepository(conn)
    staff_repo = StaffRepository(conn)
    auditor = AuditLogger(conn)

    case = case_repo.get_by_id(case_id)
    if case is None:
        ui.label(f"案件 {case_id} 不存在").classes("text-red-500 text-2xl p-8")
        return

    # 可視性檢查
    visibility = CaseVisibilityFilter(conn)
    visible_ids = {c.case_id for c in visibility.visible_cases(staff)}
    if case_id not in visible_ids:
        ui.label("您無權限查看此案件").classes("text-red-500 text-2xl p-8")
        return

    # 已結案的 banner
    if case.status == "已結案":
        with ui.row().classes("w-full p-4 bg-slate-700 text-slate-100"):
            ui.icon("lock")
            ui.label(
                "本案件已結案，客戶後續回信不會重新開啟，僅會新增記錄"
            ).classes("font-semibold")

    # 表頭
    with ui.row().classes("w-full items-center p-4"):
        ui.label(f"案件 {case_id}").classes("text-2xl font-bold")
        ui.space()
        ui.link("← 回清單", "/cases")

    # 主旨 + 寄件
    ui.label(f"主旨：{case.subject or ''}").classes("text-lg p-2")
    ui.label(f"寄件時間：{case.sent_time or ''}").classes("text-slate-500 p-2")

    # 編輯區
    cs_staff = [s.name for s in staff_repo.list_all() if s.role == "cs"]

    with ui.column().classes("gap-4 p-4 w-full max-w-3xl"):
        status_sel = ui.select(
            STATUS_OPTIONS,
            value=case.status or "處理中",
            label="狀態",
        ).classes("w-full")

        progress_input = ui.textarea(
            label="處理進度",
            value=case.progress or "",
        ).classes("w-full")

        handler_sel = ui.select(
            cs_staff,
            value=case.handler if case.handler in cs_staff else None,
            label="處理人員",
            with_input=True,
        ).classes("w-full")

        priority_sel = ui.select(
            PRIORITY_OPTIONS,
            value=case.priority or "中",
            label="優先度",
        ).classes("w-full")

        rd_assignee_input = ui.input(
            label="技術負責人",
            value=case.rd_assignee or "",
        ).classes("w-full")

        def save() -> None:
            # 變更比對 + audit log
            old = case_repo.get_by_id(case_id)
            changed_fields: list[str] = []
            new_status = status_sel.value
            if new_status == "已結案" and old.status != "已結案":
                # confirm dialog
                _confirm_close_case(
                    case_repo, log_repo, auditor, case, staff,
                    new_status, progress_input, handler_sel, priority_sel, rd_assignee_input,
                )
                return
            _apply_save(
                case_repo, auditor, old, staff,
                new_status, progress_input.value, handler_sel.value,
                priority_sel.value, rd_assignee_input.value,
            )

        ui.button("儲存", on_click=save).classes("bg-blue-600 text-white px-6 py-2")

    # case_logs
    ui.separator()
    ui.label("補充紀錄").classes("text-xl font-bold p-4")
    logs = log_repo.list_by_case_id(case_id)
    for log in logs:
        with ui.card().classes("w-full max-w-3xl m-2"):
            ui.label(f"[{log.direction}] {log.logged_at}").classes("text-sm text-slate-400")
            ui.label(log.content or "").classes("whitespace-pre-wrap")

    # Mantis 連結與推送 UI（Task 18 補）
    _render_mantis_section(conn, case, staff, link_repo)


def _apply_save(case_repo, auditor, old_case, staff,
                new_status, new_progress, new_handler, new_priority, new_rd) -> None:
    changes = {
        "status": (old_case.status, new_status),
        "progress": (old_case.progress or "", new_progress or ""),
        "handler": (old_case.handler, new_handler),
        "priority": (old_case.priority, new_priority),
        "rd_assignee": (old_case.rd_assignee, new_rd),
    }
    for field, (oldv, newv) in changes.items():
        if oldv != newv:
            auditor.log_field_change(staff.staff_id, old_case.case_id, field)
            setattr(old_case, field, newv)
    case_repo.update(old_case)
    ui.notify("已儲存", type="positive")


def _confirm_close_case(case_repo, log_repo, auditor, case, staff,
                        new_status, progress_input, handler_sel, priority_sel, rd_assignee_input) -> None:
    with ui.dialog() as dialog, ui.card():
        ui.label("確認標記為「已結案」？").classes("text-xl font-bold")
        ui.label("已結案後，客戶後續回信不會重新開啟此案件，僅會新增記錄。")
        with ui.row():
            ui.button("取消", on_click=dialog.close).props("flat")
            def confirm():
                _apply_save(
                    case_repo, auditor, case, staff,
                    new_status, progress_input.value, handler_sel.value,
                    priority_sel.value, rd_assignee_input.value,
                )
                dialog.close()
            ui.button("確認", on_click=confirm).classes("bg-slate-700 text-white")
    dialog.open()


def _render_mantis_section(conn, case, staff, link_repo) -> None:
    """佔位 — Task 18 補實作。"""
    ui.separator()
    ui.label("Mantis 整合").classes("text-xl font-bold p-4")
    links = link_repo.list_by_case_id(case.case_id)
    if links:
        ui.label(f"已連結 Mantis ticket #{links[0].ticket_id}")
    else:
        ui.label("尚未連結 Mantis ticket").classes("text-slate-500")
```

- [ ] **Step 2：在 app.py 註冊路由**

於 `src/hcp_cms/web/app.py` 加：

```python
from hcp_cms.web.pages.case_detail import build_case_detail_page


# 在 create_app 內加：
    @ui.page("/cases/{case_id}")
    def case_detail_page(case_id: str):
        staff_id = app.storage.user.get("staff_id")
        if not staff_id:
            return ui.navigate.to("/login")
        staff = auth.get_staff_by_id(staff_id)
        if staff is None:
            return ui.navigate.to("/login")
        build_case_detail_page(conn, staff, case_id)
```

- [ ] **Step 3：手動測試**

```bash
.venv/Scripts/python.exe -m hcp_cms.web
```

從清單頁點任一案件 → 應看到詳情頁、可編輯 5 欄位、選「已結案」會彈 confirm dialog。

- [ ] **Step 4：commit**

```bash
git add src/hcp_cms/web/app.py src/hcp_cms/web/pages/case_detail.py
git commit -m "feat(web): /cases/{id} 詳情頁 + 5 欄位編輯 + 已結案 confirm"
```

---

### Task 18：詳情頁「推到 Mantis」按鈕（模式 a + c 自動切換）

**Files:**
- Modify: `src/hcp_cms/web/pages/case_detail.py`（替換 `_render_mantis_section`）
- Modify: `src/hcp_cms/web/app.py`（注入 MantisClient + project_id）

**目的：** 詳情頁依連結狀態顯示「建新 ticket」或「推為 bugnote」按鈕。

- [ ] **Step 1：在 app.py 注入 Mantis 設定**

於 `create_app` 加（從 config 讀取或先暫硬編 dev 值）：

```python
def create_app(
    conn: sqlite3.Connection,
    db_dir: Path,
    mantis_base_url: str = "",
    mantis_user: str = "",
    mantis_password: str = "",
    mantis_project_id: str = "",
) -> None:
    from hcp_cms.services.mantis.soap import MantisSoapClient
    mantis_client: MantisSoapClient | None = None
    if mantis_base_url:
        mantis_client = MantisSoapClient(mantis_base_url, mantis_user, mantis_password)
        mantis_client.connect()
    auth = WebAuthManager(conn)
    # ... 既有 ...
```

於 `__main__.py` 從環境變數讀取：

```python
def main() -> None:
    db_path = Path(os.environ.get("HCP_CMS_DB", Path.home() / ".hcp_cms" / "cs_tracker.db"))
    db = DatabaseManager(db_path)
    db.initialize()

    create_app(
        conn=db.conn,
        db_dir=db_path.parent,
        mantis_base_url=os.environ.get("HCP_CMS_MANTIS_URL", ""),
        mantis_user=os.environ.get("HCP_CMS_MANTIS_USER", ""),
        mantis_password=os.environ.get("HCP_CMS_MANTIS_PASS", ""),
        mantis_project_id=os.environ.get("HCP_CMS_MANTIS_PROJECT", ""),
    )
```

並將 `mantis_client` / `mantis_project_id` 透過 closure 傳遞給 `build_case_detail_page`：

```python
    @ui.page("/cases/{case_id}")
    def case_detail_page(case_id: str):
        # ...
        build_case_detail_page(
            conn, staff, case_id,
            mantis_client=mantis_client,
            mantis_project_id=mantis_project_id,
        )
```

- [ ] **Step 2：替換 `_render_mantis_section`**

在 `case_detail.py` 改 `build_case_detail_page` 簽名：

```python
def build_case_detail_page(
    conn: sqlite3.Connection,
    staff: Staff,
    case_id: str,
    mantis_client=None,
    mantis_project_id: str = "",
) -> None:
    # ... 既有頂端不變 ...

    # 最後改：
    _render_mantis_section(conn, case, staff, link_repo, mantis_client, mantis_project_id)
```

替換 `_render_mantis_section` 為實際實作：

```python
def _render_mantis_section(
    conn, case, staff, link_repo, mantis_client, mantis_project_id,
) -> None:
    from hcp_cms.web.mantis_push import MantisPushManager

    ui.separator()
    ui.label("Mantis 整合").classes("text-xl font-bold p-4")

    if mantis_client is None or not mantis_project_id:
        ui.label("⚠ Mantis 未設定（環境變數 HCP_CMS_MANTIS_URL）").classes("text-amber-500")
        return

    links = link_repo.list_by_case_id(case.case_id)
    push_mgr = MantisPushManager(conn, mantis_client, mantis_project_id)

    if not links:
        # 模式 (a) 建新 ticket
        ui.label("本案件尚未連結 Mantis ticket").classes("text-slate-500")

        def on_create() -> None:
            with ui.dialog() as dialog, ui.card():
                ui.label(f"將案件 {case.case_id} 建為新 Mantis ticket？")
                with ui.row():
                    ui.button("取消", on_click=dialog.close).props("flat")
                    def confirm():
                        success, payload = push_mgr.push_case_as_new_ticket(
                            case.case_id, staff.staff_id,
                        )
                        if success:
                            ui.notify(f"已建立 Mantis ticket #{payload}", type="positive")
                            ui.navigate.to(f"/cases/{case.case_id}")
                        else:
                            ui.notify(f"失敗：{payload}", type="negative")
                        dialog.close()
                    ui.button("確認推送", on_click=confirm).classes("bg-blue-600 text-white")
            dialog.open()

        ui.button("建立 Mantis ticket", on_click=on_create).classes("bg-blue-600 text-white px-4 py-2")

    else:
        # 模式 (c) 推為 bugnote
        ticket_id = links[0].ticket_id
        ui.label(f"已連結 Mantis ticket #{ticket_id}")

        def on_bugnote() -> None:
            with ui.dialog() as dialog, ui.card():
                ui.label(f"將當前進度推為 Mantis ticket #{ticket_id} 的留言？")
                with ui.row():
                    ui.button("取消", on_click=dialog.close).props("flat")
                    def confirm():
                        success, payload = push_mgr.push_case_as_bugnote(
                            case.case_id, staff.staff_id,
                        )
                        if success:
                            ui.notify(f"已新增留言 #{payload}", type="positive")
                            ui.navigate.to(f"/cases/{case.case_id}")
                        else:
                            ui.notify(f"失敗：{payload}", type="negative")
                        dialog.close()
                    ui.button("確認推送", on_click=confirm).classes("bg-blue-600 text-white")
            dialog.open()

        ui.button("推送更新為 bugnote", on_click=on_bugnote).classes("bg-blue-600 text-white px-4 py-2")
```

- [ ] **Step 3：手動測試**

設定環境變數（PowerShell）：

```powershell
$env:HCP_CMS_MANTIS_URL = "http://your-mantis-host"
$env:HCP_CMS_MANTIS_USER = "your-user"
$env:HCP_CMS_MANTIS_PASS = "your-pass"
$env:HCP_CMS_MANTIS_PROJECT = "1"
.venv/Scripts/python.exe -m hcp_cms.web
```

開詳情頁，按「建立 Mantis ticket」→ confirm → 應建出新 ticket 並重新整理頁面。

- [ ] **Step 4：commit**

```bash
git add src/hcp_cms/web/pages/case_detail.py src/hcp_cms/web/app.py src/hcp_cms/web/__main__.py
git commit -m "feat(web): 詳情頁「推到 Mantis」按鈕（單筆 / bugnote 自動切換）"
```

---

### Task 19：清單頁批次推送 UI（模式 b）

**Files:**
- Modify: `src/hcp_cms/web/pages/case_list.py`（綁定 batch button）
- Modify: `src/hcp_cms/web/app.py`（傳 Mantis 設定給 list 頁）

- [ ] **Step 1：傳遞 mantis_client 到 case_list**

於 `app.py` 的 `/cases` 路由：

```python
    @ui.page("/cases")
    def case_list_page():
        # ... auth check ...
        build_case_list_page(
            conn, staff,
            mantis_client=mantis_client,
            mantis_project_id=mantis_project_id,
        )
```

於 `case_list.py` 改簽名：

```python
def build_case_list_page(
    conn: sqlite3.Connection,
    staff: Staff,
    mantis_client=None,
    mantis_project_id: str = "",
) -> None:
    # ... 既有 ...
```

- [ ] **Step 2：實作批次推送邏輯**

於 `case_list.py` 將 `batch_button` 改為帶 on_click：

```python
        from hcp_cms.web.mantis_push import MantisPushManager
        from hcp_cms.data.repositories import CaseRepository

        def on_batch_push() -> None:
            if not selected_ids:
                return
            if mantis_client is None or not mantis_project_id:
                ui.notify("Mantis 未設定", type="warning")
                return

            case_repo = CaseRepository(conn)
            selected_cases = [case_repo.get_by_id(cid) for cid in selected_ids]
            selected_cases = [c for c in selected_cases if c]

            # 列出 confirm dialog
            with ui.dialog() as dialog, ui.card().classes("w-[600px]"):
                ui.label(f"將推送以下 {len(selected_cases)} 筆案件為新 Mantis ticket：").classes("font-bold")
                ui.label("（已連結 ticket 的案件會自動略過）").classes("text-slate-500 text-sm")
                with ui.column().classes("max-h-80 overflow-auto w-full"):
                    for c in selected_cases:
                        ui.label(f"• {c.case_id}  {c.subject}（客戶: {c.company_id or '—'}）")
                with ui.row():
                    ui.button("取消", on_click=dialog.close).props("flat")

                    def confirm():
                        push_mgr = MantisPushManager(conn, mantis_client, mantis_project_id)
                        results = push_mgr.push_cases_batch(
                            list(selected_ids), staff.staff_id,
                        )
                        ok = sum(1 for r in results if r[1] == "success")
                        fail = sum(1 for r in results if r[1] == "failed")
                        skip = sum(1 for r in results if r[1] == "skipped")
                        ui.notify(
                            f"成功 {ok} 筆 / 失敗 {fail} 筆 / 略過 {skip} 筆",
                            type="positive" if fail == 0 else "warning",
                        )
                        # 若有失敗，秀詳細
                        if fail > 0:
                            failures = [r for r in results if r[1] == "failed"]
                            with ui.dialog() as detail, ui.card():
                                ui.label("失敗明細").classes("font-bold")
                                for r in failures:
                                    ui.label(f"{r[0]}: {r[2]}")
                                ui.button("關閉", on_click=detail.close)
                            detail.open()
                        dialog.close()
                        ui.navigate.to("/cases")

                    ui.button("確認推送", on_click=confirm).classes("bg-blue-600 text-white")
            dialog.open()

        batch_button.on("click", on_batch_push)
```

- [ ] **Step 3：手動測試**

打開 `/cases`，多選 2-3 筆案件，按「推到 Mantis」→ confirm → 應顯示明細 → 確認後執行批次推送 → 看到結果摘要。

- [ ] **Step 4：commit**

```bash
git add src/hcp_cms/web/pages/case_list.py src/hcp_cms/web/app.py
git commit -m "feat(web): 清單頁批次推送 Mantis（含 confirm 明細 + 結果摘要）"
```

---

### Task 20：稽核頁 `/audit`（僅 admin）

**Files:**
- Create: `src/hcp_cms/web/pages/audit.py`
- Modify: `src/hcp_cms/web/app.py`（註冊路由）

- [ ] **Step 1：寫稽核頁**

新增 `src/hcp_cms/web/pages/audit.py`：

```python
"""稽核 log 頁 — /audit (admin only)."""
from __future__ import annotations

import sqlite3

from nicegui import ui

from hcp_cms.data.models import Staff
from hcp_cms.data.repositories import WebAuditLogRepository, StaffRepository


def build_audit_page(conn: sqlite3.Connection, staff: Staff) -> None:
    if staff.role != "admin":
        ui.label("您無權限查看稽核紀錄").classes("text-red-500 text-2xl p-8")
        return

    audit_repo = WebAuditLogRepository(conn)
    staff_repo = StaffRepository(conn)
    rows = audit_repo.list_all(limit=200)

    # staff_id → name 映射
    staff_names = {s.staff_id: s.name for s in staff_repo.list_all()}

    ui.label("Web Portal 稽核紀錄").classes("text-2xl font-bold p-4")
    ui.label(f"最近 {len(rows)} 筆").classes("text-slate-500 p-2")

    with ui.grid(columns="200px 100px 150px 200px").classes("w-full gap-1 p-4"):
        ui.label("時間").classes("font-bold")
        ui.label("操作人").classes("font-bold")
        ui.label("案件").classes("font-bold")
        ui.label("欄位").classes("font-bold")
        for r in rows:
            ui.label(r.occurred_at)
            ui.label(staff_names.get(r.staff_id, r.staff_id))
            ui.link(r.case_id, f"/cases/{r.case_id}")
            ui.label(r.field_name)
```

- [ ] **Step 2：在 app.py 註冊路由**

```python
from hcp_cms.web.pages.audit import build_audit_page


    @ui.page("/audit")
    def audit_page():
        staff_id = app.storage.user.get("staff_id")
        if not staff_id:
            return ui.navigate.to("/login")
        # admin 可不是 cs role，需另用 staff repo 取
        from hcp_cms.data.repositories import StaffRepository
        s = StaffRepository(conn).get_by_id(staff_id)
        if s is None or s.role != "admin":
            ui.label("無權限").classes("text-red-500 text-2xl p-8")
            return
        build_audit_page(conn, s)
```

⚠ 注意：admin role 的 staff 走的是 `StaffRepository.get_by_id`，不過 `WebAuthManager.get_staff_by_id` 只回傳 cs role。admin 登入需要另一個 flow 或共用 `WebAuthManager` 並放寬 role 檢查（取捨：MVP 簡化用 StaffRepository 直接取）。

- [ ] **Step 3：手動測試**

`/audit` 頁面：以 admin role staff cookie 登入應看到列表；以 cs role 登入應看「無權限」。

- [ ] **Step 4：commit**

```bash
git add src/hcp_cms/web/pages/audit.py src/hcp_cms/web/app.py
git commit -m "feat(web): /audit 稽核紀錄頁（僅 admin）"
```

---

### Task 21：新增 case_log + 既有 Mantis 連結手動輸入 UI

**Files:**
- Modify: `src/hcp_cms/web/pages/case_detail.py`

**目的：** 詳情頁可新增 case_log 與手動輸入既有 Mantis ticket_id 做連結。

- [ ] **Step 1：在 case_detail.py 加 case_log 新增區**

於 `build_case_detail_page` 內、`# case_logs` 區塊之前加：

```python
    # 新增 case_log
    with ui.column().classes("p-4 w-full max-w-3xl"):
        ui.label("新增補充記錄").classes("text-lg font-bold")
        new_log_text = ui.textarea(label="內容").classes("w-full")
        direction_sel = ui.select(
            ["內部討論", "HCP 線上回覆", "HCP 信件回覆"],
            value="內部討論",
            label="類型",
        ).classes("w-full")

        def add_log() -> None:
            from datetime import datetime
            from hcp_cms.data.models import CaseLog

            content = (new_log_text.value or "").strip()
            if not content:
                ui.notify("內容不可為空", type="warning")
                return
            now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            log = CaseLog(
                log_id=log_repo.next_log_id(),
                case_id=case_id,
                direction=direction_sel.value,
                content=content,
                logged_by=staff.staff_id,
                logged_at=now,
            )
            log_repo.insert(log)
            ui.notify("已新增記錄", type="positive")
            ui.navigate.to(f"/cases/{case_id}")

        ui.button("新增", on_click=add_log).classes("bg-green-600 text-white")

    # 既有 Mantis ticket 連結（不透過 SOAP）
    with ui.column().classes("p-4 w-full max-w-3xl"):
        ui.label("連結既有 Mantis ticket").classes("text-lg font-bold")
        ticket_input = ui.input(label="Mantis ticket id（已存在的）").classes("w-full")

        def link_existing() -> None:
            from hcp_cms.data.models import CaseMantisLink
            tid = (ticket_input.value or "").strip()
            if not tid:
                ui.notify("請輸入 ticket id", type="warning")
                return
            link_repo.insert(CaseMantisLink(case_id=case_id, ticket_id=tid))
            ui.notify(f"已連結 #{tid}", type="positive")
            ui.navigate.to(f"/cases/{case_id}")

        ui.button("連結", on_click=link_existing).classes("bg-slate-600 text-white")
```

- [ ] **Step 2：手動測試**

詳情頁應出現「新增補充記錄」+「連結既有 Mantis ticket」兩區。各自送出後頁面 reload，下方記錄區顯示新增的 log。

- [ ] **Step 3：commit**

```bash
git add src/hcp_cms/web/pages/case_detail.py
git commit -m "feat(web): 詳情頁新增 case_log + 連結既有 Mantis ticket"
```

---

## Phase 5：整合、部署、文件

### Task 22：整合測試 — 端到端 Web Portal 流程

**Files:**
- Create: `tests/integration/test_web_portal_flow.py`

**目的：** 驗證登入 → 列案件 → 編輯 → 推送 Mantis 整條鏈不破。

- [ ] **Step 1：寫整合測試**

新增 `tests/integration/test_web_portal_flow.py`：

```python
"""Web Portal 端到端流程測試（mock Mantis client）。"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, Company, Staff
from hcp_cms.data.repositories import (
    CaseRepository,
    CompanyRepository,
    StaffRepository,
)
from hcp_cms.web.audit import AuditLogger
from hcp_cms.web.auth import WebAuthManager
from hcp_cms.web.mantis_push import MantisPushManager
from hcp_cms.web.visibility import CaseVisibilityFilter


@pytest.fixture
def full_setup(tmp_path: Path):
    db = DatabaseManager(tmp_path / "t.db")
    db.initialize()
    StaffRepository(db.conn).insert(Staff(staff_id="S-YOGA", name="YOGA", role="cs"))
    CompanyRepository(db.conn).insert(Company(company_id="CO-A", name="A", domain="a.com", cs_staff_id="S-YOGA"))
    CaseRepository(db.conn).insert(
        Case(case_id="C-100", subject="印表機問題", handler="YOGA", company_id="CO-A", priority="高")
    )
    yield db
    db.close()


def test_full_flow_login_to_mantis_push(full_setup) -> None:
    db = full_setup
    auth = WebAuthManager(db.conn)
    visibility = CaseVisibilityFilter(db.conn)
    audit = AuditLogger(db.conn)

    # 1. 登入：取 staff
    staff = auth.get_staff_by_id("S-YOGA")
    assert staff is not None

    # 2. 列案件：應看到 C-100
    cases = visibility.visible_cases(staff)
    assert any(c.case_id == "C-100" for c in cases)

    # 3. 推送 Mantis
    client = MagicMock()
    client.create_issue.return_value = "555"
    pusher = MantisPushManager(db.conn, client, project_id="1")
    success, ticket_id = pusher.push_case_as_new_ticket("C-100", "S-YOGA")
    assert success is True
    assert ticket_id == "555"

    # 4. 確認 audit log 有紀錄
    from hcp_cms.data.repositories import WebAuditLogRepository
    audit_rows = WebAuditLogRepository(db.conn).list_by_case_id("C-100")
    assert any(r.field_name == "mantis_push" for r in audit_rows)

    # 5. 再推一次（已連結，應失敗）
    success, msg = pusher.push_case_as_new_ticket("C-100", "S-YOGA")
    assert success is False
    assert "已連結" in msg

    # 6. 推 bugnote
    client.add_note.return_value = "note-1"
    success, note_id = pusher.push_case_as_bugnote("C-100", "S-YOGA")
    assert success is True
    assert note_id == "note-1"
```

- [ ] **Step 2：跑測試**

```bash
.venv/Scripts/python.exe -m pytest tests/integration/test_web_portal_flow.py -v
```

預期：PASS

- [ ] **Step 3：跑全部測試**

```bash
.venv/Scripts/python.exe -m pytest tests/ --tb=short
```

預期：全部 PASS

- [ ] **Step 4：commit**

```bash
git add tests/integration/test_web_portal_flow.py
git commit -m "test(web): 整合測試 Web Portal 端到端流程"
```

---

### Task 23：NSSM 服務設定 + 開機自啟

**Files:**
- Create: `scripts/install_web_service.bat`
- Create: `scripts/uninstall_web_service.bat`

**目的：** 用 NSSM 把 Web Portal 註冊為 Windows 服務，開機自啟。

- [ ] **Step 1：寫安裝腳本**

新增 `scripts/install_web_service.bat`：

```batch
@echo off
REM 安裝 HCP CMS Web Portal 為 Windows 服務（需要 NSSM）
REM 用法：以管理員身分執行此腳本

set SERVICE_NAME=HCP_CMS_Web
set PROJECT_ROOT=%~dp0..
set PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe

REM 檢查 NSSM
where nssm >nul 2>nul
if errorlevel 1 (
    echo NSSM 未安裝。請從 https://nssm.cc 下載並加入 PATH。
    pause
    exit /b 1
)

REM 移除既有服務（若存在）
nssm stop %SERVICE_NAME% 2>nul
nssm remove %SERVICE_NAME% confirm 2>nul

REM 安裝
nssm install %SERVICE_NAME% "%PYTHON_EXE%" "-m" "hcp_cms.web"
nssm set %SERVICE_NAME% AppDirectory "%PROJECT_ROOT%"
nssm set %SERVICE_NAME% DisplayName "HCP CMS Web Portal"
nssm set %SERVICE_NAME% Description "客服 3 人共用 Web Portal"
nssm set %SERVICE_NAME% Start SERVICE_AUTO_START
nssm set %SERVICE_NAME% AppStdout "%PROJECT_ROOT%\logs\web_service.log"
nssm set %SERVICE_NAME% AppStderr "%PROJECT_ROOT%\logs\web_service_error.log"

REM Mantis 環境變數（請編輯後再執行）
nssm set %SERVICE_NAME% AppEnvironmentExtra ^
    HCP_CMS_DB=C:\path\to\cs_tracker.db ^
    HCP_CMS_MANTIS_URL=http://your-mantis ^
    HCP_CMS_MANTIS_USER=your-user ^
    HCP_CMS_MANTIS_PASS=your-pass ^
    HCP_CMS_MANTIS_PROJECT=1

mkdir "%PROJECT_ROOT%\logs" 2>nul

REM 啟動
nssm start %SERVICE_NAME%

echo HCP CMS Web Portal 服務已安裝並啟動。
echo 開瀏覽器：http://localhost:8080
pause
```

- [ ] **Step 2：寫解除安裝腳本**

新增 `scripts/uninstall_web_service.bat`：

```batch
@echo off
set SERVICE_NAME=HCP_CMS_Web
nssm stop %SERVICE_NAME%
nssm remove %SERVICE_NAME% confirm
echo HCP CMS Web Portal 服務已移除。
pause
```

- [ ] **Step 3：commit**

```bash
git add scripts/install_web_service.bat scripts/uninstall_web_service.bat
git commit -m "feat(deploy): NSSM 安裝 / 解除安裝腳本"
```

---

### Task 24：使用文件

**Files:**
- Create: `docs/客服 Web Portal 使用說明.md`

- [ ] **Step 1：寫使用說明**

新增 `docs/客服 Web Portal 使用說明.md`：

```markdown
# HCP 客服 Web Portal 使用說明

## 一、開始使用

### 公司辦公室內

開瀏覽器，輸入：`http://<Jill PC IP>:8080`

### 在家或出差

1. 裝 Tailscale（https://tailscale.com） — 免費版 3 人團隊夠用
2. 連 Jill PC 同一 Tailscale 網段
3. 開瀏覽器：`http://<Jill PC Tailscale IP>:8080`

## 二、登入

第一次開頁面會看到 3 個按鈕：jill / YOGA / Rebecca
→ 點自己名字 → cookie 自動記住，下次自動登入
→ 想切換身分：右上「登出」

## 三、看到哪些案件？

「我的案件」清單顯示：

- 您被指派 (`handler` = 您) 的案件
- 您管轄公司 (`companies.cs_staff_id` = 您) 的案件

⚠ **未指派的案件不會出現**，請 Jill 在桌面 App 指派後才會進來。

## 四、編輯案件

點任一案件 → 詳情頁可改：

- 狀態（處理中 / 已回覆 / 已完成 / **已結案**）
- 處理進度（多行文字）
- 處理人員
- 優先度
- 技術負責人

按「儲存」即可。

### 何時用「已結案」？

「**已完成**」：本次回覆完成，**客戶後續若回信會自動新增子案件**（從 thread 視角看像是重開）
「**已結案**」：問題徹底解決，**客戶後續回信不會重新開啟，僅新增記錄**

選「已結案」會彈確認視窗，確認後即鎖定。

## 五、新增補充紀錄

詳情頁下方有「新增補充記錄」區，可選類型：

- 內部討論
- HCP 線上回覆
- HCP 信件回覆

## 六、回信給客戶

**請繼續使用 Outlook 回信，並 CC `hcpservice@`**——
HCP CMS 會自動把您的回信抓進系統，所有客服都看得到。

## 七、Mantis 整合

### 推到 Mantis

詳情頁底部有「**建立 Mantis ticket**」按鈕：
1. 按下 → 確認視窗 → 確認推送
2. 成功 → 顯示新 ticket id + 案件即連結到該 ticket

### 推送更新

若案件已連結 Mantis ticket，按鈕變「**推送更新為 bugnote**」：
1. 將當前狀態 + 進度 + 最新記錄推為 Mantis ticket 留言
2. 客戶端看不到（內部 bugnote）

### 批次推送

清單頁勾選多筆案件 → 按「**推到 Mantis（N 筆）**」：
1. 確認視窗列出將推送的明細
2. 已連結 ticket 的會自動略過
3. 成功 / 失敗 / 略過 統計顯示

## 八、報表匯出

報表功能在 Jill 的桌面 App，請洽 Jill。

## 九、常見問題

**Q1: 為什麼我看不到某些案件？**
A: 該案件可能還沒指派 handler，或所屬公司不在您管轄範圍。請 Jill 確認。

**Q2: 我關案件後客戶又回信，案件會復活嗎？**
A:
- 選「已完成」→ 系統會建一筆新子案件連結到原案件
- 選「已結案」→ 不會復活，只在原案件加一筆「客戶來信」紀錄

**Q3: Mantis 推送失敗怎麼辦？**
A: 看錯誤訊息：
- 「Issue not found」→ Mantis 那個 ticket 被刪了，請重新連結
- 「Access denied」→ 通知 Jill 檢查 Mantis 帳號權限
- 連線失敗 → 公司網路或 Mantis 主機問題

**Q4: 我可以在手機上用嗎？**
A: 可以，但目前 UI 沒做 RWD 最佳化，建議桌機 / 筆電。
```

- [ ] **Step 2：commit**

```bash
git add "docs/客服 Web Portal 使用說明.md"
git commit -m "docs: 客服 Web Portal 使用說明"
```

---

## 完工檢查

- [ ] **跑全部測試確認沒回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short
```

預期：所有測試 PASS

- [ ] **Lint + 格式**

```bash
.venv/Scripts/ruff.exe check src/ tests/
.venv/Scripts/ruff.exe format src/ tests/
```

預期：0 errors，0 修正提示

- [ ] **手動端到端驗收**

1. 啟動：`.venv/Scripts/python.exe -m hcp_cms.web`
2. 開 `http://localhost:8080` → 點客服名字登入
3. 開清單頁，確認顯示案件
4. 點任一案件 → 編輯 5 欄位 → 儲存
5. 選「已結案」→ 確認 dialog → 儲存
6. 加 case_log + 連結既有 Mantis ticket
7. 詳情頁按「推送更新為 bugnote」（若連結 Mantis）
8. 清單頁多選 2-3 筆 → 批次推 Mantis → 看結果摘要
9. 以 admin 身分開 `/audit` → 看稽核紀錄

- [ ] **部署到 production**

執行 `scripts/install_web_service.bat`（以管理員身分），編輯腳本內環境變數後啟動服務。

- [ ] **告知客服**

告訴 YOGA / Rebecca：`http://<your-PC-IP>:8080`，點自己名字即可。

---

## 風險與處理

| 風險 | 處理方式 |
|------|------|
| Task 4 SOAP `mc_issue_add` POC 失敗 | Stop, 回報 Jill 決定方案（REST / Phase 2 / 升級 Mantis）|
| Task 8 `CaseRepository.delete` 不存在 | 重構：將 insert 移到 if/else 分支內，先決定 parent 再 insert |
| Task 17 `StaffRepository.list_all` 不存在 | 改用 `list_by_role('cs')` 或加新方法 |
| NiceGUI 版本相容性 | 鎖定 `nicegui>=2.0.0,<3.0.0` |
| 既有測試因新 Migration 失敗 | 檢查 `_apply_pending_migrations` 是否冪等，必要時加 IF NOT EXISTS |
