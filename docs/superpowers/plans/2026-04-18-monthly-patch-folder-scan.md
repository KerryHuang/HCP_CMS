# 每月大 PATCH 資料夾掃描功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在「每月大 PATCH」Tab 新增「掃描資料夾」來源，自動解壓 11G/12C 子目錄內所有封存、彙整 Issue、產出帶測試報告超連結的 `PATCH_LIST_YYYYMM_11G.xlsx`。

**Architecture:** `MonthlyPatchEngine` 新增 `scan_monthly_dir()` 與 `generate_patch_list_from_dir()` 兩個方法；`MonthlyPatchTab` 加入第三個來源選項「掃描資料夾」，與現有「上傳檔案」、「Mantis」共存。掃描的檔案資訊（FORM/SQL/MUTI 清單）以 JSON 儲存在 `PatchIssue.mantis_detail`，無需修改資料庫 schema。

**Tech Stack:** Python 3.14, py7zr 1.1, zipfile（標準庫）, openpyxl 3.1, PySide6 6.10, SQLite

---

## 檔案結構

| 動作 | 檔案 | 說明 |
|---|---|---|
| Modify | `src/hcp_cms/core/monthly_patch_engine.py` | 新增 scan / generate 方法 |
| Modify | `src/hcp_cms/ui/patch_monthly_tab.py` | 新增「掃描資料夾」來源 UI |
| Modify | `tests/unit/test_monthly_patch_engine.py` | 新增 scan / generate 測試 |
| Modify | `tests/unit/test_patch_monthly_tab.py` | 新增 UI 來源切換測試 |

---

## Task 1: MonthlyPatchEngine — scan_monthly_dir()

**Files:**
- Modify: `src/hcp_cms/core/monthly_patch_engine.py`
- Test: `tests/unit/test_monthly_patch_engine.py`

### 背景知識

月份資料夾結構（模式 A，主要）：
```
202412/
├── 11G/
│   ├── 01.IP_20241128_0016552_11G.7z   ← 單一 Issue 封存
│   ├── 02.IP_20241128_0015371_11G.7z
│   └── 測試報告/
│       ├── 01.IP_20241204_0016552_TESTREPORT_11G.doc
│       └── 02.IP_20241118_0015371_TESTREPORT_11G.doc
└── 12C/（相同結構）
```

模式 B（平坦，需自動整理）：
```
202501/
├── 01.IP_20241128_0016552_11G.7z
├── 01.IP_20241128_0016552_12C.zip
├── 01.IP_20241204_0016552_TESTREPORT_11G.doc
└── 01.IP_20241204_0016552_TESTREPORT_12C.doc
```

### `__init__` 修改

`MonthlyPatchEngine.__init__` 需存 `self._conn` 以供內部使用 `SinglePatchEngine`（讀取 ReleaseNote）：

```python
def __init__(self, conn: sqlite3.Connection) -> None:
    self._conn = conn          # 新增這行
    self._repo = PatchRepository(conn)
```

- [ ] **Step 1: 寫失敗測試（__init__ 存 _conn）**

在 `tests/unit/test_monthly_patch_engine.py` 最後加：

```python
class TestScanMonthlyDir:
    def test_engine_stores_conn(self, conn):
        eng = MonthlyPatchEngine(conn)
        assert eng._conn is conn
```

- [ ] **Step 2: 確認測試失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestScanMonthlyDir::test_engine_stores_conn -v
```

Expected: `FAILED` — AttributeError: 'MonthlyPatchEngine' object has no attribute '_conn'

- [ ] **Step 3: 實作 — 在 `__init__` 加 `self._conn = conn`**

```python
# src/hcp_cms/core/monthly_patch_engine.py  MonthlyPatchEngine.__init__
def __init__(self, conn: sqlite3.Connection) -> None:
    self._conn = conn
    self._repo = PatchRepository(conn)
```

- [ ] **Step 4: 確認測試通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestScanMonthlyDir::test_engine_stores_conn -v
```

Expected: `PASSED`

---

- [ ] **Step 5: 寫失敗測試（detect_structure）**

```python
    def test_detect_structure_mode_a(self, conn, tmp_path):
        (tmp_path / "11G").mkdir()
        eng = MonthlyPatchEngine(conn)
        assert eng._detect_structure(tmp_path) == "A"

    def test_detect_structure_mode_b(self, conn, tmp_path):
        (tmp_path / "01.IP_20241128_0016552_11G.7z").write_bytes(b"")
        eng = MonthlyPatchEngine(conn)
        assert eng._detect_structure(tmp_path) == "B"
```

- [ ] **Step 6: 確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestScanMonthlyDir::test_detect_structure_mode_a tests/unit/test_monthly_patch_engine.py::TestScanMonthlyDir::test_detect_structure_mode_b -v
```

Expected: `FAILED` — AttributeError

- [ ] **Step 7: 實作 `_detect_structure`**

在 `MonthlyPatchEngine` 類別（`get_issues` 方法後）新增：

```python
# ── 資料夾掃描 ────────────────────────────────────────────────────────────────

_ARCHIVE_RE = re.compile(r"\d{2}\.IP_\d{8}_(\d{7})_", re.IGNORECASE)

