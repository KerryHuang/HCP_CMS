# Mantis Ticket 資訊呈現改善 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在案件詳情的 Mantis 關聯 Tab 以「表格 + 詳情面板」方式呈現 Ticket 完整資訊，包含嚴重性、版本、問題描述及最後 5 條 Bug 筆記（超過 5 條時顯示原始 Mantis 連結）。

**Architecture:** 從 SOAP 新增抓取 6 個欄位 + 最後 5 條 Notes，透過 Services → Core → Data 層存入 `mantis_tickets`，UI 層重新設計為精簡表格（上）+ 常駐詳情面板（下）。

**Tech Stack:** PySide6 6.10.2、SQLite FTS5、requests SOAP、Python 3.14、pytest

---

## 受影響檔案

| 動作 | 檔案 | 說明 |
|------|------|------|
| 修改 | `src/hcp_cms/services/mantis/base.py` | 新增 MantisNote dataclass、擴充 MantisIssue |
| 修改 | `src/hcp_cms/services/mantis/soap.py` | 修正 `_extract_xml`、新增欄位抓取、`_parse_notes` |
| 修改 | `src/hcp_cms/data/models.py` | MantisTicket 新增 severity/reporter/description/notes_json/notes_count |
| 修改 | `src/hcp_cms/data/database.py` | `_apply_pending_migrations` 新增 5 條 ALTER TABLE |
| 修改 | `src/hcp_cms/data/repositories.py` | MantisRepository.upsert() 加入新欄位 |
| 修改 | `src/hcp_cms/core/case_detail_manager.py` | sync_mantis_ticket() 映射新欄位 |
| 修改 | `src/hcp_cms/ui/case_detail_dialog.py` | _build_tab3() 重新設計、新增詳情面板 |
| 新增 | `tests/unit/test_mantis_soap_fields.py` | SOAP 解析單元測試 |
| 新增 | `tests/unit/test_mantis_ticket_repository.py` | Repository 新欄位測試 |
| 新增 | `tests/unit/test_case_detail_manager_sync.py` | sync 映射測試 |

---

## Task 1：擴充 MantisIssue / 新增 MantisNote（base.py）

**Files:**
- Modify: `src/hcp_cms/services/mantis/base.py`

- [ ] **Step 1：寫失敗測試**

建立 `tests/unit/test_mantis_soap_fields.py`：

```python
"""測試 MantisSoapClient 新欄位解析。"""
from __future__ import annotations
from hcp_cms.services.mantis.base import MantisIssue, MantisNote


def test_mantis_issue_has_new_fields():
    issue = MantisIssue(id="1", summary="test")
    assert issue.severity == ""
    assert issue.reporter == ""
    assert issue.date_submitted == ""
    assert issue.target_version == ""
    assert issue.fixed_in_version == ""
    assert issue.description == ""
    assert issue.notes_list == []
    assert issue.notes_count == 0


def test_mantis_note_fields():
    note = MantisNote()
    assert note.note_id == ""
    assert note.reporter == ""
    assert note.text == ""
    assert note.date_submitted == ""
```

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_soap_fields.py::test_mantis_issue_has_new_fields -v
```

期望：`ImportError` 或 `AttributeError`（欄位不存在）

- [ ] **Step 3：實作 MantisNote + 擴充 MantisIssue**

取代 `src/hcp_cms/services/mantis/base.py` 全部內容：

```python
"""Mantis client abstract interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class MantisNote:
    """單條 Mantis Bug 筆記。"""
    note_id: str = ""
    reporter: str = ""
    text: str = ""
    date_submitted: str = ""


@dataclass
class MantisIssue:
    """Parsed Mantis issue data."""
    id: str
    summary: str
    status: str = ""
    priority: str = ""
    handler: str = ""
    severity: str = ""
    reporter: str = ""
    date_submitted: str = ""        # 原 created 欄位改名，語意統一
    target_version: str = ""
    fixed_in_version: str = ""
    description: str = ""
    notes_list: list[MantisNote] = field(default_factory=list)
    last_updated: str = ""          # Mantis 最後更新時間（提醒最新狀態）
    notes_count: int = 0            # SOAP 回傳的筆記總數（不受 max_count 限制）


class MantisClient(ABC):
    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def get_issue(self, issue_id: str) -> MantisIssue | None: ...

    @abstractmethod
    def get_issues(self, project_id: str | None = None) -> list[MantisIssue]: ...
```

- [ ] **Step 4：確認測試通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_soap_fields.py -v
```

期望：2 tests PASSED

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/services/mantis/base.py tests/unit/test_mantis_soap_fields.py
git commit -m "feat(mantis): 新增 MantisNote dataclass、擴充 MantisIssue 欄位"
```

---

## Task 2：更新 MantisSoapClient（soap.py）

**Files:**
- Modify: `src/hcp_cms/services/mantis/soap.py`
- Test: `tests/unit/test_mantis_soap_fields.py`

- [ ] **Step 1：新增 SOAP 解析測試**

在 `tests/unit/test_mantis_soap_fields.py` 尾端附加：

```python
from unittest.mock import patch, MagicMock
from hcp_cms.services.mantis.soap import MantisSoapClient


_SAMPLE_SOAP = """<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                   xmlns:ns1="http://futureware.biz/mantisconnect">
  <SOAP-ENV:Body>
    <ns1:mc_issue_getResponse>
      <return xsi:type="ns1:IssueData">
        <id xsi:type="xsd:integer">17186</id>
        <summary xsi:type="xsd:string">薪資計算錯誤</summary>
        <severity xsi:type="ns1:ObjectRef">
          <id xsi:type="xsd:integer">50</id>
          <name xsi:type="xsd:string">major</name>
        </severity>
        <priority xsi:type="ns1:ObjectRef">
          <id xsi:type="xsd:integer">40</id>
          <name xsi:type="xsd:string">high</name>
        </priority>
        <status xsi:type="ns1:ObjectRef">
          <id xsi:type="xsd:integer">80</id>
          <name xsi:type="xsd:string">resolved</name>
        </status>
        <reporter xsi:type="ns1:AccountData">
          <id xsi:type="xsd:integer">5</id>
          <name xsi:type="xsd:string">林美麗</name>
        </reporter>
        <handler xsi:type="ns1:AccountData">
          <id xsi:type="xsd:integer">3</id>
          <name xsi:type="xsd:string">王小明</name>
        </handler>
        <date_submitted xsi:type="xsd:dateTime">2026-01-15T10:00:00+08:00</date_submitted>
        <target_version xsi:type="xsd:string">v2.5.1</target_version>
        <fixed_in_version xsi:type="xsd:string">v2.5.2</fixed_in_version>
        <description xsi:type="xsd:string">月底批次薪資計算時發生加班費錯誤。</description>
        <notes>
          <item xsi:type="ns1:IssueNoteData">
            <id xsi:type="xsd:integer">101</id>
            <reporter xsi:type="ns1:AccountData">
              <name xsi:type="xsd:string">王小明</name>
            </reporter>
            <text xsi:type="xsd:string">已確認問題根因。</text>
            <date_submitted xsi:type="xsd:dateTime">2026-01-16T09:00:00+08:00</date_submitted>
          </item>
          <item xsi:type="ns1:IssueNoteData">
            <id xsi:type="xsd:integer">102</id>
            <reporter xsi:type="ns1:AccountData">
              <name xsi:type="xsd:string">王小明</name>
            </reporter>
            <text xsi:type="xsd:string">修復完畢，已合併至 v2.5.2。</text>
            <date_submitted xsi:type="xsd:dateTime">2026-01-20T14:00:00+08:00</date_submitted>
          </item>
        </notes>
      </return>
    </ns1:mc_issue_getResponse>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""


