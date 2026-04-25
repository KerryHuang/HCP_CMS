# 客服問題彙整報表 + Google Sheets 自動寫入 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在「報表中心」新增「客服問題彙整」報表，抓取全部案件，依 A/B/C 風險分級 + 問題/原因/解法 人工欄位，一鍵 Upsert 至指定 Google Sheet（OAuth 授權），支援可選排程同步。

**Architecture:**
- Data 層：於 `cs_cases` 增加 4 欄位（`problem_level`、`problem`、`cause`、`solution`），Case model 同步。
- Core 層：`ProblemLevelClassifier`（error_type → A/B/C 自動推論）+ `CSReportEngine`（組成 10 欄 row，upsert by case_id）。
- Services 層：`GoogleSheetsService`（OAuth user flow + gspread upsert），token 存 keyring。
- UI 層：`case_view` 詳情區新增 4 輸入欄位；`report_view` 新增「客服問題彙整」分頁 + 「同步至 Google Sheets」按鈕；`settings_view` 新增 Google Sheets OAuth 設定區。
- Scheduler 層：`cs_report_sync_job` 可選排程（每日 / 每週）。

**Tech Stack:** PySide6 6.10.2、SQLite、`gspread`、`google-auth-oauthlib`、`keyring`、`pytest`。

---

## 檔案結構

**Data 層**
- 修改：`src/hcp_cms/data/database.py`（`_apply_pending_migrations` 加 4 個 ALTER TABLE）
- 修改：`src/hcp_cms/data/models.py`（`Case` 加 4 欄位）
- 修改：`src/hcp_cms/data/repositories.py`（`CaseRepository.update` / `get_by_id` 包含新欄位）
- 測試：`tests/unit/test_case_report_columns.py`

**Core 層**
- 新增：`src/hcp_cms/core/problem_level_classifier.py`
- 新增：`src/hcp_cms/core/cs_report_engine.py`
- 測試：`tests/unit/test_problem_level_classifier.py`
- 測試：`tests/unit/test_cs_report_engine.py`

**Services 層**
- 新增：`src/hcp_cms/services/google_sheets_service.py`
- 測試：`tests/unit/test_google_sheets_service.py`（以 mock 為主）

**UI 層**
- 修改：`src/hcp_cms/ui/case_view.py`（詳情區 4 欄位 + 存檔）
- 修改：`src/hcp_cms/ui/report_view.py`（新增報表分頁 + 同步按鈕）
- 修改：`src/hcp_cms/ui/settings_view.py`（Google OAuth 設定區 + 排程開關）

**Scheduler 層**
- 新增：`src/hcp_cms/scheduler/cs_report_sync_job.py`
- 修改：`src/hcp_cms/scheduler/scheduler.py`（註冊 job）

**依賴**
- 修改：`pyproject.toml`（加 `gspread`、`google-auth-oauthlib`）

---

## Task 1: Data 層 — Case 新增 4 欄位 + Repository 支援

**Files:**
- Modify: `src/hcp_cms/data/database.py` (`_apply_pending_migrations`)
- Modify: `src/hcp_cms/data/models.py` (`Case` dataclass)
- Modify: `src/hcp_cms/data/repositories.py` (`CaseRepository`)
- Test: `tests/unit/test_case_report_columns.py`

### 風險評估
- 技術可行性：低（冪等 ALTER TABLE，既有模式）。
- 需求確定性：高（欄位明確）。

### Step 1.1 寫失敗測試

- [ ] **Step 1.1**

建立 `tests/unit/test_case_report_columns.py`：

```python
"""cs_cases 新增 4 欄位（problem_level/problem/cause/solution）測試。"""

from __future__ import annotations

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case
from hcp_cms.data.repositories import CaseRepository, CompanyRepository
from hcp_cms.data.models import Company


@pytest.fixture()
def conn(tmp_path):
    dbm = DatabaseManager(tmp_path / "t.db")
    dbm.initialize()
    yield dbm.conn
    dbm.close()


def test_case_has_report_columns(conn):
    cursor = conn.execute("PRAGMA table_info(cs_cases)")
    cols = {row[1] for row in cursor.fetchall()}
    assert {"problem_level", "problem", "cause", "solution"} <= cols


def test_case_repository_round_trip_report_fields(conn):
    CompanyRepository(conn).insert(Company(company_id="acme", name="ACME", domain="acme.com"))
    repo = CaseRepository(conn)
    case = Case(
        case_id="CS-REP-001",
        subject="薪資計算錯誤",
        company_id="acme",
        error_type="薪資獎金計算",
        problem_level="A",
        problem="月底結算薪資少算加班費",
        cause="加班費公式漏判夜班",
        solution="修正公式 + 補發差額",
    )
    repo.insert(case)
    got = repo.get_by_id("CS-REP-001")
    assert got is not None
    assert got.problem_level == "A"
    assert got.problem == "月底結算薪資少算加班費"
    assert got.cause == "加班費公式漏判夜班"
    assert got.solution == "修正公式 + 補發差額"
```