def _detect_structure(self, base: Path) -> str:
    """回傳 'A'（有 11G/12C 子目錄）或 'B'（平坦）。"""
    if (base / "11G").exists() or (base / "12C").exists():
        return "A"
    return "B"
```

- [ ] **Step 8: 確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestScanMonthlyDir -v
```

Expected: 2 PASSED

---

- [ ] **Step 9: 寫失敗測試（_reorganize_to_mode_a）**

```python
    def test_reorganize_to_mode_a(self, conn, tmp_path):
        # 模式 B 平坦結構
        (tmp_path / "01.IP_20241128_0016552_11G.7z").write_bytes(b"dummy")
        (tmp_path / "01.IP_20241128_0016552_12C.zip").write_bytes(b"dummy")
        (tmp_path / "01.IP_20241204_0016552_TESTREPORT_11G.doc").write_bytes(b"dummy")
        (tmp_path / "01.IP_20241204_0016552_TESTREPORT_12C.doc").write_bytes(b"dummy")

        eng = MonthlyPatchEngine(conn)
        eng._reorganize_to_mode_a(tmp_path)

        assert (tmp_path / "11G" / "01.IP_20241128_0016552_11G.7z").exists()
        assert (tmp_path / "12C" / "01.IP_20241128_0016552_12C.zip").exists()
        assert (tmp_path / "11G" / "測試報告" / "01.IP_20241204_0016552_TESTREPORT_11G.doc").exists()
        assert (tmp_path / "12C" / "測試報告" / "01.IP_20241204_0016552_TESTREPORT_12C.doc").exists()
```

- [ ] **Step 10: 確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestScanMonthlyDir::test_reorganize_to_mode_a -v
```

Expected: `FAILED`

- [ ] **Step 11: 實作 `_reorganize_to_mode_a`、`_extract_archive`、`_list_files`、`_extract_issue_no`、`_read_release_note`**

在 `_detect_structure` 後新增以下方法（全部加在 `# ── 資料夾掃描` 區塊）：

```python
def _reorganize_to_mode_a(self, base: Path) -> None:
    """將模式 B 平坦結構整理至 11G/12C 子目錄。"""
    import shutil
    for version in ("11G", "12C"):
        ver_dir = base / version
        report_dir = ver_dir / "測試報告"
        ver_dir.mkdir(exist_ok=True)
        report_dir.mkdir(exist_ok=True)
        v_upper = version.upper()
        for f in list(base.iterdir()):
            if not f.is_file():
                continue
            name_upper = f.name.upper()
            if f"_{v_upper}" not in name_upper:
                continue
            if "TESTREPORT" in name_upper:
                shutil.move(str(f), str(report_dir / f.name))
            elif f.suffix.lower() in (".7z", ".zip", ".rar"):
                shutil.move(str(f), str(ver_dir / f.name))

def _extract_archive(self, archive: Path, extract_dir: Path) -> None:
    """解壓 .7z 或 .zip 至 extract_dir。"""
    extract_dir.mkdir(parents=True, exist_ok=True)
    suffix = archive.suffix.lower()
    if suffix == ".7z":
        import py7zr
        with py7zr.SevenZipFile(str(archive), mode="r") as z:
            z.extractall(path=str(extract_dir))
    elif suffix == ".zip":
        import zipfile
        with zipfile.ZipFile(str(archive), "r") as z:
            z.extractall(path=str(extract_dir))

def _list_files(self, directory: Path, extensions: list[str], keep_ext: bool = False) -> list[str]:
    """列出目錄內符合副檔名的檔案，keep_ext=False 則去副檔名。"""
    if not directory.exists():
        return []
    return [
        f.name if keep_ext else f.stem
        for f in sorted(directory.iterdir())
        if f.is_file() and f.suffix.lower() in extensions
    ]

def _extract_issue_no(self, filename: str) -> str | None:
    """從封存檔名解析 7 位數 Issue No，如 '01.IP_20241128_0016552_11G.7z' → '0016552'。"""
    m = self._ARCHIVE_RE.search(filename)
    return m.group(1) if m else None

def _read_release_note(self, extract_dir: Path) -> list[dict[str, str]]:
    """在解壓資料夾尋找 ReleaseNote，委託 SinglePatchEngine 解析。"""
    from hcp_cms.core.patch_engine import SinglePatchEngine
    for f in extract_dir.iterdir():
        if not f.is_file():
            continue
        low = f.name.lower()
        if "releasenote" in low or "release_note" in low:
            return SinglePatchEngine(self._conn).read_release_doc(str(f))
    return []
```