def _make_client_with_response(xml_text: str) -> MantisSoapClient:
    """建立已連線且 HTTP 回傳指定 XML 的假 client。"""
    client = MantisSoapClient("https://example.com/mantis", "user", "pass")
    client._connected = True
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = xml_text
    with patch("requests.post", return_value=mock_resp):
        client._cached_issue = client.get_issue("17186")
    return client


def test_get_issue_parses_severity_and_reporter():
    client = MantisSoapClient("https://example.com/mantis", "user", "pass")
    client._connected = True
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = _SAMPLE_SOAP
    with patch("requests.post", return_value=mock_resp):
        issue = client.get_issue("17186")
    assert issue is not None
    assert issue.summary == "薪資計算錯誤"
    assert issue.severity == "major"
    assert issue.reporter == "林美麗"
    assert issue.handler == "王小明"
    assert issue.status == "resolved"
    assert issue.target_version == "v2.5.1"
    assert issue.fixed_in_version == "v2.5.2"
    assert "加班費" in issue.description


def test_get_issue_parses_notes():
    client = MantisSoapClient("https://example.com/mantis", "user", "pass")
    client._connected = True
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = _SAMPLE_SOAP
    with patch("requests.post", return_value=mock_resp):
        issue = client.get_issue("17186")
    assert issue is not None
    assert issue.notes_count == 2
    assert len(issue.notes_list) == 2
    # 最新在前（降序）
    assert issue.notes_list[0].text == "修復完畢，已合併至 v2.5.2。"
    assert issue.notes_list[1].text == "已確認問題根因。"


def test_parse_notes_max_5():
    """超過 5 條時 notes_list 只取最後 5 條，notes_count 保留總數。"""
    # 建立含 7 條 note 的假 XML
    items = "".join(
        f"""<item xsi:type="ns1:IssueNoteData">
          <id xsi:type="xsd:integer">{i}</id>
          <reporter xsi:type="ns1:AccountData"><name xsi:type="xsd:string">u{i}</name></reporter>
          <text xsi:type="xsd:string">note {i}</text>
          <date_submitted xsi:type="xsd:dateTime">2026-01-{i:02d}T00:00:00+08:00</date_submitted>
        </item>"""
        for i in range(1, 8)
    )
    xml = _SAMPLE_SOAP.replace(
        "<notes>",
        f"<notes>{items}",
    ).replace(
        """<item xsi:type="ns1:IssueNoteData">
            <id xsi:type="xsd:integer">101</id>""",
        "<!-- replaced -->",
    )
    # 直接測試靜態方法
    notes, count = MantisSoapClient._parse_notes(xml, max_count=5)
    assert count == 7
    assert len(notes) == 5
