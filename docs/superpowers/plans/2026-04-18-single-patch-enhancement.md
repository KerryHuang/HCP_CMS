# 單次 Patch 整理強化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將「小 PATCH 更新」流程整合進 CMS，讓客服人員選取 .7z 封存檔後，一鍵解壓匯入、編輯 Issue 清單，並分別產出 Issue清單整理、發行通知、IT/HR Issue清單、測試腳本等報表給客戶。

**Architecture:** 擴展現有 `SinglePatchEngine`（`patch_engine.py`）新增 `load_from_archive`（解壓+掃描+DB 寫入）與三個獨立 generate 方法；完全改寫 `SinglePatchTab`（`patch_single_tab.py`）為 5 步流程，以 .7z 檔選取取代舊版資料夾選取，4 個獨立產報表按鈕。現有測試繼續通過（generate_test_scripts 加 default 參數向下相容）。

**Tech Stack:** PySide6 6.10, openpyxl, python-docx, py7zr, SQLite, pytest

---

## 檔案結構

| 動作 | 路徑 | 職責 |
|------|------|------|
| 修改 | `src/hcp_cms/core/patch_engine.py` | 新增 `load_from_archive`、`_parse_version_tag`、`generate_issue_list`、`generate_release_notice`、`generate_issue_split`；更新 `_write_header_row`、`generate_test_scripts` |
| 修改 | `src/hcp_cms/ui/patch_single_tab.py` | 完全改寫 — 5 步流程、.7z 輸入、版本標籤、4 產報表按鈕 |
| 修改 | `tests/unit/test_patch_engine.py` | 新增 Task 1–5 對應測試類別 |
| 修改 | `tests/unit/test_patch_single_tab.py` | 改寫為符合新 UI 的測試 |

---

## 背景知識（subagent 必讀）

### 現有 `SinglePatchEngine`（`src/hcp_cms/core/patch_engine.py`）
- 建構子：`__init__(self, conn: sqlite3.Connection)` → 建立 `self._repo = PatchRepository(conn)`
- 已有：`scan_patch_dir`、`read_release_doc`、`extract_patch_archives`、`setup_new_patch`、`load_issues_from_release_doc`、`generate_excel_reports`（3 個 xlsx 舊版）、`generate_test_scripts`（3 個檔案）
- 已有色彩常數：`_CLR_CS="D5F5E3"`、`_CLR_CUST="D6EAF8"`、`_CLR_PATCH="FEF9E7"`、`_CLR_NOTE="F5EEF8"`、`_CLR_ENH="E2EFDA"`、`_CLR_BUG="FCE4D6"`
- 已有：`_write_header_row(ws, headers)` — 深藍 #1F3864 標題列，Task 1 需加 `fgColor` 參數

### Data 層
- `PatchRecord`：`type="single"`、`patch_dir: str | None`、`patch_id: int | None`（insert 後自動填入）
- `PatchIssue`：`patch_id`、`issue_no`、`issue_type`（"BugFix"/"Enhancement"）、`region`（"TW"/"CN"/"共用"）、`program_code`、`program_name`、`description`、`impact`、`test_direction`
- `PatchRepository.get_patch_by_id(patch_id: int) -> PatchRecord | None`
- `PatchRepository.list_issues_by_patch(patch_id: int) -> list[PatchIssue]`
- `PatchRepository.insert_patch(record: PatchRecord) -> int`

### 現有 `SinglePatchTab`（`src/hcp_cms/ui/patch_single_tab.py`）
- 目前：6 步，資料夾選取，Mantis 登入步驟，單一「產生報表」按鈕
- 目標：**完全改寫** — 5 步（選 .7z / 解壓匯入 / 編輯 / 產報表 / 完成）、.7z + 輸出目錄選取、版本標籤欄位、4 個產報表按鈕
- `patch_view.py` 從 `patch_single_tab.py` import `SinglePatchTab`（不動）

### 測試慣例（CLAUDE.md）
- fixture：`DatabaseManager(":memory:").initialize()`，以 `yield` + `.close()` teardown
- `qtbot.addWidget(tab)` 用於 PySide6 widget 測試
- signal 等待：`qtbot.waitSignal(tab._xxx_done, timeout=3000)`

---

## Task 1：`load_from_archive` + `_parse_version_tag`

**Files:**
- Modify: `src/hcp_cms/core/patch_engine.py`
- Test: `tests/unit/test_patch_engine.py`

- [ ] **Step 1: 寫失敗測試**

在 `tests/unit/test_patch_engine.py` 末尾新增：

```python
class TestLoadFromArchive:
    def test_parse_version_tag_extracts_ip_pattern(self, conn):
        eng = SinglePatchEngine(conn)
        assert eng._parse_version_tag("IP_合併_20261101_HCP11G.7z") == "IP_合併_20261101"

    def test_parse_version_tag_fallback_to_stem(self, conn):
        eng = SinglePatchEngine(conn)
        assert eng._parse_version_tag("MyPatch.7z") == "MyPatch"

    def test_parse_version_tag_long_stem_truncated(self, conn):
        eng = SinglePatchEngine(conn)
        tag = eng._parse_version_tag("A" * 30 + ".7z")
        assert len(tag) <= 20

    def test_load_from_archive_returns_tuple(self, conn, tmp_path):
        from unittest.mock import MagicMock, patch
        archive = tmp_path / "IP_合併_20261101.7z"
        archive.write_bytes(b"fake")
        extract_dir = tmp_path / "out"

        mock_z = MagicMock()
        mock_z.__enter__ = lambda s: mock_z
        mock_z.__exit__ = MagicMock(return_value=False)

        with patch("py7zr.SevenZipFile", return_value=mock_z), \
             patch.object(SinglePatchEngine, "scan_patch_dir",
                          return_value={"release_note": None, "form_files": [],
                                        "sql_files": [], "muti_files": [],
                                        "setup_bat": False, "install_guide": None,
                                        "missing": []}):
            eng = SinglePatchEngine(conn)
            patch_id, version_tag, issue_count = eng.load_from_archive(
                str(archive), str(extract_dir)
            )
        assert version_tag == "IP_合併_20261101"
        assert isinstance(patch_id, int)
        assert issue_count == 0

    def test_load_from_archive_loads_issues_from_release_note(self, conn, tmp_path):
        from unittest.mock import MagicMock, patch
        archive = tmp_path / "IP_合併_20261201.7z"
        archive.write_bytes(b"fake")
        extract_dir = tmp_path / "out"
        fake_release = str(tmp_path / "ReleaseNote.docx")

        mock_z = MagicMock()
        mock_z.__enter__ = lambda s: mock_z
        mock_z.__exit__ = MagicMock(return_value=False)

        fake_scan = {"release_note": fake_release, "form_files": ["A.fmx"],
                     "sql_files": [], "muti_files": [],
                     "setup_bat": False, "install_guide": None, "missing": []}
        fake_issues = [{"issue_no": "0015659", "issue_type": "BugFix",
                        "description": "修正", "region": "TW"}]

        with patch("py7zr.SevenZipFile", return_value=mock_z), \
             patch.object(SinglePatchEngine, "scan_patch_dir", return_value=fake_scan), \
             patch.object(SinglePatchEngine, "read_release_doc", return_value=fake_issues):
            eng = SinglePatchEngine(conn)
            patch_id, version_tag, issue_count = eng.load_from_archive(
                str(archive), str(extract_dir)
            )
        assert issue_count == 1
        assert version_tag == "IP_合併_20261201"
```