- [ ] **Step 12: 確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestScanMonthlyDir -v
```

Expected: 3 PASSED

---

- [ ] **Step 13: 寫失敗測試（scan_monthly_dir — 完整流程）**

```python
    def test_scan_monthly_dir_mode_a(self, conn, tmp_path, monkeypatch):
        import json, py7zr
        from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
        from hcp_cms.data.repositories import PatchRepository

        # 建立模式 A 結構：11G/ 含一個 .7z
        ver_dir = tmp_path / "11G"
        ver_dir.mkdir()
        archive = ver_dir / "01.IP_20241128_0016552_11G.7z"
        # 建立包含 form/ sql/ 的 .7z
        extracted_stub = tmp_path / "_stub"
        extracted_stub.mkdir()
        (extracted_stub / "form").mkdir()
        (extracted_stub / "form" / "HRWF304.fmb").write_bytes(b"")
        (extracted_stub / "sql").mkdir()
        (extracted_stub / "sql" / "pk_test.sql").write_bytes(b"")
        with py7zr.SevenZipFile(str(archive), "w") as z:
            z.writeall(str(extracted_stub), "")

        # mock _read_release_note 回傳固定資料
        def fake_release(self_inner, path):
            return [{"issue_no": "0016552", "issue_type": "BugFix",
                     "description": "測試說明", "region": "共用"}]
        monkeypatch.setattr(MonthlyPatchEngine, "_read_release_note", fake_release)

        eng = MonthlyPatchEngine(conn)
        result = eng.scan_monthly_dir(str(tmp_path), "202412")

        assert "11G" in result
        repo = PatchRepository(conn)
        issues = repo.list_issues_by_patch(result["11G"])
        assert len(issues) == 1
        assert issues[0].issue_no == "0016552"
        meta = json.loads(issues[0].mantis_detail)
        assert "HRWF304" in meta["form_files"]
        assert "pk_test" in meta["sql_files"]

    def test_scan_monthly_dir_mode_b_reorganizes(self, conn, tmp_path, monkeypatch):
        from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine

        # 模式 B：平坦結構，只放空 bytes（不真的解壓）
        archive_11g = tmp_path / "01.IP_20241128_0016552_11G.7z"
        archive_11g.write_bytes(b"dummy")
        report = tmp_path / "01.IP_20241204_0016552_TESTREPORT_11G.doc"
        report.write_bytes(b"dummy")

        def fake_extract(self_inner, archive, extract_dir):
            extract_dir.mkdir(parents=True, exist_ok=True)

        def fake_release(self_inner, path):
            return []

        monkeypatch.setattr(MonthlyPatchEngine, "_extract_archive", fake_extract)
        monkeypatch.setattr(MonthlyPatchEngine, "_read_release_note", fake_release)

        eng = MonthlyPatchEngine(conn)
        eng.scan_monthly_dir(str(tmp_path), "202412")

        assert (tmp_path / "11G" / "01.IP_20241128_0016552_11G.7z").exists()
        assert (tmp_path / "11G" / "測試報告" / "01.IP_20241204_0016552_TESTREPORT_11G.doc").exists()
```

- [ ] **Step 14: 確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestScanMonthlyDir::test_scan_monthly_dir_mode_a tests/unit/test_monthly_patch_engine.py::TestScanMonthlyDir::test_scan_monthly_dir_mode_b_reorganizes -v
```

Expected: `FAILED`

- [ ] **Step 15: 實作 `scan_monthly_dir`**

在 `_read_release_note` 後新增：

```python
def scan_monthly_dir(self, patch_dir: str, month_str: str) -> dict[str, int]:
    """掃描月份資料夾，建立各版本 PatchRecord 並匯入 Issues。

    自動偵測模式 A（11G/12C 子目錄）或模式 B（平坦），模式 B 時自動整理。
    回傳 {"11G": patch_id, "12C": patch_id}（版本不存在則無對應 key）。
    """
    base = Path(patch_dir)
    patch_ids: dict[str, int] = {}

    if self._detect_structure(base) == "B":
        self._reorganize_to_mode_a(base)

    for version in ("11G", "12C"):
        version_dir = base / version
        if not version_dir.exists():
            continue
        archives = sorted(version_dir.glob("*.7z")) + sorted(version_dir.glob("*.zip"))
        if not archives:
            continue

        patch = PatchRecord(type="monthly", month_str=month_str, patch_dir=patch_dir)
        patch_id = self._repo.insert_patch(patch)
        patch_ids[version] = patch_id

        for idx, archive in enumerate(archives):
            issue_no = self._extract_issue_no(archive.name)
            extract_dir = version_dir / f"_extracted_{archive.stem}"
            try:
                self._extract_archive(archive, extract_dir)
            except Exception as e:
                logging.warning("解壓縮失敗 [%s]: %s", archive.name, e)
                continue

            raw_issues = self._read_release_note(extract_dir)
            form_files = self._list_files(extract_dir / "form", [".fmb", ".rdf", ".fmx"])
            sql_files = self._list_files(extract_dir / "sql", [".sql"])
            muti_files = self._list_files(extract_dir / "muti", [".sql"], keep_ext=True)
            scan_meta = json.dumps({
                "form_files": form_files,
                "sql_files": sql_files,
                "muti_files": muti_files,
                "archive_name": archive.name,
            })

            if raw_issues:
                for raw_idx, raw in enumerate(raw_issues):
                    self._repo.insert_issue(PatchIssue(
                        patch_id=patch_id,
                        issue_no=raw.get("issue_no", issue_no or ""),
                        issue_type=raw.get("issue_type", "BugFix"),
                        region=raw.get("region", "共用"),
                        description=raw.get("description"),
                        source="scan",
                        sort_order=idx * 100 + raw_idx,
                        mantis_detail=scan_meta,
                    ))
            elif issue_no:
                self._repo.insert_issue(PatchIssue(
                    patch_id=patch_id,
                    issue_no=issue_no,
                    source="scan",
                    sort_order=idx,
                    mantis_detail=scan_meta,
                ))

    return patch_ids
```

