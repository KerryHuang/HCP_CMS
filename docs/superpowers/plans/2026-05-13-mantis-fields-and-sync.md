# Mantis 推送欄位強化 + bugnote 雙向同步 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A 補強 Mantis 推送欄位（custom_fields + 客戶原信 description）；B 加 case_logs ↔ bugnotes 雙向同步（手動觸發按鈕、bugnote_id 去重）。

**Architecture:** A 擴 SOAP `mc_issue_add` 支援 `<man:custom_fields>` + MantisPushManager 改 description 來源。B 加 `case_logs.bugnote_id` 欄位作 dedup key，CaseDetailManager 新增 outbound/inbound/bidirectional 方法，UI 擴充既有「🔄 同步選取」按鈕。

**Tech Stack:** Python 3.14、PySide6、SQLite、既有 `MantisSoapClient`、`CaseLogRepository`

**Spec:** [`docs/superpowers/specs/2026-05-13-mantis-fields-and-sync-design.md`](../specs/2026-05-13-mantis-fields-and-sync-design.md)

---

## 檔案結構規劃

### 修改
```
src/hcp_cms/services/mantis/base.py             # MantisClient.create_issue ABC 加 custom_fields 參數
src/hcp_cms/services/mantis/soap.py             # MantisSoapClient.create_issue 實作 + REST stub 同步
src/hcp_cms/services/mantis/rest.py             # REST stub 同步加 custom_fields kwarg
src/hcp_cms/core/mantis_push.py                 # _build_description 改用客戶來信；push_case_as_new_ticket 傳 custom_fields
src/hcp_cms/data/database.py                    # case_logs.bugnote_id schema + migration
src/hcp_cms/data/models.py                      # CaseLog.bugnote_id field
src/hcp_cms/data/repositories.py                # CaseLogRepository.insert 加 bugnote_id；新增 update()
src/hcp_cms/core/case_detail_manager.py         # sync_bugnotes_outbound / inbound / bidirectional
src/hcp_cms/ui/case_detail_dialog.py            # _on_sync_mantis 擴充 bugnote 同步 + 結果摘要

tests/unit/test_mantis_soap_write.py            # 加 3 custom_fields 測試
tests/unit/test_mantis_push_manager.py          # 加 2 描述與 custom_fields 整合測試
tests/unit/test_case_detail_manager_sync.py     # 加 6 同步測試
```

---

## Task 1：MantisClient ABC + SOAP 加 custom_fields 參數

**Files:**
- Modify: `src/hcp_cms/services/mantis/base.py` (MantisClient ABC)
- Modify: `src/hcp_cms/services/mantis/soap.py` (MantisSoapClient.create_issue)
- Modify: `src/hcp_cms/services/mantis/rest.py` (NotImplementedError stub 加 kwarg)
- Modify: `tests/unit/test_mantis_soap_write.py`

**目的：** 讓 `create_issue` 接受 custom_fields dict，組 SOAP envelope 內 `<man:custom_fields>` 區段。

- [ ] **Step 1：在 test 檔加 3 個新測試**

於 `tests/unit/test_mantis_soap_write.py` 末加：

```python
def test_create_issue_includes_custom_fields_when_provided(client: MantisSoapClient) -> None:
    response_xml = '<return xsi:type="xsd:integer">99</return>'
    with patch("hcp_cms.services.mantis.soap.requests.post") as mock_post:
        mock_post.return_value = _mock_response(response_xml)
        client.create_issue(
            project_id="1",
            summary="x",
            description="y",
            custom_fields={"客戶提問人員": "customer@xyz.com"},
        )
        sent_body = mock_post.call_args.kwargs.get("data", b"").decode("utf-8")
    assert "<man:custom_fields>" in sent_body
    assert "<man:name>客戶提問人員</man:name>" in sent_body
    assert "<man:value>customer@xyz.com</man:value>" in sent_body


def test_create_issue_omits_custom_fields_when_none(client: MantisSoapClient) -> None:
    response_xml = '<return xsi:type="xsd:integer">99</return>'
    with patch("hcp_cms.services.mantis.soap.requests.post") as mock_post:
        mock_post.return_value = _mock_response(response_xml)
        client.create_issue(
            project_id="1",
            summary="x",
            description="y",
            custom_fields=None,
        )
        sent_body = mock_post.call_args.kwargs.get("data", b"").decode("utf-8")
    assert "<man:custom_fields>" not in sent_body


def test_create_issue_custom_field_xml_escapes(client: MantisSoapClient) -> None:
    response_xml = '<return xsi:type="xsd:integer">99</return>'
    with patch("hcp_cms.services.mantis.soap.requests.post") as mock_post:
        mock_post.return_value = _mock_response(response_xml)
        client.create_issue(
            project_id="1",
            summary="x",
            description="y",
            custom_fields={"問題類型": "A&B <test>"},
        )
        sent_body = mock_post.call_args.kwargs.get("data", b"").decode("utf-8")
    assert "A&amp;B &lt;test&gt;" in sent_body
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
cd /d/CMS/.claude/worktrees/mantis-fields-and-sync
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_soap_write.py -v 2>&1 | tail -10
```

預期：3 個新測試 FAIL（custom_fields 參數不存在）

- [ ] **Step 3：修改 MantisClient ABC**

`src/hcp_cms/services/mantis/base.py` 找到 `def create_issue` 抽象方法簽名，加 `custom_fields` 參數：

```python
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
        custom_fields: dict[str, str] | None = None,
    ) -> str | None:
        """建立新 issue，成功回傳 ticket_id，失敗回 None（self.last_error 含原因）。"""
```

- [ ] **Step 4：修改 MantisSoapClient.create_issue**