- [ ] **Step 2: 確認測試失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestLoadFromArchive -v
```
預期：FAIL（`AttributeError: 'SinglePatchEngine' object has no attribute '_parse_version_tag'`）

- [ ] **Step 3: 實作 `_parse_version_tag` 與 `load_from_archive`**

在 `patch_engine.py` 的 `extract_patch_archives` 方法前加入：

```python
def load_from_archive(self, archive_path: str, output_dir: str) -> tuple[int, str, int]:
    """解壓 .7z 至 output_dir，掃描目錄，建立 DB Patch 記錄，讀 ReleaseNote。
    Returns (patch_id, version_tag, issue_count)
    """
    import py7zr
    archive = Path(archive_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with py7zr.SevenZipFile(str(archive), mode="r") as z:
        z.extractall(path=str(out))
    version_tag = self._parse_version_tag(archive.name)
    patch = PatchRecord(type="single", patch_dir=str(out))
    patch_id = self._repo.insert_patch(patch)
    scan = self.scan_patch_dir(str(out))
    issue_count = 0
    if scan.get("release_note"):
        issue_count = self.load_issues_from_release_doc(patch_id, scan["release_note"])
    return patch_id, version_tag, issue_count

def _parse_version_tag(self, filename: str) -> str:
    """從檔名解析版本標籤，優先比對 IP_合併_YYYYMMDD 格式。"""
    m = re.search(r"IP_合併_\d{8}", filename)
    if m:
        return m.group(0)
    stem = Path(filename).stem
    return stem[:20] if len(stem) > 20 else stem
```

- [ ] **Step 4: 確認測試通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestLoadFromArchive -v
```
預期：5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/core/patch_engine.py tests/unit/test_patch_engine.py
git commit -m "feat(core): 新增 SinglePatchEngine.load_from_archive 與 _parse_version_tag"
```

---

## Task 2：`generate_issue_list`（3 頁籤 Issue清單整理 xlsx）

**Files:**
- Modify: `src/hcp_cms/core/patch_engine.py`
- Test: `tests/unit/test_patch_engine.py`

### 背景
`generate_issue_list` 產出 `{version_tag}_Issue清單整理.xlsx`，含 3 個 sheet：
1. **ReleaseNote**（13 欄）：Issue No / 類型 / 程式代號 / 程式名稱 / 說明 / 客服驗證 / 測試結果(客服) / 測試日期(客服) / 提供客戶驗證 / 測試結果(客戶) / 測試日期(客戶) / 可納入大PATCH / 備註
2. **安裝說明**（2 欄）：Issue No / 安裝步驟（資料列空白，供人工填寫）
3. **檔案清單**（2 欄）：子目錄 / 檔名（來自 PatchRecord.patch_dir 下 form/、sql/、muti/ 子目錄）

同時需在 `_write_header_row` 加入 `fgColor` 參數（預設 `"1F3864"`，向下相容）。

- [ ] **Step 1: 寫失敗測試**

在 `tests/unit/test_patch_engine.py` 新增 `TestGenerateIssueList` 類別（新增於既有測試末尾）：

```python
class TestGenerateIssueList:
    @pytest.fixture
    def engine_with_patch(self, conn, tmp_path):
        from hcp_cms.data.models import PatchIssue, PatchRecord
        from hcp_cms.data.repositories import PatchRepository
        patch_path = tmp_path / "patch_src"
        patch_path.mkdir()
        (patch_path / "form").mkdir()
        (patch_path / "sql").mkdir()
        (patch_path / "form" / "PAYROLL.fmx").write_text("")
        (patch_path / "sql" / "update.sql").write_text("")
        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="single", patch_dir=str(patch_path)))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="0015659",
                                     issue_type="BugFix", region="TW",
                                     description="薪資修正", sort_order=1))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="0015660",
                                     issue_type="Enhancement", region="共用",
                                     description="新增功能", sort_order=2))
        return SinglePatchEngine(conn), pid

    def test_creates_file_with_version_tag(self, engine_with_patch, tmp_path):
        eng, pid = engine_with_patch
        path = eng.generate_issue_list(pid, str(tmp_path / "out"), "IP_合併_20261101")
        assert Path(path).exists()
        assert "IP_合併_20261101_Issue清單整理" in path

    def test_releasenote_sheet_13_columns(self, engine_with_patch, tmp_path):
        import openpyxl
        eng, pid = engine_with_patch
        path = eng.generate_issue_list(pid, str(tmp_path / "out"), "IP_合併_20261101")
        wb = openpyxl.load_workbook(path)
        assert "ReleaseNote" in wb.sheetnames
        ws = wb["ReleaseNote"]
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        assert headers[0] == "Issue No"
        assert "客服驗證" in headers
        assert "提供客戶驗證" in headers
        assert "可納入大PATCH" in headers
        assert "備註" in headers
        assert len(headers) == 13

    def test_installation_sheet_exists(self, engine_with_patch, tmp_path):
        import openpyxl
        eng, pid = engine_with_patch
        path = eng.generate_issue_list(pid, str(tmp_path / "out"), "IP_合併_20261101")
        wb = openpyxl.load_workbook(path)
        assert "安裝說明" in wb.sheetnames
        ws = wb["安裝說明"]
        assert ws.cell(1, 1).value == "Issue No"
        assert ws.cell(1, 2).value == "安裝步驟"

    def test_file_list_sheet_lists_files(self, engine_with_patch, tmp_path):
        import openpyxl
        eng, pid = engine_with_patch
        path = eng.generate_issue_list(pid, str(tmp_path / "out"), "IP_合併_20261101")
        wb = openpyxl.load_workbook(path)
        assert "檔案清單" in wb.sheetnames
        ws = wb["檔案清單"]
        file_names = [ws.cell(r, 2).value for r in range(2, ws.max_row + 1)
                      if ws.cell(r, 2).value]
        assert "PAYROLL.fmx" in file_names
        assert "update.sql" in file_names