- [ ] **Step 16: 確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestScanMonthlyDir -v
```

Expected: 5 PASSED

- [ ] **Step 17: 執行全部測試確認無 regression**

```
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: 既有測試全數通過

- [ ] **Step 18: Lint**

```
.venv/Scripts/ruff.exe check src/hcp_cms/core/monthly_patch_engine.py
```

Expected: All checks passed!

- [ ] **Step 19: Commit**

```bash
git add src/hcp_cms/core/monthly_patch_engine.py tests/unit/test_monthly_patch_engine.py
git commit -m "feat(core): MonthlyPatchEngine 新增 scan_monthly_dir 及輔助方法"
```

---

## Task 2: MonthlyPatchEngine — generate_patch_list_from_dir() [POC: openpyxl 超連結首次使用]

**Files:**
- Modify: `src/hcp_cms/core/monthly_patch_engine.py`
- Test: `tests/unit/test_monthly_patch_engine.py`

### 產出格式

每個版本（11G、12C）產一份 xlsx，存至 `{patch_dir}/{version}/PATCH_LIST_{month_str}_{version}.xlsx`。

**Sheet 1「清單整理」（欄位：Issue No, 6I, 11G, 12C, （空）, Mantis說明）：**
- Issue 清單取兩版本聯集（以 issue_no 去重，依 11G 版本順序為主）
- 11G 欄：若 issue_no 在 11G issues 中則填 "V"，否則空白；12C 同理

**Sheet 2「{VER}新項目說明」（欄位：區域, 類別, 程式代碼, 程式名稱, 說明, 測試報告）：**
- 列出本版本的 issues
- issue_type "BugFix" → 類別 "修正"；"Enhancement" → "改善"
- 測試報告欄：搜尋 `{patch_dir}/{VER}/測試報告/` 找含 issue_no 的 .doc/.docx，找到則設超連結

**Sheet 3「更新物件」（欄位：測試報告, 資料庫物件, 程式代碼, 多語）：**
- 測試報告欄：issue_no 純文字
- 資料庫物件：`mantis_detail.sql_files` 以 "、" 連接
- 程式代碼：`mantis_detail.form_files` 以 "、" 連接
- 多語：`mantis_detail.muti_files` 以 "\n" 連接

### openpyxl 超連結寫法

```python
from openpyxl.styles import Font
cell.value = issue_no
cell.hyperlink = f"file:///{abs_path.replace(chr(92), '/')}"  # Windows 路徑反斜線 → 正斜線
cell.font = Font(color="0563C1", underline="single")
```

- [ ] **Step 1: 寫失敗測試（_find_test_report）**

在 `TestScanMonthlyDir` 後新增測試類別：

```python
class TestGeneratePatchListFromDir:
    @pytest.fixture
    def conn(self):
        db = DatabaseManager(":memory:")
        db.initialize()
        yield db.connection
        db.connection.close()

    def test_find_test_report_found(self, conn, tmp_path):
        (tmp_path / "11G" / "測試報告").mkdir(parents=True)
        report = tmp_path / "11G" / "測試報告" / "01.IP_20241204_0016552_TESTREPORT_11G.doc"
        report.write_bytes(b"")

        eng = MonthlyPatchEngine(conn)
        result = eng._find_test_report(tmp_path, "11G", "0016552")
        assert result is not None
        assert "0016552" in result

    def test_find_test_report_not_found(self, conn, tmp_path):
        (tmp_path / "11G" / "測試報告").mkdir(parents=True)
        eng = MonthlyPatchEngine(conn)
        assert eng._find_test_report(tmp_path, "11G", "9999999") is None
```

- [ ] **Step 2: 確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestGeneratePatchListFromDir -v
```

Expected: `FAILED`

- [ ] **Step 3: 實作 `_find_test_report` 與 `_write_patch_header_row`**

在 `scan_monthly_dir` 後新增：

```python
def _find_test_report(self, base: Path, version: str, issue_no: str) -> str | None:
    """在 {base}/{version}/測試報告/ 搜尋含 issue_no 的 .doc/.docx，回傳絕對路徑。"""
    report_dir = base / version / "測試報告"
    if not report_dir.exists():
        return None
    for f in sorted(report_dir.iterdir()):
        if issue_no in f.name and f.suffix.lower() in (".doc", ".docx"):
            return str(f.absolute())
    return None

def _write_patch_header_row(self, ws: object, headers: list[str], row: int = 1) -> None:
    from openpyxl.styles import Alignment, Font, PatternFill
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row, c)
        cell.value = h
        cell.font = Font(name="微軟正黑體", bold=True, size=11, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=self._HDR_DARK)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
```

- [ ] **Step 4: 確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestGeneratePatchListFromDir -v
```

Expected: 2 PASSED

---

- [ ] **Step 5: 寫失敗測試（generate_patch_list_from_dir — 完整）**