`src/hcp_cms/services/mantis/soap.py` 找到 `create_issue`，修改簽名 + 在 SOAP body 組裝中插入 custom_fields 區段：

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
        custom_fields: dict[str, str] | None = None,
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
        # ★ 新增 custom_fields 區段
        custom_fields_block = ""
        if custom_fields:
            items = "".join(
                f"<man:item>"
                f"<man:field><man:name>{self._escape_xml(name)}</man:name></man:field>"
                f"<man:value>{self._escape_xml(value)}</man:value>"
                f"</man:item>"
                for name, value in custom_fields.items()
            )
            custom_fields_block = f"<man:custom_fields>{items}</man:custom_fields>"

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
                {custom_fields_block}
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
```

⚠ 既有方法整段替換（保留簽名 + 加邏輯 + 整段 try/except）。

- [ ] **Step 5：REST stub 同步加 kwarg**

`src/hcp_cms/services/mantis/rest.py` 的 `create_issue` 簽名加 `custom_fields`：

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
        custom_fields: dict[str, str] | None = None,
    ) -> str | None:
        raise NotImplementedError("REST create_issue 未實作；MVP 僅支援 SOAP")
```

- [ ] **Step 6：跑測試驗證通過**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_soap_write.py -v 2>&1 | tail -15
```

預期：所有測試 PASS（既有 9 + 新 3 = 12 個）

- [ ] **Step 7：跑既有 push manager 測試確認簽名相容**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_push_manager.py -q 2>&1 | tail -5
```

預期：14 個全 PASS（既有 push manager 沒傳 custom_fields，向後相容）

- [ ] **Step 8：commit**

```bash
git add src/hcp_cms/services/mantis/base.py src/hcp_cms/services/mantis/soap.py src/hcp_cms/services/mantis/rest.py tests/unit/test_mantis_soap_write.py
git commit -m "feat(mantis): create_issue 加 custom_fields 參數

Task 1 of Mantis 推送欄位強化實作計畫。

- MantisClient ABC + SOAP + REST 同步加 custom_fields: dict[str,str] | None
- SOAP envelope 動態組裝 <man:custom_fields><man:item>... 區段
- custom_fields=None / 空 dict 時不送該區段（向後相容）
- 新增 3 個測試：含 / 不含 custom_fields / XML escape"
```

---

## Task 2：MantisPushManager description 改用客戶來信 + 傳 custom_fields

**Files:**
- Modify: `src/hcp_cms/core/mantis_push.py`（`_build_description` + `push_case_as_new_ticket`）
- Modify: `tests/unit/test_mantis_push_manager.py`

**目的：** description 用第一筆「客戶來信」case_log 內容（最舊在前，[0]）；推送時帶 `{"客戶提問人員": case.contact_person}`。

- [ ] **Step 1：在 test 檔加 2 個新測試**

於 `tests/unit/test_mantis_push_manager.py` 末加（注意：fixture `setup` 內 C-1 已含 contact_person?需確認，未有則調整）：

```python
def test_push_description_uses_first_customer_log(setup) -> None:
    """description 應為第一筆 direction=客戶來信 的 case_log content（list_by_case 為 ASC，第一筆是最舊）。"""
    db = setup
    from datetime import datetime
    from hcp_cms.data.models import CaseLog
    from hcp_cms.data.repositories import CaseLogRepository
    log_repo = CaseLogRepository(db.connection)
    # 故意先插較新的（測排序正確）
    log_repo.insert(CaseLog(
        log_id=log_repo.next_log_id(),
        case_id="C-1",
        direction="客戶來信",
        content="第二封補充來信",
        logged_at="2026/05/05 10:00:00",
    ))
    log_repo.insert(CaseLog(
        log_id=log_repo.next_log_id(),
        case_id="C-1",
        direction="客戶來信",
        content="原始來信內容",
        logged_at="2026/05/04 09:00:00",
    ))

    client = MagicMock()
    client.create_issue.return_value = "100"
    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    mgr.push_case_as_new_ticket("C-1", "S-YOGA")

    description = client.create_issue.call_args.kwargs["description"]
    # 用第一筆（最舊）
    assert "原始來信內容" in description
    assert "第二封補充來信" not in description
    # 仍含 [HCP-CMS] header
    assert "[HCP-CMS: C-1]" in description


def test_push_sends_contact_person_as_custom_field(setup) -> None:
    """contact_person 應作為 custom_field '客戶提問人員' 送進 SOAP。"""
    db = setup
    # 案件需有 contact_person — fixture 預設可能沒，補上
    case_repo = CaseRepository(db.connection)
    case = case_repo.get_by_id("C-1")
    case.contact_person = "customer@xyz.com"
    case_repo.update(case)

    client = MagicMock()
    client.create_issue.return_value = "101"
    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    mgr.push_case_as_new_ticket("C-1", "S-YOGA")

    custom_fields = client.create_issue.call_args.kwargs.get("custom_fields")
    assert custom_fields == {"客戶提問人員": "customer@xyz.com"}


def test_push_omits_custom_field_when_no_contact_person(setup) -> None:
    """無 contact_person → 不送 custom_fields。"""
    db = setup
    case_repo = CaseRepository(db.connection)
    case = case_repo.get_by_id("C-1")
    case.contact_person = None
    case_repo.update(case)

    client = MagicMock()
    client.create_issue.return_value = "102"
    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    mgr.push_case_as_new_ticket("C-1", "S-YOGA")

    assert client.create_issue.call_args.kwargs.get("custom_fields") is None
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_push_manager.py::test_push_description_uses_first_customer_log tests/unit/test_mantis_push_manager.py::test_push_sends_contact_person_as_custom_field tests/unit/test_mantis_push_manager.py::test_push_omits_custom_field_when_no_contact_person -v 2>&1 | tail -10
```

預期：FAIL（description 仍用結構化版本 / custom_fields 沒傳）

- [ ] **Step 3：修改 `_build_description`**

`src/hcp_cms/core/mantis_push.py` 找到 `_build_description`，整段替換：