```

- [ ] **Step 2: 確認測試失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestGenerateIssueList -v
```
預期：FAIL（`AttributeError: 'SinglePatchEngine' object has no attribute 'generate_issue_list'`）

- [ ] **Step 3: 更新 `_write_header_row`，加入 `fgColor` 參數**

將現有 `_write_header_row` 方法（在 `generate_excel_reports` 後、`generate_test_scripts` 前）改為：

```python
def _write_header_row(self, ws: object, headers: list[str],
                      fgColor: str = "1F3864") -> None:
    from openpyxl.styles import Alignment, Font, PatternFill
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(1, c)
        cell.value = h
        cell.font = Font(name="微軟正黑體", bold=True, size=11, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=fgColor)
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
```

- [ ] **Step 4: 實作 `generate_issue_list`**

在 `_write_header_row` 方法後、`generate_test_scripts` 前插入：

```python
def generate_issue_list(self, patch_id: int, output_dir: str,
                        version_tag: str) -> str:
    """產出 {version_tag}_Issue清單整理.xlsx（3 頁籤）。"""
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill

    issues = self._repo.list_issues_by_patch(patch_id)
    patch_rec = self._repo.get_patch_by_id(patch_id)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    wb = Workbook()

    # ── Tab 1: ReleaseNote ──────────────────────────────────────────────
    ws = wb.active
    ws.title = "ReleaseNote"
    rn_headers = [
        "Issue No", "類型", "程式代號", "程式名稱", "說明",
        "客服驗證", "測試結果(客服)", "測試日期(客服)",
        "提供客戶驗證", "測試結果(客戶)", "測試日期(客戶)",
        "可納入大PATCH", "備註",
    ]
    self._write_header_row(ws, rn_headers)
    for row_i, iss in enumerate(issues, start=2):
        ws.cell(row_i, 1).value = iss.issue_no
        ws.cell(row_i, 2).value = iss.issue_type
        ws.cell(row_i, 3).value = iss.program_code
        ws.cell(row_i, 4).value = iss.program_name
        ws.cell(row_i, 5).value = iss.description
        row_clr = self._CLR_ENH if iss.issue_type == "Enhancement" else self._CLR_BUG
        for c in range(1, 6):
            ws.cell(row_i, c).fill = PatternFill("solid", fgColor=row_clr)
        for c in range(6, 9):
            ws.cell(row_i, c).fill = PatternFill("solid", fgColor=self._CLR_CS)
        for c in range(9, 12):
            ws.cell(row_i, c).fill = PatternFill("solid", fgColor=self._CLR_CUST)
        ws.cell(row_i, 12).fill = PatternFill("solid", fgColor=self._CLR_PATCH)
        ws.cell(row_i, 13).fill = PatternFill("solid", fgColor=self._CLR_NOTE)

    # ── Tab 2: 安裝說明 ───────────────────────────────────────────────────
    ws2 = wb.create_sheet("安裝說明")
    self._write_header_row(ws2, ["Issue No", "安裝步驟"])
    for row_i, iss in enumerate(issues, start=2):
        ws2.cell(row_i, 1).value = iss.issue_no

    # ── Tab 3: 檔案清單 ───────────────────────────────────────────────────
    ws3 = wb.create_sheet("檔案清單")
    self._write_header_row(ws3, ["子目錄", "檔名"])
    file_row = 2
    patch_dir = (Path(patch_rec.patch_dir)
                 if patch_rec and patch_rec.patch_dir else None)
    if patch_dir:
        for sub in ("form", "sql", "muti"):
            sub_path = patch_dir / sub
            if sub_path.exists():
                for f in sorted(sub_path.iterdir()):
                    if f.is_file():
                        ws3.cell(file_row, 1).value = sub + "/"
                        ws3.cell(file_row, 2).value = f.name
                        file_row += 1

    fname = f"{version_tag}_Issue清單整理.xlsx"
    path = str(out / fname)
    wb.save(path)
    return path
```

- [ ] **Step 5: 確認測試通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestGenerateIssueList -v
```
預期：4 tests PASS

- [ ] **Step 6: 確認既有測試未損**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py -v
```
預期：全部 PASS

- [ ] **Step 7: Commit**

```bash
git add src/hcp_cms/core/patch_engine.py tests/unit/test_patch_engine.py
git commit -m "feat(core): 新增 generate_issue_list（3 頁籤 Issue清單整理）"
```

---

## Task 3：`generate_release_notice`（1 頁籤發行通知 xlsx）

**Files:**
- Modify: `src/hcp_cms/core/patch_engine.py`
- Test: `tests/unit/test_patch_engine.py`

- [ ] **Step 1: 寫失敗測試**

在 `tests/unit/test_patch_engine.py` 末尾新增：