```python
    def test_generate_patch_list_from_dir_creates_files(self, conn, tmp_path):
        import json
        from hcp_cms.data.repositories import PatchRepository

        repo = PatchRepository(conn)
        # 建立 11G patch record + issues
        from hcp_cms.data.models import PatchRecord, PatchIssue
        pid_11g = repo.insert_patch(PatchRecord(type="monthly", month_str="202412", patch_dir=str(tmp_path)))
        repo.insert_issue(PatchIssue(
            patch_id=pid_11g, issue_no="0016552", issue_type="BugFix",
            region="共用", description="測試問題修正", source="scan",
            program_code="HRWF304", program_name="派退宿功能",
            mantis_detail=json.dumps({
                "form_files": ["HRWF304"], "sql_files": [], "muti_files": [],
                "archive_name": "01.IP_20241128_0016552_11G.7z"
            })
        ))
        # 建立 12C patch record + issues
        pid_12c = repo.insert_patch(PatchRecord(type="monthly", month_str="202412", patch_dir=str(tmp_path)))
        repo.insert_issue(PatchIssue(
            patch_id=pid_12c, issue_no="0016552", issue_type="BugFix",
            region="共用", description="測試問題修正", source="scan",
            mantis_detail=json.dumps({"form_files": [], "sql_files": [], "muti_files": []})
        ))

        # 建立版本子目錄（xlsx 要存在這裡）
        (tmp_path / "11G").mkdir()
        (tmp_path / "12C").mkdir()
        (tmp_path / "11G" / "測試報告").mkdir()

        eng = MonthlyPatchEngine(conn)
        paths = eng.generate_patch_list_from_dir(
            {"11G": pid_11g, "12C": pid_12c}, str(tmp_path), "202412"
        )

        assert len(paths) == 2
        assert any("11G" in p for p in paths)
        assert any("12C" in p for p in paths)
        for p in paths:
            assert Path(p).exists()

    def test_generate_sheet_names(self, conn, tmp_path):
        import json
        from openpyxl import load_workbook
        from hcp_cms.data.repositories import PatchRepository
        from hcp_cms.data.models import PatchRecord, PatchIssue

        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="monthly", month_str="202412", patch_dir=str(tmp_path)))
        repo.insert_issue(PatchIssue(
            patch_id=pid, issue_no="0016552", source="scan",
            mantis_detail=json.dumps({"form_files": [], "sql_files": [], "muti_files": []})
        ))
        (tmp_path / "11G").mkdir()

        eng = MonthlyPatchEngine(conn)
        paths = eng.generate_patch_list_from_dir({"11G": pid}, str(tmp_path), "202412")

        wb = load_workbook(paths[0])
        assert "清單整理" in wb.sheetnames
        assert "11G新項目說明" in wb.sheetnames
        assert "更新物件" in wb.sheetnames

    def test_generate_11g_v_mark(self, conn, tmp_path):
        import json
        from openpyxl import load_workbook
        from hcp_cms.data.repositories import PatchRepository
        from hcp_cms.data.models import PatchRecord, PatchIssue

        repo = PatchRepository(conn)
        pid_11g = repo.insert_patch(PatchRecord(type="monthly", month_str="202412", patch_dir=str(tmp_path)))
        repo.insert_issue(PatchIssue(
            patch_id=pid_11g, issue_no="0016552", source="scan",
            mantis_detail=json.dumps({"form_files": [], "sql_files": [], "muti_files": []})
        ))
        pid_12c = repo.insert_patch(PatchRecord(type="monthly", month_str="202412", patch_dir=str(tmp_path)))
        (tmp_path / "11G").mkdir()
        (tmp_path / "12C").mkdir()

        eng = MonthlyPatchEngine(conn)
        paths = eng.generate_patch_list_from_dir(
            {"11G": pid_11g, "12C": pid_12c}, str(tmp_path), "202412"
        )

        wb = load_workbook(next(p for p in paths if "11G" in p))
        ws = wb["清單整理"]
        # Row 2 = 第一筆 issue：col 3 = 11G，col 4 = 12C
        assert ws.cell(2, 3).value == "V"   # 11G 有此 issue
        assert ws.cell(2, 4).value in ("", None)  # 12C 無此 issue

    def test_generate_test_report_hyperlink(self, conn, tmp_path):
        import json
        from openpyxl import load_workbook
        from hcp_cms.data.repositories import PatchRepository
        from hcp_cms.data.models import PatchRecord, PatchIssue

        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="monthly", month_str="202412", patch_dir=str(tmp_path)))
        repo.insert_issue(PatchIssue(
            patch_id=pid, issue_no="0016552", source="scan",
            mantis_detail=json.dumps({"form_files": [], "sql_files": [], "muti_files": []})
        ))
        (tmp_path / "11G").mkdir()
        report_dir = tmp_path / "11G" / "測試報告"
        report_dir.mkdir()
        (report_dir / "01.IP_20241204_0016552_TESTREPORT_11G.doc").write_bytes(b"")

        eng = MonthlyPatchEngine(conn)
        paths = eng.generate_patch_list_from_dir({"11G": pid}, str(tmp_path), "202412")

        wb = load_workbook(paths[0])
        ws = wb["11G新項目說明"]
        # Row 3 = 第一筆 issue（row 1 = 標題列，row 2 = header）
        cell = ws.cell(3, 6)
        assert cell.hyperlink is not None
        assert "0016552" in str(cell.hyperlink)
```