```

> **注意**：`test_parse_notes_max_5` 直接測試 `_parse_notes` 靜態方法（返回 `tuple[list[MantisNote], int]`）。若實作時方法簽名不同，以實際簽名為準調整測試。

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_soap_fields.py -v
```

期望：`test_get_issue_parses_severity_and_reporter` 等 3 個新測試 FAIL

- [ ] **Step 3：更新 soap.py**

完整取代 `src/hcp_cms/services/mantis/soap.py`：

```python
"""Mantis SOAP API client."""

from __future__ import annotations

import re

import requests
import urllib3

from hcp_cms.services.mantis.base import MantisClient, MantisIssue, MantisNote

# 忽略自簽 SSL 憑證警告（內網 Mantis 伺服器常見）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class MantisSoapClient(MantisClient):
    def __init__(self, base_url: str, username: str = "", password: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._connected = False
        self.last_error: str = ""

    def connect(self) -> bool:
        """測試 SOAP 端點是否可達。"""
        try:
            resp = requests.get(
                f"{self._base_url}/api/soap/mantisconnect.php",
                timeout=10,
                verify=False,
            )
            self._connected = resp.status_code in (200, 400, 405, 500)
            return self._connected
        except Exception as e:
            self.last_error = str(e)
            self._connected = False
            return False

    def get_issue(self, issue_id: str) -> MantisIssue | None:
        if not self._connected:
            self.last_error = "尚未連線，請先呼叫 connect()"
            return None
        soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:man="http://futureware.biz/mantisconnect">
    <soapenv:Body>
        <man:mc_issue_get>
            <man:username>{self._username}</man:username>
            <man:password>{self._password}</man:password>
            <man:issue_id>{issue_id}</man:issue_id>
        </man:mc_issue_get>
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

            summary = self._extract_xml(text, "summary") or ""
            if not summary:
                self.last_error = "回應內容解析失敗（summary 為空）"
                return None

            status          = self._extract_xml(text, "name", after="status") or ""
            priority        = self._extract_xml(text, "name", after="priority") or ""
            handler         = self._extract_xml(text, "name", after="handler") or ""
            severity        = self._extract_xml(text, "name", after="severity") or ""
            reporter        = self._extract_xml(text, "name", after="reporter") or ""
            date_submitted  = self._extract_xml(text, "date_submitted") or ""
            last_updated    = self._extract_xml(text, "last_updated") or ""
            target_version  = self._extract_xml(text, "target_version") or ""
            fixed_in_version = self._extract_xml(text, "fixed_in_version") or ""
            description     = self._extract_xml(text, "description") or ""

            notes_list, notes_count = self._parse_notes(text, max_count=5)

            return MantisIssue(
                id=issue_id,
                summary=summary,
                status=status,
                priority=priority,
                handler=handler,
                severity=severity,
                reporter=reporter,
                date_submitted=date_submitted,
                last_updated=last_updated,
                target_version=target_version,
                fixed_in_version=fixed_in_version,
                description=description,
                notes_list=notes_list,
                notes_count=notes_count,
            )
        except requests.exceptions.SSLError as e:
            self.last_error = f"SSL 憑證錯誤：{e}"
            return None
        except requests.exceptions.ConnectionError as e:
            self.last_error = f"連線失敗：{e}"
            return None
        except requests.exceptions.Timeout:
            self.last_error = "連線逾時（30 秒）"
            return None
        except Exception as e:
            self.last_error = f"未知錯誤：{e}"
            return None

    def get_issues(self, project_id: str | None = None) -> list[MantisIssue]:
        return []

    @staticmethod
    def _extract_xml(text: str, tag: str, after: str | None = None) -> str | None:
        if after:
            m = re.search(f"<{after}[^>]*>", text)
            if m is None:
                return None
            text = text[m.start():]
        match = re.search(f"<{tag}[^>]*>(.*?)</{tag}>", text, re.DOTALL)
        return match.group(1).strip() if match else None

    @staticmethod
    def _parse_notes(text: str, max_count: int = 5) -> tuple[list[MantisNote], int]:
        """解析 SOAP 回應中的所有 <item>（Bug 筆記），返回最後 max_count 條（降序）與總數。"""
        # 找出 <notes> 區段
        notes_match = re.search(r"<notes[^>]*>(.*?)</notes>", text, re.DOTALL)
        if not notes_match:
            return [], 0

        notes_block = notes_match.group(1)
        items = re.findall(r"<item[^>]*>(.*?)</item>", notes_block, re.DOTALL)
        total = len(items)

        def _extract(block: str, tag: str, after: str | None = None) -> str:
            if after:
                m = re.search(f"<{after}[^>]*>", block)
                if m is None:
                    return ""
                block = block[m.start():]
            m2 = re.search(f"<{tag}[^>]*>(.*?)</{tag}>", block, re.DOTALL)
            return m2.group(1).strip() if m2 else ""

        notes: list[MantisNote] = []
        for item in items:
            notes.append(MantisNote(
                note_id=_extract(item, "id"),
                reporter=_extract(item, "name", after="reporter"),
                text=_extract(item, "text"),
                date_submitted=_extract(item, "date_submitted"),
            ))

        # 取最後 max_count 條，依 date_submitted 降序（最新在前）
        tail = notes[-max_count:] if len(notes) > max_count else notes
        tail_sorted = sorted(tail, key=lambda n: n.date_submitted, reverse=True)
        return tail_sorted, total
```

