# CSV 匯入精靈 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 實作 3 步驟 CSV 匯入精靈，讓使用者選擇 CSV 檔、確認欄位對應、預覽衝突後批次寫入 cs_cases / companies。

**Architecture:** `CsvImportEngine`（Core 層）負責解析、預覽、執行；`CsvImportDialog`（UI 層）包含 3 步驟精靈與 `CsvImportWorker`（QThread）；`CaseView` 工具列新增觸發按鈕。Worker 在自己的執行緒內建立獨立 SQLite 連線，避免跨執行緒共用。

**Tech Stack:** Python 3.14、PySide6 6.10、SQLite（內建）、csv 模組（標準庫）、re 模組（標準庫）

**Spec:** `docs/superpowers/specs/2026-03-26-csv-import-wizard-design.md`

---

## 檔案清單

| 檔案 | 動作 | 說明 |
|------|------|------|
| `src/hcp_cms/core/csv_import_engine.py` | 新增 | 型別定義 + Engine 所有邏輯 |
| `src/hcp_cms/ui/csv_import_dialog.py` | 新增 | Dialog（Step 1-3）+ CsvImportWorker |
| `src/hcp_cms/ui/case_view.py` | 修改 | 加入 db_path 參數 + 匯入按鈕 |
| `src/hcp_cms/ui/main_window.py` | 修改 | 傳遞 db_path 給 CaseView |
| `tests/unit/test_csv_import_engine.py` | 新增 | Core 層單元測試 |

---

## Task 1：型別定義 + sent_time 解析器

**Files:**
- Create: `src/hcp_cms/core/csv_import_engine.py`
- Create: `tests/unit/test_csv_import_engine.py`

- [ ] **Step 1: 建立測試檔，寫 sent_time 解析測試**

```python
# tests/unit/test_csv_import_engine.py
"""Tests for CsvImportEngine."""
from __future__ import annotations

from pathlib import Path

import pytest

from hcp_cms.core.csv_import_engine import (
    ConflictStrategy,
    CsvImportEngine,
    ImportPreview,
    ImportResult,
    _parse_sent_time,
)
from hcp_cms.data.database import DatabaseManager


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


class TestParseSentTime:
    def test_chinese_morning(self):
        result = _parse_sent_time("2026/3/2 (週一) 上午 09:27")
        assert result == "2026/03/02 09:27:00"

    def test_chinese_afternoon(self):
        result = _parse_sent_time("2026/3/2 (週一) 下午 03:25")
        assert result == "2026/03/02 15:25:00"

    def test_chinese_noon(self):
        # 下午 12:00 → 12:00（不加 12）
        result = _parse_sent_time("2026/3/2 (週一) 下午 12:00")
        assert result == "2026/03/02 12:00:00"

    def test_chinese_morning_noon(self):
        # 上午 12:00 → 00:00
        result = _parse_sent_time("2026/3/2 (週一) 上午 12:00")
        assert result == "2026/03/02 00:00:00"

    def test_iso_with_seconds(self):
        result = _parse_sent_time("2026/03/02 09:27:00")
        assert result == "2026/03/02 09:27:00"

    def test_iso_without_seconds(self):
        result = _parse_sent_time("2026/03/02 09:27")
        assert result == "2026/03/02 09:27:00"

    def test_date_only(self):
        result = _parse_sent_time("2026/03/02")
        assert result == "2026/03/02 00:00:00"

    def test_invalid_returns_none(self):
        result = _parse_sent_time("無效格式")
        assert result is None

    def test_empty_returns_none(self):
        result = _parse_sent_time("")
        assert result is None

    def test_none_returns_none(self):
        result = _parse_sent_time(None)
        assert result is None
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_csv_import_engine.py::TestParseSentTime -v
```
預期：`ImportError: cannot import name '_parse_sent_time'`

- [ ] **Step 3: 建立 `csv_import_engine.py`，實作型別定義與 `_parse_sent_time`**

```python
# src/hcp_cms/core/csv_import_engine.py
"""CsvImportEngine — CSV 歷史客服記錄批次匯入。"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# 型別定義
# ---------------------------------------------------------------------------

@dataclass
class ImportPreview:
    total: int = 0
    new_count: int = 0
    conflict_count: int = 0


@dataclass
class ImportResult:
    success: int = 0
    skipped: int = 0
    overwritten: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


class ConflictStrategy(Enum):
    SKIP = "skip"
    OVERWRITE = "overwrite"


# mapping 方向：{csv_欄名: db_欄名} 或 {csv_欄名: "skip"}
Mapping = dict[str, str]

# 下拉選單可用欄位（排除自動欄位）
MAPPABLE_DB_COLS = [
    "skip",
    "status", "progress", "sent_time", "company_id", "contact_person",
    "subject", "system_product", "issue_type", "error_type", "impact_period",
    "actual_reply", "reply_time", "notes", "rd_assignee", "handler",
    "priority", "contact_method",
]

# 預設欄位對應（CSV 欄名 → db 欄名）
DEFAULT_MAPPING: Mapping = {
    "問題狀態": "status",
    "處理進度": "progress",
    "寄件時間": "sent_time",
    "公司": "company_id",
    "聯絡人": "contact_person",
    "主旨": "subject",
    "對客服的難易度": "priority",
    "技術協助人員1": "rd_assignee",
    "技術協助人員2": "notes",  # 特殊附加處理
    "【Type】": "issue_type",
    "問題分類": "error_type",
}

# 必須對應（不可為 skip）的欄位（db 欄名）
REQUIRED_DB_COLS = {"sent_time", "subject", "company_id"}

# 中文星期日轉換（解析用，不需要實際轉換）
_WEEKDAY_RE = re.compile(r'\s*\(週.\)\s*')
_AMPM_RE = re.compile(r'(上午|下午)\s*(\d{1,2}):(\d{2})')
_TECH2_RE = re.compile(r'\n【技術協助2】.*', re.DOTALL)


def _parse_sent_time(value: str | None) -> str | None:
    """解析各種 sent_time 格式，回傳 YYYY/MM/DD HH:MM:SS，失敗回傳 None。"""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None

    # 嘗試中文上午/下午格式：2026/3/2 (週一) 上午 09:27
    m = _AMPM_RE.search(s)
    if m:
        ampm, h_str, mn_str = m.group(1), m.group(2), m.group(3)
        h = int(h_str)
        mn = int(mn_str)
        if ampm == "下午" and h < 12:
            h += 12
        elif ampm == "上午" and h == 12:
            h = 0
        # 取日期部分（移除星期）
        date_part = _WEEKDAY_RE.sub(" ", s).split()[0]
        try:
            parts = date_part.split("/")
            y, mo, d = int(parts[0]), int(parts[1]), int(parts[2])
            return f"{y}/{mo:02d}/{d:02d} {h:02d}:{mn:02d}:00"
        except (ValueError, IndexError):
            return None

    # 移除星期部分後嘗試其他格式
    s = _WEEKDAY_RE.sub(" ", s).strip()

    # YYYY/MM/DD HH:MM:SS
    try:
        from datetime import datetime
        dt = datetime.strptime(s, "%Y/%m/%d %H:%M:%S")
        return dt.strftime("%Y/%m/%d %H:%M:%S")
    except ValueError:
        pass

    # YYYY/MM/DD HH:MM
    try:
        from datetime import datetime
        dt = datetime.strptime(s, "%Y/%m/%d %H:%M")
        return dt.strftime("%Y/%m/%d %H:%M:%S")
    except ValueError:
        pass

    # YYYY/MM/DD
    try:
        from datetime import datetime
        dt = datetime.strptime(s, "%Y/%m/%d")
        return dt.strftime("%Y/%m/%d %H:%M:%S")
    except ValueError:
        pass

    return None
```