```python
    def _build_description(self, case: Case) -> str:
        """description 用第一筆「客戶來信」case_log 內容，加 [HCP-CMS] header。

        若該案件無「客戶來信」case_log（如手動建案），fallback 為舊版結構化 description。
        list_by_case 排序為 logged_at ASC，第一筆 [0] 是最舊（原始來信）。
        """
        logs = self._log_repo.list_by_case(case.case_id)
        customer_logs = [log for log in logs if log.direction == "客戶來信"]

        if customer_logs:
            original = customer_logs[0]  # 最舊 = 原始來信
            return f"[HCP-CMS: {case.case_id}]\n\n{original.content or ''}"

        # Fallback：舊版結構化（無客戶來信時保底）
        parts = [f"[HCP-CMS: {case.case_id}]"]
        if case.subject:
            parts.append(f"【主旨】{case.subject}")
        if case.progress:
            parts.append(f"【處理進度】\n{case.progress}")
        if case.company_id:
            parts.append(f"【客戶】{case.company_id}")
        if case.contact_person:
            parts.append(f"【聯絡人】{case.contact_person}")
        return "\n\n".join(parts)
```

- [ ] **Step 4：修改 `push_case_as_new_ticket` 傳 custom_fields**

`src/hcp_cms/core/mantis_push.py` 找到 `push_case_as_new_ticket` 內 `self._client.create_issue(...)` 呼叫，加 `custom_fields` 參數：

```python
        ticket_id = self._client.create_issue(
            project_id=self._project_id,
            summary=summary,
            description=self._build_description(case),
            category=self._category,
            priority=_PRIORITY_MAP.get(case.priority or "中", "normal"),
            severity="minor",
            handler=case.handler if case.handler else None,
            custom_fields=(
                {"客戶提問人員": case.contact_person}
                if case.contact_person else None
            ),
        )
```

- [ ] **Step 5：跑測試驗證通過**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_push_manager.py -v 2>&1 | tail -15
```

預期：17 個 PASS（14 既有 + 3 新）

⚠ 既有 `test_push_case_as_new_ticket_success` 內的 `assert call_kwargs["summary"] == "印表機異常"` 已經升級過（之前的 Task）。新的 description 改動可能會讓某些既有 description 相關 assertion 失敗，逐一檢查並調整為「[HCP-CMS: id]」存在 + 「印表機異常」存在（fallback 路徑）。

- [ ] **Step 6：commit**

```bash
git add src/hcp_cms/core/mantis_push.py tests/unit/test_mantis_push_manager.py
git commit -m "feat(core): description 用客戶原信 + custom_fields 帶 contact_person

Task 2 of Mantis 推送欄位強化實作計畫。

- _build_description: 找第一筆 direction=客戶來信 case_log（list_by_case ASC, [0]）
  - 有 → '[HCP-CMS: id]\n\n{原始來信}'
  - 無 → fallback 結構化（手動建案案件保底）
- push_case_as_new_ticket 傳 custom_fields={'客戶提問人員': contact_person}
- 3 個新測試覆蓋 description 排序 + custom_fields 含 / 不含"
```

---

## Task 3：case_logs.bugnote_id schema + model + repository update

**Files:**
- Modify: `src/hcp_cms/data/database.py`（schema + migration）
- Modify: `src/hcp_cms/data/models.py`（CaseLog 加 bugnote_id）
- Modify: `src/hcp_cms/data/repositories.py`（CaseLogRepository.insert 加 bugnote_id；新增 update）
- Modify: `tests/unit/` 加 schema + repository test

**目的：** 新增 bugnote_id 欄位作 dedup key，提供 insert/update 介面。

- [ ] **Step 1：寫失敗測試**

新增 `tests/unit/test_case_log_bugnote_id.py`：

```python
"""CaseLog.bugnote_id 欄位與 CaseLogRepository.update 測試。"""
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, CaseLog
from hcp_cms.data.repositories import CaseLogRepository, CaseRepository


@pytest.fixture
def db(tmp_path: Path):
    d = DatabaseManager(tmp_path / "t.db")
    d.initialize()
    CaseRepository(d.connection).insert(Case(case_id="C-1", subject="test"))
    yield d
    d.close()


def test_bugnote_id_column_exists(db) -> None:
    cur = db.connection.execute("PRAGMA table_info(case_logs)")
    cols = {row[1] for row in cur.fetchall()}
    assert "bugnote_id" in cols


def test_insert_with_bugnote_id(db) -> None:
    repo = CaseLogRepository(db.connection)
    log = CaseLog(
        log_id=repo.next_log_id(),
        case_id="C-1",
        direction="內部討論",
        content="test note",
        bugnote_id="N-789",
        logged_at="2026/05/13 10:00:00",
    )
    repo.insert(log)
    saved = repo.list_by_case("C-1")[0]
    assert saved.bugnote_id == "N-789"


def test_insert_without_bugnote_id_defaults_none(db) -> None:
    repo = CaseLogRepository(db.connection)
    log = CaseLog(
        log_id=repo.next_log_id(),
        case_id="C-1",
        direction="內部討論",
        content="無 bugnote",
        logged_at="2026/05/13 10:00:00",
    )
    repo.insert(log)
    saved = repo.list_by_case("C-1")[0]
    assert saved.bugnote_id is None