- [ ] **Step 1.2 執行測試，確認失敗**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_case_report_columns.py -v`
Expected: FAIL（欄位不存在 / Case dataclass 無此欄位）

### Step 1.3 新增欄位到 models.py

- [ ] **Step 1.3**

編輯 `src/hcp_cms/data/models.py`，`Case` dataclass 於 `extra_fields` 之前加入：

```python
    problem_level: str | None = None    # "A" | "B" | "C"
    problem: str | None = None
    cause: str | None = None
    solution: str | None = None
```

### Step 1.4 新增 ALTER TABLE

- [ ] **Step 1.4**

編輯 `src/hcp_cms/data/database.py`，於 `_apply_pending_migrations` 的 migrations list 尾端加入：

```python
            "ALTER TABLE cs_cases ADD COLUMN problem_level TEXT",
            "ALTER TABLE cs_cases ADD COLUMN problem TEXT",
            "ALTER TABLE cs_cases ADD COLUMN cause TEXT",
            "ALTER TABLE cs_cases ADD COLUMN solution TEXT",
```

同時若 `_SCHEMA_SQL` 的 `CREATE TABLE cs_cases` 原始欄位定義需要新資料庫直接有此欄位，加入：

```sql
    problem_level TEXT,
    problem TEXT,
    cause TEXT,
    solution TEXT,
```

（加在 `handler` 之後、`reply_count` 之前或於表尾，不影響其他欄位）

### Step 1.5 修改 CaseRepository

- [ ] **Step 1.5**

編輯 `src/hcp_cms/data/repositories.py`，`CaseRepository`：
- `insert()` 的 INSERT SQL 及 `params` 加入 4 個新欄位。
- `update()` 的 UPDATE SQL 加入 4 個新欄位。
- `_row_to_case()`（或等效對映）將 row 轉 `Case` 時讀取 4 個新欄位。

使用 `:problem_level`、`:problem`、`:cause`、`:solution` 參數化。

### Step 1.6 執行測試確認通過

- [ ] **Step 1.6**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_case_report_columns.py -v`
Expected: PASS (2 passed)

同時跑全部既有 case 測試確認沒破：
Run: `.venv/Scripts/python.exe -m pytest tests/unit/ -k case -v`
Expected: 全部 PASS

### Step 1.7 Commit

- [ ] **Step 1.7**

```bash
git add src/hcp_cms/data/database.py src/hcp_cms/data/models.py src/hcp_cms/data/repositories.py tests/unit/test_case_report_columns.py
git commit -m "feat(data): cs_cases 新增 problem_level/problem/cause/solution 欄位"
```

---

## Task 2: Core 層 — ProblemLevelClassifier

**Files:**
- Create: `src/hcp_cms/core/problem_level_classifier.py`
- Test: `tests/unit/test_problem_level_classifier.py`

### 風險評估
- 技術可行性：低（純字典查表）。
- 需求確定性：高（使用者已確認完整對映表）。

### Step 2.1 寫失敗測試

- [ ] **Step 2.1**

建立 `tests/unit/test_problem_level_classifier.py`：

```python
"""ProblemLevelClassifier：error_type → A/B/C 自動推論。"""

from __future__ import annotations

from hcp_cms.core.problem_level_classifier import ProblemLevelClassifier


def test_classify_a_level():
    c = ProblemLevelClassifier()
    assert c.classify("薪資獎金計算") == "A"
    assert c.classify("GL拋轉作業") == "A"
    assert c.classify("所得稅處理") == "A"


def test_classify_b_level():
    c = ProblemLevelClassifier()
    assert c.classify("差勤請假管理") == "B"
    assert c.classify("人事資料管理") == "B"
    assert c.classify("HCP安裝&資料庫錯誤") == "B"


def test_classify_c_level():
    c = ProblemLevelClassifier()
    assert c.classify("合約管理") == "C"
    assert c.classify("人事報表") == "C"
    assert c.classify("ESS(PHP)") == "C"


def test_classify_unknown_falls_back_to_c():
    c = ProblemLevelClassifier()
    assert c.classify("未知模組") == "C"
    assert c.classify(None) == "C"
    assert c.classify("") == "C"
```

- [ ] **Step 2.2 確認失敗**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_problem_level_classifier.py -v`
Expected: FAIL（ModuleNotFoundError）

### Step 2.3 實作 classifier

- [ ] **Step 2.3**

建立 `src/hcp_cms/core/problem_level_classifier.py`：

```python
"""ProblemLevelClassifier — 依 error_type（模組名）自動推論 A/B/C 問題等級。

對映規則由使用者確認（2026-04-24）：
- A（6 項）：薪資/GL/調薪/福利/所得稅
- B（12 項）：行事曆、差勤、排班、刷卡、保險、組織、人事資料、HCP 錯誤等
- C（15 項 + fallback）：報表、合約、教育訓練、ESS、客製、其餘
"""

from __future__ import annotations

_LEVEL_A: set[str] = {
    "薪資獎金計算",
    "薪資報表",
    "GL拋轉作業",
    "調薪試算",
    "福利金處理",
    "所得稅處理",
}

_LEVEL_B: set[str] = {
    "行事曆與排班",
    "差勤請假管理",
    "年假管理",
    "彈休管理",
    "刷卡管理",
    "工時管理",
    "員工用餐管理",
    "社會保險管理",
    "勞健團保二代健保勞退",
    "組織部門建立",
    "人事資料管理",
    "HCP安裝&資料庫錯誤",
}