```python
class TestGenerateReleaseNotice:
    @pytest.fixture
    def engine_with_patch(self, conn):
        from hcp_cms.data.models import PatchIssue, PatchRecord
        from hcp_cms.data.repositories import PatchRepository
        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="single"))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="0015659",
                                     issue_type="BugFix", description="修正薪資",
                                     sort_order=1))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="0015660",
                                     issue_type="Enhancement", description="新增功能",
                                     sort_order=2))
        return SinglePatchEngine(conn), pid

    def test_creates_file_with_version_tag(self, engine_with_patch, tmp_path):
        eng, pid = engine_with_patch
        path = eng.generate_release_notice(pid, str(tmp_path), "IP_合併_20261101")
        assert Path(path).exists()
        assert "IP_合併_20261101_發行通知" in path

    def test_single_sheet_with_5_columns(self, engine_with_patch, tmp_path):
        import openpyxl
        eng, pid = engine_with_patch
        path = eng.generate_release_notice(pid, str(tmp_path), "IP_合併_20261101")
        wb = openpyxl.load_workbook(path)
        assert len(wb.sheetnames) == 1
        ws = wb.active
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        assert headers == ["Issue No", "類型", "說明", "相關程式", "安裝步驟"]

    def test_no_tracking_columns(self, engine_with_patch, tmp_path):
        import openpyxl
        eng, pid = engine_with_patch
        path = eng.generate_release_notice(pid, str(tmp_path), "IP_合併_20261101")
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        assert "客服驗證" not in headers
        assert "可納入大PATCH" not in headers
```

- [ ] **Step 2: 確認測試失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestGenerateReleaseNotice -v
```
預期：FAIL（`AttributeError: 'SinglePatchEngine' object has no attribute 'generate_release_notice'`）

- [ ] **Step 3: 實作 `generate_release_notice`**

緊接在 `generate_issue_list` 方法後插入：

```python
def generate_release_notice(self, patch_id: int, output_dir: str,
                             version_tag: str) -> str:
    """產出 {version_tag}_發行通知.xlsx（1 頁籤，對外客戶用）。"""
    from openpyxl import Workbook

    issues = self._repo.list_issues_by_patch(patch_id)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "發行通知"
    self._write_header_row(ws, ["Issue No", "類型", "說明", "相關程式", "安裝步驟"])
    for row_i, iss in enumerate(issues, start=2):
        ws.cell(row_i, 1).value = iss.issue_no
        ws.cell(row_i, 2).value = iss.issue_type
        ws.cell(row_i, 3).value = iss.description

    fname = f"{version_tag}_發行通知.xlsx"
    path = str(out / fname)
    wb.save(path)
    return path
```

- [ ] **Step 4: 確認測試通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestGenerateReleaseNotice -v
```
預期：3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/core/patch_engine.py tests/unit/test_patch_engine.py
git commit -m "feat(core): 新增 generate_release_notice（1 頁籤發行通知）"
```

---

## Task 4：`generate_issue_split`（IT/HR 2 頁籤 xlsx）

**Files:**
- Modify: `src/hcp_cms/core/patch_engine.py`
- Test: `tests/unit/test_patch_engine.py`

### 欄位說明
**IT sheet**（header 色：深藍 `#1F4E79`，8 欄）：Issue No / 類型 / 程式代號 / 說明 / FORM 目錄 / DB 物件 / 多語更新 / 備註
- 類型欄填色：BugFix=淡橘 `FCE4D6`；Enhancement=淡綠 `E2EFDA`

**HR sheet**（header 色：深綠 `#1E5631`，11 欄）：Issue No / 計區域 / 類型 / 程式代號 / 程式名稱 / 功能說明 / 影響說明/用途 / 相關程式(FORM) / 上線所需動作 / 測試方向及注意事項 / 備註
- 計區域填色：CN=淡橘黃 `FFE0B2`；TW=淡藍 `DBEAFE`；共用=淡綠 `DCFCE7`
- 類型填色：同 IT
- 上線所需動作（欄 9）固定文字：`"請與資訊單位確認是否已完成更新，確認更新完成再進行測試"`

- [ ] **Step 1: 寫失敗測試**

在 `tests/unit/test_patch_engine.py` 末尾新增：

```python
class TestGenerateIssueSplit:
    @pytest.fixture
    def engine_with_patch(self, conn):
        from hcp_cms.data.models import PatchIssue, PatchRecord
        from hcp_cms.data.repositories import PatchRepository
        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="single"))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="0015659",
                                     issue_type="BugFix", region="TW",
                                     program_code="PA001", description="修正",
                                     sort_order=1))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="0015660",
                                     issue_type="Enhancement", region="CN",
                                     description="新增", sort_order=2))
        return SinglePatchEngine(conn), pid

    def test_creates_file_with_version_tag(self, engine_with_patch, tmp_path):
        eng, pid = engine_with_patch
        path = eng.generate_issue_split(pid, str(tmp_path), "IP_合併_20261101")
        assert Path(path).exists()
        assert "IP_合併_20261101_Issue清單" in path

    def test_it_sheet_8_columns(self, engine_with_patch, tmp_path):
        import openpyxl
        eng, pid = engine_with_patch
        path = eng.generate_issue_split(pid, str(tmp_path), "IP_合併_20261101")
        wb = openpyxl.load_workbook(path)
        assert "IT" in wb.sheetnames
        ws = wb["IT"]
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        assert len(headers) == 8
        assert headers[0] == "Issue No"
        assert headers[-1] == "備註"

    def test_hr_sheet_11_columns(self, engine_with_patch, tmp_path):
        import openpyxl
        eng, pid = engine_with_patch
        path = eng.generate_issue_split(pid, str(tmp_path), "IP_合併_20261101")
        wb = openpyxl.load_workbook(path)
        assert "HR" in wb.sheetnames
        ws = wb["HR"]
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        assert len(headers) == 11
        assert "計區域" in headers
        assert "上線所需動作" in headers

    def test_hr_sheet_fixed_action_text(self, engine_with_patch, tmp_path):
        import openpyxl
        eng, pid = engine_with_patch
        path = eng.generate_issue_split(pid, str(tmp_path), "IP_合併_20261101")
        wb = openpyxl.load_workbook(path)
        ws = wb["HR"]
        action_col = 9
        for row in range(2, ws.max_row + 1):
            val = ws.cell(row, action_col).value
            assert val == "請與資訊單位確認是否已完成更新，確認更新完成再進行測試"
```

- [ ] **Step 2: 確認測試失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestGenerateIssueSplit -v
```
預期：FAIL（`AttributeError: 'SinglePatchEngine' object has no attribute 'generate_issue_split'`）

- [ ] **Step 3: 實作 `generate_issue_split`**

緊接在 `generate_release_notice` 方法後插入：

```python
_CLR_REGION_CN   = "FFE0B2"
_CLR_REGION_TW   = "DBEAFE"
_CLR_REGION_COMM = "DCFCE7"

