# Patch 整理系統 — 計畫 A：Data + Core + Services

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 實作 Patch 整理系統的 Data、Core、Services 三層，不含 UI，所有功能可透過單元測試驗證。

**Architecture:** 遵循現有 6 層架構，新增 PatchRepository（Data 層）、SinglePatchEngine + MonthlyPatchEngine（Core 層）、ClaudeContentService + PlaywrightMantisService（Services 層）。各 Engine 接收 `sqlite3.Connection`，透過 PatchRepository 操作資料。

**Tech Stack:** Python 3.14 · openpyxl · python-docx · win32com（.doc 讀取）· opencc-python-reimplemented · jinja2 · anthropic SDK · playwright

---

## 檔案結構

**新增：**
- `src/hcp_cms/core/patch_engine.py` — `SinglePatchEngine`
- `src/hcp_cms/core/monthly_patch_engine.py` — `MonthlyPatchEngine`
- `src/hcp_cms/services/claude_content.py` — `ClaudeContentService`
- `src/hcp_cms/services/mantis/playwright_service.py` — `PlaywrightMantisService`
- `templates/patch_notify.html.j2` — 客戶通知信 Jinja2 範本
- `tests/unit/test_patch_repository.py`
- `tests/unit/test_patch_engine.py`
- `tests/unit/test_monthly_patch_engine.py`
- `tests/unit/test_claude_content.py`

**修改：**
- `pyproject.toml` — 新增依賴
- `src/hcp_cms/data/models.py` — 追加 `PatchRecord`、`PatchIssue`
- `src/hcp_cms/data/repositories.py` — 追加 `PatchRepository`
- `src/hcp_cms/data/database.py` — 追加 schema + migration

---

### Task 1：新增依賴套件

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1：新增 dependencies**

在 `pyproject.toml` 的 `dependencies` 陣列末尾追加：

```toml
dependencies = [
    "PySide6>=6.6",
    "PySide6-Addons>=6.6",
    "exchangelib>=5.1",
    "extract-msg>=0.48",
    "jieba>=0.42",
    "keyring>=25.0",
    "markdown>=3.5",
    "openpyxl>=3.1",
    "python-docx>=1.1",
    "requests>=2.31",
    "anthropic>=0.25",
    "jinja2>=3.1",
    "opencc-python-reimplemented>=0.1.7",
    "playwright>=1.43",
    "pywin32>=306",
]
```

- [ ] **Step 2：安裝套件**

```bash
.venv/Scripts/pip.exe install anthropic jinja2 opencc-python-reimplemented playwright pywin32
.venv/Scripts/python.exe -m playwright install chromium
```

Expected: 安裝成功，無 error。

- [ ] **Step 3：確認可 import**

```bash
.venv/Scripts/python.exe -c "import anthropic; import jinja2; import opencc; from playwright.sync_api import sync_playwright; print('OK')"
```

Expected: 印出 `OK`。

- [ ] **Step 4：Commit**

```bash
git add pyproject.toml
git commit -m "chore: 新增 patch 整理系統依賴套件"
```

---

### Task 2：Data Models

**Files:**
- Modify: `src/hcp_cms/data/models.py`

- [ ] **Step 1：在 models.py 末尾追加兩個 dataclass**

```python
@dataclass
class PatchRecord:
    """Patch 整理記錄 — cs_patches table."""
    type: str = "single"          # "single" | "monthly"
    month_str: str | None = None  # "202604"，monthly 專用
    patch_dir: str | None = None
    status: str = "in_progress"   # "in_progress" | "completed"
    patch_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class PatchIssue:
    """Patch Issue 項目 — cs_patch_issues table."""
    patch_id: int | None = None
    issue_no: str = ""
    program_code: str | None = None
    program_name: str | None = None
    issue_type: str = "BugFix"    # "BugFix" | "Enhancement"
    region: str = "共用"           # "TW" | "CN" | "共用"
    description: str | None = None
    impact: str | None = None
    test_direction: str | None = None
    mantis_detail: str | None = None  # JSON 字串
    source: str = "manual"            # "manual" | "mantis"
    sort_order: int = 0
    issue_id: int | None = None
    created_at: str | None = None
```

- [ ] **Step 2：確認 import 正常**

```bash
.venv/Scripts/python.exe -c "from hcp_cms.data.models import PatchRecord, PatchIssue; print(PatchRecord(), PatchIssue())"
```

Expected: 印出兩個 dataclass 預設值，無錯誤。

- [ ] **Step 3：Commit**

```bash
git add src/hcp_cms/data/models.py
git commit -m "feat(data): 新增 PatchRecord、PatchIssue dataclass"
```

---

### Task 3：DB Schema

**Files:**
- Modify: `src/hcp_cms/data/database.py`

- [ ] **Step 1：在 `_SCHEMA_SQL` 字串末尾（`"""` 前）追加兩張表**

在 `database.py` 的 `_SCHEMA_SQL` 變數中，`cases_fts` 建表之後追加：

```sql
CREATE TABLE IF NOT EXISTS cs_patches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    type       TEXT NOT NULL DEFAULT 'single',
    month_str  TEXT,
    patch_dir  TEXT,
    status     TEXT NOT NULL DEFAULT 'in_progress',
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS cs_patch_issues (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    patch_id       INTEGER NOT NULL REFERENCES cs_patches(id),
    issue_no       TEXT NOT NULL,
    program_code   TEXT,
    program_name   TEXT,
    issue_type     TEXT DEFAULT 'BugFix',
    region         TEXT DEFAULT '共用',
    description    TEXT,
    impact         TEXT,
    test_direction TEXT,
    mantis_detail  TEXT,
    source         TEXT DEFAULT 'manual',
    sort_order     INTEGER DEFAULT 0,
    created_at     TEXT
);
```

- [ ] **Step 2：確認 schema 建立成功**

```bash
.venv/Scripts/python.exe -c "
from pathlib import Path
from hcp_cms.data.database import DatabaseManager
db = DatabaseManager(':memory:')
db.initialize()
conn = db.connection
tables = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
names = [r[0] for r in tables]
assert 'cs_patches' in names, f'cs_patches missing, got {names}'
assert 'cs_patch_issues' in names, f'cs_patch_issues missing, got {names}'
print('Schema OK')
"
```

Expected: 印出 `Schema OK`。

- [ ] **Step 3：Commit**

```bash
git add src/hcp_cms/data/database.py
git commit -m "feat(data): 新增 cs_patches 與 cs_patch_issues 資料表"
```

---

### Task 4：PatchRepository

**Files:**
- Modify: `src/hcp_cms/data/repositories.py`
- Create: `tests/unit/test_patch_repository.py`

- [ ] **Step 1：撰寫失敗測試**

建立 `tests/unit/test_patch_repository.py`：

```python
"""PatchRepository 單元測試。"""
import sqlite3
import pytest
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import PatchIssue, PatchRecord
from hcp_cms.data.repositories import PatchRepository


@pytest.fixture
def conn():
    db = DatabaseManager(":memory:")
    db.initialize()
    yield db.connection
    db.connection.close()


class TestPatchRepository:
    def test_insert_and_get_patch(self, conn):
        repo = PatchRepository(conn)
        patch = PatchRecord(type="single", patch_dir="C:/test")
        patch_id = repo.insert_patch(patch)
        result = repo.get_patch_by_id(patch_id)
        assert result is not None
        assert result.type == "single"
        assert result.patch_dir == "C:/test"
        assert result.status == "in_progress"

    def test_update_patch_status(self, conn):
        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="monthly", month_str="202604"))
        repo.update_patch_status(pid, "completed")
        assert repo.get_patch_by_id(pid).status == "completed"

    def test_insert_and_list_issues(self, conn):
        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="single"))
        issue = PatchIssue(patch_id=pid, issue_no="0015659", issue_type="BugFix", region="TW",
                           description="測試說明", sort_order=1)
        repo.insert_issue(issue)
        issues = repo.list_issues_by_patch(pid)
        assert len(issues) == 1
        assert issues[0].issue_no == "0015659"
        assert issues[0].region == "TW"

    def test_update_issue(self, conn):
        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="single"))
        iid = repo.insert_issue(PatchIssue(patch_id=pid, issue_no="0015659"))
        issue = repo.list_issues_by_patch(pid)[0]
        issue.description = "已修改說明"
        repo.update_issue(issue)
        updated = repo.list_issues_by_patch(pid)[0]
        assert updated.description == "已修改說明"

    def test_delete_issue(self, conn):
        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="single"))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="0015659"))
        issues = repo.list_issues_by_patch(pid)
        repo.delete_issue(issues[0].issue_id)
        assert repo.list_issues_by_patch(pid) == []

    def test_list_issues_sorted_by_sort_order(self, conn):
        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="monthly"))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="BBB", sort_order=2))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="AAA", sort_order=1))
        issues = repo.list_issues_by_patch(pid)
        assert issues[0].issue_no == "AAA"
        assert issues[1].issue_no == "BBB"
```

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_repository.py -v
```

Expected: `ImportError` 或 `AttributeError`（PatchRepository 尚未實作）。

- [ ] **Step 3：在 repositories.py 末尾追加 PatchRepository**

```python
# ---------------------------------------------------------------------------
# PatchRepository
# ---------------------------------------------------------------------------


class PatchRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert_patch(self, patch: "PatchRecord") -> int:
        from hcp_cms.data.models import PatchRecord  # noqa: F401
        patch.created_at = _now()
        patch.updated_at = _now()
        cur = self._conn.execute(
            """INSERT INTO cs_patches (type, month_str, patch_dir, status, created_at, updated_at)
               VALUES (:type, :month_str, :patch_dir, :status, :created_at, :updated_at)""",
            {"type": patch.type, "month_str": patch.month_str, "patch_dir": patch.patch_dir,
             "status": patch.status, "created_at": patch.created_at, "updated_at": patch.updated_at},
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_patch_by_id(self, patch_id: int) -> "PatchRecord | None":
        from hcp_cms.data.models import PatchRecord
        row = self._conn.execute("SELECT * FROM cs_patches WHERE id=?", (patch_id,)).fetchone()
        if row is None:
            return None
        return PatchRecord(patch_id=row["id"], type=row["type"], month_str=row["month_str"],
                           patch_dir=row["patch_dir"], status=row["status"],
                           created_at=row["created_at"], updated_at=row["updated_at"])

    def list_patches(self) -> "list[PatchRecord]":
        from hcp_cms.data.models import PatchRecord
        rows = self._conn.execute("SELECT * FROM cs_patches ORDER BY created_at DESC").fetchall()
        return [PatchRecord(patch_id=r["id"], type=r["type"], month_str=r["month_str"],
                            patch_dir=r["patch_dir"], status=r["status"],
                            created_at=r["created_at"], updated_at=r["updated_at"]) for r in rows]

    def update_patch_status(self, patch_id: int, status: str) -> None:
        self._conn.execute("UPDATE cs_patches SET status=?, updated_at=? WHERE id=?",
                           (status, _now(), patch_id))
        self._conn.commit()

    def insert_issue(self, issue: "PatchIssue") -> int:
        from hcp_cms.data.models import PatchIssue  # noqa: F401
        issue.created_at = _now()
        cur = self._conn.execute(
            """INSERT INTO cs_patch_issues
               (patch_id, issue_no, program_code, program_name, issue_type, region,
                description, impact, test_direction, mantis_detail, source, sort_order, created_at)
               VALUES
               (:patch_id, :issue_no, :program_code, :program_name, :issue_type, :region,
                :description, :impact, :test_direction, :mantis_detail, :source, :sort_order, :created_at)""",
            {"patch_id": issue.patch_id, "issue_no": issue.issue_no, "program_code": issue.program_code,
             "program_name": issue.program_name, "issue_type": issue.issue_type, "region": issue.region,
             "description": issue.description, "impact": issue.impact,
             "test_direction": issue.test_direction, "mantis_detail": issue.mantis_detail,
             "source": issue.source, "sort_order": issue.sort_order, "created_at": issue.created_at},
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def list_issues_by_patch(self, patch_id: int) -> "list[PatchIssue]":
        rows = self._conn.execute(
            "SELECT * FROM cs_patch_issues WHERE patch_id=? ORDER BY sort_order, id",
            (patch_id,),
        ).fetchall()
        return [self._row_to_issue(r) for r in rows]

    def update_issue(self, issue: "PatchIssue") -> None:
        self._conn.execute(
            """UPDATE cs_patch_issues SET
               issue_no=:issue_no, program_code=:program_code, program_name=:program_name,
               issue_type=:issue_type, region=:region, description=:description,
               impact=:impact, test_direction=:test_direction, mantis_detail=:mantis_detail,
               source=:source, sort_order=:sort_order
               WHERE id=:issue_id""",
            {"issue_id": issue.issue_id, "issue_no": issue.issue_no,
             "program_code": issue.program_code, "program_name": issue.program_name,
             "issue_type": issue.issue_type, "region": issue.region,
             "description": issue.description, "impact": issue.impact,
             "test_direction": issue.test_direction, "mantis_detail": issue.mantis_detail,
             "source": issue.source, "sort_order": issue.sort_order},
        )
        self._conn.commit()

    def delete_issue(self, issue_id: int) -> None:
        self._conn.execute("DELETE FROM cs_patch_issues WHERE id=?", (issue_id,))
        self._conn.commit()

    def _row_to_issue(self, row: sqlite3.Row) -> "PatchIssue":
        from hcp_cms.data.models import PatchIssue
        return PatchIssue(
            issue_id=row["id"], patch_id=row["patch_id"], issue_no=row["issue_no"],
            program_code=row["program_code"], program_name=row["program_name"],
            issue_type=row["issue_type"], region=row["region"],
            description=row["description"], impact=row["impact"],
            test_direction=row["test_direction"], mantis_detail=row["mantis_detail"],
            source=row["source"], sort_order=row["sort_order"], created_at=row["created_at"],
        )
```

- [ ] **Step 4：執行測試確認全過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_repository.py -v
```

Expected: 6 個 PASS。

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/data/repositories.py tests/unit/test_patch_repository.py
git commit -m "feat(data): 新增 PatchRepository，支援 Patch 與 Issue CRUD"
```

---

### Task 5：SinglePatchEngine — scan_patch_dir

**Files:**
- Create: `src/hcp_cms/core/patch_engine.py`
- Create: `tests/unit/test_patch_engine.py`

- [ ] **Step 1：撰寫失敗測試**

建立 `tests/unit/test_patch_engine.py`：

```python
"""SinglePatchEngine 單元測試。"""
import sqlite3
from pathlib import Path
import pytest
from hcp_cms.data.database import DatabaseManager
from hcp_cms.core.patch_engine import SinglePatchEngine


@pytest.fixture
def conn():
    db = DatabaseManager(":memory:")
    db.initialize()
    yield db.connection
    db.connection.close()


@pytest.fixture
def patch_dir(tmp_path: Path) -> Path:
    (tmp_path / "form").mkdir()
    (tmp_path / "sql").mkdir()
    (tmp_path / "muti").mkdir()
    (tmp_path / "form" / "PAYROLL.fmx").write_text("form")
    (tmp_path / "sql" / "update.sql").write_text("sql")
    (tmp_path / "setup.bat").write_text("bat")
    (tmp_path / "ReleaseNote.docx").write_bytes(b"")
    return tmp_path


class TestScanPatchDir:
    def test_finds_form_sql_muti_files(self, conn, patch_dir):
        eng = SinglePatchEngine(conn)
        result = eng.scan_patch_dir(str(patch_dir))
        assert "PAYROLL.fmx" in result["form_files"]
        assert "update.sql" in result["sql_files"]
        assert result["setup_bat"] is True
        assert result["missing"] == []

    def test_missing_muti_not_error(self, conn, patch_dir):
        import shutil
        shutil.rmtree(patch_dir / "muti")
        eng = SinglePatchEngine(conn)
        result = eng.scan_patch_dir(str(patch_dir))
        assert result["muti_files"] == []
        assert "muti/" not in result["missing"]  # muti 是選用，不算缺少

    def test_missing_form_reported(self, conn, patch_dir):
        import shutil
        shutil.rmtree(patch_dir / "form")
        eng = SinglePatchEngine(conn)
        result = eng.scan_patch_dir(str(patch_dir))
        assert "form/" in result["missing"]

    def test_detects_release_note(self, conn, patch_dir):
        eng = SinglePatchEngine(conn)
        result = eng.scan_patch_dir(str(patch_dir))
        assert result["release_note"] is not None
        assert "ReleaseNote" in result["release_note"]
```

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestScanPatchDir -v
```

Expected: `ModuleNotFoundError: No module named 'hcp_cms.core.patch_engine'`。

- [ ] **Step 3：建立 patch_engine.py**

建立 `src/hcp_cms/core/patch_engine.py`：

```python
"""SinglePatchEngine — 單次 Patch 整理流程。"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from hcp_cms.data.models import PatchIssue, PatchRecord
from hcp_cms.data.repositories import PatchRepository


class SinglePatchEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._repo = PatchRepository(conn)

    # ── 掃描資料夾 ──────────────────────────────────────────────────────────

    def scan_patch_dir(self, patch_dir: str) -> dict:
        """掃描解壓縮資料夾，回傳結構摘要。"""
        path = Path(patch_dir)
        result: dict = {
            "form_files": [],
            "sql_files": [],
            "muti_files": [],
            "setup_bat": False,
            "release_note": None,
            "install_guide": None,
            "missing": [],
        }

        for sub, key, required in [("form", "form_files", True),
                                    ("sql", "sql_files", True),
                                    ("muti", "muti_files", False)]:
            sub_path = path / sub
            if sub_path.exists():
                result[key] = [f.name for f in sub_path.iterdir() if f.is_file()]
            elif required:
                result["missing"].append(f"{sub}/")

        result["setup_bat"] = (path / "setup.bat").exists()

        for f in path.iterdir():
            name_lower = f.name.lower()
            if "releasenote" in name_lower or "release_note" in name_lower:
                result["release_note"] = str(f)
            elif "installation" in name_lower or "installguide" in name_lower or "install_guide" in name_lower:
                result["install_guide"] = str(f)

        return result
```

- [ ] **Step 4：執行測試確認全過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestScanPatchDir -v
```

Expected: 4 個 PASS。

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/core/patch_engine.py tests/unit/test_patch_engine.py
git commit -m "feat(core): SinglePatchEngine.scan_patch_dir 掃描 patch 資料夾"
```

---

### Task 6：SinglePatchEngine — read_release_doc [POC: win32com .doc 讀取]

> ⚠️ **[POC: win32com 需要目標機器安裝 Microsoft Word；.doc 解析結果依賴文件格式，需以實際 ReleaseNote 驗證]**
> 實作前請先執行 `/poc` 確認 win32com 在此環境可正常取得 Word 文字。

**Files:**
- Modify: `src/hcp_cms/core/patch_engine.py`
- Modify: `tests/unit/test_patch_engine.py`

- [ ] **Step 1：追加測試（使用 docx 格式）**

在 `tests/unit/test_patch_engine.py` 的 `TestScanPatchDir` 類別之後追加：

```python
class TestReadReleaseDoc:
    def test_parse_docx_returns_issues(self, conn, tmp_path):
        import docx
        doc = docx.Document()
        doc.add_paragraph("Bug Fix")
        doc.add_paragraph("0015659  薪資計算錯誤修正")
        doc.add_paragraph("0015660  加班費計算異常")
        doc.add_paragraph("Enhancement")
        doc.add_paragraph("0015661  新增匯出功能")
        p = tmp_path / "ReleaseNote.docx"
        doc.save(str(p))

        eng = SinglePatchEngine(conn)
        issues = eng.read_release_doc(str(p))
        assert len(issues) == 3
        assert issues[0]["issue_no"] == "0015659"
        assert issues[0]["issue_type"] == "BugFix"
        assert issues[2]["issue_type"] == "Enhancement"

    def test_missing_file_returns_empty(self, conn, tmp_path):
        eng = SinglePatchEngine(conn)
        result = eng.read_release_doc(str(tmp_path / "nonexist.docx"))
        assert result == []
```

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestReadReleaseDoc -v
```

Expected: `AttributeError`（`read_release_doc` 尚未實作）。

- [ ] **Step 3：在 patch_engine.py 追加 read_release_doc 及輔助方法**

在 `SinglePatchEngine` 類別中，`scan_patch_dir` 方法之後追加：

```python
    # ── 讀取 ReleaseNote ─────────────────────────────────────────────────────

    def read_release_doc(self, doc_path: str) -> list[dict]:
        """解析 ReleaseNote.doc/.docx，回傳 Issue 清單。"""
        path = Path(doc_path)
        if not path.exists():
            return []
        text = self._extract_doc_text(path)
        if text is None:
            return []
        return self._parse_release_note_text(text)

    def _extract_doc_text(self, path: Path) -> str | None:
        if path.suffix.lower() == ".docx":
            return self._read_docx(path)
        return self._read_doc_win32(path)

    def _read_docx(self, path: Path) -> str | None:
        try:
            import docx as python_docx
            doc = python_docx.Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception:
            return None

    def _read_doc_win32(self, path: Path) -> str | None:
        try:
            import win32com.client
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            d = word.Documents.Open(str(path.absolute()))
            text: str = d.Range().Text
            d.Close(False)
            word.Quit()
            return text
        except Exception:
            return None

    def _parse_release_note_text(self, text: str) -> list[dict]:
        """從文字中辨識 Issue 編號、類型、說明。"""
        issues: list[dict] = []
        current_type = "BugFix"
        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            low = stripped.lower()
            if "bug fix" in low or "bug修正" in low or "缺陷修正" in low:
                current_type = "BugFix"
                continue
            if "enhancement" in low or "功能加強" in low or "功能增強" in low:
                current_type = "Enhancement"
                continue
            m = re.match(r"(\d{7})\s+(.*)", stripped)
            if m:
                issues.append({
                    "issue_no": m.group(1),
                    "issue_type": current_type,
                    "description": m.group(2).strip(),
                    "region": "共用",
                })
        return issues
```

- [ ] **Step 4：執行測試確認全過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestReadReleaseDoc -v
```

Expected: 2 個 PASS。

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/core/patch_engine.py tests/unit/test_patch_engine.py
git commit -m "feat(core): SinglePatchEngine.read_release_doc 解析 ReleaseNote"
```

---

### Task 7：SinglePatchEngine — generate_excel_reports

**Files:**
- Modify: `src/hcp_cms/core/patch_engine.py`
- Modify: `tests/unit/test_patch_engine.py`

- [ ] **Step 1：追加測試**

在 `tests/unit/test_patch_engine.py` 末尾追加：

```python
class TestGenerateExcelReports:
    @pytest.fixture
    def engine_with_patch(self, conn):
        from hcp_cms.data.models import PatchIssue, PatchRecord
        from hcp_cms.data.repositories import PatchRepository
        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="single", patch_dir="C:/test"))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="0015659",
                                     issue_type="BugFix", region="TW",
                                     description="薪資計算錯誤", sort_order=1))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="0015660",
                                     issue_type="Enhancement", region="共用",
                                     description="新增匯出功能", sort_order=2))
        return SinglePatchEngine(conn), pid

    def test_generates_three_files(self, engine_with_patch, tmp_path):
        eng, pid = engine_with_patch
        paths = eng.generate_excel_reports(pid, output_dir=str(tmp_path))
        assert len(paths) == 3
        for p in paths:
            assert Path(p).exists()

    def test_issue_list_has_tracking_columns(self, engine_with_patch, tmp_path):
        import openpyxl
        eng, pid = engine_with_patch
        paths = eng.generate_excel_reports(pid, output_dir=str(tmp_path))
        issue_list = next(p for p in paths if "Issue清單整理" in p)
        wb = openpyxl.load_workbook(issue_list)
        ws = wb.active
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        assert "客服驗證" in headers
        assert "客戶測試結果" in headers

    def test_release_notice_no_tracking_columns(self, engine_with_patch, tmp_path):
        import openpyxl
        eng, pid = engine_with_patch
        paths = eng.generate_excel_reports(pid, output_dir=str(tmp_path))
        notice = next(p for p in paths if "發行通知" in p)
        wb = openpyxl.load_workbook(notice)
        ws = wb.active
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        assert "客服驗證" not in headers
```

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestGenerateExcelReports -v
```