- [ ] **Step 4：確認所有測試通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_soap_fields.py -v
```

期望：5 tests PASSED

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/services/mantis/soap.py tests/unit/test_mantis_soap_fields.py
git commit -m "feat(mantis): SOAP 解析新增 severity/reporter/版本/描述/Bug筆記"
```

---

## Task 3：擴充 MantisTicket + DB Migration

**Files:**
- Modify: `src/hcp_cms/data/models.py`
- Modify: `src/hcp_cms/data/database.py`
- Test: `tests/unit/test_mantis_ticket_repository.py`

- [ ] **Step 1：寫失敗測試**

建立 `tests/unit/test_mantis_ticket_repository.py`：

```python
"""測試 MantisRepository 新欄位儲存與取回。"""
from __future__ import annotations
import sqlite3
import pytest
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import MantisTicket
from hcp_cms.data.repositories import MantisRepository


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    mgr = DatabaseManager(db_path)
    mgr.initialize()
    yield mgr.conn
    mgr.close()


def test_upsert_with_new_fields(db):
    repo = MantisRepository(db)
    ticket = MantisTicket(
        ticket_id="17186",
        summary="薪資計算錯誤",
        status="resolved",
        priority="high",
        handler="王小明",
        severity="major",
        reporter="林美麗",
        description="月底批次計算發生錯誤。",
        notes_json='[{"reporter":"王小明","text":"已修復","date_submitted":"2026-01-20"}]',
        notes_count=2,
    )
    repo.upsert(ticket)
    result = repo.get_by_id("17186")
    assert result is not None
    assert result.severity == "major"
    assert result.reporter == "林美麗"
    assert result.description == "月底批次計算發生錯誤。"
    assert result.notes_count == 2
    assert "已修復" in (result.notes_json or "")


def test_migration_is_idempotent(db):
    """重複呼叫 initialize() 不應拋出例外。"""
    mgr2 = DatabaseManager.__new__(DatabaseManager)
    mgr2._conn = db
    mgr2._apply_pending_migrations()  # 第二次執行不應報錯
```

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_ticket_repository.py -v
```

期望：FAIL（`MantisTicket` 無 `severity` 欄位）

- [ ] **Step 3：擴充 MantisTicket**

在 `src/hcp_cms/data/models.py` 找到 `class MantisTicket`，新增欄位：

```python
@dataclass
class MantisTicket:
    ticket_id: str
    summary: str
    created_time: str | None = None
    company_id: str | None = None
    priority: str | None = None
    status: str | None = None
    issue_type: str | None = None
    module: str | None = None
    handler: str | None = None
    planned_fix: str | None = None
    actual_fix: str | None = None
    progress: str | None = None
    notes: str | None = None
    synced_at: str | None = None
    # ── 新增欄位 ──
    severity: str | None = None
    reporter: str | None = None
    last_updated: str | None = None  # Mantis 最後更新時間
    description: str | None = None
    notes_json: str | None = None
    notes_count: int | None = None
```

- [ ] **Step 4：新增 DB Migration**

在 `src/hcp_cms/data/database.py` 的 `_apply_pending_migrations()` 的 `pending` list 末尾加入：

```python
"ALTER TABLE mantis_tickets ADD COLUMN severity TEXT",
"ALTER TABLE mantis_tickets ADD COLUMN reporter TEXT",
"ALTER TABLE mantis_tickets ADD COLUMN description TEXT",
"ALTER TABLE mantis_tickets ADD COLUMN notes_json TEXT",
"ALTER TABLE mantis_tickets ADD COLUMN last_updated TEXT",
"ALTER TABLE mantis_tickets ADD COLUMN notes_count INTEGER",
```

現有 `_apply_pending_migrations()` 的迴圈**逐條包覆**（每條 SQL 各自 try/except），因此裸 SQL 字串完全安全：

```python
for sql in pending:
    try:
        self._conn.execute(sql)
    except sqlite3.OperationalError:
        pass  # 欄位已存在，略過
```

重複執行也不會報錯，`test_migration_is_idempotent` 可正常通過。

- [ ] **Step 5：確認測試通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_ticket_repository.py -v
```

期望：2 tests FAILED（`upsert` 尚未更新）→ 繼續 Task 4

---

## Task 4：更新 MantisRepository.upsert()

**Files:**
- Modify: `src/hcp_cms/data/repositories.py`

- [ ] **Step 1：更新 upsert()**

找到 `MantisRepository.upsert()`，替換為：