def test_update_writes_bugnote_id(db) -> None:
    repo = CaseLogRepository(db.connection)
    log = CaseLog(
        log_id=repo.next_log_id(),
        case_id="C-1",
        direction="內部討論",
        content="test",
        logged_at="2026/05/13 10:00:00",
    )
    repo.insert(log)
    saved = repo.list_by_case("C-1")[0]
    assert saved.bugnote_id is None

    # update bugnote_id
    saved.bugnote_id = "N-456"
    repo.update(saved)

    after = repo.list_by_case("C-1")[0]
    assert after.bugnote_id == "N-456"
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
cd /d/CMS/.claude/worktrees/mantis-fields-and-sync
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_case_log_bugnote_id.py -v 2>&1 | tail -10
```

預期：FAIL（欄位不存在 / update 方法不存在）

- [ ] **Step 3：修改 database.py — schema + migration**

`src/hcp_cms/data/database.py` 找到 `CREATE TABLE IF NOT EXISTS case_logs (...)`（約 line 144-152），加 `bugnote_id` 欄位：

```sql
CREATE TABLE IF NOT EXISTS case_logs (
    log_id     TEXT PRIMARY KEY,
    case_id    TEXT NOT NULL REFERENCES cs_cases(case_id),
    direction  TEXT NOT NULL,
    content    TEXT NOT NULL,
    mantis_ref TEXT,
    bugnote_id TEXT,
    logged_by  TEXT,
    logged_at  TEXT NOT NULL
);
```

於 `_apply_pending_migrations` 的 `pending: list[str]` 加（約 line 262 後）：

```python
            "ALTER TABLE case_logs ADD COLUMN bugnote_id TEXT",
```

⚠ 既有 migration 用 try/except 包 ALTER，已存在欄位不報錯。

- [ ] **Step 4：修改 models.py — 加 bugnote_id**

`src/hcp_cms/data/models.py` 找到 `class CaseLog`，加 `bugnote_id`：

```python
@dataclass
class CaseLog:
    """補充記錄 — case_logs table."""
    log_id: str
    case_id: str
    direction: str            # '客戶來信' | 'HCP 信件回覆' | 'HCP 線上回覆' | '內部討論' | 'Mantis 推送' | 'Mantis bugnote'
    content: str
    mantis_ref: str | None = None
    bugnote_id: str | None = None
    logged_by: str | None = None
    logged_at: str = ""
    reply_time: str | None = None
```

- [ ] **Step 5：修改 CaseLogRepository — insert 加 bugnote_id + 新增 update**

`src/hcp_cms/data/repositories.py` 找到 `class CaseLogRepository`，修改 insert 並加 update：

```python
    def insert(self, log: CaseLog) -> None:
        self._conn.execute(
            """
            INSERT INTO case_logs (log_id, case_id, direction, content, mantis_ref, bugnote_id, logged_by, logged_at, reply_time)
            VALUES (:log_id, :case_id, :direction, :content, :mantis_ref, :bugnote_id, :logged_by, :logged_at, :reply_time)
            """,
            {
                "log_id": log.log_id,
                "case_id": log.case_id,
                "direction": log.direction,
                "content": log.content,
                "mantis_ref": log.mantis_ref,
                "bugnote_id": log.bugnote_id,
                "logged_by": log.logged_by,
                "logged_at": log.logged_at,
                "reply_time": log.reply_time,
            },
        )
        self._conn.commit()

    def update(self, log: CaseLog) -> None:
        """更新既有 case_log（依 log_id 找到對應筆覆寫）。"""
        self._conn.execute(
            """
            UPDATE case_logs SET
                direction = :direction,
                content = :content,
                mantis_ref = :mantis_ref,
                bugnote_id = :bugnote_id,
                logged_by = :logged_by,
                logged_at = :logged_at,
                reply_time = :reply_time
            WHERE log_id = :log_id
            """,
            {
                "log_id": log.log_id,
                "direction": log.direction,
                "content": log.content,
                "mantis_ref": log.mantis_ref,
                "bugnote_id": log.bugnote_id,
                "logged_by": log.logged_by,
                "logged_at": log.logged_at,
                "reply_time": log.reply_time,
            },
        )
        self._conn.commit()
```

- [ ] **Step 6：跑測試驗證通過**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_case_log_bugnote_id.py -v 2>&1 | tail -10
```

預期：4 個測試 PASS

- [ ] **Step 7：跑既有 case_log + case_manager 相關測試確認無回歸**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_case_manager.py tests/unit/test_thread_tracker.py tests/unit/test_case_manager_delete.py tests/unit/test_audit_logger.py -q 2>&1 | tail -3
```

預期：全部 PASS

- [ ] **Step 8：Lint**

```bash
/d/CMS/.venv/Scripts/ruff.exe check src/hcp_cms/data/database.py src/hcp_cms/data/models.py src/hcp_cms/data/repositories.py tests/unit/test_case_log_bugnote_id.py
```

預期：All checks passed!

- [ ] **Step 9：commit**

```bash
git add src/hcp_cms/data/database.py src/hcp_cms/data/models.py src/hcp_cms/data/repositories.py tests/unit/test_case_log_bugnote_id.py
git commit -m "feat(data): case_logs.bugnote_id 欄位（dedup key）+ Repository.update

Task 3 of Mantis 同步實作計畫。

- case_logs 加 bugnote_id TEXT 欄位（NULL = 尚未同步）
- _apply_pending_migrations 加冪等 ALTER（既有 DB 補欄位）
- CaseLog model 加 bugnote_id; direction 註解加 'Mantis bugnote' 值
- CaseLogRepository.insert 含 bugnote_id; 新增 update() 方法

4 個單元測試覆蓋欄位 / 插入 / 預設 NULL / 更新。"
```

---

## Task 4：CaseDetailManager.sync_bugnotes_outbound

**Files:**
- Modify: `src/hcp_cms/core/case_detail_manager.py`（新增 sync_bugnotes_outbound）
- Modify: `tests/unit/test_case_detail_manager_sync.py`（加 3 個測試）

**目的：** 把 case_logs 推為 Mantis bugnotes。過濾 direction + dedup（bugnote_id is NULL）+ 寫回 bugnote_id。

- [ ] **Step 1：在 test 檔加 3 個新測試**

於 `tests/unit/test_case_detail_manager_sync.py` 末加：

```python
# ============= sync_bugnotes_outbound =============