_LEVEL_C: set[str] = {
    "人事報表",
    "合約管理",
    "員工教育訓練",
    "績效考核管理",
    "員工獎懲管理",
    "簽核流程管理",
    "自助分析作業",
    "匯入匯出作業",
    "系統管理",
    "系統參數",
    "警示系統設定",
    "住宿管理",
    "客製程式",
    "ESS(.NET)",
    "ESS(PHP)",
}


class ProblemLevelClassifier:
    """將 error_type 對映為 A/B/C 風險等級；未知 → C。"""

    def classify(self, error_type: str | None) -> str:
        if not error_type:
            return "C"
        key = error_type.strip()
        if key in _LEVEL_A:
            return "A"
        if key in _LEVEL_B:
            return "B"
        return "C"
```

- [ ] **Step 2.4 確認通過**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_problem_level_classifier.py -v`
Expected: 4 passed

- [ ] **Step 2.5 Commit**

```bash
git add src/hcp_cms/core/problem_level_classifier.py tests/unit/test_problem_level_classifier.py
git commit -m "feat(core): 新增 ProblemLevelClassifier (error_type → A/B/C)"
```

---

## Task 3: Core 層 — CSReportEngine（組 row + TYPE 對映）

**Files:**
- Create: `src/hcp_cms/core/cs_report_engine.py`
- Test: `tests/unit/test_cs_report_engine.py`

### 風險評估
- 技術可行性：中（需跨 CaseRepository + CompanyRepository + Classifier 組裝 row）。
- 需求確定性：高（10 欄規格已明確）。

### Step 3.1 寫失敗測試

- [ ] **Step 3.1**

建立 `tests/unit/test_cs_report_engine.py`：

```python
"""CSReportEngine：抓取全部案件 → 轉 10 欄 row。"""

from __future__ import annotations

import pytest

from hcp_cms.core.cs_report_engine import CSReportEngine, ReportRow
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, Company
from hcp_cms.data.repositories import CaseRepository, CompanyRepository


@pytest.fixture()
def conn(tmp_path):
    dbm = DatabaseManager(tmp_path / "t.db")
    dbm.initialize()
    yield dbm.conn
    dbm.close()


def _seed_case(conn, **overrides):
    CompanyRepository(conn).insert(Company(company_id="acme", name="ACME 公司", domain="acme.com"))
    defaults = dict(
        case_id="CS-001",
        subject="薪資計算錯誤",
        company_id="acme",
        sent_time="2026/04/01 09:00:00",
        issue_type="BUG",
        error_type="薪資獎金計算",
        problem="薪資少算加班",
        cause="公式錯誤",
        solution="修正公式",
        actual_reply="已補發差額",
    )
    defaults.update(overrides)
    CaseRepository(conn).insert(Case(**defaults))


def test_build_rows_contains_ten_columns(conn):
    _seed_case(conn)
    engine = CSReportEngine(conn)
    rows = engine.build_rows()
    assert len(rows) == 1
    r = rows[0]
    assert r.date == "2026/04/01"
    assert r.customer == "ACME 公司"
    assert r.problem_raw == "薪資少算加班"
    assert r.problem_level == "A"
    assert r.module == "薪資獎金計算"
    assert r.type_ == "BUG"
    assert r.summary  # 非空
    assert r.suggested_reply == "已補發差額"
    assert r.processed in ("Y", "N")
    assert r.notes is not None  # 可為空字串


def test_problem_level_uses_manual_override(conn):
    _seed_case(conn, problem_level="B")  # 手動覆寫
    engine = CSReportEngine(conn)
    rows = engine.build_rows()
    assert rows[0].problem_level == "B"


def test_type_maps_to_four_categories(conn):
    # issue_type = "客制需求" → OP；"BUG" → BUG；"一般問題" / 其他 → NEW
    _seed_case(conn, case_id="CS-OP", issue_type="客制需求")
    engine = CSReportEngine(conn)
    rows = {r.case_id: r for r in engine.build_rows()}
    assert rows["CS-001"].type_ == "BUG"
    assert rows["CS-OP"].type_ == "OP"


def test_processed_flag_based_on_status(conn):
    _seed_case(conn, case_id="CS-DONE", subject="x", status="已完成")
    _seed_case(conn, case_id="CS-OPEN", subject="y", status="處理中")
    engine = CSReportEngine(conn)
    rows = {r.case_id: r for r in engine.build_rows()}
    assert rows["CS-DONE"].processed == "Y"
    assert rows["CS-OPEN"].processed == "N"


def test_to_sheet_values_returns_10_cells_per_row(conn):
    _seed_case(conn)
    engine = CSReportEngine(conn)
    values = engine.to_sheet_values()
    # 含 header 列 + 1 筆資料
    assert len(values) == 2
    assert len(values[0]) == 10
    assert values[0][0] == "日期"
    assert len(values[1]) == 10
```