- [ ] **Step 4: 執行測試確認通過**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_csv_import_engine.py::TestParseSentTime -v
```
預期：10 tests PASSED

- [ ] **Step 5: Commit**

```bash
cd D:/CMS && git add src/hcp_cms/core/csv_import_engine.py tests/unit/test_csv_import_engine.py
git commit -m "feat: CsvImportEngine 型別定義與 sent_time 解析器（Task 1）"
```

---

## Task 2：parse_headers + 編碼偵測

**Files:**
- Modify: `src/hcp_cms/core/csv_import_engine.py`
- Modify: `tests/unit/test_csv_import_engine.py`

- [ ] **Step 1: 新增測試（在 test 檔末尾加入）**

```python
class TestParseHeaders:
    def test_utf8_csv(self, tmp_path: Path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("問題狀態,主旨,寄件時間\n待確認,測試,2026/01/01\n", encoding="utf-8")
        engine = CsvImportEngine.__new__(CsvImportEngine)
        headers = engine.parse_headers(csv_file)
        assert headers == ["問題狀態", "主旨", "寄件時間"]

    def test_utf8_bom_csv(self, tmp_path: Path):
        csv_file = tmp_path / "test_bom.csv"
        csv_file.write_bytes(
            "問題狀態,主旨\n".encode("utf-8-sig") + "待確認,測試\n".encode("utf-8")
        )
        engine = CsvImportEngine.__new__(CsvImportEngine)
        headers = engine.parse_headers(csv_file)
        assert headers[0] == "問題狀態"  # BOM 已移除

    def test_big5_csv(self, tmp_path: Path):
        csv_file = tmp_path / "test_big5.csv"
        csv_file.write_bytes("問題狀態,主旨\n".encode("big5"))
        engine = CsvImportEngine.__new__(CsvImportEngine)
        headers = engine.parse_headers(csv_file)
        assert "問題狀態" in headers

    def test_invalid_encoding_raises(self, tmp_path: Path):
        csv_file = tmp_path / "test_bad.csv"
        csv_file.write_bytes(b"\xff\xfe\x00\x01\x02")  # 無效編碼
        engine = CsvImportEngine.__new__(CsvImportEngine)
        with pytest.raises(ValueError, match="無法識別編碼"):
            engine.parse_headers(csv_file)
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_csv_import_engine.py::TestParseHeaders -v
```
預期：AttributeError（parse_headers 不存在）

- [ ] **Step 3: 在 `CsvImportEngine` 類別中加入 `parse_headers` 與私有輔助方法**

在 `csv_import_engine.py` 末尾加入：

```python
# ---------------------------------------------------------------------------
# CsvImportEngine
# ---------------------------------------------------------------------------

def _detect_encoding(path: Path) -> str:
    """依序嘗試 UTF-8-BOM、UTF-8、Big5，回傳可用編碼，失敗拋 ValueError。"""
    for enc in ("utf-8-sig", "utf-8", "big5"):
        try:
            path.read_text(encoding=enc)
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"無法識別編碼：{path.name}")