def test_sync_outbound_pushes_eligible_logs(db_with_case_and_ticket):
    """推符合 direction 且 bugnote_id 為 NULL 的 case_logs。"""
    db, _case, _link = db_with_case_and_ticket
    log_repo = CaseLogRepository(db.connection)
    log_repo.insert(CaseLog(
        log_id=log_repo.next_log_id(),
        case_id="C-1",
        direction="內部討論",
        content="進度筆記 1",
        logged_at="2026/05/13 10:00:00",
    ))
    log_repo.insert(CaseLog(
        log_id=log_repo.next_log_id(),
        case_id="C-1",
        direction="HCP 信件回覆",
        content="已回覆客戶",
        logged_at="2026/05/13 11:00:00",
    ))

    client = MagicMock()
    client.add_note.side_effect = ["N-100", "N-101"]

    mgr = CaseDetailManager(db.connection)
    success, fail = mgr.sync_bugnotes_outbound("C-1", "9999", client)

    assert success == 2
    assert fail == 0

    # 驗證 bugnote_id 寫回
    logs = log_repo.list_by_case("C-1")
    push_logs = [log for log in logs if log.direction != "Mantis 推送"]
    bugnote_ids = {log.bugnote_id for log in push_logs}
    assert "N-100" in bugnote_ids
    assert "N-101" in bugnote_ids


def test_sync_outbound_skips_non_pushable_directions(db_with_case_and_ticket):
    """客戶來信 / Mantis 推送 / Mantis bugnote 都不應推。"""
    db, _case, _link = db_with_case_and_ticket
    log_repo = CaseLogRepository(db.connection)
    for direction in ("客戶來信", "Mantis 推送", "Mantis bugnote"):
        log_repo.insert(CaseLog(
            log_id=log_repo.next_log_id(),
            case_id="C-1",
            direction=direction,
            content=f"{direction} 內容",
            logged_at="2026/05/13 10:00:00",
        ))

    client = MagicMock()
    mgr = CaseDetailManager(db.connection)
    success, fail = mgr.sync_bugnotes_outbound("C-1", "9999", client)

    assert success == 0
    assert fail == 0
    client.add_note.assert_not_called()


def test_sync_outbound_skips_already_synced(db_with_case_and_ticket):
    """bugnote_id 已寫的 case_log 不重推。"""
    db, _case, _link = db_with_case_and_ticket
    log_repo = CaseLogRepository(db.connection)
    log_repo.insert(CaseLog(
        log_id=log_repo.next_log_id(),
        case_id="C-1",
        direction="內部討論",
        content="已同步過",
        bugnote_id="N-999",
        logged_at="2026/05/13 10:00:00",
    ))

    client = MagicMock()
    mgr = CaseDetailManager(db.connection)
    success, fail = mgr.sync_bugnotes_outbound("C-1", "9999", client)

    assert success == 0
    assert fail == 0
    client.add_note.assert_not_called()


def test_sync_outbound_handles_soap_failure(db_with_case_and_ticket):
    """add_note 回 None 時 fail 計數 +1，不寫回 bugnote_id。"""
    db, _case, _link = db_with_case_and_ticket
    log_repo = CaseLogRepository(db.connection)
    log_repo.insert(CaseLog(
        log_id=log_repo.next_log_id(),
        case_id="C-1",
        direction="內部討論",
        content="會失敗",
        logged_at="2026/05/13 10:00:00",
    ))

    client = MagicMock()
    client.add_note.return_value = None
    client.last_error = "Issue locked"

    mgr = CaseDetailManager(db.connection)
    success, fail = mgr.sync_bugnotes_outbound("C-1", "9999", client)

    assert success == 0
    assert fail == 1

    logs = log_repo.list_by_case("C-1")
    push_logs = [log for log in logs if log.direction == "內部討論"]
    assert push_logs[0].bugnote_id is None
```

⚠ 第 1 個測試的 fixture 內案件 ID 是 `C-1`，依 Task 3 / 既有 fixture 結構。`CaseLog` import 必要時加。

- [ ] **Step 2：跑測試驗證失敗**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_case_detail_manager_sync.py -k "outbound" -v 2>&1 | tail -10
```

預期：4 個測試 FAIL（method 不存在）

- [ ] **Step 3：實作 sync_bugnotes_outbound**

`src/hcp_cms/core/case_detail_manager.py` 找到既有 `unlink_mantis_with_audit` 方法後加：

```python
_PUSH_DIRECTIONS = ("內部討論", "HCP 信件回覆", "HCP 線上回覆")


# ... 接在 unlink_mantis_with_audit 之後 ...

    def sync_bugnotes_outbound(
        self,
        case_id: str,
        ticket_id: str,
        client: MantisClient,
    ) -> tuple[int, int]:
        """把 case_logs 推為 Mantis bugnotes。

        過濾規則：
        - direction 必須在 _PUSH_DIRECTIONS（內部討論 / HCP 信件回覆 / HCP 線上回覆）
        - bugnote_id 為 NULL（尚未同步）

        Returns:
            (success_count, fail_count)
        """
        logs = self._log_repo.list_by_case(case_id)
        candidates = [
            log for log in logs
            if log.direction in _PUSH_DIRECTIONS and not log.bugnote_id
        ]
        success = 0
        fail = 0
        for log in candidates:
            note_id = client.add_note(
                issue_id=ticket_id,
                text=log.content or "",
            )
            if note_id is None:
                fail += 1
                continue
            log.bugnote_id = note_id
            self._log_repo.update(log)
            success += 1
        return success, fail
```

⚠ `_PUSH_DIRECTIONS` 是模組級常數，放在 `case_detail_manager.py` 檔頂的 import 之後、`SyncResult` enum 之前。