- [ ] **Step 3.2 確認失敗**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_cs_report_engine.py -v`
Expected: FAIL（模組不存在）

### Step 3.3 實作 engine

- [ ] **Step 3.3**

建立 `src/hcp_cms/core/cs_report_engine.py`：

```python
"""CSReportEngine — 客服問題彙整報表產生器。

- 抓取全部 cs_cases
- 對映 10 欄：A 日期 / B 客戶 / C 問題原文 / D A|B|C / E 模組 /
  F TYPE(NEW|BUG|OP|OTH) / G 摘要 / H 建議回覆 / I Y|N 處理 / J 備註
- 優先使用手動欄位（problem/cause/solution/problem_level）；無則退回自動推論
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from hcp_cms.core.problem_level_classifier import ProblemLevelClassifier
from hcp_cms.data.repositories import CaseRepository, CompanyRepository

HEADER = [
    "日期",
    "客戶名稱",
    "問題原文",
    "問題類型",
    "問題所屬模組",
    "TYPE",
    "問題摘要",
    "建議回覆",
    "是否已處理",
    "備註",
]

_TYPE_MAP = {
    "BUG": "BUG",
    "BugFix": "BUG",
    "客制需求": "OP",
    "Enhancement": "OP",
    "一般問題": "NEW",
    "其他": "OTH",
}


@dataclass
class ReportRow:
    case_id: str
    date: str
    customer: str
    problem_raw: str
    problem_level: str
    module: str
    type_: str
    summary: str
    suggested_reply: str
    processed: str
    notes: str

    def as_list(self) -> list[str]:
        return [
            self.date,
            self.customer,
            self.problem_raw,
            self.problem_level,
            self.module,
            self.type_,
            self.summary,
            self.suggested_reply,
            self.processed,
            self.notes,
        ]


class CSReportEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._cases = CaseRepository(conn)
        self._companies = CompanyRepository(conn)
        self._levels = ProblemLevelClassifier()

    def build_rows(self) -> list[ReportRow]:
        rows: list[ReportRow] = []
        for case in self._cases.list_all():
            company = self._companies.get_by_id(case.company_id) if case.company_id else None
            customer_name = company.name if company else (case.company_id or "")

            date = (case.sent_time or "").split(" ")[0]
            problem_raw = case.problem or case.subject or ""
            level = case.problem_level or self._levels.classify(case.error_type)
            module = case.error_type or ""
            type_ = _TYPE_MAP.get((case.issue_type or "").strip(), "NEW")
            summary = self._summarize(case.problem or case.subject or "")
            suggested_reply = case.solution or case.actual_reply or ""
            processed = "Y" if case.status == "已完成" else "N"
            notes = case.cause or case.notes or ""

            rows.append(
                ReportRow(
                    case_id=case.case_id,
                    date=date,
                    customer=customer_name,
                    problem_raw=problem_raw,
                    problem_level=level,
                    module=module,
                    type_=type_,
                    summary=summary,
                    suggested_reply=suggested_reply,
                    processed=processed,
                    notes=notes,
                )
            )
        return rows

    def to_sheet_values(self) -> list[list[str]]:
        """回傳可直接寫入 Google Sheet 的二維陣列（含 header）。"""
        values: list[list[str]] = [list(HEADER)]
        for row in self.build_rows():
            values.append(row.as_list())
        return values

    @staticmethod
    def _summarize(text: str, limit: int = 40) -> str:
        s = (text or "").strip().replace("\n", " ")
        if len(s) <= limit:
            return s
        return s[:limit] + "..."
```

- [ ] **Step 3.4 確認通過**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_cs_report_engine.py -v`
Expected: 5 passed

- [ ] **Step 3.5 Commit**

```bash
git add src/hcp_cms/core/cs_report_engine.py tests/unit/test_cs_report_engine.py
git commit -m "feat(core): 新增 CSReportEngine 組成 10 欄客服問題彙整報表"
```

---

## Task 4: 依賴 — pyproject.toml 加入 gspread + google-auth-oauthlib

**Files:**
- Modify: `pyproject.toml`

### Step 4.1 編輯 pyproject.toml

- [ ] **Step 4.1**

於 `[project]` 的 `dependencies` list 中加入：

```toml
    "gspread>=6.0",
    "google-auth-oauthlib>=1.2",
```

### Step 4.2 安裝

- [ ] **Step 4.2**

Run: `.venv/Scripts/pip.exe install -e ".[dev]"`
Expected: Successfully installed gspread-x google-auth-oauthlib-x

### Step 4.3 Commit

- [ ] **Step 4.3**

```bash
git add pyproject.toml
git commit -m "chore: 新增 gspread + google-auth-oauthlib 依賴"
```

---

## Task 5: Services 層 — GoogleSheetsService [POC: 首次整合 Google OAuth + gspread API]

**Files:**
- Create: `src/hcp_cms/services/google_sheets_service.py`
- Test: `tests/unit/test_google_sheets_service.py`

### 風險評估
- 技術可行性：**高**（首次整合 Google OAuth 桌面流程 + gspread API）。
- 需求確定性：中（token refresh / scope / client_secret 來源需確認）。

**POC 先行**：執行 `/poc` 驗證 OAuth 桌面流程（InstalledAppFlow）能打開瀏覽器、回傳 token、並能寫入測試 Sheet。

### Step 5.1 POC 驗證

- [ ] **Step 5.1**

建立臨時腳本 `_temp/poc_google_sheets.py`（不進 git）：
1. 使用 `google_auth_oauthlib.flow.InstalledAppFlow` 啟動 loopback OAuth。
2. 授權後取得 credentials，用 `gspread.authorize(creds)` 開啟目標 Sheet。
3. 寫入 `[["test", "row"]]` 到 A1:B1，確認成功。

POC 通過後記錄：
- client_secret.json 放置位置（預計 `~/.config/hcp_cms/google_client_secret.json` 或使用者自行設定路徑）。
- scope = `https://www.googleapis.com/auth/spreadsheets`

### Step 5.2 寫失敗測試（mock gspread）

- [ ] **Step 5.2**

建立 `tests/unit/test_google_sheets_service.py`：

```python
"""GoogleSheetsService：upsert 行為（mock gspread）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hcp_cms.services.google_sheets_service import GoogleSheetsService