class CsvImportEngine:
    """CSV 歷史客服記錄批次匯入引擎。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        from hcp_cms.data.repositories import CaseRepository, CompanyRepository
        self._conn = conn
        self._case_repo = CaseRepository(conn)
        self._company_repo = CompanyRepository(conn)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_headers(self, path: Path) -> list[str]:
        """偵測編碼並回傳 CSV 標頭清單。"""
        import csv
        enc = _detect_encoding(path)
        with path.open(encoding=enc, newline="") as f:
            reader = csv.reader(f)
            headers = next(reader, [])
        return headers
```

- [ ] **Step 4: 執行測試確認通過**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_csv_import_engine.py::TestParseHeaders -v
```
預期：4 tests PASSED

- [ ] **Step 5: Commit**

```bash
cd D:/CMS && git add src/hcp_cms/core/csv_import_engine.py tests/unit/test_csv_import_engine.py
git commit -m "feat: CsvImportEngine.parse_headers 與編碼自動偵測（Task 2）"
```

---

## Task 3：case_id 產生器 + 資料列建構

**Files:**
- Modify: `src/hcp_cms/core/csv_import_engine.py`
- Modify: `tests/unit/test_csv_import_engine.py`

- [ ] **Step 1: 新增 case_id 測試**

```python
class TestNextCaseId:
    def test_first_id_for_month(self, db: DatabaseManager):
        engine = CsvImportEngine(db.connection)
        base: dict[str, int] = {}
        result = engine._next_case_id("202510", base)
        assert result == "CS-202510-001"

    def test_sequential_ids_same_month(self, db: DatabaseManager):
        engine = CsvImportEngine(db.connection)
        base: dict[str, int] = {}
        id1 = engine._next_case_id("202510", base)
        id2 = engine._next_case_id("202510", base)
        id3 = engine._next_case_id("202510", base)
        assert id1 == "CS-202510-001"
        assert id2 == "CS-202510-002"
        assert id3 == "CS-202510-003"

    def test_different_months_independent(self, db: DatabaseManager):
        engine = CsvImportEngine(db.connection)
        base: dict[str, int] = {}
        id_oct = engine._next_case_id("202510", base)
        id_nov = engine._next_case_id("202511", base)
        assert id_oct == "CS-202510-001"
        assert id_nov == "CS-202511-001"

    def test_continues_from_existing_max(self, db: DatabaseManager):
        # 先插入既有記錄
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject, status) VALUES (?, ?, ?)",
            ("CS-202510-007", "舊案件", "已完成")
        )
        db.connection.commit()
        engine = CsvImportEngine(db.connection)
        base: dict[str, int] = {}
        result = engine._next_case_id("202510", base)
        assert result == "CS-202510-008"

    def test_old_format_does_not_interfere(self, db: DatabaseManager):
        # 插入舊格式 CS-YYYY-NNN，不應影響 CS-YYYYMM-NNN 流水號
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject, status) VALUES (?, ?, ?)",
            ("CS-2025-010", "舊格式案件", "已完成")
        )
        db.connection.commit()
        engine = CsvImportEngine(db.connection)
        base: dict[str, int] = {}
        result = engine._next_case_id("202510", base)
        assert result == "CS-202510-001"  # 不受舊格式影響
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_csv_import_engine.py::TestNextCaseId -v
```
預期：AttributeError（`_next_case_id` 不存在）

- [ ] **Step 3: 在 `CsvImportEngine` 加入 `_next_case_id` 與 `_build_row` 私有方法**

在 `CsvImportEngine` class 內加入：

```python
    def _next_case_id(self, year_month: str, base: dict[str, int]) -> str:
        """依月份快取產生 CS-YYYYMM-NNN 格式 case_id。"""
        if year_month not in base:
            row = self._conn.execute(
                "SELECT MAX(case_id) FROM cs_cases WHERE case_id LIKE ?",
                (f"CS-{year_month}-%",),
            ).fetchone()
            max_id: str | None = row[0] if row else None
            base[year_month] = int(max_id[-3:]) if max_id else 0
        base[year_month] += 1
        return f"CS-{year_month}-{base[year_month]:03d}"

    def _extract_year_month(self, sent_time_normalized: str | None) -> str:
        """從標準化 sent_time 取 YYYYMM，失敗時用當下年月。"""
        from datetime import datetime
        if sent_time_normalized:
            try:
                dt = datetime.strptime(sent_time_normalized[:7], "%Y/%m")
                return dt.strftime("%Y%m")
            except ValueError:
                pass
        return datetime.now().strftime("%Y%m")

    def _append_tech2(self, existing_notes: str | None, tech2_value: str) -> str:
        """附加技術協助人員2至 notes，移除舊值後重新附加。"""
        base = _TECH2_RE.sub("", existing_notes or "").rstrip()
        if tech2_value:
            return base + f"\n【技術協助2】{tech2_value}"
        return base

    def _build_case_dict(
        self,
        row: dict[str, str],
        mapping: Mapping,
        case_id: str,
    ) -> dict[str, object]:
        """將一列 CSV 資料依 mapping 轉換為 cs_cases 欄位字典。"""
        from datetime import datetime
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

        result: dict[str, object] = {
            "case_id": case_id,
            "source": "csv_import",
            "created_at": now,
            "updated_at": now,
            "contact_method": "Email",
            "replied": "否",
            "status": "處理中",
            "priority": "中",
        }

        tech2_col: str | None = None
        for csv_col, db_col in mapping.items():
            if db_col == "skip":
                continue
            val = row.get(csv_col, "") or ""
            if db_col == "notes" and csv_col == "技術協助人員2":
                # 技術協助人員2 特殊附加格式（僅限此欄名）
                tech2_col = csv_col
                continue
            if db_col == "sent_time":
                result[db_col] = _parse_sent_time(val)
            elif db_col == "company_id":
                result[db_col] = val.strip() or None
            else:
                result[db_col] = val or None

        # 技術協助人員2 附加
        if tech2_col is not None:
            tech2_val = (row.get(tech2_col, "") or "").strip()
            existing = str(result.get("notes") or "")
            result["notes"] = self._append_tech2(existing, tech2_val) or None

        return result
```

- [ ] **Step 4: 執行測試確認通過**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_csv_import_engine.py::TestNextCaseId -v
```
預期：5 tests PASSED

- [ ] **Step 5: Commit**

```bash
cd D:/CMS && git add src/hcp_cms/core/csv_import_engine.py tests/unit/test_csv_import_engine.py
git commit -m "feat: CsvImportEngine._next_case_id + _build_case_dict（Task 3）"
```

---

## Task 4：preview()

**Files:**
- Modify: `src/hcp_cms/core/csv_import_engine.py`
- Modify: `tests/unit/test_csv_import_engine.py`

- [ ] **Step 1: 新增 preview 測試**

```python
class TestPreview:
    def _write_csv(self, tmp_path: Path, rows: list[str]) -> Path:
        csv_file = tmp_path / "cases.csv"
        content = "問題狀態,寄件時間,公司,聯絡人,主旨\n" + "\n".join(rows)
        csv_file.write_text(content, encoding="utf-8")
        return csv_file

    def test_all_new(self, db: DatabaseManager, tmp_path: Path):
        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,達爾,王小明,測試主旨1",
            "已回覆,2026/03/02 10:00,博大,李小花,測試主旨2",
        ])
        engine = CsvImportEngine(db.connection)
        mapping = {
            "問題狀態": "status", "寄件時間": "sent_time",
            "公司": "company_id", "聯絡人": "contact_person", "主旨": "subject",
        }
        preview = engine.preview(csv_file, mapping)
        assert preview.total == 2
        assert preview.new_count == 2
        assert preview.conflict_count == 0

    def test_partial_conflict(self, db: DatabaseManager, tmp_path: Path):
        # 先插入一筆相同 case_id 的資料
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject, status) VALUES (?, ?, ?)",
            ("CS-202603-001", "既有案件", "已完成")
        )
        db.connection.commit()

        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,達爾,王小明,測試主旨1",
            "已回覆,2026/03/02 10:00,博大,李小花,測試主旨2",
        ])
        engine = CsvImportEngine(db.connection)
        mapping = {
            "問題狀態": "status", "寄件時間": "sent_time",
            "公司": "company_id", "聯絡人": "contact_person", "主旨": "subject",
        }
        preview = engine.preview(csv_file, mapping)
        assert preview.total == 2
        assert preview.conflict_count == 1
        assert preview.new_count == 1
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_csv_import_engine.py::TestPreview -v
```
預期：AttributeError（`preview` 不存在）

- [ ] **Step 3: 實作 `preview()`**

在 `CsvImportEngine` 加入：

```python
    def preview(self, path: Path, mapping: Mapping) -> ImportPreview:
        """計算 CSV 中新增/衝突筆數（不寫入資料庫）。"""
        import csv
        enc = _detect_encoding(path)
        result = ImportPreview()
        base: dict[str, int] = {}

        with path.open(encoding=enc, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                result.total += 1
                sent_time_raw = row.get(
                    next((c for c, d in mapping.items() if d == "sent_time"), ""), ""
                )
                normalized = _parse_sent_time(sent_time_raw)
                year_month = self._extract_year_month(normalized)
                case_id = self._next_case_id(year_month, base)

                existing = self._conn.execute(
                    "SELECT 1 FROM cs_cases WHERE case_id = ?", (case_id,)
                ).fetchone()
                if existing:
                    result.conflict_count += 1
                else:
                    result.new_count += 1

        return result
```

- [ ] **Step 4: 執行測試確認通過**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_csv_import_engine.py::TestPreview -v
```
預期：2 tests PASSED

- [ ] **Step 5: Commit**

```bash
cd D:/CMS && git add src/hcp_cms/core/csv_import_engine.py tests/unit/test_csv_import_engine.py
git commit -m "feat: CsvImportEngine.preview()（Task 4）"
```

---

## Task 5：execute() — SKIP 模式 + 公司自動建立

**Files:**
- Modify: `src/hcp_cms/core/csv_import_engine.py`
- Modify: `tests/unit/test_csv_import_engine.py`

- [ ] **Step 1: 新增 execute SKIP 測試**

```python
class TestExecuteSkip:
    def _write_csv(self, tmp_path: Path, rows: list[str]) -> Path:
        csv_file = tmp_path / "cases.csv"
        content = "問題狀態,寄件時間,公司,聯絡人,主旨,技術協助人員2\n" + "\n".join(rows)
        csv_file.write_text(content, encoding="utf-8")
        return csv_file

    @pytest.fixture
    def mapping(self):
        return {
            "問題狀態": "status", "寄件時間": "sent_time",
            "公司": "company_id", "聯絡人": "contact_person",
            "主旨": "subject", "技術協助人員2": "notes",
        }

    def test_inserts_new_cases(self, db: DatabaseManager, tmp_path: Path, mapping):
        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,達爾,王小明,測試主旨,",
        ])
        engine = CsvImportEngine(db.connection)
        result = engine.execute(csv_file, mapping, ConflictStrategy.SKIP)
        assert result.success == 1
        assert result.failed == 0
        case = db.connection.execute(
            "SELECT * FROM cs_cases WHERE case_id = 'CS-202603-001'"
        ).fetchone()
        assert case is not None
        assert case["subject"] == "測試主旨"
        assert case["source"] == "csv_import"

    def test_auto_creates_company(self, db: DatabaseManager, tmp_path: Path, mapping):
        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,新客戶,王小明,主旨,",
        ])
        engine = CsvImportEngine(db.connection)
        engine.execute(csv_file, mapping, ConflictStrategy.SKIP)
        company = db.connection.execute(
            "SELECT * FROM companies WHERE company_id = '新客戶'"
        ).fetchone()
        assert company is not None

    def test_company_idempotent(self, db: DatabaseManager, tmp_path: Path, mapping):
        # 同一公司出現兩次，只建一筆
        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,達爾,王小明,主旨1,",
            "已回覆,2026/03/02 10:00,達爾,李小花,主旨2,",
        ])
        engine = CsvImportEngine(db.connection)
        engine.execute(csv_file, mapping, ConflictStrategy.SKIP)
        count = db.connection.execute(
            "SELECT COUNT(*) FROM companies WHERE company_id = '達爾'"
        ).fetchone()[0]
        assert count == 1

    def test_blank_company_no_company_record(self, db: DatabaseManager, tmp_path: Path, mapping):
        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,,王小明,主旨,",
        ])
        engine = CsvImportEngine(db.connection)
        engine.execute(csv_file, mapping, ConflictStrategy.SKIP)
        case = db.connection.execute("SELECT company_id FROM cs_cases").fetchone()
        assert case["company_id"] is None

    def test_skips_on_conflict(self, db: DatabaseManager, tmp_path: Path, mapping):
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject, status) VALUES (?, ?, ?)",
            ("CS-202603-001", "既有", "已完成")
        )
        db.connection.commit()
        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,達爾,王小明,新主旨,",
        ])
        engine = CsvImportEngine(db.connection)
        result = engine.execute(csv_file, mapping, ConflictStrategy.SKIP)
        assert result.skipped == 1
        assert result.success == 0
        # 原資料未被改變
        case = db.connection.execute(
            "SELECT subject FROM cs_cases WHERE case_id = 'CS-202603-001'"
        ).fetchone()
        assert case["subject"] == "既有"

    def test_invalid_sent_time_skipped(self, db: DatabaseManager, tmp_path: Path, mapping):
        csv_file = self._write_csv(tmp_path, [
            "待確認,無效日期,達爾,王小明,主旨,",
        ])
        engine = CsvImportEngine(db.connection)
        result = engine.execute(csv_file, mapping, ConflictStrategy.SKIP)
        assert result.failed == 1
        assert "sent_time 格式錯誤" in result.errors[0]

    def test_tech2_appended_to_notes(self, db: DatabaseManager, tmp_path: Path, mapping):
        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,達爾,王小明,主旨,技術王",
        ])
        engine = CsvImportEngine(db.connection)
        engine.execute(csv_file, mapping, ConflictStrategy.SKIP)
        case = db.connection.execute("SELECT notes FROM cs_cases").fetchone()
        assert "【技術協助2】技術王" in (case["notes"] or "")

    def test_empty_subject_skipped(self, db: DatabaseManager, tmp_path: Path, mapping):
        csv_file = self._write_csv(tmp_path, [
            "待確認,2026/03/01 09:00,達爾,王小明,,",  # subject 為空
        ])
        engine = CsvImportEngine(db.connection)
        result = engine.execute(csv_file, mapping, ConflictStrategy.SKIP)
        assert result.failed == 1
        assert "subject 為空" in result.errors[0]
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_csv_import_engine.py::TestExecuteSkip -v
```
預期：AttributeError（`execute` 不存在）

- [ ] **Step 3: 實作 `execute()` 與私有輔助方法**

在 `CsvImportEngine` 加入：

```python
    def _ensure_company(self, company_name: str) -> None:
        """若公司不存在則自動建立（INSERT OR IGNORE）。"""
        from datetime import datetime
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        self._conn.execute(
            """INSERT OR IGNORE INTO companies
               (company_id, name, domain, created_at)
               VALUES (?, ?, ?, ?)""",
            (company_name, company_name, company_name, now),
        )

    def execute(
        self,
        path: Path,
        mapping: Mapping,
        strategy: ConflictStrategy,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> ImportResult:
        """執行匯入。"""
        import csv
        from datetime import datetime

        enc = _detect_encoding(path)
        result = ImportResult()
        base: dict[str, int] = {}

        # 計算總列數（供進度條用）
        with path.open(encoding=enc, newline="") as f:
            total = sum(1 for _ in csv.reader(f)) - 1  # 減掉標頭

        with path.open(encoding=enc, newline="") as f:
            reader = csv.DictReader(f)
            for line_no, row in enumerate(reader, start=2):  # 2 = 第一列資料
                if progress_cb:
                    progress_cb(line_no - 1, total)

                # --- 解析 sent_time ---
                sent_time_csv_col = next(
                    (c for c, d in mapping.items() if d == "sent_time"), None
                )
                sent_time_raw = row.get(sent_time_csv_col or "", "") if sent_time_csv_col else ""
                normalized_time = _parse_sent_time(sent_time_raw)
                if normalized_time is None:
                    result.failed += 1
                    result.errors.append(f"第 {line_no} 列：sent_time 格式錯誤（{sent_time_raw!r}）")
                    continue

                # --- 驗證 subject ---
                subject_csv_col = next(
                    (c for c, d in mapping.items() if d == "subject"), None
                )
                subject_val = (row.get(subject_csv_col or "", "") or "").strip() if subject_csv_col else ""
                if not subject_val:
                    result.failed += 1
                    result.errors.append(f"第 {line_no} 列：subject 為空")
                    continue

                # --- 產生 case_id ---
                year_month = self._extract_year_month(normalized_time)
                case_id = self._next_case_id(year_month, base)

                # --- 公司自動建立 ---
                company_csv_col = next(
                    (c for c, d in mapping.items() if d == "company_id"), None
                )
                company_name = (row.get(company_csv_col or "", "") or "").strip() if company_csv_col else ""
                if company_name:
                    self._ensure_company(company_name)

                # --- 建構資料列 ---
                case_dict = self._build_case_dict(row, mapping, case_id)

                # --- 寫入 ---
                try:
                    existing = self._conn.execute(
                        "SELECT created_at FROM cs_cases WHERE case_id = ?", (case_id,)
                    ).fetchone()

                    if existing:
                        if strategy == ConflictStrategy.SKIP:
                            result.skipped += 1
                        else:  # OVERWRITE
                            self._overwrite_case(case_id, case_dict, existing["created_at"])
                            result.overwritten += 1
                    else:
                        self._insert_case(case_dict)
                        result.success += 1

                except Exception as e:
                    result.failed += 1
                    result.errors.append(f"第 {line_no} 列：資料庫錯誤 {e}")

        if progress_cb:
            progress_cb(total, total)
        return result

    def _insert_case(self, case_dict: dict[str, object]) -> None:
        cols = list(case_dict.keys())
        vals = [case_dict[c] for c in cols]
        placeholders = ", ".join("?" for _ in cols)
        col_list = ", ".join(cols)
        self._conn.execute(
            f"INSERT INTO cs_cases ({col_list}) VALUES ({placeholders})", vals
        )
        self._conn.commit()

    def _overwrite_case(
        self, case_id: str, case_dict: dict[str, object], original_created_at: str
    ) -> None:
        from datetime import datetime
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        update_dict = {k: v for k, v in case_dict.items()
                       if k not in ("case_id", "created_at", "source")}
        update_dict["updated_at"] = now
        set_clause = ", ".join(f"{k} = ?" for k in update_dict)
        vals = list(update_dict.values()) + [case_id]
        self._conn.execute(
            f"UPDATE cs_cases SET {set_clause} WHERE case_id = ?", vals
        )
        self._conn.commit()
```

- [ ] **Step 4: 執行測試確認通過**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_csv_import_engine.py::TestExecuteSkip -v
```
預期：7 tests PASSED

- [ ] **Step 5: Commit**

```bash
cd D:/CMS && git add src/hcp_cms/core/csv_import_engine.py tests/unit/test_csv_import_engine.py
git commit -m "feat: CsvImportEngine.execute() SKIP 模式 + 公司自動建立（Task 5）"
```

---

## Task 6：execute() — OVERWRITE 模式

**Files:**
- Modify: `tests/unit/test_csv_import_engine.py`

- [ ] **Step 1: 新增 OVERWRITE 測試**

```python
class TestExecuteOverwrite:
    def _write_csv(self, tmp_path: Path, subject: str) -> Path:
        csv_file = tmp_path / "cases.csv"
        content = (
            "問題狀態,寄件時間,公司,聯絡人,主旨,技術協助人員2\n"
            f"待確認,2026/03/01 09:00,達爾,王小明,{subject},"
        )
        csv_file.write_text(content, encoding="utf-8")
        return csv_file

    @pytest.fixture
    def mapping(self):
        return {
            "問題狀態": "status", "寄件時間": "sent_time",
            "公司": "company_id", "聯絡人": "contact_person",
            "主旨": "subject", "技術協助人員2": "notes",
        }

    def test_overwrites_subject(self, db: DatabaseManager, tmp_path: Path, mapping):
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject, status, created_at) VALUES (?, ?, ?, ?)",
            ("CS-202603-001", "舊主旨", "已完成", "2025/01/01 00:00:00")
        )
        db.connection.commit()
        csv_file = self._write_csv(tmp_path, "新主旨")
        engine = CsvImportEngine(db.connection)
        result = engine.execute(csv_file, mapping, ConflictStrategy.OVERWRITE)
        assert result.overwritten == 1
        case = db.connection.execute(
            "SELECT subject, created_at FROM cs_cases WHERE case_id = 'CS-202603-001'"
        ).fetchone()
        assert case["subject"] == "新主旨"
        assert case["created_at"] == "2025/01/01 00:00:00"  # created_at 保留

    def test_overwrite_tech2_replaces_old(self, db: DatabaseManager, tmp_path: Path):
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject, status, notes) VALUES (?, ?, ?, ?)",
            ("CS-202603-001", "主旨", "待確認", "原備註\n【技術協助2】舊技術員")
        )
        db.connection.commit()
        csv_file = tmp_path / "c.csv"
        csv_file.write_text(
            "問題狀態,寄件時間,公司,聯絡人,主旨,技術協助人員2\n"
            "待確認,2026/03/01 09:00,達爾,王小明,主旨,新技術員",
            encoding="utf-8"
        )
        mapping = {
            "問題狀態": "status", "寄件時間": "sent_time",
            "公司": "company_id", "聯絡人": "contact_person",
            "主旨": "subject", "技術協助人員2": "notes",
        }
        engine = CsvImportEngine(db.connection)
        engine.execute(csv_file, mapping, ConflictStrategy.OVERWRITE)
        case = db.connection.execute("SELECT notes FROM cs_cases").fetchone()
        assert "新技術員" in (case["notes"] or "")
        assert "舊技術員" not in (case["notes"] or "")
```

- [ ] **Step 2: 執行測試確認通過（OVERWRITE 已在 Task 5 實作）**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_csv_import_engine.py::TestExecuteOverwrite -v
```
預期：2 tests PASSED

- [ ] **Step 3: 執行全部 Engine 測試**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_csv_import_engine.py -v
```
預期：全部 PASSED

- [ ] **Step 4: Commit**

```bash
cd D:/CMS && git add tests/unit/test_csv_import_engine.py
git commit -m "test: 補充 CsvImportEngine OVERWRITE 模式測試（Task 6）"
```

---

## Task 7：CaseView 加入 db_path + 匯入按鈕

**Files:**
- Modify: `src/hcp_cms/ui/case_view.py`
- Modify: `src/hcp_cms/ui/main_window.py`

- [ ] **Step 1: 修改 `main_window.py`，傳遞 db_path 給 CaseView**

在 `main_window.py` 第 107 行（`"cases": CaseView(self._conn),`）修改為：

```python
"cases": CaseView(self._conn, db_path=self._db_dir / "cs_tracker.db" if self._db_dir else None),
```

- [ ] **Step 2: 修改 `case_view.py`，新增 `db_path` 參數與匯入按鈕**

1. 在 `__init__` 加入 `db_path` 參數：

```python
def __init__(self, conn: sqlite3.Connection | None = None, db_path: Path | None = None) -> None:
    super().__init__()
    self._conn = conn
    self._db_path = db_path
    self._setup_ui()
```

在 import 區段頂部加入：
```python
from pathlib import Path
```

2. 在 `_setup_ui` 的 header 區段（`new_btn` 後方）加入：

```python
import_btn = QPushButton("📥 匯入 CSV")
import_btn.clicked.connect(self._on_import_csv)
header.addWidget(import_btn)
```

3. 在 class 末尾加入：

```python
def _on_import_csv(self) -> None:
    if not self._db_path:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(self, "錯誤", "資料庫路徑未設定，無法匯入。")
        return
    from hcp_cms.ui.csv_import_dialog import CsvImportDialog
    dlg = CsvImportDialog(self._db_path, self)
    if dlg.exec():
        self.refresh()
```

- [ ] **Step 3: 執行應用程式確認按鈕出現**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m hcp_cms
```
預期：案件管理頁工具列出現「📥 匯入 CSV」按鈕（點擊後報 ImportError，因為 dialog 尚未建立）

- [ ] **Step 4: Commit**

```bash
cd D:/CMS && git add src/hcp_cms/ui/case_view.py src/hcp_cms/ui/main_window.py
git commit -m "feat: CaseView 加入 db_path 參數與匯入 CSV 按鈕（Task 7）"
```

---

## Task 8：CsvImportDialog Step 1 — 選擇檔案

**Files:**
- Create: `src/hcp_cms/ui/csv_import_dialog.py`

- [ ] **Step 1: 建立 Dialog 骨架與 Step 1**

```python
# src/hcp_cms/ui/csv_import_dialog.py
"""CSV 匯入精靈 — 3 步驟 QDialog。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QRadioButton,
    QButtonGroup,
)