- [ ] **Step 6: 確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestGeneratePatchListFromDir -v
```

Expected: 4 FAILED (generate_patch_list_from_dir not defined)

- [ ] **Step 7: 實作 `generate_patch_list_from_dir`**

在 `_find_test_report` 後新增：

```python
def generate_patch_list_from_dir(
    self, patch_ids: dict[str, int], patch_dir: str, month_str: str
) -> list[str]:
    """依 patch_ids 各版本產 PATCH_LIST_{month_str}_{VER}.xlsx，存至版本子目錄。"""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    base = Path(patch_dir)
    all_issues: dict[str, list[PatchIssue]] = {
        ver: self._repo.list_issues_by_patch(pid)
        for ver, pid in patch_ids.items()
    }

    # 建立聯集 issue_no 清單（以出現順序去重）
    union_nos: list[str] = []
    seen: set[str] = set()
    for ver_issues in all_issues.values():
        for iss in ver_issues:
            if iss.issue_no not in seen:
                union_nos.append(iss.issue_no)
                seen.add(iss.issue_no)

    paths: list[str] = []

    for version, version_issues in all_issues.items():
        wb = Workbook()

        # ① 清單整理
        ws1 = wb.active
        ws1.title = "清單整理"
        self._write_patch_header_row(ws1, ["Issue No", "6I", "11G", "12C", "", "Mantis說明"])
        nos_11g = {i.issue_no for i in all_issues.get("11G", [])}
        nos_12c = {i.issue_no for i in all_issues.get("12C", [])}
        for r, no in enumerate(union_nos, start=2):
            ws1.cell(r, 1).value = no
            ws1.cell(r, 3).value = "V" if no in nos_11g else ""
            ws1.cell(r, 4).value = "V" if no in nos_12c else ""
            desc_iss = next(
                (i for ver_list in all_issues.values() for i in ver_list if i.issue_no == no),
                None,
            )
            if desc_iss:
                ws1.cell(r, 6).value = f"{no}: {desc_iss.description or ''}"

        # ② {VER}新項目說明
        ws2 = wb.create_sheet(f"{version}新項目說明")
        ws2.cell(1, 1).value = f"{month_str[:4]}/{month_str[4:]}大PATCH更新項目說明"
        self._write_patch_header_row(
            ws2, ["區域", "類別", "程式代碼", "程式名稱", "說明", "測試報告"], row=2
        )
        for r, iss in enumerate(version_issues, start=3):
            ws2.cell(r, 1).value = iss.region
            ws2.cell(r, 2).value = "修正" if iss.issue_type == "BugFix" else "改善"
            ws2.cell(r, 3).value = iss.program_code
            ws2.cell(r, 4).value = iss.program_name
            ws2.cell(r, 5).value = iss.description
            report_path = self._find_test_report(base, version, iss.issue_no)
            cell6 = ws2.cell(r, 6)
            cell6.value = iss.issue_no
            if report_path:
                cell6.hyperlink = "file:///" + report_path.replace("\\", "/")
                cell6.font = Font(color="0563C1", underline="single")

        # ③ 更新物件
        ws3 = wb.create_sheet("更新物件")
        ws3.cell(1, 1).value = f"{month_str[:4]}/{month_str[4:]}大PATCH更新項目說明"
        self._write_patch_header_row(ws3, ["測試報告", "資料庫物件", "程式代碼", "多語"], row=2)
        for r, iss in enumerate(version_issues, start=3):
            ws3.cell(r, 1).value = iss.issue_no
            if iss.mantis_detail:
                try:
                    meta = json.loads(iss.mantis_detail)
                    ws3.cell(r, 2).value = "、".join(meta.get("sql_files", []))
                    ws3.cell(r, 3).value = "、".join(meta.get("form_files", []))
                    ws3.cell(r, 4).value = "\n".join(meta.get("muti_files", []))
                except (json.JSONDecodeError, AttributeError):
                    pass

        fname = f"PATCH_LIST_{month_str}_{version}.xlsx"
        out_path = base / version / fname
        wb.save(str(out_path))
        paths.append(str(out_path))

    return paths
```

- [ ] **Step 8: 確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestGeneratePatchListFromDir -v
```

Expected: 6 PASSED

- [ ] **Step 9: 執行全部測試**