```python
def upsert(self, ticket: MantisTicket) -> None:
    ticket.synced_at = _now()
    self._conn.execute(
        """
        INSERT INTO mantis_tickets (
            ticket_id, created_time, company_id, summary, priority, status,
            issue_type, module, handler, planned_fix, actual_fix,
            progress, notes, synced_at,
            severity, reporter, last_updated, description, notes_json, notes_count
        ) VALUES (
            :ticket_id, :created_time, :company_id, :summary, :priority, :status,
            :issue_type, :module, :handler, :planned_fix, :actual_fix,
            :progress, :notes, :synced_at,
            :severity, :reporter, :last_updated, :description, :notes_json, :notes_count
        )
        ON CONFLICT(ticket_id) DO UPDATE SET
            created_time = excluded.created_time,
            company_id = excluded.company_id,
            summary = excluded.summary,
            priority = excluded.priority,
            status = excluded.status,
            issue_type = excluded.issue_type,
            module = excluded.module,
            handler = excluded.handler,
            planned_fix = excluded.planned_fix,
            actual_fix = excluded.actual_fix,
            progress = excluded.progress,
            notes = excluded.notes,
            synced_at = excluded.synced_at,
            severity = excluded.severity,
            reporter = excluded.reporter,
            last_updated = excluded.last_updated,
            description = excluded.description,
            notes_json = excluded.notes_json,
            notes_count = excluded.notes_count
        """,
        {
            "ticket_id": ticket.ticket_id,
            "created_time": ticket.created_time,
            "company_id": ticket.company_id,
            "summary": ticket.summary,
            "priority": ticket.priority,
            "status": ticket.status,
            "issue_type": ticket.issue_type,
            "module": ticket.module,
            "handler": ticket.handler,
            "planned_fix": ticket.planned_fix,
            "actual_fix": ticket.actual_fix,
            "progress": ticket.progress,
            "notes": ticket.notes,
            "synced_at": ticket.synced_at,
            "severity": ticket.severity,
            "reporter": ticket.reporter,
            "last_updated": ticket.last_updated,
            "description": ticket.description,
            "notes_json": ticket.notes_json,
            "notes_count": ticket.notes_count,
        },
    )
    self._conn.commit()
```

- [ ] **Step 2：確認測試通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_ticket_repository.py -v
```

期望：2 tests PASSED

- [ ] **Step 3：跑全部測試確認無回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short
```

期望：全部 PASSED

- [ ] **Step 4：Commit**

```bash
git add src/hcp_cms/data/models.py src/hcp_cms/data/database.py src/hcp_cms/data/repositories.py tests/unit/test_mantis_ticket_repository.py
git commit -m "feat(data): MantisTicket 新增 severity/reporter/description/notes 欄位與 DB migration"
```

---

## Task 5：更新 sync_mantis_ticket()

**Files:**
- Modify: `src/hcp_cms/core/case_detail_manager.py`
- Test: `tests/unit/test_case_detail_manager_sync.py`

- [ ] **Step 1：寫失敗測試**

建立 `tests/unit/test_case_detail_manager_sync.py`：

```python
"""測試 CaseDetailManager.sync_mantis_ticket() 新欄位映射。"""
from __future__ import annotations
import json
import pytest
from unittest.mock import MagicMock
from hcp_cms.data.database import DatabaseManager
from hcp_cms.core.case_detail_manager import CaseDetailManager
from hcp_cms.services.mantis.base import MantisIssue, MantisNote


@pytest.fixture
def manager(tmp_path):
    db_path = tmp_path / "test.db"
    mgr = DatabaseManager(db_path)
    mgr.initialize()
    yield CaseDetailManager(mgr.conn)
    mgr.close()


def test_sync_maps_new_fields(manager):
    issue = MantisIssue(
        id="99001",
        summary="測試票",
        status="resolved",
        severity="major",
        reporter="林美麗",
        date_submitted="2026-01-15T10:00:00",
        target_version="v2.5.1",
        fixed_in_version="v2.5.2",
        description="詳細描述內容。",
        notes_list=[
            MantisNote(note_id="1", reporter="王小明", text="已修復", date_submitted="2026-01-20"),
        ],
        notes_count=1,
    )
    mock_client = MagicMock()
    mock_client.get_issue.return_value = issue

    ticket = manager.sync_mantis_ticket("99001", client=mock_client)

    assert ticket is not None
    assert ticket.severity == "major"
    assert ticket.reporter == "林美麗"
    assert ticket.planned_fix == "v2.5.1"
    assert ticket.actual_fix == "v2.5.2"
    assert ticket.description == "詳細描述內容。"
    assert ticket.notes_count == 1
    notes = json.loads(ticket.notes_json or "[]")
    assert notes[0]["text"] == "已修復"
    assert notes[0]["date_submitted"] == "2026-01-20"
```

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_case_detail_manager_sync.py -v
```

期望：FAIL（`ticket.severity` 為 None）

- [ ] **Step 3：更新 sync_mantis_ticket()**

在 `src/hcp_cms/core/case_detail_manager.py` 頂部加入：

```python
import json
```

替換 `sync_mantis_ticket()` 方法：

```python
def sync_mantis_ticket(
    self,
    ticket_id: str,
    client: MantisClient | None = None,
) -> MantisTicket | None:
    """呼叫 MantisClient 同步單一 ticket，更新本地快取。"""
    if client is None:
        return None
    issue = client.get_issue(ticket_id)
    if issue is None:
        return None

    from datetime import datetime
    synced_at = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    ticket = MantisTicket(
        ticket_id=issue.id,
        summary=issue.summary,
        status=issue.status,
        priority=issue.priority,
        handler=issue.handler,
        severity=issue.severity,
        reporter=issue.reporter,
        created_time=issue.date_submitted,
        planned_fix=issue.target_version,
        actual_fix=issue.fixed_in_version,
        description=issue.description,
        last_updated=issue.last_updated,
        notes_json=json.dumps(
            [
                {
                    "reporter": n.reporter,
                    "text": n.text,
                    "date_submitted": n.date_submitted,
                }
                for n in issue.notes_list
            ],
            ensure_ascii=False,
        ),
        notes_count=issue.notes_count,
    )
    self._mantis_repo.upsert(ticket)
    return self._mantis_repo.get_by_id(ticket_id)