Expected: `AttributeError`（`generate_excel_reports` 尚未實作）。

- [ ] **Step 3：在 patch_engine.py 追加 generate_excel_reports**

在 `SinglePatchEngine` 類別中追加：

```python
    # ── Excel 報表 ───────────────────────────────────────────────────────────

    # 色彩常數（Issue清單整理用）
    _CLR_CS    = "D5F5E3"   # 客服驗證欄
    _CLR_CUST  = "D6EAF8"   # 客戶測試欄
    _CLR_PATCH = "FEF9E7"   # 可納入大Patch
    _CLR_NOTE  = "F5EEF8"   # 備註
    _CLR_ENH   = "E2EFDA"   # Enhancement 列
    _CLR_BUG   = "FCE4D6"   # BugFix 列
    _CLR_WARN  = "FFF3CD"   # 待確認

    def generate_excel_reports(self, patch_id: int, output_dir: str) -> list[str]:
        """產生 3 份 Excel：Issue清單整理、發行通知、IT_HR清單。"""
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter

        issues = self._repo.list_issues_by_patch(patch_id)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths = []

        # ① Issue清單整理（內部追蹤）
        wb1 = Workbook()
        ws1 = wb1.active
        ws1.title = "Issue清單整理"
        hdrs1 = ["Issue No", "類型", "說明", "FORM", "SQL", "MUTI", "腳本",
                 "客服驗證", "客服測試結果", "客服測試日期",
                 "提供客戶驗證", "客戶測試結果", "客戶測試日期",
                 "可納入大Patch", "備註"]
        self._write_header_row(ws1, hdrs1)
        for i, iss in enumerate(issues, start=2):
            ws1.cell(i, 1).value = iss.issue_no
            ws1.cell(i, 2).value = iss.issue_type
            ws1.cell(i, 3).value = iss.description
            row_fill = self._CLR_ENH if iss.issue_type == "Enhancement" else self._CLR_BUG
            for c in range(1, 4):
                ws1.cell(i, c).fill = PatternFill("solid", fgColor=row_fill)
            for c in range(8, 11):
                ws1.cell(i, c).fill = PatternFill("solid", fgColor=self._CLR_CS)
            for c in range(11, 14):
                ws1.cell(i, c).fill = PatternFill("solid", fgColor=self._CLR_CUST)
            ws1.cell(i, 14).fill = PatternFill("solid", fgColor=self._CLR_PATCH)
            ws1.cell(i, 15).fill = PatternFill("solid", fgColor=self._CLR_NOTE)
        p1 = str(out / "Issue清單整理.xlsx")
        wb1.save(p1)
        paths.append(p1)

        # ② 發行通知（對客戶，不含追蹤欄）
        wb2 = Workbook()
        ws2 = wb2.active
        ws2.title = "發行通知"
        hdrs2 = ["Issue No", "類型", "說明", "FORM目錄", "DB物件", "多語更新", "安裝步驟", "備註"]
        self._write_header_row(ws2, hdrs2)
        for i, iss in enumerate(issues, start=2):
            ws2.cell(i, 1).value = iss.issue_no
            ws2.cell(i, 2).value = iss.issue_type
            ws2.cell(i, 3).value = iss.description
        p2 = str(out / "發行通知.xlsx")
        wb2.save(p2)
        paths.append(p2)

        # ③ IT/HR 清單（雙頁籤）
        wb3 = Workbook()
        ws_it = wb3.active
        ws_it.title = "IT 清單"
        hdrs_it = ["Issue No", "類型", "程式代號", "說明", "FORM目錄", "DB物件", "多語更新", "備註"]
        self._write_header_row(ws_it, hdrs_it)
        ws_hr = wb3.create_sheet("HR 清單")
        hdrs_hr = ["Issue No", "計區域", "類型", "程式代號", "程式名稱",
                   "功能說明", "影響說明", "相關程式(FORM)",
                   "上線所需動作", "測試方向及注意事項", "備註"]
        self._write_header_row(ws_hr, hdrs_hr)
        for i, iss in enumerate(issues, start=2):
            ws_it.cell(i, 1).value = iss.issue_no
            ws_it.cell(i, 2).value = iss.issue_type
            ws_it.cell(i, 3).value = iss.program_code
            ws_it.cell(i, 4).value = iss.description
            ws_hr.cell(i, 1).value = iss.issue_no
            ws_hr.cell(i, 2).value = iss.region
            ws_hr.cell(i, 3).value = iss.issue_type
            ws_hr.cell(i, 4).value = iss.program_code
            ws_hr.cell(i, 5).value = iss.program_name
            ws_hr.cell(i, 6).value = iss.description
            ws_hr.cell(i, 7).value = iss.impact
            ws_hr.cell(i, 9).value = "請與資訊單位確認是否已完成更新\n確認更新完成再進行測試"
            ws_hr.cell(i, 10).value = iss.test_direction
        p3 = str(out / "Issue清單_IT_HR.xlsx")
        wb3.save(p3)
        paths.append(p3)

        return paths

    def _write_header_row(self, ws, headers: list[str]) -> None:
        from openpyxl.styles import Font, PatternFill, Alignment
        for c, h in enumerate(headers, start=1):
            cell = ws.cell(1, c)
            cell.value = h
            cell.font = Font(name="微軟正黑體", bold=True, size=11, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F3864")
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
```