```
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: 既有測試全數通過

- [ ] **Step 10: Lint**

```
.venv/Scripts/ruff.exe check src/hcp_cms/core/monthly_patch_engine.py
```

- [ ] **Step 11: Commit**

```bash
git add src/hcp_cms/core/monthly_patch_engine.py tests/unit/test_monthly_patch_engine.py
git commit -m "feat(core): MonthlyPatchEngine 新增 generate_patch_list_from_dir 含超連結"
```

---

## Task 3: MonthlyPatchTab — 新增「掃描資料夾」來源

**Files:**
- Modify: `src/hcp_cms/ui/patch_monthly_tab.py`
- Test: `tests/unit/test_patch_monthly_tab.py`

### 變更說明

1. 新增常數 `_SOURCE_FOLDER = "掃描資料夾"`
2. `__init__` 新增 `self._scan_dir: str | None = None` 與 `self._scan_patch_ids: dict[str, int] | None = None`
3. `_setup_ui` 新增資料夾路徑列（`_scan_edit` + `_scan_btn`），預設隱藏
4. `_on_issue_source_changed` 新增 `_SOURCE_FOLDER` 的顯示邏輯
5. 新增 Slot `_on_scan_browse_clicked`
6. `_on_import_clicked` 新增 `_SOURCE_FOLDER` 分支，呼叫 `engine.scan_monthly_dir()`
7. `_on_import_result` 新增 `patch_ids` key 的處理（掃描模式結果）
8. `_on_generate_excel_clicked` 新增判斷：若 `_scan_patch_ids` 存在則呼叫 `generate_patch_list_from_dir`

- [ ] **Step 1: 寫失敗測試（掃描資料夾 UI 元件存在）**

在 `tests/unit/test_patch_monthly_tab.py` 最後新增：

```python
class TestFolderScanSource:
    def test_source_combo_has_scan_folder_option(self, qtbot, db):
        from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab
        tab = MonthlyPatchTab(conn=db)
        qtbot.addWidget(tab)
        items = [tab._source_combo.itemText(i) for i in range(tab._source_combo.count())]
        assert "掃描資料夾" in items

    def test_scan_folder_widgets_visible_when_selected(self, qtbot, db):
        from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab
        tab = MonthlyPatchTab(conn=db)
        qtbot.addWidget(tab)
        idx = [tab._source_combo.itemText(i) for i in range(tab._source_combo.count())].index("掃描資料夾")
        tab._source_combo.setCurrentIndex(idx)
        assert not tab._scan_edit.isHidden()
        assert not tab._scan_btn.isHidden()
        assert tab._file_edit.isHidden()
        assert tab._file_btn.isHidden()

    def test_scan_dir_set_after_browse(self, qtbot, db, tmp_path, monkeypatch):
        from PySide6.QtWidgets import QFileDialog
        from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
        tab = MonthlyPatchTab(conn=db)
        qtbot.addWidget(tab)
        tab._on_scan_browse_clicked()
        assert tab._scan_dir == str(tmp_path)
        assert tab._scan_edit.text() == str(tmp_path)
```

- [ ] **Step 2: 確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_monthly_tab.py::TestFolderScanSource -v
```

Expected: 3 FAILED

- [ ] **Step 3: 實作 UI 變更（MonthlyPatchTab）**

**a) 頂部常數區新增：**

```python
_SOURCE_FOLDER = "掃描資料夾"
```

**b) `__init__` 新增實例變數（在 `self._output_dir` 後）：**

```python
self._scan_dir: str | None = None
self._scan_patch_ids: dict[str, int] | None = None
```

**c) `_setup_ui` 的 source_combo 加入第三個選項：**

```python
self._source_combo.addItems([_SOURCE_FILE, _SOURCE_MANTIS, _SOURCE_FOLDER])
```

**d) 在 file 路徑列後新增掃描資料夾路徑列（`layout.addLayout(src_row)` 後）：**

```python
# 掃描資料夾路徑列
scan_row = QHBoxLayout()
scan_row.addWidget(QLabel("Patch 資料夾："))
self._scan_edit = QLineEdit()
self._scan_edit.setPlaceholderText("選擇月份 Patch 頂層資料夾（含 11G/12C 子目錄）…")
self._scan_edit.setReadOnly(True)
self._scan_btn = QPushButton("瀏覽…")
scan_row.addWidget(self._scan_edit)
scan_row.addWidget(self._scan_btn)
layout.addLayout(scan_row)
```

**e) Signal/Slot 連線區新增（在 `self._file_btn.clicked.connect` 後）：**

```python
self._scan_btn.clicked.connect(self._on_scan_browse_clicked)
```

**f) 替換整個 `_on_issue_source_changed` 方法：**

```python
def _on_issue_source_changed(self, index: int) -> None:
    current = self._source_combo.currentText()
    is_file = current == _SOURCE_FILE
    is_folder = current == _SOURCE_FOLDER
    self._file_edit.setVisible(is_file)
    self._file_btn.setVisible(is_file)
    self._scan_edit.setVisible(is_folder)
    self._scan_btn.setVisible(is_folder)
```

**g) 新增 Slot（在 `_on_file_browse_clicked` 後）：**

```python
def _on_scan_browse_clicked(self) -> None:
    path = QFileDialog.getExistingDirectory(self, "選擇月份 Patch 資料夾")
    if path:
        self._scan_dir = path
        self._scan_edit.setText(path)
        self._set_step(1)
```

- [ ] **Step 4: 確認 UI 測試通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_monthly_tab.py::TestFolderScanSource -v
```

Expected: 3 PASSED

---

- [ ] **Step 5: 寫失敗測試（import 觸發掃描）**

```python
    def test_import_with_scan_folder_calls_engine(self, qtbot, db, tmp_path, monkeypatch):
        from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab
        from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine

        scanned = {}
        def fake_scan(self_eng, patch_dir, month_str):
            scanned["patch_dir"] = patch_dir
            scanned["month_str"] = month_str
            return {}
        monkeypatch.setattr(MonthlyPatchEngine, "scan_monthly_dir", fake_scan)
        monkeypatch.setattr(MonthlyPatchEngine, "get_issue_count", lambda s, pid: 0)

        tab = MonthlyPatchTab(conn=db)
        qtbot.addWidget(tab)
        idx = [tab._source_combo.itemText(i) for i in range(tab._source_combo.count())].index("掃描資料夾")
        tab._source_combo.setCurrentIndex(idx)
        tab._scan_dir = str(tmp_path)
        tab._year_spin.setValue(2026)
        tab._month_combo.setCurrentIndex(3)  # 4月

        tab._on_import_clicked()

        import time; time.sleep(0.5)
        qtbot.waitSignal(tab._import_done, timeout=3000)

        assert scanned.get("month_str") == "202604"
        assert scanned.get("patch_dir") == str(tmp_path)