```

- [ ] **Step 4：確認測試通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_case_detail_manager_sync.py tests/unit/test_mantis_ticket_repository.py tests/unit/test_mantis_soap_fields.py -v
```

期望：全部 PASSED

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/core/case_detail_manager.py tests/unit/test_case_detail_manager_sync.py
git commit -m "feat(core): sync_mantis_ticket 映射新欄位（severity/reporter/版本/描述/筆記）"
```

---

## Task 6：重新設計 Mantis 關聯 Tab UI

**Files:**
- Modify: `src/hcp_cms/ui/case_detail_dialog.py`

> UI 層不寫自動測試，改以人工驗收確認。

- [ ] **Step 1：更新 imports**

在 `src/hcp_cms/ui/case_detail_dialog.py` 的 imports 區塊新增：

```python
import json

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (
    # ...（現有）
    QFrame,
    QGridLayout,
    QSizePolicy,
)
```

- [ ] **Step 2：新增 `_status_badge_style()` 輔助方法**

在 `CaseDetailDialog` 類別中新增（可放在 `_build_tab3` 之前）：

```python
@staticmethod
def _status_colors(status: str) -> tuple[str, str]:
    """依 Mantis 狀態字串回傳 (背景色, 文字色)。"""
    s = status.lower()
    if "resolved" in s or "已解決" in s:
        return "#166534", "#bbf7d0"
    if "closed" in s or "已關閉" in s:
        return "#1f2937", "#9ca3af"
    if "assigned" in s or "in progress" in s or "處理中" in s:
        return "#7c2d12", "#fed7aa"
    if "acknowledged" in s or "confirmed" in s or "已確認" in s:
        return "#78350f", "#fde68a"
    if "feedback" in s or "回饋" in s:
        return "#3730a3", "#c7d2fe"
    # new / 其他
    return "#1e3a5f", "#93c5fd"