from hcp_cms.core.csv_import_engine import (
    MAPPABLE_DB_COLS,
    DEFAULT_MAPPING,
    REQUIRED_DB_COLS,
    ConflictStrategy,
    CsvImportEngine,
    ImportPreview,
    ImportResult,
    Mapping,
    _detect_encoding,
)


class CsvImportDialog(QDialog):
    """3 步驟 CSV 匯入精靈。"""

    def __init__(self, db_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._csv_path: Path | None = None
        self._headers: list[str] = []
        self._mapping: Mapping = {}
        self._preview: ImportPreview | None = None
        self.setWindowTitle("📥 CSV 匯入精靈")
        self.setMinimumSize(700, 500)
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI 建構
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 步驟指示
        self._step_label = QLabel("步驟 1 / 3：選擇 CSV 檔案")
        self._step_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self._step_label)

        # 主體（堆疊頁）
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_step1())
        self._stack.addWidget(self._build_step2())
        self._stack.addWidget(self._build_step3())
        layout.addWidget(self._stack)

        # 底部按鈕
        btn_layout = QHBoxLayout()
        self._back_btn = QPushButton("← 上一步")
        self._back_btn.setEnabled(False)
        self._back_btn.clicked.connect(self._go_back)
        self._next_btn = QPushButton("下一步 →")
        self._next_btn.clicked.connect(self._go_next)
        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._back_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        btn_layout.addWidget(self._next_btn)
        layout.addLayout(btn_layout)

    def _build_step1(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        desc = QLabel("選擇要匯入的 CSV 檔案（支援 UTF-8、UTF-8 BOM、Big5 編碼）：")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        file_row = QHBoxLayout()
        self._file_label = QLabel("（未選擇）")
        self._file_label.setStyleSheet("color: #94a3b8;")
        browse_btn = QPushButton("瀏覽...")
        browse_btn.clicked.connect(self._on_browse)
        file_row.addWidget(self._file_label, 1)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        self._file_info = QLabel("")
        self._file_info.setWordWrap(True)
        layout.addWidget(self._file_info)

        layout.addStretch()
        return w

    # ------------------------------------------------------------------
    # Step 1 邏輯
    # ------------------------------------------------------------------

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇 CSV 檔案", "", "CSV 檔案 (*.csv);;所有檔案 (*)"
        )
        if not path:
            return
        csv_path = Path(path)
        try:
            enc = _detect_encoding(csv_path)
            import csv as csv_mod
            with csv_path.open(encoding=enc, newline="") as f:
                reader = csv_mod.reader(f)
                headers = next(reader, [])
                row_count = sum(1 for _ in reader)
        except ValueError as e:
            QMessageBox.critical(self, "編碼錯誤", str(e))
            return

        self._csv_path = csv_path
        self._headers = headers
        self._file_label.setText(csv_path.name)
        self._file_label.setStyleSheet("color: #f1f5f9;")
        self._file_info.setText(
            f"偵測編碼：{enc}　|　欄位數：{len(headers)}　|　資料筆數：{row_count}\n"
            f"欄位：{', '.join(headers[:8])}{'...' if len(headers) > 8 else ''}"
        )
        self._next_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # 導覽
    # ------------------------------------------------------------------

    def _go_next(self) -> None:
        idx = self._stack.currentIndex()
        if idx == 0:
            if not self._csv_path:
                QMessageBox.warning(self, "提示", "請先選擇 CSV 檔案。")
                return
            self._populate_step2()
            self._stack.setCurrentIndex(1)
            self._step_label.setText("步驟 2 / 3：確認欄位對應")
            self._back_btn.setEnabled(True)
            self._next_btn.setText("下一步 →")
        elif idx == 1:
            if not self._validate_step2():
                return
            self._collect_mapping()
            self._populate_step3()
            self._stack.setCurrentIndex(2)
            self._step_label.setText("步驟 3 / 3：預覽與執行")
            self._next_btn.setText("執行匯入")
        elif idx == 2:
            self._run_import()

    def _go_back(self) -> None:
        idx = self._stack.currentIndex()
        if idx == 1:
            self._stack.setCurrentIndex(0)
            self._step_label.setText("步驟 1 / 3：選擇 CSV 檔案")
            self._back_btn.setEnabled(False)
            self._next_btn.setText("下一步 →")
        elif idx == 2:
            self._stack.setCurrentIndex(1)
            self._step_label.setText("步驟 2 / 3：確認欄位對應")
            self._next_btn.setText("下一步 →")