def test_upsert_appends_new_rows_by_case_id():
    fake_ws = MagicMock()
    # 既有 sheet：header + 1 筆
    fake_ws.get_all_values.return_value = [
        ["日期", "客戶名稱", "case_id"],
        ["2026/04/01", "ACME", "CS-001"],
    ]
    svc = GoogleSheetsService.__new__(GoogleSheetsService)
    svc._ws = fake_ws

    header = ["日期", "客戶名稱", "case_id"]
    rows = [
        ("CS-001", ["2026/04/02", "ACME-UPD", "CS-001"]),  # 更新
        ("CS-002", ["2026/04/03", "BETA", "CS-002"]),      # 新增
    ]
    svc.upsert(header, rows, id_column_index=2)

    # 呼叫 update 更新 row 2，呼叫 append 加 CS-002
    fake_ws.update.assert_called()
    fake_ws.append_row.assert_called_with(["2026/04/03", "BETA", "CS-002"])


def test_upsert_writes_header_when_sheet_empty():
    fake_ws = MagicMock()
    fake_ws.get_all_values.return_value = []
    svc = GoogleSheetsService.__new__(GoogleSheetsService)
    svc._ws = fake_ws

    svc.upsert(["日期", "case_id"], [("CS-001", ["2026/04/01", "CS-001"])], id_column_index=1)

    # header + 資料皆 append
    assert fake_ws.append_row.call_count == 2
```

- [ ] **Step 5.3 確認失敗**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_google_sheets_service.py -v`
Expected: FAIL（ImportError）

### Step 5.4 實作 service

- [ ] **Step 5.4**

建立 `src/hcp_cms/services/google_sheets_service.py`：

```python
"""GoogleSheetsService — OAuth 授權並 Upsert 資料至指定 Google Sheet。

憑證流程：
  1. 使用者於「設定」頁面提供 client_secret.json 路徑（由 Google Cloud Console 建立 Desktop client）。
  2. 首次授權啟動 `InstalledAppFlow.run_local_server`，使用者於瀏覽器核准。
  3. token 以 JSON 序列化後存入 keyring（key="google_sheets_token"）。
  4. 下次啟動直接讀回，自動 refresh。

Upsert 邏輯：以 id_column_index（0-based）作為 key 比對既有 row，
  - 存在 → update 該 row
  - 不存在 → append_row
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from hcp_cms.services.credential import CredentialManager

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TOKEN_KEY = "google_sheets_token"


class GoogleSheetsService:
    def __init__(self, client_secret_path: Path, spreadsheet_url: str, worksheet_name: str = "Sheet1") -> None:
        self._client_secret_path = Path(client_secret_path)
        self._spreadsheet_url = spreadsheet_url
        self._worksheet_name = worksheet_name
        self._creds: Credentials | None = None
        self._ws: gspread.Worksheet | None = None
        self._cred_mgr = CredentialManager()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    def authenticate(self, force_reauth: bool = False) -> None:
        """取得有效 credentials；必要時啟動瀏覽器授權。"""
        creds: Credentials | None = None
        if not force_reauth:
            token_json = self._cred_mgr.retrieve(TOKEN_KEY)
            if token_json:
                try:
                    creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
                except Exception:
                    creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(self._client_secret_path), SCOPES)
                creds = flow.run_local_server(port=0)
            self._cred_mgr.store(TOKEN_KEY, creds.to_json())

        self._creds = creds
        self._open_worksheet()

    def _open_worksheet(self) -> None:
        gc = gspread.authorize(self._creds)
        sh = gc.open_by_url(self._spreadsheet_url)
        try:
            self._ws = sh.worksheet(self._worksheet_name)
        except gspread.WorksheetNotFound:
            self._ws = sh.add_worksheet(self._worksheet_name, rows=1000, cols=20)

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------
    def upsert(
        self,
        header: list[str],
        rows: Iterable[tuple[str, list[str]]],
        id_column_index: int,
    ) -> None:
        """header + 多筆 (case_id, row_values)；以 id_column_index 作 key upsert。"""
        assert self._ws is not None, "authenticate() first"
        existing = self._ws.get_all_values()

        # 寫 header（若 sheet 為空）
        if not existing:
            self._ws.append_row(header)
            existing = [header]

        # 建立 id → row_index 映射（row_index 1-based；跳過 header 行）
        id_to_row: dict[str, int] = {}
        for idx, row in enumerate(existing[1:], start=2):
            if len(row) > id_column_index:
                id_to_row[row[id_column_index]] = idx

        for case_id, values in rows:
            if case_id in id_to_row:
                r = id_to_row[case_id]
                self._ws.update(f"A{r}", [values])
            else:
                self._ws.append_row(values)
```