- [ ] **Step 4：執行測試確認全過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestGenerateExcelReports -v
```

Expected: 3 個 PASS。

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/core/patch_engine.py tests/unit/test_patch_engine.py
git commit -m "feat(core): SinglePatchEngine.generate_excel_reports 產 3 份 Excel 報表"
```

---

### Task 8：SinglePatchEngine — generate_test_scripts

**Files:**
- Modify: `src/hcp_cms/core/patch_engine.py`
- Modify: `tests/unit/test_patch_engine.py`

- [ ] **Step 1：追加測試**

在 `tests/unit/test_patch_engine.py` 末尾追加：

```python
class TestGenerateTestScripts:
    @pytest.fixture
    def engine_with_patch(self, conn):
        from hcp_cms.data.models import PatchIssue, PatchRecord
        from hcp_cms.data.repositories import PatchRepository
        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="single"))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="0015659",
                                     description="測試說明", test_direction="測試步驟"))
        return SinglePatchEngine(conn), pid

    def test_generates_three_script_files(self, engine_with_patch, tmp_path):
        eng, pid = engine_with_patch
        paths = eng.generate_test_scripts(pid, output_dir=str(tmp_path))
        assert len(paths) == 3
        names = [Path(p).name for p in paths]
        assert any("客服版" in n for n in names)
        assert any("客戶版" in n for n in names)
        assert any("追蹤表" in n and n.endswith(".xlsx") for n in names)
        for p in paths:
            assert Path(p).exists()
```

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestGenerateTestScripts -v
```

Expected: `AttributeError`。

- [ ] **Step 3：在 patch_engine.py 追加 generate_test_scripts**

```python
    # ── 測試腳本 ─────────────────────────────────────────────────────────────

    def generate_test_scripts(self, patch_id: int, output_dir: str) -> list[str]:
        """產測試腳本_客服版.docx、客戶版.docx、測試追蹤表.xlsx。"""
        import docx as python_docx
        from openpyxl import Workbook

        issues = self._repo.list_issues_by_patch(patch_id)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths = []

        # 客服版 Word
        doc_cs = python_docx.Document()
        doc_cs.add_heading("測試腳本（客服版）", 0)
        for iss in issues:
            doc_cs.add_heading(f"Issue {iss.issue_no}", level=1)
            doc_cs.add_paragraph(f"說明：{iss.description or ''}")
            doc_cs.add_paragraph(f"測試步驟：{iss.test_direction or '請填寫'}")
            doc_cs.add_paragraph("測試人員：＿＿＿＿　審核人員：＿＿＿＿")
        p_cs = str(out / "測試腳本_客服版.docx")
        doc_cs.save(p_cs)
        paths.append(p_cs)

        # 客戶版 Word
        doc_cu = python_docx.Document()
        doc_cu.add_heading("測試腳本（客戶版）", 0)
        for iss in issues:
            doc_cu.add_heading(f"Issue {iss.issue_no}", level=1)
            doc_cu.add_paragraph(f"說明：{iss.description or ''}")
            doc_cu.add_paragraph("□ 正常　□ 異常")
            doc_cu.add_paragraph("客戶回覆日期：＿＿＿＿　簽名：＿＿＿＿")
        p_cu = str(out / "測試腳本_客戶版.docx")
        doc_cu.save(p_cu)
        paths.append(p_cu)

        # 追蹤表 xlsx
        wb = Workbook()
        ws_cs = wb.active
        ws_cs.title = "客服驗證"
        self._write_header_row(ws_cs, ["Issue No", "說明", "測試結果(PASS/FAIL)", "測試日期", "備註"])
        ws_cu = wb.create_sheet("客戶驗證")
        self._write_header_row(ws_cu, ["Issue No", "說明", "測試結果(正常/異常)", "回覆日期", "備註"])
        for i, iss in enumerate(issues, start=2):
            ws_cs.cell(i, 1).value = iss.issue_no
            ws_cs.cell(i, 2).value = iss.description
            ws_cu.cell(i, 1).value = iss.issue_no
            ws_cu.cell(i, 2).value = iss.description
        p_tr = str(out / "測試追蹤表.xlsx")
        wb.save(p_tr)
        paths.append(p_tr)

        return paths
```

- [ ] **Step 4：執行測試確認全過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestGenerateTestScripts -v
```