```

- [ ] **Step 2: 確認無語法錯誤**

```bash
cd D:/CMS && .venv/Scripts/python.exe -c "from hcp_cms.ui.csv_import_dialog import CsvImportDialog; print('OK')"
```
預期：`OK`

- [ ] **Step 3: Commit**

```bash
cd D:/CMS && git add src/hcp_cms/ui/csv_import_dialog.py
git commit -m "feat: CsvImportDialog Step 1 — 選擇檔案（Task 8）"
```

---

## Task 9：CsvImportDialog Step 2 — 欄位對應

**Files:**
- Modify: `src/hcp_cms/ui/csv_import_dialog.py`

- [ ] **Step 1: 在 `_setup_ui` 的 `_build_step2()` 中加入欄位對應表**

在 `CsvImportDialog` 加入以下方法：

```python
    def _build_step2(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        desc = QLabel("左欄為 CSV 欄位，右欄選擇對應的資料庫欄位（選「skip」略過）：")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self._mapping_layout = QFormLayout(inner)
        scroll.setWidget(inner)
        layout.addWidget(scroll)

        self._combo_map: dict[str, QComboBox] = {}  # csv_col → QComboBox
        return w

    def _populate_step2(self) -> None:
        # 清除舊內容
        while self._mapping_layout.rowCount():
            self._mapping_layout.removeRow(0)
        self._combo_map.clear()

        for csv_col in self._headers:
            combo = QComboBox()
            combo.addItems(MAPPABLE_DB_COLS)
            # 預設值
            default = DEFAULT_MAPPING.get(csv_col, "skip")
            idx = combo.findText(default)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            self._combo_map[csv_col] = combo
            self._mapping_layout.addRow(csv_col, combo)

    def _validate_step2(self) -> bool:
        """檢查必填欄位（sent_time, subject, company_id）是否已對應。"""
        mapped_db_cols = {combo.currentText() for combo in self._combo_map.values()}
        missing = REQUIRED_DB_COLS - mapped_db_cols
        if missing:
            QMessageBox.warning(
                self, "必填欄位未對應",
                f"以下欄位必須對應（不可略過）：\n{', '.join(missing)}"
            )
            return False
        return True

    def _collect_mapping(self) -> None:
        self._mapping = {
            csv_col: combo.currentText()
            for csv_col, combo in self._combo_map.items()
        }
```

- [ ] **Step 2: 確認 Step 2 無語法錯誤**

```bash
cd D:/CMS && .venv/Scripts/python.exe -c "from hcp_cms.ui.csv_import_dialog import CsvImportDialog; print('OK')"
```
預期：`OK`

- [ ] **Step 3: Commit**

```bash
cd D:/CMS && git add src/hcp_cms/ui/csv_import_dialog.py
git commit -m "feat: CsvImportDialog Step 2 — 欄位對應表（Task 9）"
```

---

## Task 10：CsvImportDialog Step 3 + CsvImportWorker

**Files:**
- Modify: `src/hcp_cms/ui/csv_import_dialog.py`

- [ ] **Step 1: 加入 CsvImportWorker 與 Step 3 UI**

在 `csv_import_dialog.py` 頂部 import 區段加入：
```python
from PySide6.QtCore import QThread
```

在檔案末尾加入 `CsvImportWorker`：

```python
class CsvImportWorker(QThread):
    """在獨立執行緒執行 CsvImportEngine.execute()。"""

    progress = Signal(int, int)   # (current, total)
    finished = Signal(object)     # ImportResult

    def __init__(
        self,
        db_path: Path,
        csv_path: Path,
        mapping: Mapping,
        strategy: ConflictStrategy,
    ) -> None:
        super().__init__()
        self._db_path = db_path
        self._csv_path = csv_path
        self._mapping = mapping
        self._strategy = strategy

    def run(self) -> None:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            engine = CsvImportEngine(conn)
            result = engine.execute(
                self._csv_path,
                self._mapping,
                self._strategy,
                progress_cb=lambda c, t: self.progress.emit(c, t),
            )
            self.finished.emit(result)
        except Exception as e:
            from hcp_cms.core.csv_import_engine import ImportResult
            err = ImportResult(failed=1, errors=[str(e)])
            self.finished.emit(err)
        finally:
            conn.close()
```

在 `CsvImportDialog` 加入 Step 3 方法：

```python
    def _build_step3(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        self._preview_label = QLabel("正在計算...")
        layout.addWidget(self._preview_label)

        # 衝突策略
        strategy_label = QLabel("衝突處理：")
        layout.addWidget(strategy_label)
        self._skip_radio = QRadioButton("略過（保留現有資料）")
        self._overwrite_radio = QRadioButton("覆蓋（以 CSV 資料取代）")
        self._skip_radio.setChecked(True)
        self._strategy_group = QButtonGroup(w)
        self._strategy_group.addButton(self._skip_radio)
        self._strategy_group.addButton(self._overwrite_radio)
        layout.addWidget(self._skip_radio)
        layout.addWidget(self._overwrite_radio)

        # 進度條
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        # 結果
        self._result_text = QTextEdit()
        self._result_text.setReadOnly(True)
        self._result_text.setVisible(False)
        layout.addWidget(self._result_text)

        layout.addStretch()
        return w

    def _populate_step3(self) -> None:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            engine = CsvImportEngine(conn)
            self._preview = engine.preview(self._csv_path, self._mapping)
        finally:
            conn.close()

        p = self._preview
        self._preview_label.setText(
            f"預覽結果：共 {p.total} 筆　"
            f"新增 {p.new_count} 筆　"
            f"衝突 {p.conflict_count} 筆"
        )
        self._result_text.setVisible(False)
        self._progress_bar.setVisible(False)
        self._next_btn.setEnabled(True)

    def _run_import(self) -> None:
        strategy = (
            ConflictStrategy.OVERWRITE
            if self._overwrite_radio.isChecked()
            else ConflictStrategy.SKIP
        )
        total = self._preview.total if self._preview else 0
        self._progress_bar.setMaximum(max(total, 1))
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        self._next_btn.setEnabled(False)
        self._back_btn.setEnabled(False)

        self._worker = CsvImportWorker(
            self._db_path, self._csv_path, self._mapping, strategy
        )
        self._worker.progress.connect(
            lambda c, t: self._progress_bar.setValue(c)
        )
        self._worker.finished.connect(self._on_import_finished)
        self._worker.start()

    def _on_import_finished(self, result: ImportResult) -> None:
        self._progress_bar.setVisible(False)
        self._result_text.setVisible(True)
        lines = [
            f"✅ 匯入完成",
            f"   成功：{result.success} 筆",
            f"   略過：{result.skipped} 筆",
            f"   覆蓋：{result.overwritten} 筆",
            f"   失敗：{result.failed} 筆",
        ]
        if result.errors:
            lines.append("\n錯誤清單：")
            lines.extend(f"  • {e}" for e in result.errors[:20])
            if len(result.errors) > 20:
                lines.append(f"  ... 還有 {len(result.errors) - 20} 筆錯誤")
        self._result_text.setPlainText("\n".join(lines))
        self._next_btn.setText("完成")
        self._next_btn.setEnabled(True)
        self._next_btn.clicked.disconnect()
        self._next_btn.clicked.connect(self.accept)
```

- [ ] **Step 2: 確認整個 Dialog 無語法錯誤**

```bash
cd D:/CMS && .venv/Scripts/python.exe -c "from hcp_cms.ui.csv_import_dialog import CsvImportDialog, CsvImportWorker; print('OK')"
```
預期：`OK`

- [ ] **Step 3: 執行應用程式，端對端測試匯入流程**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m hcp_cms
```
操作步驟：
1. 進入「案件管理」頁
2. 點擊「📥 匯入 CSV」
3. Step 1：選擇 `C:\Users\Jill\Downloads\202510開始客服問題記錄 - 202603問題記錄.csv`
4. Step 2：確認欄位對應（「公司」、「聯絡人」欄應已自動對應）
5. Step 3：確認顯示預覽筆數，執行匯入
6. 確認案件列表有新資料

- [ ] **Step 4: 執行 Lint**

```bash
cd D:/CMS && .venv/Scripts/ruff.exe check src/hcp_cms/core/csv_import_engine.py src/hcp_cms/ui/csv_import_dialog.py src/hcp_cms/ui/case_view.py
```
預期：無錯誤（或僅格式警告，執行 `ruff format` 修正）

- [ ] **Step 5: 執行全部測試**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_csv_import_engine.py -v
```
預期：全部 PASSED

- [ ] **Step 6: Commit**

```bash
cd D:/CMS && git add src/hcp_cms/ui/csv_import_dialog.py
git commit -m "feat: CsvImportDialog Step 3 + CsvImportWorker — 完整匯入精靈（Task 10）"
```