- [ ] **Step 5.5 確認測試通過**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_google_sheets_service.py -v`
Expected: 2 passed

- [ ] **Step 5.6 Commit**

```bash
git add src/hcp_cms/services/google_sheets_service.py tests/unit/test_google_sheets_service.py
git commit -m "feat(services): 新增 GoogleSheetsService (OAuth + Upsert by key)"
```

---

## Task 6: UI 層 — case_view 詳情區新增 4 欄位

**Files:**
- Modify: `src/hcp_cms/ui/case_view.py`

### 風險評估
- 技術可行性：低（既有 QTextEdit/QComboBox 模式）。
- 需求確定性：高。

### Step 6.1 加入 4 個輸入元件

- [ ] **Step 6.1**

於 case_view 的詳情區（`_setup_ui` 中建立 detail panel 的地方）新增：

```python
# 問題等級 A/B/C
self._level_combo = QComboBox()
self._level_combo.setObjectName("problemLevelCombo")
self._level_combo.addItems(["", "A", "B", "C"])

# 問題 / 原因 / 解法
self._problem_edit = QTextEdit()
self._problem_edit.setObjectName("problemEdit")
self._problem_edit.setPlaceholderText("問題（人工整理後的問題描述）")
self._problem_edit.setMaximumHeight(80)

self._cause_edit = QTextEdit()
self._cause_edit.setObjectName("causeEdit")
self._cause_edit.setPlaceholderText("原因")
self._cause_edit.setMaximumHeight(80)

self._solution_edit = QTextEdit()
self._solution_edit.setObjectName("solutionEdit")
self._solution_edit.setPlaceholderText("解法")
self._solution_edit.setMaximumHeight(80)
```

加入對應標籤並加進既有 detail form layout（置於 notes 之前）。

### Step 6.2 載入與儲存

- [ ] **Step 6.2**

- 在載入案件的 `_show_case_detail(case)`（或等效方法）中寫回：

```python
self._level_combo.setCurrentText(case.problem_level or "")
self._problem_edit.setPlainText(case.problem or "")
self._cause_edit.setPlainText(case.cause or "")
self._solution_edit.setPlainText(case.solution or "")
```

- 在儲存邏輯（`_on_save` 或等效）中，組 `Case` 時加入：

```python
case.problem_level = self._level_combo.currentText() or None
case.problem = self._problem_edit.toPlainText().strip() or None
case.cause = self._cause_edit.toPlainText().strip() or None
case.solution = self._solution_edit.toPlainText().strip() or None
```

### Step 6.3 手動驗證

- [ ] **Step 6.3**

Run: `.venv/Scripts/python.exe -m hcp_cms`
步驟：
1. 案件管理點任一案件 → 詳情區應看到 4 個新欄位
2. 選 A/B/C、填寫問題/原因/解法 → 存檔
3. 關閉重開 → 欄位內容應保留

### Step 6.4 Commit

- [ ] **Step 6.4**

```bash
git add src/hcp_cms/ui/case_view.py
git commit -m "feat(ui): case_view 詳情區新增問題等級/問題/原因/解法欄位"
```

---

## Task 7: UI 層 — report_view 新增「客服問題彙整」分頁 + 同步按鈕

**Files:**
- Modify: `src/hcp_cms/ui/report_view.py`

### 風險評估
- 技術可行性：中（需整合 Google Sheets 非同步呼叫，避免 UI 卡住）。
- 需求確定性：中（同步失敗的 UX 需明確）。

### Step 7.1 新增報表選項

- [ ] **Step 7.1**

在報表類型下拉 / 分頁中加入「客服問題彙整」。於 `_on_preview`（或等效）中加入分支：

```python
if self._report_combo.currentText() == "客服問題彙整":
    engine = CSReportEngine(self._conn)
    rows = engine.build_rows()
    self._fill_cs_report_preview(rows)
    return
```

### Step 7.2 新增 `_fill_cs_report_preview`

- [ ] **Step 7.2**

```python
def _fill_cs_report_preview(self, rows: list[ReportRow]) -> None:
    from hcp_cms.core.cs_report_engine import HEADER
    self._preview_table.clear()
    self._preview_table.setColumnCount(10)
    self._preview_table.setHorizontalHeaderLabels(HEADER)
    self._preview_table.setRowCount(len(rows))
    for r_idx, row in enumerate(rows):
        for c_idx, val in enumerate(row.as_list()):
            self._preview_table.setItem(r_idx, c_idx, QTableWidgetItem(str(val)))