def generate_issue_split(self, patch_id: int, output_dir: str,
                         version_tag: str) -> str:
    """產出 {version_tag}_Issue清單.xlsx（IT/HR 2 頁籤）。"""
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill

    issues = self._repo.list_issues_by_patch(patch_id)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    wb = Workbook()

    # ── IT sheet ──────────────────────────────────────────────────────────
    ws_it = wb.active
    ws_it.title = "IT"
    it_headers = ["Issue No", "類型", "程式代號", "說明",
                  "FORM 目錄", "DB 物件", "多語更新", "備註"]
    self._write_header_row(ws_it, it_headers, fgColor="1F4E79")
    for row_i, iss in enumerate(issues, start=2):
        ws_it.cell(row_i, 1).value = iss.issue_no
        ws_it.cell(row_i, 2).value = iss.issue_type
        ws_it.cell(row_i, 3).value = iss.program_code
        ws_it.cell(row_i, 4).value = iss.description
        row_clr = self._CLR_ENH if iss.issue_type == "Enhancement" else self._CLR_BUG
        ws_it.cell(row_i, 2).fill = PatternFill("solid", fgColor=row_clr)

    # ── HR sheet ──────────────────────────────────────────────────────────
    ws_hr = wb.create_sheet("HR")
    hr_headers = ["Issue No", "計區域", "類型", "程式代號", "程式名稱",
                  "功能說明", "影響說明/用途", "相關程式(FORM)",
                  "上線所需動作", "測試方向及注意事項", "備註"]
    self._write_header_row(ws_hr, hr_headers, fgColor="1E5631")
    _region_clr = {"CN": self._CLR_REGION_CN, "TW": self._CLR_REGION_TW,
                   "共用": self._CLR_REGION_COMM}
    for row_i, iss in enumerate(issues, start=2):
        ws_hr.cell(row_i, 1).value = iss.issue_no
        ws_hr.cell(row_i, 2).value = iss.region
        ws_hr.cell(row_i, 3).value = iss.issue_type
        ws_hr.cell(row_i, 4).value = iss.program_code
        ws_hr.cell(row_i, 5).value = iss.program_name
        ws_hr.cell(row_i, 6).value = iss.description
        ws_hr.cell(row_i, 7).value = iss.impact
        ws_hr.cell(row_i, 9).value = (
            "請與資訊單位確認是否已完成更新，確認更新完成再進行測試"
        )
        ws_hr.cell(row_i, 10).value = iss.test_direction
        ws_hr.cell(row_i, 2).fill = PatternFill(
            "solid", fgColor=_region_clr.get(iss.region or "共用", self._CLR_REGION_COMM)
        )
        row_clr = self._CLR_ENH if iss.issue_type == "Enhancement" else self._CLR_BUG
        ws_hr.cell(row_i, 3).fill = PatternFill("solid", fgColor=row_clr)

    fname = f"{version_tag}_Issue清單.xlsx"
    path = str(out / fname)
    wb.save(path)
    return path
```

注意：`_CLR_REGION_CN`、`_CLR_REGION_TW`、`_CLR_REGION_COMM` 為 class-level 常數，加在 `_CLR_WARN` 後（現有常數區塊的末尾）。

- [ ] **Step 4: 確認測試通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestGenerateIssueSplit -v
```
預期：4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/core/patch_engine.py tests/unit/test_patch_engine.py
git commit -m "feat(core): 新增 generate_issue_split（IT/HR 2 頁籤 Issue 清單）"
```

---

## Task 5：更新 `generate_test_scripts` 支援版本標籤前綴

**Files:**
- Modify: `src/hcp_cms/core/patch_engine.py`
- Test: `tests/unit/test_patch_engine.py`

### 說明
加入 `version_tag: str = ""` 參數（向下相容），若非空則檔名前加 `{version_tag}_`。

- [ ] **Step 1: 寫失敗測試**

在 `tests/unit/test_patch_engine.py` 的 `TestGenerateTestScripts` 類別末尾新增兩個 test：

```python
    def test_version_tag_prefixes_filenames(self, engine_with_patch, tmp_path):
        eng, pid = engine_with_patch
        paths = eng.generate_test_scripts(pid, output_dir=str(tmp_path),
                                          version_tag="IP_合併_20261101")
        names = [Path(p).name for p in paths]
        assert all(n.startswith("IP_合併_20261101_") for n in names)

    def test_no_version_tag_uses_plain_filenames(self, engine_with_patch, tmp_path):
        eng, pid = engine_with_patch
        paths = eng.generate_test_scripts(pid, output_dir=str(tmp_path))
        names = [Path(p).name for p in paths]
        assert any(n == "測試腳本_客服版.docx" for n in names)
        assert any(n == "測試腳本_客戶版.docx" for n in names)
        assert any(n == "測試追蹤表.xlsx" for n in names)
```

- [ ] **Step 2: 確認測試失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestGenerateTestScripts::test_version_tag_prefixes_filenames -v
```
預期：FAIL（`TypeError: generate_test_scripts() got an unexpected keyword argument 'version_tag'`）

- [ ] **Step 3: 更新 `generate_test_scripts` 方法簽名與檔名邏輯**

將現有 `generate_test_scripts(self, patch_id: int, output_dir: str)` 的第一行改為：

```python
def generate_test_scripts(self, patch_id: int, output_dir: str,
                          version_tag: str = "") -> list[str]:
```

在 `issues = self._repo.list_issues_by_patch(patch_id)` 之後、`out = Path(output_dir)` 之前插入：

```python
prefix = f"{version_tag}_" if version_tag else ""
```

並將三個 `str(out / "測試腳本_客服版.docx")`、`str(out / "測試腳本_客戶版.docx")`、`str(out / "測試追蹤表.xlsx")` 分別改為：

```python
p_cs = str(out / f"{prefix}測試腳本_客服版.docx")
...
p_cu = str(out / f"{prefix}測試腳本_客戶版.docx")
...
p_tr = str(out / f"{prefix}測試追蹤表.xlsx")
```

注意：`doc_cs.save(p_cs)`、`doc_cu.save(p_cu)`、`wb.save(p_tr)` 使用的是 local 變數名，不是硬編碼字串，請同步更新整個方法的檔名變數名稱以使用 `p_cs`、`p_cu`、`p_tr`（若現有程式已用這些名字則無需改名）。