Expected: 1 個 PASS。

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/core/patch_engine.py tests/unit/test_patch_engine.py
git commit -m "feat(core): SinglePatchEngine.generate_test_scripts 產測試腳本三份"
```

---

### Task 9：MonthlyPatchEngine — load_issues（手動來源）

**Files:**
- Create: `src/hcp_cms/core/monthly_patch_engine.py`
- Create: `tests/unit/test_monthly_patch_engine.py`

- [ ] **Step 1：撰寫失敗測試**

建立 `tests/unit/test_monthly_patch_engine.py`：

```python
"""MonthlyPatchEngine 單元測試。"""
import json
import sqlite3
from pathlib import Path
import pytest
from hcp_cms.data.database import DatabaseManager
from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine


@pytest.fixture
def conn():
    db = DatabaseManager(":memory:")
    db.initialize()
    yield db.connection
    db.connection.close()


class TestLoadIssues:
    def test_load_from_json_file(self, conn, tmp_path):
        data = [
            {"issue_no": "0015659", "program_code": "PAYA001", "program_name": "薪資計算",
             "issue_type": "BugFix", "region": "TW", "description": "修正錯誤",
             "impact": "影響薪資", "test_direction": "執行薪資計算"},
        ]
        f = tmp_path / "issues.json"
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        eng = MonthlyPatchEngine(conn)
        patch_id = eng.load_issues(source="manual", month_str="202604", file_path=str(f))
        from hcp_cms.data.repositories import PatchRepository
        issues = PatchRepository(conn).list_issues_by_patch(patch_id)
        assert len(issues) == 1
        assert issues[0].issue_no == "0015659"
        assert issues[0].region == "TW"

    def test_load_from_txt_file(self, conn, tmp_path):
        txt = "0015659\tPAYA001\t薪資計算\tBugFix\tTW\t修正錯誤\t影響薪資\t執行薪資計算\n"
        txt += "0015660\tLEAA001\t請假管理\tEnhancement\t共用\t新增功能\t影響請假\t測試請假\n"
        f = tmp_path / "issues.txt"
        f.write_text(txt, encoding="utf-8")

        eng = MonthlyPatchEngine(conn)
        patch_id = eng.load_issues(source="manual", month_str="202604", file_path=str(f))
        from hcp_cms.data.repositories import PatchRepository
        issues = PatchRepository(conn).list_issues_by_patch(patch_id)
        assert len(issues) == 2
        assert issues[1].issue_no == "0015660"

    def test_creates_patch_record(self, conn, tmp_path):
        f = tmp_path / "issues.json"
        f.write_text("[]", encoding="utf-8")
        eng = MonthlyPatchEngine(conn)
        patch_id = eng.load_issues(source="manual", month_str="202604", file_path=str(f))
        from hcp_cms.data.repositories import PatchRepository
        patch = PatchRepository(conn).get_patch_by_id(patch_id)
        assert patch.type == "monthly"
        assert patch.month_str == "202604"
```

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestLoadIssues -v
```

Expected: `ModuleNotFoundError`。

- [ ] **Step 3：建立 monthly_patch_engine.py**

建立 `src/hcp_cms/core/monthly_patch_engine.py`：

```python
"""MonthlyPatchEngine — 每月大 PATCH 整理流程。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from hcp_cms.data.models import PatchIssue, PatchRecord
from hcp_cms.data.repositories import PatchRepository

_TXT_FIELDS = ["issue_no", "program_code", "program_name", "issue_type",
               "region", "description", "impact", "test_direction"]


class MonthlyPatchEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._repo = PatchRepository(conn)

    # ── Issue 載入 ───────────────────────────────────────────────────────────

    def load_issues(self, source: str, month_str: str,
                    file_path: str | None = None) -> int:
        """載入 Issue 清單，回傳 patch_id。

        source='manual': 讀 file_path（.json 或 .txt tab 分隔）
        source='mantis': 透過 PlaywrightMantisService（需另行呼叫）
        """
        patch = PatchRecord(type="monthly", month_str=month_str)
        patch_id = self._repo.insert_patch(patch)

        if source == "manual" and file_path:
            issues = self._load_file(file_path)
            for idx, raw in enumerate(issues):
                issue = PatchIssue(
                    patch_id=patch_id,
                    issue_no=raw.get("issue_no", ""),
                    program_code=raw.get("program_code"),
                    program_name=raw.get("program_name"),
                    issue_type=raw.get("issue_type", "BugFix"),
                    region=raw.get("region", "共用"),
                    description=raw.get("description"),
                    impact=raw.get("impact"),
                    test_direction=raw.get("test_direction"),
                    source="manual",
                    sort_order=idx,
                )
                self._repo.insert_issue(issue)

        return patch_id

    def _load_file(self, file_path: str) -> list[dict]:
        path = Path(file_path)
        if path.suffix.lower() == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        # tab-delimited .txt
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= len(_TXT_FIELDS):
                rows.append(dict(zip(_TXT_FIELDS, parts)))
        return rows
```

- [ ] **Step 4：執行測試確認全過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestLoadIssues -v
```

Expected: 3 個 PASS。

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/core/monthly_patch_engine.py tests/unit/test_monthly_patch_engine.py
git commit -m "feat(core): MonthlyPatchEngine.load_issues 支援 JSON/TXT 手動載入"
```

---

### Task 10：MonthlyPatchEngine — prepare_test_reports（簡繁轉換）

**Files:**
- Modify: `src/hcp_cms/core/monthly_patch_engine.py`
- Modify: `tests/unit/test_monthly_patch_engine.py`

- [ ] **Step 1：追加測試**

在 `tests/unit/test_monthly_patch_engine.py` 末尾追加：

```python
class TestPrepareTestReports:
    def test_detects_and_converts_simplified(self, conn, tmp_path):
        import docx as python_docx
        # 建立包含簡體字的 .docx
        doc = python_docx.Document()
        doc.add_paragraph("这是简体中文测试报告")
        report_dir = tmp_path / "11G" / "测试报告"
        report_dir.mkdir(parents=True)
        f = report_dir / "01.IP_20260203_0015659_TESTREPORT_11G.docx"
        doc.save(str(f))

        eng = MonthlyPatchEngine(conn)
        result = eng.prepare_test_reports(str(tmp_path))
        assert result["converted"] >= 1

    def test_validates_naming_format(self, conn, tmp_path):
        import docx as python_docx
        doc = python_docx.Document()
        report_dir = tmp_path / "11G" / "測試報告"
        report_dir.mkdir(parents=True)
        bad_name = report_dir / "wrong_name.docx"
        doc.save(str(bad_name))

        eng = MonthlyPatchEngine(conn)
        result = eng.prepare_test_reports(str(tmp_path))
        assert len(result["invalid_names"]) >= 1
```

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestPrepareTestReports -v
```

Expected: `AttributeError`。

- [ ] **Step 3：在 monthly_patch_engine.py 追加 prepare_test_reports**

```python
    # ── 測試報告整理 ─────────────────────────────────────────────────────────

    _REPORT_NAME_RE = re.compile(
        r"^\d{2}\.IP_\d{8}_\d{7}_TESTREPORT_(11G|12C)\.(doc|docx)$",
        re.IGNORECASE,
    )

    def prepare_test_reports(self, month_dir: str) -> dict:
        """掃描測試報告資料夾，轉換簡體→繁體，驗證命名格式。"""
        import re as _re
        base = Path(month_dir)
        result = {"converted": 0, "invalid_names": [], "files_checked": 0}

        for version in ("11G", "12C"):
            for sub in ("測試報告", "测试报告"):
                report_dir = base / version / sub
                if not report_dir.exists():
                    continue
                for f in report_dir.iterdir():
                    if f.suffix.lower() not in (".doc", ".docx"):
                        continue
                    result["files_checked"] += 1
                    if not self._REPORT_NAME_RE.match(f.name):
                        result["invalid_names"].append(f.name)
                    if f.suffix.lower() == ".docx":
                        converted = self._convert_simplified_to_traditional(f)
                        if converted:
                            result["converted"] += 1

        return result

    def _convert_simplified_to_traditional(self, path: Path) -> bool:
        """若 .docx 含簡體字則就地轉換為繁體，回傳是否有轉換。"""
        try:
            import opencc
            import docx as python_docx
            cc = opencc.OpenCC("s2t")
            doc = python_docx.Document(str(path))
            changed = False
            for para in doc.paragraphs:
                converted = cc.convert(para.text)
                if converted != para.text:
                    for run in para.runs:
                        run.text = cc.convert(run.text)
                    changed = True
            if changed:
                doc.save(str(path))
            return changed
        except Exception:
            return False
```

在 `monthly_patch_engine.py` 的 import 區塊頂部追加：

```python
import re
```

- [ ] **Step 4：執行測試確認全過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestPrepareTestReports -v
```