```

- [ ] **Step 3：重寫 `_build_tab3()`**

取代現有 `_build_tab3()` 方法：

```python
def _build_tab3(self) -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)

    # ── 工具列 ──
    toolbar = QHBoxLayout()
    self._ticket_input = QLineEdit()
    self._ticket_input.setPlaceholderText("輸入 Ticket 編號")
    self._ticket_input.setFixedWidth(150)
    link_btn = QPushButton("🔗 連結")
    link_btn.clicked.connect(self._on_link_mantis)
    sync_btn = QPushButton("🔄 同步選取")
    sync_btn.clicked.connect(self._on_sync_mantis)
    unlink_btn = QPushButton("🗑 取消連結")
    unlink_btn.clicked.connect(self._on_unlink_mantis)
    toolbar.addWidget(self._ticket_input)
    toolbar.addWidget(link_btn)
    toolbar.addWidget(sync_btn)
    toolbar.addWidget(unlink_btn)
    toolbar.addStretch()
    layout.addLayout(toolbar)

    # ── 上方表格（5欄） ──
    self._mantis_table = QTableWidget(0, 5)
    self._mantis_table.setHorizontalHeaderLabels(
        ["票號", "狀態", "摘要", "處理人", "最後同步"]
    )
    self._mantis_table.horizontalHeader().setStretchLastSection(True)
    self._mantis_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    self._mantis_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    self._mantis_table.setColumnWidth(0, 70)
    self._mantis_table.setColumnWidth(1, 90)
    self._mantis_table.setColumnWidth(3, 80)
    self._mantis_table.setColumnWidth(4, 140)
    self._mantis_table.currentRowChanged.connect(self._on_mantis_table_row_changed)
    layout.addWidget(self._mantis_table)

    # ── 下方詳情面板（常駐） ──
    detail_frame = QFrame()
    detail_frame.setStyleSheet(
        "QFrame { background-color: #1e293b; border: 1px solid #334155; border-radius: 6px; }"
    )
    detail_layout = QVBoxLayout(detail_frame)
    detail_layout.setContentsMargins(12, 10, 12, 10)

    # 標題列
    self._detail_title = QLabel("請點選上方 Ticket 查看詳情")
    self._detail_title.setStyleSheet("color: #475569; font-size: 12px;")
    detail_layout.addWidget(self._detail_title)

    # 6格 Grid（2行×3欄）
    self._detail_grid_widget = QWidget()
    grid = QGridLayout(self._detail_grid_widget)
    grid.setContentsMargins(0, 6, 0, 6)
    grid.setHorizontalSpacing(20)
    self._detail_grid_widget.setVisible(False)

    self._detail_labels: dict[str, QLabel] = {}
    # 8 個欄位，3 欄 × 3 行（第 3 行只有 2 格）
    fields = [
        ("嚴重性", "severity"), ("優先", "priority"), ("回報者", "reporter"),
        ("建立時間", "created_time"), ("🎯 目標版本", "planned_fix"), ("✅ 修復版本", "actual_fix"),
        ("🕐 最後更新", "last_updated"), ("處理人", "handler"),
    ]
    for idx, (label_text, key) in enumerate(fields):
        row, col = divmod(idx, 3)  # 每行 3 欄
        lbl = QLabel(label_text)
        lbl.setStyleSheet("color: #64748b; font-size: 10px;")
        val = QLabel("—")
        val.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        self._detail_labels[key] = val
        cell = QVBoxLayout()
        cell.addWidget(lbl)
        cell.addWidget(val)
        cell.setSpacing(1)
        container = QWidget()
        container.setLayout(cell)
        grid.addWidget(container, row, col)

    detail_layout.addWidget(self._detail_grid_widget)

    # 問題描述
    self._detail_desc_label = QLabel("📝 問題描述")
    self._detail_desc_label.setStyleSheet("color: #64748b; font-size: 10px;")
    self._detail_desc_label.setVisible(False)
    detail_layout.addWidget(self._detail_desc_label)

    self._detail_desc = QTextEdit()
    self._detail_desc.setReadOnly(True)
    self._detail_desc.setMaximumHeight(90)
    self._detail_desc.setStyleSheet(
        "QTextEdit { background: #0f172a; color: #94a3b8; border: none; font-size: 11px; }"
    )
    self._detail_desc.setVisible(False)
    detail_layout.addWidget(self._detail_desc)

    # Bug 筆記
    self._detail_notes_label = QLabel("💬 最後 5 條 Bug 筆記")
    self._detail_notes_label.setStyleSheet("color: #64748b; font-size: 10px;")
    self._detail_notes_label.setVisible(False)
    detail_layout.addWidget(self._detail_notes_label)

    self._detail_notes = QTextEdit()
    self._detail_notes.setReadOnly(True)
    self._detail_notes.setMaximumHeight(110)
    self._detail_notes.setStyleSheet(
        "QTextEdit { background: #0f172a; color: #94a3b8; border: none; font-size: 11px; }"
    )
    self._detail_notes.setVisible(False)
    detail_layout.addWidget(self._detail_notes)

    # 「查看更多」連結（僅在 notes_count > 5 時顯示）
    self._detail_more_link = QLabel()
    self._detail_more_link.setStyleSheet("color: #60a5fa; font-size: 11px;")
    self._detail_more_link.setOpenExternalLinks(False)
    self._detail_more_link.linkActivated.connect(self._on_open_mantis_url)
    self._detail_more_link.setVisible(False)
    detail_layout.addWidget(self._detail_more_link)

    layout.addWidget(detail_frame)
    return w
```

- [ ] **Step 4：新增 `_on_mantis_table_row_changed()` 與 `_refresh_detail_panel()`**

在 `_build_tab3` 之後新增：

```python
def _on_mantis_table_row_changed(self, row: int) -> None:  # noqa: N802
    if row < 0:
        self._refresh_detail_panel(None)
        return
    ticket_id_item = self._mantis_table.item(row, 0)
    if ticket_id_item is None:
        self._refresh_detail_panel(None)
        return
    ticket_id = ticket_id_item.text()
    ticket = self._manager.get_mantis_ticket(ticket_id)
    self._refresh_detail_panel(ticket)