完整更新後的方法應為：

```python
def generate_test_scripts(self, patch_id: int, output_dir: str,
                          version_tag: str = "") -> list[str]:
    """產生測試腳本_客服版.docx、客戶版.docx、測試追蹤表.xlsx。"""
    import docx as python_docx
    from openpyxl import Workbook

    issues = self._repo.list_issues_by_patch(patch_id)
    prefix = f"{version_tag}_" if version_tag else ""
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
    p_cs = str(out / f"{prefix}測試腳本_客服版.docx")
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
    p_cu = str(out / f"{prefix}測試腳本_客戶版.docx")
    doc_cu.save(p_cu)
    paths.append(p_cu)

    # 追蹤表 xlsx
    wb = Workbook()
    ws_cs = wb.active
    ws_cs.title = "客服驗證"
    self._write_header_row(ws_cs, ["Issue No", "說明", "測試結果(PASS/FAIL)",
                                   "測試日期", "備註"])
    ws_cu = wb.create_sheet("客戶驗證")
    self._write_header_row(ws_cu, ["Issue No", "說明", "測試結果(正常/異常)",
                                   "回覆日期", "備註"])
    for i, iss in enumerate(issues, start=2):
        ws_cs.cell(i, 1).value = iss.issue_no
        ws_cs.cell(i, 2).value = iss.description
        ws_cu.cell(i, 1).value = iss.issue_no
        ws_cu.cell(i, 2).value = iss.description
    p_tr = str(out / f"{prefix}測試追蹤表.xlsx")
    wb.save(p_tr)
    paths.append(p_tr)

    return paths
```

- [ ] **Step 4: 確認測試通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py::TestGenerateTestScripts -v
```
預期：5 tests PASS（含原本 3 個）

- [ ] **Step 5: 全部 patch_engine 測試通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py -v
```
預期：全部 PASS

- [ ] **Step 6: Commit**

```bash
git add src/hcp_cms/core/patch_engine.py tests/unit/test_patch_engine.py
git commit -m "feat(core): generate_test_scripts 支援版本標籤前綴"
```

---

## Task 6：改寫 `SinglePatchTab` — 5 步流程 [POC: 完全改寫 UI，需驗證 Signal 與 5 步流程互動]

**Files:**
- Modify: `src/hcp_cms/ui/patch_single_tab.py`（完全改寫）
- Modify: `tests/unit/test_patch_single_tab.py`（完全改寫）

### 新 UI 說明

**步驟條（5 步）：**
```
① 選 .7z  →  ② 解壓匯入  →  ③ 編輯  →  ④ 產報表  →  ⑤ 完成
 index 0       index 1       index 2      index 3      index 4
```

**UI 元件（由上至下）：**
1. 步驟進度列
2. `.7z 封存檔` 選擇列：`_archive_edit (readonly QLineEdit)` + `_archive_btn`
3. `輸出目錄` 選擇列：`_output_dir_edit (readonly QLineEdit)` + `_output_dir_btn`
4. `版本標籤` 列：`_version_tag_edit (QLineEdit, 可手動修改)`
5. 操作按鈕：`_load_btn "📥 解壓匯入"`
6. `_issue_table (IssueTableWidget)`
7. 產報表按鈕群（載入後 enable）：`_issue_list_btn "📊 Issue清單整理"` / `_release_notice_btn "📄 發行通知"` / `_issue_split_btn "📋 Issue清單(IT/HR)"` / `_test_scripts_btn "📝 測試腳本"`
8. `_log (QTextEdit readonly, maxHeight=150)`
9. `_output_list (QListWidget, maxHeight=100)`

**Signals（class-level）：**
- `_load_done = Signal(object)` — dict: `{patch_id, version_tag, issue_count, error}`
- `_generate_done = Signal(object)` — dict: `{type, paths, error}`

**state：**
- `self._patch_id: int | None`
- `self._version_tag: str`（從 .7z 檔名自動解析，可由 `_version_tag_edit` 修改）

**關鍵邏輯：**
- 選 .7z 後：自動解析 `IP_合併_\d{8}` 填入 `_version_tag_edit`；步驟 → index 1
- 解壓匯入成功後：`_version_tag_edit` 若空則自動填入 engine 回傳的 tag；4 個產報表按鈕 enable；步驟 → index 2
- 點任一產報表按鈕時：步驟 → index 3（產報表進行中）
- 產報表成功後：步驟 → index 4（完成）

- [ ] **Step 1: 寫失敗測試**

**完整改寫** `tests/unit/test_patch_single_tab.py`：