Expected: 2 個 PASS。

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/core/monthly_patch_engine.py tests/unit/test_monthly_patch_engine.py
git commit -m "feat(core): MonthlyPatchEngine.prepare_test_reports 簡繁轉換與命名驗證"
```

---

### Task 11：MonthlyPatchEngine — generate_patch_list

**Files:**
- Modify: `src/hcp_cms/core/monthly_patch_engine.py`
- Modify: `tests/unit/test_monthly_patch_engine.py`

- [ ] **Step 1：追加測試**

在 `tests/unit/test_monthly_patch_engine.py` 末尾追加：

```python
class TestGeneratePatchList:
    @pytest.fixture
    def engine_with_patch(self, conn, tmp_path):
        import json
        data = [
            {"issue_no": "0015659", "program_code": "PAYA001", "program_name": "薪資計算",
             "issue_type": "BugFix", "region": "TW", "description": "修正錯誤",
             "impact": "影響薪資", "test_direction": "執行薪資計算"},
            {"issue_no": "0015660", "program_code": "LEAA001", "program_name": "請假管理",
             "issue_type": "Enhancement", "region": "CN", "description": "新增功能",
             "impact": "影響請假", "test_direction": "測試請假"},
        ]
        f = tmp_path / "issues.json"
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        eng = MonthlyPatchEngine(conn)
        pid = eng.load_issues(source="manual", month_str="202604", file_path=str(f))
        return eng, pid

    def test_generates_two_excel_files(self, engine_with_patch, tmp_path):
        eng, pid = engine_with_patch
        paths = eng.generate_patch_list(pid, output_dir=str(tmp_path))
        assert len(paths) == 2
        names = [Path(p).name for p in paths]
        assert any("11G" in n for n in names)
        assert any("12C" in n for n in names)
        for p in paths:
            assert Path(p).exists()

    def test_excel_has_three_tabs(self, engine_with_patch, tmp_path):
        import openpyxl
        eng, pid = engine_with_patch
        paths = eng.generate_patch_list(pid, output_dir=str(tmp_path), month_str="202604")
        wb = openpyxl.load_workbook(paths[0])
        sheet_names = wb.sheetnames
        assert "IT 發行通知" in sheet_names
        assert "HR 發行通知" in sheet_names
        assert "問題修正補充說明" in sheet_names

    def test_region_color_coding(self, engine_with_patch, tmp_path):
        import openpyxl
        eng, pid = engine_with_patch
        paths = eng.generate_patch_list(pid, output_dir=str(tmp_path), month_str="202604")
        wb = openpyxl.load_workbook(paths[0])
        ws = wb["HR 發行通知"]
        # TW 列應為淡藍，CN 列應為淡橘黃
        tw_fill = ws.cell(2, 2).fill.fgColor.rgb  # 第一筆 TW
        cn_fill = ws.cell(3, 2).fill.fgColor.rgb  # 第二筆 CN
        assert tw_fill != cn_fill
```

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestGeneratePatchList -v
```

Expected: `AttributeError`。

- [ ] **Step 3：在 monthly_patch_engine.py 追加 generate_patch_list**

```python
    # ── PATCH_LIST Excel ─────────────────────────────────────────────────────

    _CLR_TW   = "D6EAF8"   # TW 淡藍
    _CLR_CN   = "FFF3CD"   # CN 淡橘黃
    _CLR_BOTH = "E8F5E9"   # 共用 淡綠
    _CLR_BUG  = "FCE4D6"   # BugFix
    _CLR_ENH  = "E2EFDA"   # Enhancement
    _HDR_DARK = "1F3864"   # 主標題深藍
    _HDR_MID  = "2E75B6"   # 副標題中藍

    def generate_patch_list(self, patch_id: int, output_dir: str,
                            month_str: str | None = None) -> list[str]:
        """產 PATCH_LIST_{YYYYMM}_11G.xlsx 與 12C.xlsx，各含 3 頁籤。"""
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter

        issues = self._repo.list_issues_by_patch(patch_id)
        if month_str is None:
            patch = self._repo.get_patch_by_id(patch_id)
            month_str = patch.month_str if patch and patch.month_str else "000000"

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths = []

        for version in ("11G", "12C"):
            wb = Workbook()

            # ── 頁籤①：IT 發行通知（8 欄）──
            ws_it = wb.active
            ws_it.title = "IT 發行通知"
            hdrs_it = ["Issue No", "類型", "程式代號", "說明",
                       "FORM目錄", "DB物件", "多語更新", "備註"]
            self._write_patch_header(ws_it, hdrs_it)
            for i, iss in enumerate(issues, start=2):
                ws_it.cell(i, 1).value = iss.issue_no
                ws_it.cell(i, 2).value = iss.issue_type
                ws_it.cell(i, 3).value = iss.program_code
                ws_it.cell(i, 4).value = iss.description
                row_fill = self._CLR_ENH if iss.issue_type == "Enhancement" else self._CLR_BUG
                for c in range(1, 9):
                    ws_it.cell(i, c).fill = PatternFill("solid", fgColor=row_fill)

            # ── 頁籤②：HR 發行通知（11 欄）──
            ws_hr = wb.create_sheet("HR 發行通知")
            hdrs_hr = ["Issue No", "計區域", "類型", "程式代號", "程式名稱",
                       "功能說明", "影響說明/用途", "相關程式(FORM)",
                       "上線所需動作", "測試方向及注意事項", "備註"]
            self._write_patch_header(ws_hr, hdrs_hr)
            for i, iss in enumerate(issues, start=2):
                region_fill = {"TW": self._CLR_TW, "CN": self._CLR_CN}.get(iss.region, self._CLR_BOTH)
                ws_hr.cell(i, 1).value = iss.issue_no
                ws_hr.cell(i, 2).value = iss.region
                ws_hr.cell(i, 3).value = iss.issue_type
                ws_hr.cell(i, 4).value = iss.program_code
                ws_hr.cell(i, 5).value = iss.program_name
                ws_hr.cell(i, 6).value = iss.description
                ws_hr.cell(i, 7).value = iss.impact
                ws_hr.cell(i, 9).value = "請與資訊單位確認是否已完成更新\n確認更新完成再進行測試"
                ws_hr.cell(i, 10).value = iss.test_direction
                for c in range(1, 12):
                    ws_hr.cell(i, c).fill = PatternFill("solid", fgColor=region_fill)
                ws_hr.cell(i, 2).fill = PatternFill("solid", fgColor=region_fill)

            # ── 頁籤③：問題修正補充說明 ──
            ws_supp = wb.create_sheet("問題修正補充說明")
            self._write_patch_header(ws_supp,
                ["Issue No", "修改原因", "原問題", "範例說明", "修正後", "注意事項"])
            for i, iss in enumerate(issues, start=2):
                ws_supp.cell(i, 1).value = iss.issue_no
                if iss.mantis_detail:
                    try:
                        detail = json.loads(iss.mantis_detail)
                        ws_supp.cell(i, 2).value = detail.get("reason")
                        ws_supp.cell(i, 3).value = detail.get("original")
                        ws_supp.cell(i, 4).value = detail.get("example")
                        ws_supp.cell(i, 5).value = detail.get("fixed")
                        ws_supp.cell(i, 6).value = detail.get("notes")
                    except (json.JSONDecodeError, AttributeError):
                        pass

            fname = f"PATCH_LIST_{month_str}_{version}.xlsx"
            p = str(out / fname)
            wb.save(p)
            paths.append(p)

        return paths

    def _write_patch_header(self, ws, headers: list[str]) -> None:
        from openpyxl.styles import Font, PatternFill, Alignment
        for c, h in enumerate(headers, start=1):
            cell = ws.cell(1, c)
            cell.value = h
            cell.font = Font(name="微軟正黑體", bold=True, size=11, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=self._HDR_DARK)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
```

在 `monthly_patch_engine.py` 頂部的 import 區塊加入：

```python
import json
```

- [ ] **Step 4：執行測試確認全過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestGeneratePatchList -v
```

Expected: 3 個 PASS。

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/core/monthly_patch_engine.py tests/unit/test_monthly_patch_engine.py
git commit -m "feat(core): MonthlyPatchEngine.generate_patch_list 產 PATCH_LIST 11G/12C"
```

---

### Task 12：ClaudeContentService

**Files:**
- Create: `src/hcp_cms/services/claude_content.py`
- Create: `tests/unit/test_claude_content.py`

- [ ] **Step 1：撰寫失敗測試**

建立 `tests/unit/test_claude_content.py`：