- [ ] **Step 4：跑測試驗證通過**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_case_detail_manager_sync.py -v 2>&1 | tail -15
```

預期：所有測試 PASS（既有 + 4 新 outbound）

- [ ] **Step 5：commit**

```bash
git add src/hcp_cms/core/case_detail_manager.py tests/unit/test_case_detail_manager_sync.py
git commit -m "feat(core): sync_bugnotes_outbound 推 case_logs 為 bugnotes

Task 4 of Mantis 同步實作計畫。

- 過濾：direction in (內部討論, HCP 信件回覆, HCP 線上回覆)
- dedup：bugnote_id IS NULL
- 推送成功寫回 bugnote_id；失敗不寫
- 4 個測試覆蓋成功 / 跳過非推送類型 / 跳過已同步 / SOAP 失敗"
```

---

## Task 5：CaseDetailManager.sync_bugnotes_inbound

**Files:**
- Modify: `src/hcp_cms/core/case_detail_manager.py`（新增 sync_bugnotes_inbound）
- Modify: `tests/unit/test_case_detail_manager_sync.py`（加 2 個測試）

**目的：** 從 Mantis 拉新 bugnotes 為 case_logs。dedup 依 bugnote_id；插入 direction='Mantis bugnote'。

- [ ] **Step 1：在 test 檔加 2 個新測試**

於 `tests/unit/test_case_detail_manager_sync.py` 末加：

```python
# ============= sync_bugnotes_inbound =============


def test_sync_inbound_pulls_new_bugnotes(db_with_case_and_ticket):
    """Mantis 端有的 note_id 不在 case_logs.bugnote_id → 插入新 case_log。"""
    from hcp_cms.services.mantis.base import MantisIssue, MantisNote
    db, _case, _link = db_with_case_and_ticket

    client = MagicMock()
    client.get_issue.return_value = MantisIssue(
        id="9999",
        summary="x",
        notes_list=[
            MantisNote(note_id="N-200", reporter="RD 王", text="RD 已修", date_submitted="2026/05/13"),
            MantisNote(note_id="N-201", reporter="RD 林", text="測試通過", date_submitted="2026/05/13"),
        ],
        notes_count=2,
    )

    mgr = CaseDetailManager(db.connection)
    pulled, fail = mgr.sync_bugnotes_inbound("C-1", "9999", client)

    assert pulled == 2
    assert fail == 0

    logs = CaseLogRepository(db.connection).list_by_case("C-1")
    inbound_logs = [log for log in logs if log.direction == "Mantis bugnote"]
    assert len(inbound_logs) == 2
    contents = {log.content for log in inbound_logs}
    assert "RD 已修" in contents
    assert "測試通過" in contents
    # 寫入 bugnote_id 作 dedup
    ids = {log.bugnote_id for log in inbound_logs}
    assert ids == {"N-200", "N-201"}


def test_sync_inbound_skips_existing_bugnote_id(db_with_case_and_ticket):
    """已有對應 bugnote_id 的 case_log 不重複插入。"""
    from hcp_cms.services.mantis.base import MantisIssue, MantisNote
    db, _case, _link = db_with_case_and_ticket
    log_repo = CaseLogRepository(db.connection)
    # 預存一筆 bugnote_id=N-300 的 case_log（模擬之前已同步過）
    log_repo.insert(CaseLog(
        log_id=log_repo.next_log_id(),
        case_id="C-1",
        direction="Mantis bugnote",
        content="先前已存在",
        bugnote_id="N-300",
        logged_at="2026/05/12 09:00:00",
    ))

    client = MagicMock()
    client.get_issue.return_value = MantisIssue(
        id="9999", summary="x",
        notes_list=[
            MantisNote(note_id="N-300", reporter="RD", text="重複", date_submitted="2026/05/12"),
            MantisNote(note_id="N-301", reporter="RD", text="新的", date_submitted="2026/05/13"),
        ],
        notes_count=2,
    )

    mgr = CaseDetailManager(db.connection)
    pulled, fail = mgr.sync_bugnotes_inbound("C-1", "9999", client)

    assert pulled == 1  # 只 pull N-301
    inbound_logs = [log for log in log_repo.list_by_case("C-1") if log.direction == "Mantis bugnote"]
    assert len(inbound_logs) == 2  # 先前 1 + 新 1
    new_log = next(log for log in inbound_logs if log.bugnote_id == "N-301")
    assert new_log.content == "新的"


def test_sync_inbound_handles_get_issue_failure(db_with_case_and_ticket):
    """client.get_issue 回 None → fail += 1，pulled = 0。"""
    db, _case, _link = db_with_case_and_ticket
    client = MagicMock()
    client.get_issue.return_value = None

    mgr = CaseDetailManager(db.connection)
    pulled, fail = mgr.sync_bugnotes_inbound("C-1", "9999", client)

    assert pulled == 0
    assert fail == 1
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_case_detail_manager_sync.py -k "inbound" -v 2>&1 | tail -10
```

預期：3 個測試 FAIL

- [ ] **Step 3：實作 sync_bugnotes_inbound**

於 `src/hcp_cms/core/case_detail_manager.py` 內 `sync_bugnotes_outbound` 後加：

```python
    def sync_bugnotes_inbound(
        self,
        case_id: str,
        ticket_id: str,
        client: MantisClient,
    ) -> tuple[int, int]:
        """從 Mantis 拉新 bugnotes 為 case_logs。

        過濾規則：
        - 從 client.get_issue(ticket_id) 取 notes_list
        - note_id 不在現有 case_logs.bugnote_id → 新增

        Returns:
            (pulled_count, fail_count)
        """
        issue = client.get_issue(ticket_id)
        if issue is None:
            return 0, 1

        existing_logs = self._log_repo.list_by_case(case_id)
        existing_ids = {log.bugnote_id for log in existing_logs if log.bugnote_id}

        pulled = 0
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        for note in issue.notes_list:
            if not note.note_id or note.note_id in existing_ids:
                continue
            new_log = CaseLog(
                log_id=self._log_repo.next_log_id(),
                case_id=case_id,
                direction="Mantis bugnote",
                content=note.text or "",
                bugnote_id=note.note_id,
                logged_by=note.reporter,
                logged_at=note.date_submitted or now,
            )
            self._log_repo.insert(new_log)
            pulled += 1
        return pulled, 0