```python
"""SinglePatchTab 單元測試（5 步 .7z 流程）。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import PatchRecord
from hcp_cms.data.repositories import PatchRepository


@pytest.fixture
def db(tmp_path):
    dm = DatabaseManager(str(tmp_path / "t.db"))
    dm.initialize()
    conn = dm.connection
    yield conn
    conn.close()


def test_single_patch_tab_instantiates(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    assert tab._archive_edit is not None
    assert tab._output_dir_edit is not None
    assert tab._version_tag_edit is not None
    assert tab._issue_table is not None
    assert tab._log is not None


def test_step_labels_are_5(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    assert len(tab._step_labels) == 5


def test_generate_buttons_disabled_initially(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    assert not tab._issue_list_btn.isEnabled()
    assert not tab._release_notice_btn.isEnabled()
    assert not tab._issue_split_btn.isEnabled()
    assert not tab._test_scripts_btn.isEnabled()


def test_archive_browse_sets_path_and_version_tag(qtbot, db, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from hcp_cms.ui.patch_single_tab import SinglePatchTab

    fake_archive = str(tmp_path / "IP_合併_20261101_HCP.7z")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        lambda *a, **kw: (fake_archive, ""),
    )
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._on_archive_browse_clicked()
    assert tab._archive_edit.text() == fake_archive
    assert tab._version_tag_edit.text() == "IP_合併_20261101"


def test_output_dir_browse_sets_path(qtbot, db, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from hcp_cms.ui.patch_single_tab import SinglePatchTab

    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory",
        lambda *a, **kw: str(tmp_path),
    )
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._on_output_dir_browse_clicked()
    assert tab._output_dir_edit.text() == str(tmp_path)


def test_load_disabled_without_archive_or_output(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._on_load_clicked()  # 無 archive/output，直接 return，不 crash


def test_load_result_enables_generate_buttons(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    result = {"patch_id": 1, "version_tag": "IP_合併_20261101",
              "issue_count": 2, "error": None}
    tab._on_load_result(result)
    assert tab._patch_id == 1
    assert tab._issue_list_btn.isEnabled()
    assert tab._release_notice_btn.isEnabled()
    assert tab._issue_split_btn.isEnabled()
    assert tab._test_scripts_btn.isEnabled()


def test_load_result_error_keeps_buttons_disabled(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    result = {"patch_id": None, "version_tag": "", "issue_count": 0,
              "error": "解壓縮失敗"}
    tab._on_load_result(result)
    assert tab._patch_id is None
    assert not tab._issue_list_btn.isEnabled()


def test_load_done_signal_emitted(qtbot, db, tmp_path):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    from hcp_cms.core.patch_engine import SinglePatchEngine

    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._archive_edit.setText(str(tmp_path / "fake.7z"))
    tab._output_dir_edit.setText(str(tmp_path))

    with patch.object(SinglePatchEngine, "load_from_archive",
                      return_value=(1, "IP_合併_20261101", 0)):
        with qtbot.waitSignal(tab._load_done, timeout=3000):
            tab._on_load_clicked()


def test_generate_result_appends_to_output_list(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    result = {"type": "issue_list",
              "paths": ["/tmp/IP_合併_20261101_Issue清單整理.xlsx"],
              "error": None}
    tab._on_generate_result(result)
    assert tab._output_list.count() == 1


def test_generate_done_signal_emitted(qtbot, db, tmp_path):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    from hcp_cms.core.patch_engine import SinglePatchEngine

    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._patch_id = 1
    tab._version_tag = "IP_合併_20261101"
    tab._output_dir_edit.setText(str(tmp_path))

    fake_path = str(tmp_path / "IP_合併_20261101_Issue清單整理.xlsx")
    with patch.object(SinglePatchEngine, "generate_issue_list",
                      return_value=fake_path):
        with qtbot.waitSignal(tab._generate_done, timeout=3000):
            tab._on_issue_list_clicked()
```

- [ ] **Step 2: 確認測試失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_single_tab.py -v
```
預期：多數 FAIL（舊 UI 屬性不存在）

- [ ] **Step 3: 完全改寫 `patch_single_tab.py`**

用以下內容**完整取代** `src/hcp_cms/ui/patch_single_tab.py`：

```python
"""SinglePatchTab — 單次 Patch 整理五步流程。"""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.ui.widgets.issue_table_widget import IssueTableWidget

_STEPS = ["① 選 .7z", "② 解壓匯入", "③ 編輯", "④ 產報表", "⑤ 完成"]
_CLR_DONE    = "color: #22c55e; font-weight: bold;"
_CLR_CURRENT = "color: #3b82f6; font-weight: bold;"
_CLR_PENDING = "color: #64748b;"