```python
"""ClaudeContentService 單元測試（使用 mock）。"""
import pytest
from unittest.mock import MagicMock, patch


class TestClaudeContentService:
    def test_returns_none_when_no_api_key(self):
        with patch("hcp_cms.services.credential.CredentialManager.retrieve", return_value=None):
            from hcp_cms.services.claude_content import ClaudeContentService
            svc = ClaudeContentService()
            assert svc.generate_description({"issue_no": "0015659"}) is None

    def test_generate_description_returns_text(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="測試生成說明文字")]
        with patch("hcp_cms.services.credential.CredentialManager.retrieve", return_value="fake-key"), \
             patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_response
            from importlib import reload
            import hcp_cms.services.claude_content as m
            reload(m)
            svc = m.ClaudeContentService()
            svc._client = MockClient.return_value
            result = svc.generate_description({"issue_no": "0015659", "description": "修正薪資"})
            assert result == "測試生成說明文字"

    def test_generate_description_retries_on_failure(self):
        with patch("hcp_cms.services.credential.CredentialManager.retrieve", return_value="fake-key"), \
             patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.side_effect = Exception("timeout")
            from importlib import reload
            import hcp_cms.services.claude_content as m
            reload(m)
            svc = m.ClaudeContentService()
            svc._client = MockClient.return_value
            result = svc.generate_description({"issue_no": "0015659"})
            assert result is None
            assert MockClient.return_value.messages.create.call_count == 3

    def test_generate_notify_body_returns_text(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="本月更新說明")]
        with patch("hcp_cms.services.credential.CredentialManager.retrieve", return_value="fake-key"), \
             patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_response
            from importlib import reload
            import hcp_cms.services.claude_content as m
            reload(m)
            svc = m.ClaudeContentService()
            svc._client = MockClient.return_value
            issues = [{"issue_no": "0015659", "description": "修正薪資"}]
            result = svc.generate_notify_body(issues, "202604")
            assert result == "本月更新說明"
```

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_claude_content.py -v
```

Expected: `ModuleNotFoundError`。

- [ ] **Step 3：建立 claude_content.py**

建立 `src/hcp_cms/services/claude_content.py`：

```python
"""ClaudeContentService — 使用 Claude API 生成說明文字與通知信內容。"""

from __future__ import annotations

_MODEL = "claude-sonnet-4-6"
_MAX_RETRIES = 3