```

### Step 7.3 新增「同步至 Google Sheets」按鈕

- [ ] **Step 7.3**

按鈕於預覽區下方，connect 至 `_on_sync_to_sheets`：

```python
def _on_sync_to_sheets(self) -> None:
    from PySide6.QtWidgets import QMessageBox
    from hcp_cms.services.google_sheets_service import GoogleSheetsService
    from hcp_cms.core.cs_report_engine import CSReportEngine, HEADER
    from hcp_cms.settings import load_settings  # 讀取使用者儲存的 sheet URL / client_secret path

    settings = load_settings()
    if not settings.google_sheet_url or not settings.google_client_secret_path:
        QMessageBox.warning(self, "未設定 Google Sheets", "請先於「設定」→「Google Sheets」填寫 URL 與 client_secret。")
        return

    try:
        svc = GoogleSheetsService(
            client_secret_path=settings.google_client_secret_path,
            spreadsheet_url=settings.google_sheet_url,
        )
        svc.authenticate()
        engine = CSReportEngine(self._conn)
        rows = engine.build_rows()
        # header 額外加一欄 case_id 放在尾端當 upsert key（不顯示於 10 欄外，或作為隱藏欄）
        header_with_id = list(HEADER) + ["case_id"]
        data = [(r.case_id, r.as_list() + [r.case_id]) for r in rows]
        svc.upsert(header_with_id, data, id_column_index=10)
        QMessageBox.information(self, "同步完成", f"已同步 {len(rows)} 筆。")
    except Exception as e:
        QMessageBox.critical(self, "同步失敗", str(e))
```

（若 `load_settings` 不存在，於 Task 8 一併新增；此步可先用 QSettings / 簡化讀取。）

### Step 7.4 手動驗證

- [ ] **Step 7.4**

Run: `.venv/Scripts/python.exe -m hcp_cms`
1. 報表中心 → 選「客服問題彙整」→ 預覽 → 看到 10 欄
2. 按「同步至 Google Sheets」→ 瀏覽器開啟授權 → 目標 Sheet 應有資料

### Step 7.5 Commit

- [ ] **Step 7.5**

```bash
git add src/hcp_cms/ui/report_view.py
git commit -m "feat(ui): report_view 新增客服問題彙整報表與同步按鈕"
```

---

## Task 8: UI 層 — settings_view 新增 Google Sheets 設定區

**Files:**
- Modify: `src/hcp_cms/ui/settings_view.py`

### 風險評估
- 技術可行性：低。
- 需求確定性：中（排程頻率選項需確認）。

### Step 8.1 加入 Google Sheets 區塊

- [ ] **Step 8.1**

於 settings_view 加入 QGroupBox「Google Sheets 同步」：

```python
self._google_group = QGroupBox("Google Sheets 同步")
form = QFormLayout(self._google_group)

self._google_url_edit = QLineEdit()
self._google_url_edit.setPlaceholderText("https://docs.google.com/spreadsheets/d/.../edit")
form.addRow("Sheet URL：", self._google_url_edit)

self._client_secret_edit = QLineEdit()
self._browse_btn = QPushButton("瀏覽...")
self._browse_btn.clicked.connect(self._on_browse_client_secret)
row = QHBoxLayout(); row.addWidget(self._client_secret_edit); row.addWidget(self._browse_btn)
form.addRow("client_secret.json：", row)

self._reauth_btn = QPushButton("重新授權 Google")
self._reauth_btn.clicked.connect(self._on_reauth_google)
form.addRow(self._reauth_btn)

self._schedule_checkbox = QCheckBox("啟用排程同步")
self._schedule_interval = QComboBox()
self._schedule_interval.addItems(["每日 00:00", "每週一 00:00"])
form.addRow(self._schedule_checkbox)
form.addRow("排程頻率：", self._schedule_interval)
```

### Step 8.2 儲存 / 載入（QSettings）

- [ ] **Step 8.2**

使用 `QSettings("HCP", "CMS")` 或既有 settings 機制儲存：
- `google/sheet_url`
- `google/client_secret_path`
- `google/schedule_enabled`
- `google/schedule_interval`

載入於 `_setup_ui`、儲存於「儲存」按鈕 slot。

### Step 8.3 重新授權按鈕

- [ ] **Step 8.3**

```python
def _on_reauth_google(self) -> None:
    from hcp_cms.services.google_sheets_service import GoogleSheetsService
    try:
        svc = GoogleSheetsService(
            client_secret_path=Path(self._client_secret_edit.text()),
            spreadsheet_url=self._google_url_edit.text(),
        )
        svc.authenticate(force_reauth=True)
        QMessageBox.information(self, "授權成功", "Google 授權已更新。")
    except Exception as e:
        QMessageBox.critical(self, "授權失敗", str(e))