class SinglePatchTab(QWidget):
    _load_done     = Signal(object)
    _generate_done = Signal(object)

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._patch_id: int | None = None
        self._version_tag: str = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 步驟進度列
        self._step_labels: list[QLabel] = []
        step_bar = QHBoxLayout()
        for i, title in enumerate(_STEPS):
            lbl = QLabel(title)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._step_labels.append(lbl)
            step_bar.addWidget(lbl)
            if i < len(_STEPS) - 1:
                arrow = QLabel("→")
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                step_bar.addWidget(arrow)
        layout.addLayout(step_bar)

        # .7z 選擇列
        archive_row = QHBoxLayout()
        archive_row.addWidget(QLabel(".7z 封存檔："))
        self._archive_edit = QLineEdit()
        self._archive_edit.setPlaceholderText("選擇 .7z 封存檔…")
        self._archive_edit.setReadOnly(True)
        self._archive_btn = QPushButton("瀏覽…")
        archive_row.addWidget(self._archive_edit)
        archive_row.addWidget(self._archive_btn)
        layout.addLayout(archive_row)

        # 輸出目錄列
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("輸出目錄："))
        self._output_dir_edit = QLineEdit()
        self._output_dir_edit.setPlaceholderText("選擇輸出目錄…")
        self._output_dir_edit.setReadOnly(True)
        self._output_dir_btn = QPushButton("瀏覽…")
        output_row.addWidget(self._output_dir_edit)
        output_row.addWidget(self._output_dir_btn)
        layout.addLayout(output_row)

        # 版本標籤列
        tag_row = QHBoxLayout()
        tag_row.addWidget(QLabel("版本標籤："))
        self._version_tag_edit = QLineEdit()
        self._version_tag_edit.setPlaceholderText("如：IP_合併_20261101")
        tag_row.addWidget(self._version_tag_edit)
        tag_row.addStretch()
        layout.addLayout(tag_row)

        # 解壓匯入按鈕
        action_row = QHBoxLayout()
        self._load_btn = QPushButton("📥 解壓匯入")
        action_row.addWidget(self._load_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        # Issue 表格
        self._issue_table = IssueTableWidget(conn=self._conn)
        layout.addWidget(self._issue_table, stretch=2)

        # 產報表按鈕群
        gen_row = QHBoxLayout()
        self._issue_list_btn     = QPushButton("📊 Issue清單整理")
        self._release_notice_btn = QPushButton("📄 發行通知")
        self._issue_split_btn    = QPushButton("📋 Issue清單(IT/HR)")
        self._test_scripts_btn   = QPushButton("📝 測試腳本")
        for btn in [self._issue_list_btn, self._release_notice_btn,
                    self._issue_split_btn, self._test_scripts_btn]:
            btn.setEnabled(False)
            gen_row.addWidget(btn)
        gen_row.addStretch()
        layout.addLayout(gen_row)

        # 執行 Log
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(150)
        layout.addWidget(self._log)

        # 產出清單
        self._output_list = QListWidget()
        self._output_list.setMaximumHeight(100)
        layout.addWidget(self._output_list)

        # Signal / Slot 連線
        self._archive_btn.clicked.connect(self._on_archive_browse_clicked)
        self._output_dir_btn.clicked.connect(self._on_output_dir_browse_clicked)
        self._version_tag_edit.textChanged.connect(self._on_version_tag_changed)
        self._load_btn.clicked.connect(self._on_load_clicked)
        self._issue_list_btn.clicked.connect(self._on_issue_list_clicked)
        self._release_notice_btn.clicked.connect(self._on_release_notice_clicked)
        self._issue_split_btn.clicked.connect(self._on_issue_split_clicked)
        self._test_scripts_btn.clicked.connect(self._on_test_scripts_clicked)
        self._load_done.connect(self._on_load_result)
        self._generate_done.connect(self._on_generate_result)

        self._set_step(0)

    # ── 步驟高亮 ──────────────────────────────────────────────────────────

    def _set_step(self, step: int) -> None:
        for i, lbl in enumerate(self._step_labels):
            if i < step:
                lbl.setStyleSheet(_CLR_DONE)
            elif i == step:
                lbl.setStyleSheet(_CLR_CURRENT)
            else:
                lbl.setStyleSheet(_CLR_PENDING)

    def _append_log(self, msg: str) -> None:
        self._log.append(msg)

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_archive_browse_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇 .7z 封存檔", "", "7z Archives (*.7z)"
        )
        if not path:
            return
        self._archive_edit.setText(path)
        m = re.search(r"IP_合併_\d{8}", Path(path).name)
        tag = m.group(0) if m else Path(path).stem
        self._version_tag_edit.setText(tag[:20] if len(tag) > 20 else tag)
        self._set_step(1)

    def _on_output_dir_browse_clicked(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "選擇輸出目錄")
        if path:
            self._output_dir_edit.setText(path)

    def _on_version_tag_changed(self, text: str) -> None:
        self._version_tag = text.strip()

    def _on_load_clicked(self) -> None:
        archive = self._archive_edit.text()
        output_dir = self._output_dir_edit.text()
        if not archive or not output_dir or not self._conn:
            return
        self._load_btn.setEnabled(False)
        self._append_log("📥 解壓匯入中…")
        conn = self._conn

        def work() -> dict:
            from hcp_cms.core.patch_engine import SinglePatchEngine
            engine = SinglePatchEngine(conn)
            try:
                patch_id, version_tag, issue_count = engine.load_from_archive(
                    archive, output_dir
                )
                return {"patch_id": patch_id, "version_tag": version_tag,
                        "issue_count": issue_count, "error": None}
            except Exception as e:
                return {"patch_id": None, "version_tag": "",
                        "issue_count": 0, "error": str(e)}

        threading.Thread(
            target=lambda: self._load_done.emit(work()), daemon=True
        ).start()

    def _on_load_result(self, result: dict) -> None:
        self._load_btn.setEnabled(True)
        if result.get("error"):
            self._append_log(f"❌ 匯入失敗：{result['error']}")
            return
        self._patch_id = result["patch_id"]
        if not self._version_tag and result.get("version_tag"):
            self._version_tag = result["version_tag"]
            self._version_tag_edit.setText(self._version_tag)
        self._append_log(f"✅ 匯入完成：{result['issue_count']} 筆 Issue")
        if self._patch_id is not None:
            self._issue_table.load_issues(self._patch_id)
        for btn in [self._issue_list_btn, self._release_notice_btn,
                    self._issue_split_btn, self._test_scripts_btn]:
            btn.setEnabled(True)
        self._set_step(2)

    def _on_issue_list_clicked(self) -> None:
        self._start_generate("issue_list")

    def _on_release_notice_clicked(self) -> None:
        self._start_generate("release_notice")

    def _on_issue_split_clicked(self) -> None:
        self._start_generate("issue_split")

    def _on_test_scripts_clicked(self) -> None:
        self._start_generate("test_scripts")

    def _start_generate(self, gen_type: str) -> None:
        if self._patch_id is None or not self._conn:
            return
        output_dir = self._output_dir_edit.text() or "."
        patch_id = self._patch_id
        version_tag = self._version_tag
        conn = self._conn
        self._set_step(3)
        self._append_log(f"⏳ 產出中（{gen_type}）…")

        def work() -> dict:
            from hcp_cms.core.patch_engine import SinglePatchEngine
            engine = SinglePatchEngine(conn)
            try:
                if gen_type == "issue_list":
                    paths = [engine.generate_issue_list(patch_id, output_dir,
                                                        version_tag)]
                elif gen_type == "release_notice":
                    paths = [engine.generate_release_notice(patch_id, output_dir,
                                                            version_tag)]
                elif gen_type == "issue_split":
                    paths = [engine.generate_issue_split(patch_id, output_dir,
                                                         version_tag)]
                else:
                    paths = engine.generate_test_scripts(patch_id, output_dir,
                                                         version_tag)
                return {"type": gen_type, "paths": paths, "error": None}
            except Exception as e:
                return {"type": gen_type, "paths": [], "error": str(e)}

        threading.Thread(
            target=lambda: self._generate_done.emit(work()), daemon=True
        ).start()

    def _on_generate_result(self, result: dict) -> None:
        if result.get("error"):
            self._append_log(f"❌ 產出失敗：{result['error']}")
            return
        for path in result.get("paths", []):
            self._output_list.addItem(QListWidgetItem(path))
            self._append_log(f"✅ {path}")
        self._set_step(4)
```

- [ ] **Step 4: 確認測試通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_single_tab.py -v
```
預期：12 tests PASS

- [ ] **Step 5: 全套測試**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py tests/unit/test_patch_single_tab.py -v
```
預期：全部 PASS

- [ ] **Step 6: Lint**

```
.venv/Scripts/ruff.exe check src/hcp_cms/ui/patch_single_tab.py src/hcp_cms/core/patch_engine.py
```
預期：無錯誤

- [ ] **Step 7: Commit**

```bash
git add src/hcp_cms/ui/patch_single_tab.py tests/unit/test_patch_single_tab.py
git commit -m "feat(ui): 改寫 SinglePatchTab — 5 步 .7z 流程、4 個產報表按鈕"
```

---

## 自我驗收清單

執行完所有 Task 後確認：

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_patch_engine.py tests/unit/test_patch_single_tab.py -v
```
預期：全部 PASS，無任何 ERROR 或 FAIL。

```bash
.venv/Scripts/ruff.exe check src/hcp_cms/core/patch_engine.py src/hcp_cms/ui/patch_single_tab.py
```
預期：無 lint 錯誤。