class ClaudeContentService:
    def __init__(self) -> None:
        from hcp_cms.services.credential import CredentialManager
        api_key = CredentialManager().retrieve("claude_api_key")
        if api_key:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=api_key)
        else:
            self._client = None

    def generate_description(self, issue_data: dict) -> str | None:
        """依 Issue 資料生成 HR 版功能說明文字（50-100字）。"""
        if self._client is None:
            return None
        prompt = (
            f"請根據以下 HCP Issue 資訊，用繁體中文撰寫一段簡潔的功能說明（50-100字）：\n"
            f"Issue No: {issue_data.get('issue_no', '')}\n"
            f"說明: {issue_data.get('description', '')}\n"
            f"類型: {issue_data.get('issue_type', '')}"
        )
        return self._call_api(prompt, max_tokens=300)

    def generate_notify_body(self, issues: list[dict], month_str: str) -> str | None:
        """依 Issue 清單生成客戶通知信主體段落。"""
        if self._client is None:
            return None
        year = month_str[:4]
        month = month_str[4:]
        summary = "\n".join(
            f"- {i.get('issue_no', '')}: {i.get('description', '')}" for i in issues
        )
        prompt = (
            f"請根據以下 {year}年{month}月 HCP 大PATCH Issue 清單，"
            f"撰寫一段給客戶的更新說明（繁體中文，說明各項修正的業務影響）：\n{summary}"
        )
        return self._call_api(prompt, max_tokens=800)

    def _call_api(self, prompt: str, max_tokens: int) -> str | None:
        for attempt in range(_MAX_RETRIES):
            try:
                response = self._client.messages.create(  # type: ignore[union-attr]
                    model=_MODEL,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text
            except Exception:
                if attempt == _MAX_RETRIES - 1:
                    return None
        return None
```

- [ ] **Step 4：執行測試確認全過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_claude_content.py -v
```

Expected: 4 個 PASS。

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/services/claude_content.py tests/unit/test_claude_content.py
git commit -m "feat(services): ClaudeContentService 生成 HR 說明與通知信文字"
```

---

### Task 13：MonthlyPatchEngine — generate_notify_html + Jinja2 範本

**Files:**
- Create: `templates/patch_notify.html.j2`
- Modify: `src/hcp_cms/core/monthly_patch_engine.py`
- Modify: `tests/unit/test_monthly_patch_engine.py`

- [ ] **Step 1：建立 Jinja2 範本**

建立 `templates/patch_notify.html.j2`：

```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>{{ year }}年{{ month }}月 HCP 大PATCH 更新通知</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; font-family: "微軟正黑體", Arial, sans-serif; }
body { background: #f0f4f8; color: #222; }
.header { background: linear-gradient(135deg, #1F3864, #2E75B6); color: #fff; padding: 20px 32px; }
.header h1 { font-size: 18px; }
.header p  { font-size: 12px; color: #b8cde8; margin-top: 4px; }
.container { max-width: 900px; margin: 24px auto; padding: 0 20px 40px; }
.section-title { font-size: 13px; font-weight: bold; color: #1F3864;
  border-left: 4px solid #2E75B6; padding-left: 10px; margin: 24px 0 12px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { background: #1F3864; color: #fff; padding: 8px 10px; text-align: left; }
td { padding: 7px 10px; border: 1px solid #ddd; vertical-align: top; }
tr:nth-child(even) td { background: #f9fafb; }
.bug    { background: #FCE4D6; }
.enh    { background: #E2EFDA; }
.tw     { background: #D6EAF8; }
.cn     { background: #FFF3CD; }
.shared { background: #E8F5E9; }
.reminder { background: #FFF9E6; border: 1px solid #F9A825; border-radius: 6px;
  padding: 14px 18px; margin-top: 16px; font-size: 12px; line-height: 1.8; }
.reminder strong { color: #E65100; }
.footer { text-align: center; color: #aaa; font-size: 11px; margin-top: 32px; }
</style>
</head>
<body>
<div class="header">
  <h1>📦 {{ year }}年{{ month }}月 HCP 大PATCH 更新通知</h1>
  <p>HCP 11G 維護客戶 · 請於更新後依序完成驗證</p>
</div>
<div class="container">

  {% if notify_body %}
  <div class="section-title">本月更新說明</div>
  <p style="font-size:13px;line-height:1.8;color:#444;">{{ notify_body }}</p>
  {% endif %}

  <div class="section-title">本月修正項目</div>
  <table>
    <tr>
      <th>Issue No</th><th>計區域</th><th>類型</th>
      <th>程式代號</th><th>功能說明</th><th>影響說明</th>
    </tr>
    {% for iss in issues %}
    <tr class="{{ 'bug' if iss.issue_type == 'BugFix' else 'enh' }}">
      <td>{{ iss.issue_no }}</td>
      <td class="{{ 'tw' if iss.region == 'TW' else ('cn' if iss.region == 'CN' else 'shared') }}">{{ iss.region }}</td>
      <td>{{ iss.issue_type }}</td>
      <td>{{ iss.program_code or '' }}</td>
      <td>{{ iss.description or '' }}</td>
      <td>{{ iss.impact or '' }}</td>
    </tr>
    {% endfor %}
  </table>

  {% if reminders %}
  <div class="section-title">本月排班考勤提醒</div>
  <div class="reminder">
    {% for r in reminders %}
    <p><strong>{{ r }}</strong></p>
    {% endfor %}
  </div>
  {% endif %}

  <div class="footer">
    HCP 客服團隊 · {{ year }}年{{ month }}月 · 如有疑問請聯絡客服
  </div>
</div>
</body>
</html>
```

- [ ] **Step 2：追加測試**

在 `tests/unit/test_monthly_patch_engine.py` 末尾追加：

```python
class TestGenerateNotifyHtml:
    @pytest.fixture
    def engine_with_patch(self, conn, tmp_path):
        import json
        data = [{"issue_no": "0015659", "program_code": "PAYA001", "program_name": "薪資計算",
                 "issue_type": "BugFix", "region": "TW", "description": "修正錯誤",
                 "impact": "影響薪資", "test_direction": "執行薪資計算"}]
        f = tmp_path / "issues.json"
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        eng = MonthlyPatchEngine(conn)
        pid = eng.load_issues(source="manual", month_str="202604", file_path=str(f))
        return eng, pid

    def test_generates_html_file(self, engine_with_patch, tmp_path):
        eng, pid = engine_with_patch
        path = eng.generate_notify_html(pid, output_dir=str(tmp_path), month_str="202604")
        assert Path(path).exists()
        assert path.endswith(".html")

    def test_html_contains_issue_no(self, engine_with_patch, tmp_path):
        eng, pid = engine_with_patch
        path = eng.generate_notify_html(pid, output_dir=str(tmp_path), month_str="202604")
        content = Path(path).read_text(encoding="utf-8")
        assert "0015659" in content

    def test_html_filename_format(self, engine_with_patch, tmp_path):
        eng, pid = engine_with_patch
        path = eng.generate_notify_html(pid, output_dir=str(tmp_path), month_str="202604")
        assert "202604" in Path(path).name
        assert "大PATCH更新通知" in Path(path).name
```

- [ ] **Step 3：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestGenerateNotifyHtml -v
```

Expected: `AttributeError`。

- [ ] **Step 4：在 monthly_patch_engine.py 追加 generate_notify_html**

```python
    # ── 客戶通知 HTML ────────────────────────────────────────────────────────

    def generate_notify_html(self, patch_id: int, output_dir: str,
                             month_str: str | None = None,
                             reminders: list[str] | None = None,
                             notify_body: str | None = None) -> str:
        """使用 Jinja2 範本產客戶通知信 HTML。"""
        from jinja2 import Environment, FileSystemLoader
        from pathlib import Path as _Path

        issues = self._repo.list_issues_by_patch(patch_id)
        if month_str is None:
            patch = self._repo.get_patch_by_id(patch_id)
            month_str = patch.month_str if patch and patch.month_str else "000000"

        year = month_str[:4]
        month = month_str[4:]

        # 找 templates 資料夾（相對於 repo 根目錄）
        templates_dir = _Path(__file__).parent.parent.parent.parent / "templates"
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
        tmpl = env.get_template("patch_notify.html.j2")

        html = tmpl.render(
            year=year,
            month=month,
            issues=issues,
            notify_body=notify_body or "",
            reminders=reminders or [],
        )

        out = _Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        fname = f"【HCP11G維護客戶】{month_str}月份大PATCH更新通知.html"
        path = str(out / fname)
        _Path(path).write_text(html, encoding="utf-8")
        return path
```

- [ ] **Step 5：執行測試確認全過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestGenerateNotifyHtml -v
```

Expected: 3 個 PASS。

- [ ] **Step 6：Commit**

```bash
git add templates/patch_notify.html.j2 src/hcp_cms/core/monthly_patch_engine.py tests/unit/test_monthly_patch_engine.py
git commit -m "feat(core): MonthlyPatchEngine.generate_notify_html 產客戶通知信"
```

---

### Task 14：PlaywrightMantisService [POC: Playwright 在 Python 背景線程執行]

> ⚠️ **[POC: 首次使用 Playwright；需在目標機器驗證 Chromium 啟動、Mantis 登入等待機制、Issue 頁面 DOM 結構。實作前先執行 `/poc` 確認可行性。]**

**Files:**
- Create: `src/hcp_cms/services/mantis/playwright_service.py`

- [ ] **Step 1：建立基本骨架，可手動測試**

建立 `src/hcp_cms/services/mantis/playwright_service.py`：

```python
"""PlaywrightMantisService — 瀏覽器自動化讀取 Mantis Issue 狀態。"""

from __future__ import annotations

import threading
from typing import Callable

_LOGIN_TIMEOUT_SEC = 300  # 5 分鐘


class PlaywrightMantisService:
    """以 Playwright Chromium 開啟 Mantis，等待使用者登入後擷取 Issue 資料。

    使用方式：
        svc = PlaywrightMantisService(mantis_url="https://mantis.example.com")
        # 在 UI 呼叫 open_browser()，使用者登入後呼叫 confirm_login()
        svc.open_browser()
        # ... 等待使用者按「已登入」按鈕 ...
        svc.confirm_login()
        data = svc.fetch_issue("0015659")
    """

    def __init__(self, mantis_url: str) -> None:
        self._mantis_url = mantis_url.rstrip("/")
        self._page = None
        self._browser = None
        self._playwright = None
        self._login_event = threading.Event()

    def open_browser(self) -> None:
        """啟動 Chromium 並導向 Mantis 登入頁。在背景線程執行。"""
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=False)
        self._page = self._browser.new_page()
        self._page.goto(f"{self._mantis_url}/login_page.php")

    def confirm_login(self) -> None:
        """使用者按下「已登入」後呼叫，解除等待封鎖。"""
        self._login_event.set()

    def fetch_issue(self, issue_no: str) -> dict | None:
        """擷取單一 Issue 的狀態資料（需在 confirm_login() 之後呼叫）。"""
        if self._page is None:
            return None
        try:
            url = f"{self._mantis_url}/view.php?id={issue_no}"
            self._page.goto(url)
            self._page.wait_for_load_state("networkidle", timeout=10000)
            return self._extract_issue_data(issue_no)
        except Exception:
            return None

    def _extract_issue_data(self, issue_no: str) -> dict:
        """從 Mantis Issue 頁面擷取追蹤欄位。

        ⚠️ DOM 選擇器需在實際 Mantis 環境執行 POC 後調整。
        以下為預設佔位，POC 時以瀏覽器 DevTools 確認正確選擇器。
        """
        data: dict = {"issue_no": issue_no}
        try:
            # 活動紀錄文字（包含客服驗證、客戶測試等資訊）
            notes = self._page.query_selector_all(".bugnote-note")  # type: ignore[union-attr]
            data["notes"] = [n.inner_text() for n in notes]
            # 狀態
            status_el = self._page.query_selector("[data-column='status'] .column-value")  # type: ignore[union-attr]
            data["status"] = status_el.inner_text() if status_el else None
        except Exception:
            pass
        return data

    def fetch_issues_batch(self, issue_nos: list[str],
                           on_progress: Callable[[str, dict | None], None] | None = None) -> list[dict]:
        """批次擷取多個 Issue，每筆完成後呼叫 on_progress 回調。"""
        results = []
        for no in issue_nos:
            data = self.fetch_issue(no)
            results.append(data or {"issue_no": no})
            if on_progress:
                on_progress(no, data)
        return results

    def close(self) -> None:
        """關閉瀏覽器並釋放資源。"""
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        finally:
            self._page = None
            self._browser = None
            self._playwright = None
```

- [ ] **Step 2：確認可 import**

```bash
.venv/Scripts/python.exe -c "from hcp_cms.services.mantis.playwright_service import PlaywrightMantisService; print('OK')"
```

Expected: 印出 `OK`。

- [ ] **Step 3：Commit**

```bash
git add src/hcp_cms/services/mantis/playwright_service.py
git commit -m "feat(services): PlaywrightMantisService 骨架（待 POC 確認 DOM 選擇器）"
```

---

### Task 15：全部測試 + Lint

- [ ] **Step 1：執行全部新增測試**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_repository.py tests/unit/test_patch_engine.py tests/unit/test_monthly_patch_engine.py tests/unit/test_claude_content.py -v
```

Expected: 全部 PASS，0 FAIL。

- [ ] **Step 2：執行 Lint**

```bash
.venv/Scripts/ruff.exe check src/hcp_cms/core/patch_engine.py src/hcp_cms/core/monthly_patch_engine.py src/hcp_cms/services/claude_content.py src/hcp_cms/services/mantis/playwright_service.py src/hcp_cms/data/models.py src/hcp_cms/data/repositories.py
```

修正所有 E/F 類錯誤。

- [ ] **Step 3：Commit**

```bash
git add -A
git commit -m "test: 計畫 A 全部測試通過，lint 乾淨"
```

---

## 自我審查

**Spec 覆蓋確認：**
- ✅ cs_patches / cs_patch_issues 資料表 → Task 3
- ✅ PatchRepository 完整 CRUD（含 update_issue / delete_issue）→ Task 4
- ✅ SinglePatchEngine: scan, read_release_doc, generate_excel_reports, generate_test_scripts → Tasks 5-8
- ✅ MonthlyPatchEngine: load_issues(manual), prepare_test_reports, generate_patch_list, generate_notify_html → Tasks 9-13
- ✅ ClaudeContentService（含重試邏輯）→ Task 12
- ✅ PlaywrightMantisService 骨架 [POC] → Task 14
- ✅ 3份 Excel 色彩規範 → Task 7
- ✅ PATCH_LIST 3頁籤、11欄 HR、8欄 IT → Task 11
- ✅ HTML 範本含 Issue 表格、排班提醒、通知文字 → Task 13

**待計畫 B：** IssueTableWidget、PatchView UI、MainWindow 整合