def _refresh_detail_panel(self, ticket) -> None:  # type: ignore[return]
    """填入詳情面板資料；ticket=None 時還原為提示狀態。"""
    from hcp_cms.data.models import MantisTicket
    no_data = ticket is None
    self._detail_grid_widget.setVisible(not no_data)
    self._detail_desc_label.setVisible(not no_data)
    self._detail_desc.setVisible(not no_data)
    self._detail_notes_label.setVisible(not no_data)
    self._detail_notes.setVisible(not no_data)
    self._detail_more_link.setVisible(False)

    if no_data:
        self._detail_title.setText("請點選上方 Ticket 查看詳情")
        self._detail_title.setStyleSheet("color: #475569; font-size: 12px;")
        return

    # 標題
    status_text = ticket.status or ""
    self._detail_title.setText(
        f"#{ticket.ticket_id}　{status_text}　{ticket.summary or ''}"
    )
    self._detail_title.setStyleSheet("color: #93c5fd; font-weight: bold; font-size: 12px;")

    # 6格資訊
    values = {
        "severity": ticket.severity or "—",
        "priority": ticket.priority or "—",
        "reporter": ticket.reporter or "—",
        "created_time": ticket.created_time or "—",
        "planned_fix": ticket.planned_fix or "—",
        "actual_fix": ticket.actual_fix or "—",
        "last_updated": ticket.last_updated or "—",
        "handler": ticket.handler or "—",
    }
    for key, val in values.items():
        lbl = self._detail_labels.get(key)
        if lbl:
            lbl.setText(val)

    # 描述
    self._detail_desc.setPlainText(ticket.description or "（無描述）")

    # Bug 筆記
    notes_html = ""
    if ticket.notes_json:
        try:
            notes = json.loads(ticket.notes_json)
            for n in notes:
                reporter = n.get("reporter", "")
                date = n.get("date_submitted", "")
                text = n.get("text", "")[:200]
                notes_html += f"[{date}] {reporter}：{text}\n\n"
        except (json.JSONDecodeError, AttributeError):
            notes_html = "（筆記解析失敗）"
    self._detail_notes.setPlainText(notes_html or "（無筆記）")

    # 「查看更多」連結
    count = ticket.notes_count or 0
    if count > 5:
        self._detail_more_link.setVisible(True)
        self._detail_more_link.setText(
            f'<a href="{ticket.ticket_id}">📎 尚有更多筆記（共 {count} 條），點此在 Mantis 查看完整記錄</a>'
        )

def _on_open_mantis_url(self, ticket_id: str) -> None:
    """開啟 Mantis 原始 Ticket 頁面。"""
    from hcp_cms.services.credential import CredentialManager
    creds = CredentialManager()
    base = creds.retrieve("mantis_url") or ""
    if not base:
        QMessageBox.warning(self, "未設定", "請先在系統設定填寫 Mantis URL。")
        return
    base = base.rstrip("/")
    url = f"{base}/view.php?id={ticket_id}"
    QDesktopServices.openUrl(QUrl(url))
```

- [ ] **Step 5：更新 `_refresh_mantis_table()` 改為 5 欄並加狀態顏色**

取代現有 `_refresh_mantis_table()` 方法：

```python
def _refresh_mantis_table(self) -> None:
    tickets = self._manager.list_linked_tickets(self._case_id)
    self._mantis_table.setRowCount(len(tickets))
    for i, t in enumerate(tickets):
        self._mantis_table.setItem(i, 0, QTableWidgetItem(t.ticket_id))

        # 狀態（帶背景色）
        status_item = QTableWidgetItem(t.status or "")
        bg, fg = self._status_colors(t.status or "")
        status_item.setBackground(QBrush(QColor(bg)))
        status_item.setForeground(QBrush(QColor(fg)))
        self._mantis_table.setItem(i, 1, status_item)

        self._mantis_table.setItem(i, 2, QTableWidgetItem(t.summary or ""))
        self._mantis_table.setItem(i, 3, QTableWidgetItem(t.handler or ""))
        self._mantis_table.setItem(i, 4, QTableWidgetItem(t.synced_at or ""))
    # 重設詳情面板
    self._refresh_detail_panel(None)
```

- [ ] **Step 6：在 CaseDetailManager 新增 `get_mantis_ticket()` 方法**

在 `src/hcp_cms/core/case_detail_manager.py` 的 `list_linked_tickets()` 後新增：

```python
def get_mantis_ticket(self, ticket_id: str) -> MantisTicket | None:
    """依 ticket_id 取得本地快取的 Ticket 資料。"""
    return self._mantis_repo.get_by_id(ticket_id)
```

- [ ] **Step 7：跑全部測試**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short
```

期望：全部 PASSED

- [ ] **Step 8：Commit**

```bash
git add src/hcp_cms/ui/case_detail_dialog.py src/hcp_cms/core/case_detail_manager.py
git commit -m "feat(ui): Mantis 關聯 Tab 改版為表格+詳情面板，顯示嚴重性/版本/描述/Bug筆記"
```

---

## Task 7：人工驗收

- [ ] **Step 1：啟動應用程式**

```bash
.venv/Scripts/python.exe -m hcp_cms
```

- [ ] **Step 2：驗收項目**

| 場景 | 期望結果 |
|------|---------|
| 開啟案件 → Mantis 關聯 Tab | 面板底部顯示「請點選上方 Ticket 查看詳情」 |
| 輸入票號 → 點「🔗 連結」 | 自動從 SOAP 取得並連結；表格出現 1 筆，狀態有背景色 |
| 點選表格列 | 詳情面板顯示嚴重性、版本、描述、筆記 |
| 票號有 > 5 條筆記 | 底部顯示「📎 尚有更多筆記...」連結 |
| 點擊「查看完整記錄」連結 | 瀏覽器開啟 Mantis view.php?id=XXXXX |
| 未設定 Mantis URL 時點連結 | 彈出「請先在系統設定填寫 Mantis URL」警告 |

- [ ] **Step 3：最終 commit（如有修正）**

```bash
git add -p   # 逐一確認
git commit -m "fix(ui): 驗收後小修正"
```