```

- [ ] **Step 4：跑測試驗證通過**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_case_detail_manager_sync.py -v 2>&1 | tail -15
```

預期：所有測試 PASS

- [ ] **Step 5：commit**

```bash
git add src/hcp_cms/core/case_detail_manager.py tests/unit/test_case_detail_manager_sync.py
git commit -m "feat(core): sync_bugnotes_inbound 拉 Mantis bugnotes 為 case_logs

Task 5 of Mantis 同步實作計畫。

- 從 client.get_issue(ticket_id).notes_list 取
- dedup：note_id NOT IN existing case_logs.bugnote_id
- 插入 direction='Mantis bugnote' + bugnote_id + reporter + date_submitted
- 3 個測試覆蓋拉新 / dedup / get_issue 失敗"
```

---

## Task 6：sync_bugnotes_bidirectional + UI _on_sync_mantis 擴充

**Files:**
- Modify: `src/hcp_cms/core/case_detail_manager.py`（加 sync_bugnotes_bidirectional）
- Modify: `src/hcp_cms/ui/case_detail_dialog.py`（_on_sync_mantis 接 bugnote 同步）
- Modify: `tests/unit/test_case_detail_manager_sync.py`（加 1 整合測試）

**目的：** 把 outbound + inbound 整合為單一方法 + UI 結果摘要 dialog。

- [ ] **Step 1：在 test 檔加整合測試**

於 `tests/unit/test_case_detail_manager_sync.py` 末加：

```python
# ============= sync_bugnotes_bidirectional 整合 =============


def test_sync_bidirectional_returns_summary(db_with_case_and_ticket):
    """整合：1 筆出向（成功）+ 1 筆入向（新）+ 1 筆 SOAP 失敗 → summary 正確。"""
    from hcp_cms.services.mantis.base import MantisIssue, MantisNote

    db, _case, _link = db_with_case_and_ticket
    log_repo = CaseLogRepository(db.connection)
    log_repo.insert(CaseLog(
        log_id=log_repo.next_log_id(),
        case_id="C-1", direction="內部討論", content="會成功",
        logged_at="2026/05/13 10:00:00",
    ))
    log_repo.insert(CaseLog(
        log_id=log_repo.next_log_id(),
        case_id="C-1", direction="內部討論", content="會失敗",
        logged_at="2026/05/13 10:01:00",
    ))

    client = MagicMock()
    # 出向：第 1 筆成功 N-X、第 2 筆 fail
    client.add_note.side_effect = ["N-X", None]
    client.last_error = "Issue locked"
    # 入向：拉一筆新的 N-Y
    client.get_issue.return_value = MantisIssue(
        id="9999", summary="x",
        notes_list=[MantisNote(note_id="N-Y", reporter="RD", text="新留言", date_submitted="2026/05/13")],
        notes_count=1,
    )

    mgr = CaseDetailManager(db.connection)
    summary = mgr.sync_bugnotes_bidirectional("C-1", "9999", client)

    assert summary == {"pushed": 1, "pulled": 1, "fail": 1}
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_case_detail_manager_sync.py::test_sync_bidirectional_returns_summary -v 2>&1 | tail -5
```

預期：FAIL

- [ ] **Step 3：實作 sync_bugnotes_bidirectional**

於 `src/hcp_cms/core/case_detail_manager.py` 內 `sync_bugnotes_inbound` 後加：

```python
    def sync_bugnotes_bidirectional(
        self,
        case_id: str,
        ticket_id: str,
        client: MantisClient,
    ) -> dict:
        """雙向同步 case_logs ↔ Mantis bugnotes。

        Returns:
            {"pushed": int, "pulled": int, "fail": int}
        """
        push_success, push_fail = self.sync_bugnotes_outbound(case_id, ticket_id, client)
        pull_success, pull_fail = self.sync_bugnotes_inbound(case_id, ticket_id, client)
        return {
            "pushed": push_success,
            "pulled": pull_success,
            "fail": push_fail + pull_fail,
        }
```

- [ ] **Step 4：跑測試驗證通過**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_case_detail_manager_sync.py -v 2>&1 | tail -5
```

預期：所有測試 PASS

- [ ] **Step 5：修改 case_detail_dialog.py 的 `_on_sync_mantis`**

讀 `src/hcp_cms/ui/case_detail_dialog.py` 找到 `_on_sync_mantis`（之前 mantis-detect-deleted Task 已改過），整段替換為：

```python
    def _on_sync_mantis(self) -> None:
        from hcp_cms.core.case_detail_manager import SyncResult

        rows = self._mantis_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "提示", "請先選取要同步的 Ticket。")
            return
        ticket_id = self._mantis_table.item(rows[0].row(), 0).text()
        client = self._build_mantis_client()
        result, _ticket = self._manager.sync_mantis_ticket(ticket_id, client=client)

        if result == SyncResult.NOT_FOUND:
            reply = QMessageBox.question(
                self,
                "Ticket 已不存在",
                f"Mantis ticket #{ticket_id} 已不存在（可能已被刪除）。\n\n"
                "是否要從本案件解除連結？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._manager.unlink_mantis_with_audit(
                    self._case_id, ticket_id,
                    reason="Mantis 找不到此 ticket（同步時偵測）",
                )
                self._refresh_mantis_table()
                QMessageBox.information(
                    self, "已解除連結", f"Ticket #{ticket_id} 連結已移除。"
                )
            return

        if result == SyncResult.ERROR:
            QMessageBox.warning(self, "同步失敗", "無法連線至 Mantis，或 Mantis 設定未完成。")
            return

        # SUCCESS — 接著雙向同步 bugnotes
        summary_dict = self._manager.sync_bugnotes_bidirectional(
            case_id=self._case_id,
            ticket_id=ticket_id,
            client=client,
        )
        self._refresh_mantis_table()
        # 嘗試重整 log 表（既有方法名可能不同，try 兩種）
        if hasattr(self, "_load_logs"):
            self._load_logs()
        elif hasattr(self, "_refresh_log_table"):
            self._refresh_log_table()

        QMessageBox.information(
            self,
            "同步完成",
            f"Ticket metadata 已更新。\n\n"
            f"補充記錄同步：\n"
            f"  推出 {summary_dict['pushed']} 筆\n"
            f"  拉入 {summary_dict['pulled']} 筆\n"
            f"  失敗 {summary_dict['fail']} 筆",
        )