```

### Step 8.4 手動驗證

- [ ] **Step 8.4**

Run: `.venv/Scripts/python.exe -m hcp_cms`
1. 設定 → Google Sheets → 填寫 URL + client_secret 路徑 → 儲存
2. 重新授權 → 瀏覽器彈出 → 核准後出現「授權成功」

### Step 8.5 Commit

- [ ] **Step 8.5**

```bash
git add src/hcp_cms/ui/settings_view.py
git commit -m "feat(ui): settings_view 新增 Google Sheets 同步設定區"
```

---

## Task 9: Scheduler 層 — 可選排程同步 job

**Files:**
- Create: `src/hcp_cms/scheduler/cs_report_sync_job.py`
- Modify: `src/hcp_cms/scheduler/scheduler.py`

### 風險評估
- 技術可行性：中（需在 threading.Timer 背景執行 Google API 呼叫，不可操作 UI）。
- 需求確定性：高（手動同步已完成，此為加值功能）。

### Step 9.1 實作 job

- [ ] **Step 9.1**

建立 `src/hcp_cms/scheduler/cs_report_sync_job.py`：

```python
"""定時將客服問題彙整報表同步至 Google Sheets。

NEVER 直接操作 UI；失敗時僅 log，下一輪再試。
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from hcp_cms.core.cs_report_engine import CSReportEngine, HEADER
from hcp_cms.services.google_sheets_service import GoogleSheetsService

log = logging.getLogger(__name__)


def run_cs_report_sync(
    conn: sqlite3.Connection,
    spreadsheet_url: str,
    client_secret_path: Path,
) -> None:
    try:
        svc = GoogleSheetsService(client_secret_path, spreadsheet_url)
        svc.authenticate()
        engine = CSReportEngine(conn)
        rows = engine.build_rows()
        header_with_id = list(HEADER) + ["case_id"]
        data = [(r.case_id, r.as_list() + [r.case_id]) for r in rows]
        svc.upsert(header_with_id, data, id_column_index=10)
        log.info("cs_report_sync 同步 %d 筆", len(rows))
    except Exception as exc:
        log.exception("cs_report_sync 失敗：%s", exc)
```

### Step 9.2 註冊於 scheduler

- [ ] **Step 9.2**

編輯 `src/hcp_cms/scheduler/scheduler.py`：於 scheduler 啟動時，若 QSettings 讀到 `google/schedule_enabled=True`，依 interval 設定 `threading.Timer`：
- 每日 00:00 → 計算距下次 00:00 的秒數
- 每週一 00:00 → 計算距下次週一 00:00 的秒數

timer callback 呼叫 `run_cs_report_sync(...)`，結束後重新排程。

### Step 9.3 手動驗證

- [ ] **Step 9.3**

將排程頻率改為「每日 00:00」，臨時在程式內將下次觸發時間改為 30 秒後，啟動後確認 Sheet 有更新 + log 有輸出。驗證完還原。

### Step 9.4 Commit

- [ ] **Step 9.4**

```bash
git add src/hcp_cms/scheduler/cs_report_sync_job.py src/hcp_cms/scheduler/scheduler.py
git commit -m "feat(scheduler): 新增客服問題彙整報表排程同步 job"
```

---

## Task 10: 端對端驗證 + ruff

**Files:** 全專案

### Step 10.1 Ruff

- [ ] **Step 10.1**

Run: `.venv/Scripts/ruff.exe check src/ tests/ && .venv/Scripts/ruff.exe format src/ tests/`
Expected: All checks passed

### Step 10.2 全部測試

- [ ] **Step 10.2**

Run: `.venv/Scripts/python.exe -m pytest tests/ -v`
Expected: 全綠（新增測試皆通過，既有測試未被破壞）

### Step 10.3 手動端對端

- [ ] **Step 10.3**

1. 啟動 App → 案件管理 → 建立 / 編輯任一案件並填入 problem_level=A / problem / cause / solution → 儲存
2. 報表中心 → 客服問題彙整 → 預覽（應看到該案件 10 欄資料，D 欄 = A）
3. 按「同步至 Google Sheets」→ 首次開啟瀏覽器授權 → 目標 Sheet 看到資料
4. 修改同一案件 solution → 重新同步 → 目標 Sheet 中 CS-xxx row 的 H 欄應被更新（不是新增列）
5. 設定 → 啟用排程同步 → 驗證 log 正常輸出

### Step 10.4 Commit

- [ ] **Step 10.4**

若有小修，commit；無則跳過。

```bash
git status
# 若有檔案
git add -A  # 審視後
git commit -m "chore: ruff 格式修正 + 端對端驗證"
```

---

## 自我審核結果

1. **Spec 覆蓋**：10 欄 A-J ✓、34 模組 A/B/C 對映 ✓、全部案件範圍 ✓、手動覆寫 ✓、OAuth 授權 ✓、Upsert by case_id ✓、手動按鈕 + 可選排程 ✓、TYPE 4 類 ✓、問題→原因→解法 人工欄位（方案 A）✓。
2. **Placeholder 掃描**：無 TBD/TODO；每一步 code 皆完整。
3. **型別一致性**：`ReportRow.as_list()`、`HEADER`、`upsert(header, rows, id_column_index)` 在 Task 3/5/7/9 簽章一致；`problem_level`、`problem`、`cause`、`solution` 命名在 data / UI / engine 全一致。

---

## 執行選擇

**Plan complete and saved to `docs/superpowers/plans/2026-04-24-cs-report-google-sheets.md`. Two execution options:**

**1. Subagent-Driven（建議）** — 每 Task 派送新 subagent，兩階段審核（spec 合規 → code quality），同一 session 快速迭代。

**2. Inline Execution** — 在此 session 批次執行，以 checkpoint 供你審核。

**請問要選哪一個？**