```

- [ ] **Step 6: 確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_monthly_tab.py::TestFolderScanSource::test_import_with_scan_folder_calls_engine -v
```

Expected: FAILED

- [ ] **Step 7: 實作 `_on_import_clicked` 新增 `_SOURCE_FOLDER` 分支**

在 `_on_import_clicked` 的 `source_text == _SOURCE_FILE` 判斷後，加入新分支。將現有方法改為：

```python
def _on_import_clicked(self) -> None:
    if not self._conn:
        return
    source_text = self._source_combo.currentText()
    if source_text == _SOURCE_FILE and not self._file_path:
        self._append_log("⚠️ 請先選擇檔案")
        return
    if source_text == _SOURCE_FOLDER and not self._scan_dir:
        self._append_log("⚠️ 請先選擇資料夾")
        return
    month_str = self._get_month_str()
    conn = self._conn
    file_path = self._file_path
    scan_dir = self._scan_dir

    self._import_btn.setEnabled(False)
    self._append_log(f"📥 匯入 {month_str} Issue 清單…")

    if source_text == _SOURCE_FOLDER:
        def work() -> dict:
            from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
            engine = MonthlyPatchEngine(conn)
            try:
                patch_ids = engine.scan_monthly_dir(scan_dir, month_str)
                counts = {v: engine.get_issue_count(pid) for v, pid in patch_ids.items()}
                return {"patch_ids": patch_ids, "counts": counts, "error": None}
            except Exception as e:
                return {"patch_ids": {}, "counts": {}, "error": str(e)}
        threading.Thread(target=lambda: self._import_done.emit(work()), daemon=True).start()
    else:
        def work() -> dict:  # type: ignore[no-redef]
            from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
            engine = MonthlyPatchEngine(conn)
            try:
                pid = engine.load_issues("manual", month_str, file_path)
                count = engine.get_issue_count(pid)
                return {"patch_id": pid, "count": count, "error": None}
            except Exception as e:
                return {"patch_id": None, "count": 0, "error": str(e)}
        threading.Thread(target=lambda: self._import_done.emit(work()), daemon=True).start()
```

**同時替換 `_on_import_result`：**

```python
def _on_import_result(self, result: dict) -> None:
    self._import_btn.setEnabled(True)
    if result.get("error"):
        self._append_log(f"❌ 匯入失敗：{result['error']}")
        return
    if "patch_ids" in result:
        self._scan_patch_ids = result["patch_ids"]
        counts = result.get("counts", {})
        for ver, cnt in counts.items():
            self._append_log(f"✅ {ver}：{cnt} 筆 Issue")
        first_id = next(iter(result["patch_ids"].values()), None)
        if first_id is not None:
            self._patch_id = first_id
            self._issue_table.load_issues(first_id)
    else:
        self._patch_id = result["patch_id"]
        self._append_log(f"✅ 匯入完成：{result['count']} 筆 Issue")
        self._issue_table.load_issues(self._patch_id)
    self._set_step(3)
```

**同時修改 `_on_generate_excel_clicked` 的 `work()` 閉包：**

```python
def _on_generate_excel_clicked(self) -> None:
    if not self._conn:
        return
    if self._scan_patch_ids is None and self._patch_id is None:
        return
    self._generate_excel_btn.setEnabled(False)
    self._append_log("📊 產生 PATCH_LIST Excel…")
    conn = self._conn
    patch_id = self._patch_id
    month_str = self._get_month_str()
    output_dir = self._get_output_dir()
    scan_patch_ids = self._scan_patch_ids
    scan_dir = self._scan_dir

    def work() -> dict:
        from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
        engine = MonthlyPatchEngine(conn)
        try:
            if scan_patch_ids:
                paths = engine.generate_patch_list_from_dir(scan_patch_ids, scan_dir, month_str)
            else:
                paths = engine.generate_patch_list(patch_id, output_dir, month_str)
            return {"paths": paths, "type": "excel", "error": None}
        except Exception as e:
            return {"paths": [], "type": "excel", "error": str(e)}

    threading.Thread(target=lambda: self._generate_done.emit(work()), daemon=True).start()
```

- [ ] **Step 8: 確認所有 MonthlyPatchTab 測試通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_monthly_tab.py -v
```

Expected: All PASSED

- [ ] **Step 9: 執行全部測試**

```
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -25
```

Expected: 既有測試全數通過

- [ ] **Step 10: Lint**

```
.venv/Scripts/ruff.exe check src/hcp_cms/ui/patch_monthly_tab.py
```

- [ ] **Step 11: Commit**

```bash
git add src/hcp_cms/ui/patch_monthly_tab.py tests/unit/test_patch_monthly_tab.py
git commit -m "feat(ui): MonthlyPatchTab 新增「掃描資料夾」來源選項"
```