```

⚠ `_load_logs` / `_refresh_log_table` 名稱不確定，Step 6 grep 驗證後保留正確的，移除錯的。

- [ ] **Step 6：grep 找 dialog 內補充記錄重整方法名**

```bash
grep -n "_load_logs\|_refresh_log\|_log_table\|log_table\|logs.*setRowCount\|_load_case_logs" /d/CMS/.claude/worktrees/mantis-fields-and-sync/src/hcp_cms/ui/case_detail_dialog.py | head -10
```

依結果調整 Step 5 的 hasattr 檢查或直接呼叫實際方法名。若都沒找到（dialog 沒提供 log 重整 method），可省略並讓使用者手動關閉再開夠詳情視窗。

- [ ] **Step 7：Import smoke test**

```bash
cd /d/CMS/.claude/worktrees/mantis-fields-and-sync
PYTHONPATH=src /d/CMS/.venv/Scripts/python.exe -c "
from hcp_cms.ui.case_detail_dialog import CaseDetailDialog
from hcp_cms.core.case_detail_manager import CaseDetailManager
print('Import OK')
"
```

預期：`Import OK`

- [ ] **Step 8：Lint**

```bash
/d/CMS/.venv/Scripts/ruff.exe check src/hcp_cms/core/case_detail_manager.py src/hcp_cms/ui/case_detail_dialog.py tests/unit/test_case_detail_manager_sync.py
```

預期：All checks passed!

- [ ] **Step 9：跑全 sync 相關測試**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_case_detail_manager_sync.py tests/unit/test_case_detail_manager.py tests/unit/test_mantis_error_detector.py tests/unit/test_case_log_bugnote_id.py tests/unit/test_mantis_push_manager.py tests/unit/test_mantis_soap_write.py -q 2>&1 | tail -3
```

預期：全部 PASS

- [ ] **Step 10：commit**

```bash
git add src/hcp_cms/core/case_detail_manager.py src/hcp_cms/ui/case_detail_dialog.py tests/unit/test_case_detail_manager_sync.py
git commit -m "feat(ui): _on_sync_mantis 整合 bugnote 雙向同步 + 結果摘要

Task 6 of Mantis 同步實作計畫。

- 新增 sync_bugnotes_bidirectional 整合 outbound + inbound
- _on_sync_mantis SUCCESS 路徑接著雙向同步
- 結果 QMessageBox 顯示「推出 N / 拉入 M / 失敗 X」
- NOT_FOUND / ERROR 既有路徑不變

1 個整合測試覆蓋 1 推 + 1 拉 + 1 失敗的 summary。"
```

---

## 完工檢查

- [ ] **跑全部相關測試**

```bash
cd /d/CMS/.claude/worktrees/mantis-fields-and-sync
/d/CMS/.venv/Scripts/python.exe -m pytest \
  tests/unit/test_mantis_soap_write.py \
  tests/unit/test_mantis_push_manager.py \
  tests/unit/test_case_log_bugnote_id.py \
  tests/unit/test_case_detail_manager_sync.py \
  tests/unit/test_case_detail_manager.py \
  tests/unit/test_mantis_error_detector.py \
  tests/unit/test_case_formatter.py \
  -q 2>&1 | tail -3
```

預期：全部 PASS

- [ ] **Lint**

```bash
/d/CMS/.venv/Scripts/ruff.exe check \
  src/hcp_cms/services/mantis/base.py \
  src/hcp_cms/services/mantis/soap.py \
  src/hcp_cms/services/mantis/rest.py \
  src/hcp_cms/core/mantis_push.py \
  src/hcp_cms/core/case_detail_manager.py \
  src/hcp_cms/data/database.py \
  src/hcp_cms/data/models.py \
  src/hcp_cms/data/repositories.py \
  src/hcp_cms/ui/case_detail_dialog.py
```

預期：All checks passed!

---

## 風險與處理

| 風險 | 處理方式 |
|------|------|
| Mantis SOAP `<man:custom_fields>` 區段格式跨版本不一致 | Task 1 完成後可選 Live POC：對 project 218 推一筆含 custom_fields 的測試 ticket，驗證 SOAP 接受 |
| 「客戶提問人員」實際 Mantis custom field name 含特殊字元 / 大小寫 | Live POC 用既有 `mc_issue_get` 反查 ticket 看實際 custom field name |
| 既有 push manager 測試對 description 結構化內容做 assert 會破 | Task 2 Step 5 補既有 fixture / 改 assert（看 [HCP-CMS: id] 在不在）|
| `_load_logs` / `_refresh_log_table` 不存在 | Task 6 Step 6 grep 確認；若無就略過 log table 重整，使用者重開 dialog 才看到 |
| Mantis 端 bugnotes 超過 10 筆 → 入向只拉 10 筆 | 既有 SOAP `_parse_notes(max_count=10)` 限制；Phase 2 擴充 |
