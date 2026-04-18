# 月 PATCH 強化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 強化現有月 PATCH Tab，補齊 Excel 正確格式、S2T 轉換、超連結驗證、Mantis 補充說明、HTML 通知信季節橫幅及排班提醒等功能。

**Architecture:** 在現有 `MonthlyPatchEngine`（Core 層）新增 5 個公開方法；`ClaudeContentService`（Services 層）新增 `extract_supplement`；`templates/patch_notify.html.j2` 完整重寫；`MonthlyPatchTab`（UI 層）擴展步驟條與新增 3 個互動區塊。

**Tech Stack:** PySide6、openpyxl、python-docx、opencc-python-reimplemented（已安裝）、Jinja2、Anthropic SDK、MantisSoapClient（現有）

---

## 檔案結構

| 動作 | 路徑 | 職責 |
|------|------|------|
| 修改 | `src/hcp_cms/core/monthly_patch_engine.py` | 新增 `run_s2t`、`fetch_supplements`、`_fetch_supplement`、`verify_patch_links`；修正 `generate_patch_list_from_dir`；更新 `generate_notify_html` |
| 修改 | `src/hcp_cms/services/claude_content.py` | 新增 `extract_supplement` |
| 修改 | `templates/patch_notify.html.j2` | 完整重寫：季節橫幅、左右分欄、固定 checklist |
| 修改 | `src/hcp_cms/ui/patch_monthly_tab.py` | 9 步驟條、S2T 按鈕、驗證按鈕、排班提醒列表、底圖上傳 |
| 修改 | `tests/unit/test_monthly_patch_engine.py` | 補充 Task 1–5 測試 |
| 新增 | `tests/unit/test_claude_content_supplement.py` | extract_supplement 測試 |

---

## Task 1：Excel 格式修正（IT/HR/補充說明欄位與樣式）

**Files:**
- Modify: `src/hcp_cms/core/monthly_patch_engine.py:406-487`
- Test: `tests/unit/test_monthly_patch_engine.py`

### 目標
1. IT 欄位名稱：`"程式代碼"` → `"程式代號"`
2. IT/HR 第 1 欄（Issue No）加藍色超連結至測試報告
3. 資料列所有儲存格套用 `微軟正黑體 11pt`
4. 補充說明 sheet 擴展為 7 欄（加入 修改原因/原問題/範例說明/修正後/注意事項）

- [ ] **Step 1：寫失敗測試（IT 欄名 + 超連結）**

```python
# tests/unit/test_monthly_patch_engine.py
# 在 TestGeneratePatchListFromDir 中新增：

def test_it_sheet_column_names(self, conn, tmp_path):
    import json
    from openpyxl import load_workbook
    from hcp_cms.data.repositories import PatchRepository
    from hcp_cms.data.models import PatchRecord, PatchIssue

    repo = PatchRepository(conn)
    pid = repo.insert_patch(PatchRecord(type="monthly", month_str="202604", patch_dir=str(tmp_path)))
    repo.insert_issue(PatchIssue(
        patch_id=pid, issue_no="0016552", issue_type="BugFix",
        region="共用", description="測試", source="scan",
        mantis_detail=json.dumps({"form_files": [], "sql_files": [], "muti_files": []})
    ))
    (tmp_path / "11G").mkdir()

    eng = MonthlyPatchEngine(conn)
    paths = eng.generate_patch_list_from_dir({"11G": pid}, str(tmp_path), "202604")

    wb = load_workbook(paths[0])
    ws_it = wb["IT 發行通知"]
    headers = [ws_it.cell(1, c).value for c in range(1, 9)]
    assert headers == ["Issue No", "類型", "程式代號", "說明", "FORM 目錄", "DB 物件", "多語更新", "備註"]


def test_it_sheet_issue_no_hyperlink(self, conn, tmp_path):
    import json
    from openpyxl import load_workbook
    from hcp_cms.data.repositories import PatchRepository
    from hcp_cms.data.models import PatchRecord, PatchIssue

    repo = PatchRepository(conn)
    pid = repo.insert_patch(PatchRecord(type="monthly", month_str="202604", patch_dir=str(tmp_path)))
    repo.insert_issue(PatchIssue(
        patch_id=pid, issue_no="0016552", source="scan",
        mantis_detail=json.dumps({"form_files": [], "sql_files": [], "muti_files": []})
    ))
    report_dir = tmp_path / "11G" / "測試報告"
    report_dir.mkdir(parents=True)
    (report_dir / "01.IP_20241128_0016552_TESTREPORT_11G.docx").write_bytes(b"")

    eng = MonthlyPatchEngine(conn)
    paths = eng.generate_patch_list_from_dir({"11G": pid}, str(tmp_path), "202604")

    wb = load_workbook(paths[0])
    ws_it = wb["IT 發行通知"]
    cell = ws_it.cell(2, 1)
    assert cell.hyperlink is not None
    assert "0016552" in str(cell.hyperlink.target if hasattr(cell.hyperlink, "target") else cell.hyperlink)


def test_supplement_sheet_7_columns(self, conn, tmp_path):
    import json
    from openpyxl import load_workbook
    from hcp_cms.data.repositories import PatchRepository
    from hcp_cms.data.models import PatchRecord, PatchIssue

    repo = PatchRepository(conn)
    pid = repo.insert_patch(PatchRecord(type="monthly", month_str="202604", patch_dir=str(tmp_path)))
    supplement = {"修改原因": "原因說明", "原問題": "問題描述", "範例說明": "", "修正後": "修正說明", "注意事項": ""}
    repo.insert_issue(PatchIssue(
        patch_id=pid, issue_no="0016552", source="scan",
        mantis_detail=json.dumps({
            "form_files": [], "sql_files": [], "muti_files": [],
            "supplement": supplement,
        })
    ))
    (tmp_path / "11G").mkdir()

    eng = MonthlyPatchEngine(conn)
    paths = eng.generate_patch_list_from_dir({"11G": pid}, str(tmp_path), "202604")

    wb = load_workbook(paths[0])
    ws = wb["問題修正補充說明"]
    headers = [ws.cell(1, c).value for c in range(1, 8)]
    assert headers == ["Issue No", "測試報告", "修改原因", "原問題", "範例說明", "修正後", "注意事項"]
    assert ws.cell(2, 3).value == "原因說明"
    assert ws.cell(2, 4).value == "問題描述"
```

- [ ] **Step 2：執行測試，確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestGeneratePatchListFromDir::test_it_sheet_column_names -v
```
Expected: FAIL

- [ ] **Step 3：修改 `generate_patch_list_from_dir`**

在 `src/hcp_cms/core/monthly_patch_engine.py` 的 `generate_patch_list_from_dir` 方法中，替換整個方法實作（行 406–487）：

```python
def generate_patch_list_from_dir(
    self, patch_ids: dict[str, int], patch_dir: str, month_str: str
) -> list[str]:
    """依 patch_ids 各版本產 PATCH_LIST_{month_str}_{VER}.xlsx（IT/HR/補充說明格式），存至版本子目錄。"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    base = Path(patch_dir)
    paths: list[str] = []
    data_font = Font(name="微軟正黑體", size=11)
    data_align = Alignment(vertical="center", wrap_text=True)

    def _set_data_cell(cell, value):
        cell.value = value
        cell.font = data_font
        cell.alignment = data_align

    def _set_hyperlink_cell(cell, value, target):
        _set_data_cell(cell, value)
        cell.hyperlink = target
        cell.font = Font(name="微軟正黑體", size=11, color="0563C1", underline="single")

    for version, patch_id in patch_ids.items():
        issues = self._repo.list_issues_by_patch(patch_id)
        wb = Workbook()

        # ① IT 發行通知
        ws_it = wb.active
        ws_it.title = "IT 發行通知"
        self._write_patch_header(
            ws_it, ["Issue No", "類型", "程式代號", "說明", "FORM 目錄", "DB 物件", "多語更新", "備註"]
        )
        for i, iss in enumerate(issues, start=2):
            meta = self._parse_scan_meta(iss)
            report_path = self._find_test_report(base, version, iss.issue_no)
            row_fill = PatternFill("solid", fgColor=self._CLR_ENH if iss.issue_type == "Enhancement" else self._CLR_BUG)
            if report_path:
                _set_hyperlink_cell(ws_it.cell(i, 1), iss.issue_no, "file:///" + report_path.replace("\\", "/"))
            else:
                _set_data_cell(ws_it.cell(i, 1), iss.issue_no)
            _set_data_cell(ws_it.cell(i, 2), iss.issue_type)
            _set_data_cell(ws_it.cell(i, 3), iss.program_code)
            _set_data_cell(ws_it.cell(i, 4), iss.description)
            _set_data_cell(ws_it.cell(i, 5), "、".join(meta.get("form_files") or []))
            _set_data_cell(ws_it.cell(i, 6), "、".join(meta.get("sql_files") or []))
            _set_data_cell(ws_it.cell(i, 7), "\n".join(meta.get("muti_files") or []))
            _set_data_cell(ws_it.cell(i, 8), None)
            for c in range(1, 9):
                ws_it.cell(i, c).fill = row_fill

        # ② HR 發行通知
        ws_hr = wb.create_sheet("HR 發行通知")
        self._write_patch_header(ws_hr, [
            "Issue No", "計區域", "類型", "程式代號", "程式名稱",
            "功能說明", "影響說明/用途", "相關程式(FORM)",
            "上線所需動作", "測試方向及注意事項", "備註",
        ])
        for i, iss in enumerate(issues, start=2):
            meta = self._parse_scan_meta(iss)
            region_fill = PatternFill("solid", fgColor={
                "TW": self._CLR_TW, "CN": self._CLR_CN
            }.get(iss.region or "", self._CLR_BOTH))
            report_path = self._find_test_report(base, version, iss.issue_no)
            if report_path:
                _set_hyperlink_cell(ws_hr.cell(i, 1), iss.issue_no, "file:///" + report_path.replace("\\", "/"))
            else:
                _set_data_cell(ws_hr.cell(i, 1), iss.issue_no)
            _set_data_cell(ws_hr.cell(i, 2), iss.region)
            _set_data_cell(ws_hr.cell(i, 3), iss.issue_type)
            _set_data_cell(ws_hr.cell(i, 4), iss.program_code)
            _set_data_cell(ws_hr.cell(i, 5), iss.program_name)
            _set_data_cell(ws_hr.cell(i, 6), iss.description)
            _set_data_cell(ws_hr.cell(i, 7), iss.impact)
            _set_data_cell(ws_hr.cell(i, 8), "、".join(meta.get("form_files") or []))
            _set_data_cell(ws_hr.cell(i, 9), "請與資訊單位確認是否已完成更新\n確認更新完成再進行測試")
            ws_hr.cell(i, 9).fill = PatternFill("solid", fgColor="FFF9C4")
            _set_data_cell(ws_hr.cell(i, 10), iss.test_direction)
            _set_data_cell(ws_hr.cell(i, 11), None)
            for c in [1, 2, 3, 4, 5, 6, 7, 8, 10, 11]:
                ws_hr.cell(i, c).fill = region_fill

        # ③ 問題修正補充說明（7 欄，含 Mantis supplement）
        ws_supp = wb.create_sheet("問題修正補充說明")
        self._write_patch_header(ws_supp, [
            "Issue No", "測試報告", "修改原因", "原問題", "範例說明", "修正後", "注意事項"
        ])
        for i, iss in enumerate(issues, start=2):
            meta = self._parse_scan_meta(iss)
            supplement = meta.get("supplement") or {}
            _set_data_cell(ws_supp.cell(i, 1), iss.issue_no)
            report_path = self._find_test_report(base, version, iss.issue_no)
            cell2 = ws_supp.cell(i, 2)
            if report_path:
                _set_hyperlink_cell(cell2, iss.issue_no, "file:///" + report_path.replace("\\", "/"))
            else:
                _set_data_cell(cell2, iss.issue_no)
            _set_data_cell(ws_supp.cell(i, 3), supplement.get("修改原因", ""))
            _set_data_cell(ws_supp.cell(i, 4), supplement.get("原問題", ""))
            _set_data_cell(ws_supp.cell(i, 5), supplement.get("範例說明", ""))
            _set_data_cell(ws_supp.cell(i, 6), supplement.get("修正後", ""))
            _set_data_cell(ws_supp.cell(i, 7), supplement.get("注意事項", ""))

        fname = f"PATCH_LIST_{month_str}_{version}.xlsx"
        out_path = base / version / fname
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            wb.save(str(out_path))
        except PermissionError:
            raise PermissionError(f"無法寫入 {out_path.name}，請先關閉已開啟的 Excel 檔案後重試")
        paths.append(str(out_path))

    return paths
```

- [ ] **Step 4：執行測試，確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestGeneratePatchListFromDir -v
```
Expected: 全部 PASS（含原有測試）

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/core/monthly_patch_engine.py tests/unit/test_monthly_patch_engine.py
git commit -m "feat(core): 修正 PATCH_LIST Excel 格式（IT/HR 欄名、超連結、補充說明7欄）"
```

---

## Task 2：S2T 公開方法（run_s2t）

**Files:**
- Modify: `src/hcp_cms/core/monthly_patch_engine.py`
- Test: `tests/unit/test_monthly_patch_engine.py`

`_convert_simplified_to_traditional` 已存在，只需新增一個掃描目錄的公開方法。

- [ ] **Step 1：寫失敗測試**

```python
# tests/unit/test_monthly_patch_engine.py
# 新增 TestRunS2T class

class TestRunS2T:
    def test_converts_simplified_docx(self, conn, tmp_path):
        import docx as python_docx
        doc = python_docx.Document()
        doc.add_paragraph("这是简体中文内容")
        report_dir = tmp_path / "11G" / "測試報告"
        report_dir.mkdir(parents=True)
        f = report_dir / "01.IP_20241128_0016552_TESTREPORT_11G.docx"
        doc.save(str(f))

        eng = MonthlyPatchEngine(conn)
        result = eng.run_s2t(str(tmp_path))

        assert "01.IP_20241128_0016552_TESTREPORT_11G.docx" in result
        assert result["01.IP_20241128_0016552_TESTREPORT_11G.docx"] > 0

    def test_skips_traditional_docx(self, conn, tmp_path):
        import docx as python_docx
        doc = python_docx.Document()
        doc.add_paragraph("這是繁體中文內容")
        report_dir = tmp_path / "12C" / "測試報告"
        report_dir.mkdir(parents=True)
        f = report_dir / "01.IP_20241128_0016552_TESTREPORT_12C.docx"
        doc.save(str(f))

        eng = MonthlyPatchEngine(conn)
        result = eng.run_s2t(str(tmp_path))

        assert result.get("01.IP_20241128_0016552_TESTREPORT_12C.docx", -1) == 0

    def test_returns_empty_when_no_docx(self, conn, tmp_path):
        eng = MonthlyPatchEngine(conn)
        result = eng.run_s2t(str(tmp_path))
        assert result == {}
```

- [ ] **Step 2：執行測試，確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestRunS2T -v
```
Expected: FAIL（AttributeError: run_s2t）

- [ ] **Step 3：在 `MonthlyPatchEngine` 新增 `run_s2t` 方法**

在 `_convert_simplified_to_traditional` 方法之後（約行 281）插入：

```python
def run_s2t(self, scan_dir: str) -> dict[str, int]:
    """掃描 scan_dir 下所有版本子目錄的測試報告資料夾，將 .docx 簡體轉繁體。
    回傳 {filename: converted_char_count}，0 表示無需轉換。
    """
    import opencc
    import docx as python_docx

    base = Path(scan_dir)
    result: dict[str, int] = {}
    cc = opencc.OpenCC("s2t")

    for report_dir in base.rglob("測試報告"):
        if not report_dir.is_dir():
            continue
        for docx_path in sorted(report_dir.glob("*.docx")):
            try:
                doc = python_docx.Document(str(docx_path))
                changed_chars = 0
                for para in doc.paragraphs:
                    converted = cc.convert(para.text)
                    if converted != para.text:
                        diff = sum(1 for a, b in zip(para.text, converted) if a != b)
                        changed_chars += diff
                        for run in para.runs:
                            run.text = cc.convert(run.text)
                if changed_chars:
                    doc.save(str(docx_path))
                result[docx_path.name] = changed_chars
            except Exception as e:
                logging.warning("S2T 失敗 [%s]: %s", docx_path.name, e)
                result[docx_path.name] = -1
    return result
```

- [ ] **Step 4：執行測試，確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestRunS2T -v
```
Expected: PASS

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/core/monthly_patch_engine.py tests/unit/test_monthly_patch_engine.py
git commit -m "feat(core): 新增 run_s2t 掃描目錄並批次轉換簡繁"
```

---

## Task 3：ClaudeContentService.extract_supplement

**Files:**
- Modify: `src/hcp_cms/services/claude_content.py`
- Create: `tests/unit/test_claude_content_supplement.py`

- [ ] **Step 1：寫失敗測試**

```python
# tests/unit/test_claude_content_supplement.py
"""ClaudeContentService.extract_supplement 測試（mock Claude API）。"""
from unittest.mock import MagicMock, patch
import pytest
from hcp_cms.services.claude_content import ClaudeContentService


def _make_service_with_mock(response_text: str) -> ClaudeContentService:
    svc = ClaudeContentService.__new__(ClaudeContentService)
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text=response_text)]
    )
    svc._client = mock_client
    return svc


def test_extract_supplement_parses_json():
    import json
    payload = {
        "修改原因": "原始計算邏輯有誤",
        "原問題": "加班費計算不正確",
        "範例說明": "輸入 8 小時卻計算 7 小時",
        "修正後": "修正乘數為 1.5",
        "注意事項": "需重新跑月結",
    }
    svc = _make_service_with_mock(json.dumps(payload, ensure_ascii=False))
    result = svc.extract_supplement("加班費計算有誤：輸入8小時卻計算7小時")
    assert result["修改原因"] == "原始計算邏輯有誤"
    assert result["修正後"] == "修正乘數為 1.5"
    assert set(result.keys()) == {"修改原因", "原問題", "範例說明", "修正後", "注意事項"}


def test_extract_supplement_returns_empty_on_invalid_json():
    svc = _make_service_with_mock("這不是 JSON 格式")
    result = svc.extract_supplement("任意說明文字")
    assert result == {"修改原因": "", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}


def test_extract_supplement_returns_empty_when_client_none():
    svc = ClaudeContentService.__new__(ClaudeContentService)
    svc._client = None
    result = svc.extract_supplement("任意說明文字")
    assert result == {"修改原因": "", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}
```

- [ ] **Step 2：執行測試，確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_claude_content_supplement.py -v
```
Expected: FAIL

- [ ] **Step 3：在 `ClaudeContentService` 新增 `extract_supplement` 方法**

在 `generate_notify_body` 後插入（`src/hcp_cms/services/claude_content.py`）：

```python
_SUPPLEMENT_KEYS = ("修改原因", "原問題", "範例說明", "修正後", "注意事項")

def extract_supplement(self, mantis_text: str) -> dict[str, str]:
    """分析 Mantis Issue 說明，回傳結構化補充說明五欄位。"""
    empty = {k: "" for k in _SUPPLEMENT_KEYS}
    if self._client is None or not mantis_text.strip():
        return empty
    prompt = (
        "請根據以下 Mantis Issue 說明文字，以繁體中文提取並整理下列五個欄位，"
        "以 JSON 格式回傳，key 為繁體中文欄位名稱：\n"
        "欄位：修改原因、原問題、範例說明、修正後、注意事項\n"
        "若某欄位無對應內容則值為空字串。只回傳 JSON，不要其他說明。\n\n"
        f"Mantis 說明：\n{mantis_text}"
    )
    raw = self._call_api(prompt, max_tokens=600)
    if not raw:
        return empty
    try:
        import json, re
        # 擷取 JSON 區塊（Claude 有時前後有說明文字）
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return empty
        data = json.loads(match.group())
        return {k: str(data.get(k, "")) for k in _SUPPLEMENT_KEYS}
    except (ValueError, KeyError):
        return empty
```

並在檔案頂層常數區（`_MAX_RETRIES` 後）加入：
```python
_SUPPLEMENT_KEYS = ("修改原因", "原問題", "範例說明", "修正後", "注意事項")
```

- [ ] **Step 4：執行測試，確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_claude_content_supplement.py -v
```
Expected: PASS

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/services/claude_content.py tests/unit/test_claude_content_supplement.py
git commit -m "feat(services): 新增 ClaudeContentService.extract_supplement"
```

---

## Task 4：MonthlyPatchEngine.fetch_supplements（Mantis + Claude）

**Files:**
- Modify: `src/hcp_cms/core/monthly_patch_engine.py`
- Test: `tests/unit/test_monthly_patch_engine.py`

- [ ] **Step 1：寫失敗測試**

```python
# tests/unit/test_monthly_patch_engine.py
# 新增 TestFetchSupplements class

class TestFetchSupplements:
    def test_stores_supplement_in_mantis_detail(self, conn, tmp_path):
        import json
        from unittest.mock import MagicMock, patch
        from hcp_cms.data.repositories import PatchRepository
        from hcp_cms.data.models import PatchRecord, PatchIssue

        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="monthly", month_str="202604", patch_dir=str(tmp_path)))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="0016552", source="scan"))

        fake_issue = MagicMock()
        fake_issue.description = "加班費計算有誤"
        fake_issue.notes_list = []

        fake_supplement = {
            "修改原因": "原因", "原問題": "問題", "範例說明": "",
            "修正後": "修正", "注意事項": "",
        }

        with patch("hcp_cms.core.monthly_patch_engine.MantisSoapClient") as mock_cls, \
             patch("hcp_cms.core.monthly_patch_engine.ClaudeContentService") as mock_svc_cls:
            mock_client = MagicMock()
            mock_client.connect.return_value = True
            mock_client.get_issue.return_value = fake_issue
            mock_cls.return_value = mock_client

            mock_svc = MagicMock()
            mock_svc.extract_supplement.return_value = fake_supplement
            mock_svc_cls.return_value = mock_svc

            with patch("hcp_cms.core.monthly_patch_engine.CredentialManager") as mock_creds:
                mock_creds.return_value.retrieve.side_effect = lambda k: {
                    "mantis_url": "http://mantis.test", "mantis_user": "u", "mantis_password": "p"
                }.get(k, "")
                eng = MonthlyPatchEngine(conn)
                count = eng.fetch_supplements(pid)

        assert count == 1
        issues = repo.list_issues_by_patch(pid)
        detail = json.loads(issues[0].mantis_detail or "{}")
        assert detail["supplement"]["修改原因"] == "原因"

    def test_returns_zero_when_no_mantis(self, conn, tmp_path):
        from hcp_cms.data.repositories import PatchRepository
        from hcp_cms.data.models import PatchRecord, PatchIssue

        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="monthly", month_str="202604", patch_dir=str(tmp_path)))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="0016552", source="scan"))

        from unittest.mock import patch
        with patch("hcp_cms.core.monthly_patch_engine.CredentialManager") as mock_creds:
            mock_creds.return_value.retrieve.return_value = ""
            eng = MonthlyPatchEngine(conn)
            count = eng.fetch_supplements(pid)
        assert count == 0
```

- [ ] **Step 2：執行測試，確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestFetchSupplements -v
```

- [ ] **Step 3：新增 `fetch_supplements` 與 `_fetch_supplement` 方法**

在 `monthly_patch_engine.py` 的 import 區增加：
```python
from hcp_cms.services.claude_content import ClaudeContentService
from hcp_cms.services.credential import CredentialManager
from hcp_cms.services.mantis.soap import MantisSoapClient
```

在 `run_s2t` 之後插入：

```python
def fetch_supplements(self, patch_id: int) -> int:
    """從 Mantis 取得各 Issue 說明，以 Claude 整理補充說明五欄位，回傳成功筆數。"""
    client = self._build_mantis_client()
    if client is None:
        return 0
    svc = ClaudeContentService()
    issues = self._repo.list_issues_by_patch(patch_id)
    count = 0
    for iss in issues:
        supplement = self._fetch_supplement(iss.issue_no, client, svc)
        if not any(supplement.values()):
            continue
        existing = self._parse_scan_meta(iss)
        existing["supplement"] = supplement
        import json
        self._repo.update_issue_mantis_detail(iss.issue_id, json.dumps(existing, ensure_ascii=False))
        count += 1
    return count

def _fetch_supplement(
    self, issue_no: str, client: "MantisSoapClient", svc: "ClaudeContentService"
) -> dict[str, str]:
    """呼叫 Mantis + Claude，回傳補充說明五欄位 dict。"""
    empty = {"修改原因": "", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}
    try:
        issue = client.get_issue(issue_no)
        if issue is None:
            return empty
        notes_text = "\n".join(n.text for n in (issue.notes_list or []))
        full_text = f"{issue.description}\n{notes_text}".strip()
        return svc.extract_supplement(full_text)
    except Exception as e:
        logging.warning("fetch_supplement 失敗 [%s]: %s", issue_no, e)
        return empty

def _build_mantis_client(self) -> "MantisSoapClient | None":
    """從 keyring 讀取憑證建立 MantisSoapClient，失敗時回傳 None。"""
    try:
        from urllib.parse import urlparse
        creds = CredentialManager()
        url = creds.retrieve("mantis_url") or ""
        user = creds.retrieve("mantis_user") or ""
        pwd = creds.retrieve("mantis_password") or ""
        if not url:
            return None
        parsed = urlparse(url)
        path = parsed.path
        if ".php" in path:
            path = path[:path.rfind("/")]
        base_url = f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/")
        client = MantisSoapClient(base_url, user, pwd)
        client.connect()
        return client
    except Exception:
        return None
```

同時需在 `PatchRepository` 新增 `update_issue_mantis_detail` 方法（`src/hcp_cms/data/repositories.py`）：

```python
def update_issue_mantis_detail(self, issue_id: int, mantis_detail: str) -> None:
    self._conn.execute(
        "UPDATE cs_patch_issues SET mantis_detail = :d WHERE issue_id = :id",
        {"d": mantis_detail, "id": issue_id},
    )
    self._conn.commit()
```

- [ ] **Step 4：執行測試，確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestFetchSupplements -v
```

- [ ] **Step 5：執行全部測試，確認無回歸**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py -v
```

- [ ] **Step 6：Commit**

```bash
git add src/hcp_cms/core/monthly_patch_engine.py src/hcp_cms/data/repositories.py tests/unit/test_monthly_patch_engine.py
git commit -m "feat(core): 新增 fetch_supplements（Mantis+Claude 補充說明）"
```

---

## Task 5：MonthlyPatchEngine.verify_patch_links

**Files:**
- Modify: `src/hcp_cms/core/monthly_patch_engine.py`
- Test: `tests/unit/test_monthly_patch_engine.py`

- [ ] **Step 1：寫失敗測試**

```python
# tests/unit/test_monthly_patch_engine.py
# 新增 TestVerifyPatchLinks class

class TestVerifyPatchLinks:
    def test_all_links_valid(self, conn, tmp_path):
        import json
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from hcp_cms.data.repositories import PatchRepository
        from hcp_cms.data.models import PatchRecord, PatchIssue

        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="monthly", month_str="202604", patch_dir=str(tmp_path)))
        repo.insert_issue(PatchIssue(
            patch_id=pid, issue_no="0016552", source="scan",
            mantis_detail=json.dumps({"form_files": [], "sql_files": [], "muti_files": []})
        ))
        report_dir = tmp_path / "11G" / "測試報告"
        report_dir.mkdir(parents=True)
        report = report_dir / "01.IP_20241128_0016552_TESTREPORT_11G.docx"
        report.write_bytes(b"")

        eng = MonthlyPatchEngine(conn)
        paths = eng.generate_patch_list_from_dir({"11G": pid}, str(tmp_path), "202604")

        result = eng.verify_patch_links(str(tmp_path))
        assert result["11G"]["ok"] == 1
        assert result["11G"]["total"] == 1
        assert result["11G"]["failed"] == []

    def test_detects_broken_link(self, conn, tmp_path):
        import json
        from hcp_cms.data.repositories import PatchRepository
        from hcp_cms.data.models import PatchRecord, PatchIssue

        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="monthly", month_str="202604", patch_dir=str(tmp_path)))
        repo.insert_issue(PatchIssue(
            patch_id=pid, issue_no="0016552", source="scan",
            mantis_detail=json.dumps({"form_files": [], "sql_files": [], "muti_files": []})
        ))
        report_dir = tmp_path / "11G" / "測試報告"
        report_dir.mkdir(parents=True)
        report = report_dir / "01.IP_20241128_0016552_TESTREPORT_11G.docx"
        report.write_bytes(b"")

        eng = MonthlyPatchEngine(conn)
        eng.generate_patch_list_from_dir({"11G": pid}, str(tmp_path), "202604")
        report.unlink()  # 刪除測試報告，超連結失效

        result = eng.verify_patch_links(str(tmp_path))
        assert result["11G"]["ok"] == 0
        assert len(result["11G"]["failed"]) == 1
        assert "0016552" in result["11G"]["failed"][0]
```

- [ ] **Step 2：執行測試，確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestVerifyPatchLinks -v
```

- [ ] **Step 3：新增 `verify_patch_links` 方法**

在 `generate_patch_list_from_dir` 之前插入：

```python
def verify_patch_links(self, patch_dir: str) -> dict[str, dict]:
    """掃描 patch_dir 下各版本 PATCH_LIST_*.xlsx，驗證 Issue No 超連結是否有效。
    回傳 {version: {"total": N, "ok": N, "failed": [issue_no_or_path, ...]}}
    """
    import openpyxl

    base = Path(patch_dir)
    result: dict[str, dict] = {}
    for version_dir in sorted(base.iterdir()):
        if not version_dir.is_dir():
            continue
        version = version_dir.name
        xlsx_files = list(version_dir.glob("PATCH_LIST_*.xlsx"))
        if not xlsx_files:
            continue
        total = ok = 0
        failed: list[str] = []
        for xlsx_path in xlsx_files:
            try:
                wb = openpyxl.load_workbook(str(xlsx_path))
            except Exception:
                continue
            for sheet_name in ["IT 發行通知", "HR 發行通知"]:
                if sheet_name not in wb.sheetnames:
                    continue
                ws = wb[sheet_name]
                seen: set[str] = set()
                for row in ws.iter_rows(min_row=2):
                    cell = row[0]
                    if not cell.value or cell.value in seen:
                        continue
                    seen.add(str(cell.value))
                    hl = cell.hyperlink
                    if hl is None:
                        continue
                    target = hl.target if hasattr(hl, "target") else str(hl)
                    total += 1
                    if target:
                        local = target.replace("file:///", "").replace("/", "\\")
                        if Path(local).exists():
                            ok += 1
                            continue
                    failed.append(f"{cell.value} → {target}")
        if total > 0:
            result[version] = {"total": total, "ok": ok, "failed": failed}
    return result
```

- [ ] **Step 4：執行測試，確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestVerifyPatchLinks -v
```

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/core/monthly_patch_engine.py tests/unit/test_monthly_patch_engine.py
git commit -m "feat(core): 新增 verify_patch_links 超連結驗證"
```

---

## Task 6：HTML 通知信模板重設計

**Files:**
- Modify: `templates/patch_notify.html.j2`
- Modify: `src/hcp_cms/core/monthly_patch_engine.py:494-553`
- Test: `tests/unit/test_monthly_patch_engine.py`

- [ ] **Step 1：寫失敗測試**

```python
# tests/unit/test_monthly_patch_engine.py
# 在 TestGenerateNotifyHtml 中新增：

def test_html_has_seasonal_header_spring(self, engine_with_patch, tmp_path):
    eng, pid = engine_with_patch
    path = eng.generate_notify_html(pid, output_dir=str(tmp_path), month_str="202603")
    content = Path(path).read_text(encoding="utf-8")
    assert "1F4E79" in content or "2E75B6" in content  # 春季深藍

def test_html_seasonal_summer_color(self, engine_with_patch, tmp_path):
    eng, pid = engine_with_patch
    path = eng.generate_notify_html(pid, output_dir=str(tmp_path), month_str="202606")
    content = Path(path).read_text(encoding="utf-8")
    assert "1B5E20" in content or "2E7D32" in content  # 夏季深綠

def test_html_schedule_reminders_section(self, engine_with_patch, tmp_path):
    eng, pid = engine_with_patch
    path = eng.generate_notify_html(
        pid, output_dir=str(tmp_path), month_str="202604",
        schedule_reminders=["清明連假 4/4–4/6", "補班日 4/7"]
    )
    content = Path(path).read_text(encoding="utf-8")
    assert "清明連假 4/4–4/6" in content
    assert "補班日 4/7" in content

def test_html_no_reminders_section_when_empty(self, engine_with_patch, tmp_path):
    eng, pid = engine_with_patch
    path = eng.generate_notify_html(
        pid, output_dir=str(tmp_path), month_str="202604",
        schedule_reminders=[]
    )
    content = Path(path).read_text(encoding="utf-8")
    assert "排班" not in content

def test_html_with_banner_image(self, engine_with_patch, tmp_path):
    eng, pid = engine_with_patch
    dummy_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    path = eng.generate_notify_html(
        pid, output_dir=str(tmp_path), month_str="202604",
        banner_image_bytes=dummy_png
    )
    content = Path(path).read_text(encoding="utf-8")
    assert "data:image/" in content
    assert "base64," in content
```

- [ ] **Step 2：執行測試，確認失敗**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestGenerateNotifyHtml -v
```

- [ ] **Step 3：更新 `generate_notify_html` 函式簽名**

替換 `monthly_patch_engine.py` 中的 `generate_notify_html` 方法（行 494–533）：

```python
_SEASON_COLORS = {
    1: ("1F4E79", "2E75B6", "🌸"),
    2: ("1F4E79", "2E75B6", "🌸"),
    3: ("1F4E79", "2E75B6", "🌸"),
    4: ("1B5E20", "2E7D32", "🌿"),
    5: ("1B5E20", "2E7D32", "🌿"),
    6: ("1B5E20", "2E7D32", "🌿"),
    7: ("E65100", "F57C00", "🌻"),
    8: ("E65100", "F57C00", "🌻"),
    9: ("E65100", "F57C00", "🌻"),
    10: ("263238", "37474F", "❄️"),
    11: ("263238", "37474F", "❄️"),
    12: ("263238", "37474F", "❄️"),
}

def generate_notify_html(
    self,
    patch_id: int,
    output_dir: str,
    month_str: str | None = None,
    notify_body: str | None = None,
    version: str = "11G",
    banner_image_bytes: bytes | None = None,
    schedule_reminders: list[str] | None = None,
) -> str:
    """使用 Jinja2 範本產客戶通知信 HTML。"""
    import base64
    from pathlib import Path as _Path
    from jinja2 import Environment, FileSystemLoader

    issues = self._repo.list_issues_by_patch(patch_id)
    if month_str is None:
        patch = self._repo.get_patch_by_id(patch_id)
        month_str = patch.month_str if patch and patch.month_str else "000000"

    year = month_str[:4]
    month_num = int(month_str[4:]) if month_str[4:].isdigit() else 1
    month = month_str[4:]
    color_dark, color_mid, season_icon = self._SEASON_COLORS.get(month_num, ("1F4E79", "2E75B6", "🌸"))

    banner_b64 = None
    if banner_image_bytes:
        mime = "image/png" if banner_image_bytes[:4] == b"\x89PNG" else "image/jpeg"
        banner_b64 = f"data:{mime};base64,{base64.b64encode(banner_image_bytes).decode()}"

    templates_dir = _Path(__file__).parent.parent.parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
    tmpl = env.get_template("patch_notify.html.j2")

    html = tmpl.render(
        year=year,
        month=month,
        version=version,
        issues=issues,
        notify_body=notify_body or "",
        schedule_reminders=schedule_reminders or [],
        color_dark=color_dark,
        color_mid=color_mid,
        season_icon=season_icon,
        banner_b64=banner_b64,
    )

    out = _Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fname = f"【HCP{version}維護客戶】{month_str}月份大PATCH更新通知.html"
    path = str(out / fname)
    _Path(path).write_text(html, encoding="utf-8")
    return path
```

同時更新 `generate_notify_html_from_dir`（行 535–）以傳入新參數：

```python
def generate_notify_html_from_dir(
    self,
    patch_ids: dict[str, int],
    patch_dir: str,
    month_str: str,
    schedule_reminders: list[str] | None = None,
    banner_image_bytes: bytes | None = None,
) -> list[str]:
    """依 patch_ids 各版本產客戶通知信 HTML，存至 patch_dir 頂層。"""
    paths: list[str] = []
    for version, patch_id in patch_ids.items():
        path = self.generate_notify_html(
            patch_id=patch_id,
            output_dir=patch_dir,
            month_str=month_str,
            version=version,
            schedule_reminders=schedule_reminders,
            banner_image_bytes=banner_image_bytes,
        )
        paths.append(path)
    return paths
```

- [ ] **Step 4：重寫 `templates/patch_notify.html.j2`**

完整替換 `templates/patch_notify.html.j2`（使用 Write 工具）：

```jinja2
<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>【HCP{{ version }}維護客戶】{{ year }}年{{ month }}月份大PATCH更新通知</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; font-family: "微軟正黑體", Arial, sans-serif; }
body { background: #f0f4f8; color: #222; }
.header-wrap { position: relative; background: #{{ color_dark }}; color: #fff; overflow: hidden; }
.header-bg { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; opacity: 0.35; }
.header-content { position: relative; z-index: 1; padding: 20px 32px; }
.header-badge-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.badge { background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.4); border-radius: 4px; padding: 3px 10px; font-size: 11px; letter-spacing: 1px; }
.header-title { font-size: 22px; font-weight: bold; line-height: 1.3; }
.header-sub { font-size: 12px; color: rgba(255,255,255,0.8); margin-top: 4px; }
.checklist { margin-top: 14px; background: rgba(0,0,0,0.25); border-radius: 6px; padding: 12px 16px; }
.checklist-title { font-size: 13px; font-weight: bold; color: #FFD54F; margin-bottom: 8px; }
.checklist-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 16px; }
.checklist-item { font-size: 11px; color: rgba(255,255,255,0.92); }
.checklist-item::before { content: "✓ "; color: #A5D6A7; }
.checklist-warn { grid-column: 1 / -1; font-size: 11px; color: #FFD54F; }
.checklist-warn::before { content: "⚠ "; }
.main { max-width: 960px; margin: 24px auto; padding: 0 20px 40px; display: flex; gap: 20px; }
.main-left { flex: 2; min-width: 0; }
.main-right { flex: 1; min-width: 180px; }
.section-title { font-size: 13px; font-weight: bold; color: #{{ color_dark }};
  border-left: 4px solid #{{ color_mid }}; padding-left: 10px; margin: 0 0 12px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { background: #{{ color_dark }}; color: #fff; padding: 8px 10px; text-align: left; }
td { padding: 7px 10px; border: 1px solid #ddd; vertical-align: top; }
tr:nth-child(even) td { background: #f9fafb; }
.bug { background: #FCE4D6; }
.enh { background: #E2EFDA; }
.tw  { background: #D6EAF8; }
.cn  { background: #FFF3CD; }
.shared { background: #E8F5E9; }
.reminder-card { background: #FFFDE7; border: 1px solid #FDD835; border-radius: 6px; padding: 14px 16px; }
.reminder-card .section-title { margin-bottom: 10px; color: #E65100; border-color: #FF8F00; }
.reminder-item { font-size: 12px; color: #5D4037; line-height: 1.9; }
.reminder-item::before { content: "• "; color: #FF8F00; }
.footer { text-align: center; color: #aaa; font-size: 11px; margin-top: 28px; }
@media (max-width: 640px) { .main { flex-direction: column; } .checklist-grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>

<div class="header-wrap">
  {% if banner_b64 %}
  <img class="header-bg" src="{{ banner_b64 }}" alt="">
  {% endif %}
  <div class="header-content">
    <div class="header-badge-row">
      <span class="badge">HCP MAINTENANCE NOTIFICATION</span>
      <div style="display:flex;gap:6px">
        <span class="badge">{{ year }}/{{ month }} PATCH</span>
        <span class="badge" style="background:#{{ color_mid }};border-color:#{{ color_mid }}">HCP {{ version }}</span>
      </div>
    </div>
    <div class="header-title">{{ season_icon }} 【HCP{{ version }}維護客戶】<br>{{ year }}年{{ month }}月份大 PATCH 更新通知</div>
    <div class="header-sub">資通電腦 HCP 人力資源管理系統 ／ 系統維護更新公告</div>
    <div class="checklist">
      <div class="checklist-title">△ 大 PATCH 更新前重要提醒</div>
      <div class="checklist-grid">
        <div class="checklist-item">更新前請務必先完整備份系統資料與資料庫</div>
        <div class="checklist-item">套用前確認目前系統版本，依指定 PATCH 順序更新</div>
        <div class="checklist-item">請確認測試環境已驗證完畢，再部署至正式環境</div>
        <div class="checklist-item">建議於非上班時段（下班後）執行，避免影響使用者</div>
        <div class="checklist-warn">避免電腦主機中毒導致系統無法正常運作，請務必確認防毒軟體已更新至最新病毒碼</div>
      </div>
    </div>
  </div>
</div>

<div class="main">
  <div class="main-left">
    {% if notify_body %}
    <div class="section-title" style="margin-top:0">本月更新說明</div>
    <p style="font-size:13px;line-height:1.8;color:#444;margin-bottom:20px">{{ notify_body }}</p>
    {% endif %}
    <div class="section-title" {% if not notify_body %}style="margin-top:0"{% endif %}>本月修正項目</div>
    <table>
      <tr>
        <th>Issue No</th><th>計區域</th><th>類型</th>
        <th>程式代號</th><th>功能說明</th><th>影響說明</th>
      </tr>
      {% for iss in issues %}
      <tr class="{{ 'bug' if iss.issue_type == 'BugFix' else 'enh' }}">
        <td>{{ iss.issue_no }}</td>
        <td class="{{ 'tw' if iss.region == 'TW' else ('cn' if iss.region == 'CN' else 'shared') }}">{{ iss.region or '共用' }}</td>
        <td>{{ '修正' if iss.issue_type == 'BugFix' else '改善' }}</td>
        <td>{{ iss.program_code or '' }}</td>
        <td>{{ iss.description or '' }}</td>
        <td>{{ iss.impact or '' }}</td>
      </tr>
      {% endfor %}
    </table>
  </div>

  {% if schedule_reminders %}
  <div class="main-right">
    <div class="reminder-card">
      <div class="section-title">📅 本月排班提醒</div>
      {% for item in schedule_reminders %}
      <div class="reminder-item">{{ item }}</div>
      {% endfor %}
    </div>
  </div>
  {% endif %}
</div>

<div class="footer">
  HCP 客服團隊 · {{ year }}年{{ month }}月 · 如有疑問請聯絡客服
</div>
</body>
</html>
```

- [ ] **Step 5：執行測試，確認通過**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py::TestGenerateNotifyHtml -v
```
Expected: PASS

- [ ] **Step 6：執行全部測試，確認無回歸**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py tests/unit/test_claude_content_supplement.py -v
```

- [ ] **Step 7：Commit**

```bash
git add src/hcp_cms/core/monthly_patch_engine.py templates/patch_notify.html.j2 tests/unit/test_monthly_patch_engine.py
git commit -m "feat(core/template): 重設計 HTML 通知信（季節橫幅、底圖支援、左右排班提醒）"
```

---

## Task 7：MonthlyPatchTab UI 更新

**Files:**
- Modify: `src/hcp_cms/ui/patch_monthly_tab.py`

- [ ] **Step 1：替換 `_STEPS` 常數並更新 `_setup_ui`**

在 `patch_monthly_tab.py` 中：

```python
# 舊
_STEPS = ["① 選月份", "② 選來源", "③ 匯入", "④ 編輯", "⑤ Excel", "⑥ 通知信", "⑦ 完成"]

# 新
_STEPS = ["① 選月份", "② 選來源", "③ 匯入", "④ 編輯", "⑤ S2T",
          "⑥ Excel", "⑦ 驗證", "⑧ 通知信", "⑨ 完成"]
```

在 `__init__` 新增：
```python
self._banner_image_bytes: bytes | None = None
```

- [ ] **Step 2：在 `_setup_ui` 月份列新增「🖼 上傳橫幅底圖」**

在月份列（`month_row`）的 `month_row.addStretch()` 之前插入：

```python
self._banner_label = QLabel("底圖：無")
self._banner_label.setStyleSheet("color: #64748b; font-size: 11px;")
self._banner_btn = QPushButton("🖼 上傳橫幅底圖")
self._banner_btn.setFixedWidth(120)
month_row.addWidget(self._banner_label)
month_row.addWidget(self._banner_btn)
```

- [ ] **Step 3：在操作按鈕列新增 S2T 和驗證按鈕**

在 `_setup_ui` 的 `action_row` 區段中，在 `self._import_btn` 和 `self._generate_excel_btn` 之間插入：

```python
self._s2t_btn = QPushButton("🔤 S2T 轉換")
self._verify_btn = QPushButton("🔗 驗證超連結")
```

並更新按鈕群的 for 迴圈：
```python
for btn in [self._import_btn, self._s2t_btn, self._generate_excel_btn,
            self._verify_btn, self._generate_html_btn, self._regenerate_btn]:
    action_row.addWidget(btn)
```

- [ ] **Step 4：在 Log 上方新增排班提醒區塊**

在 `self._log = QTextEdit(...)` 之前插入：

```python
# 排班提醒區塊
from PySide6.QtWidgets import QGroupBox, QListWidget, QListWidgetItem
reminder_group = QGroupBox("📅 排班提醒（選填，留空則不顯示於通知信）")
reminder_inner = QVBoxLayout()
self._reminder_list = QListWidget()
self._reminder_list.setMaximumHeight(80)
self._reminder_list.setToolTip("每條提醒可獨立刪除，切換月份自動清空")
reminder_btn_row = QHBoxLayout()
self._reminder_add_btn = QPushButton("＋ 新增")
self._reminder_add_btn.setFixedWidth(70)
self._reminder_del_btn = QPushButton("✕ 刪除選取")
self._reminder_del_btn.setFixedWidth(90)
reminder_btn_row.addWidget(self._reminder_add_btn)
reminder_btn_row.addWidget(self._reminder_del_btn)
reminder_btn_row.addStretch()
reminder_inner.addWidget(self._reminder_list)
reminder_inner.addLayout(reminder_btn_row)
reminder_group.setLayout(reminder_inner)
layout.addWidget(reminder_group)
```

- [ ] **Step 5：在 Signal/Slot 連線區新增所有新連線**

在 `_setup_ui` 的連線區（`self._source_combo.currentIndexChanged.connect(...)` 附近）插入：

```python
self._banner_btn.clicked.connect(self._on_banner_upload_clicked)
self._s2t_btn.clicked.connect(self._on_s2t_clicked)
self._verify_btn.clicked.connect(self._on_verify_clicked)
self._reminder_add_btn.clicked.connect(self._on_reminder_add_clicked)
self._reminder_del_btn.clicked.connect(self._on_reminder_del_clicked)
self._month_combo.currentIndexChanged.connect(self._on_month_changed)
self._year_spin.valueChanged.connect(self._on_month_changed)
self._s2t_done.connect(self._on_s2t_result)
self._verify_done.connect(self._on_verify_result)
self._supplement_done.connect(self._on_supplement_result)
```

⚠ `Signal` 必須在類別層級宣告，不在 `_setup_ui` 內。在類別定義頂部新增：

```python
class MonthlyPatchTab(QWidget):
    _import_done = Signal(object)
    _generate_done = Signal(object)
    _s2t_done = Signal(object)      # 新增
    _verify_done = Signal(object)   # 新增
    _supplement_done = Signal(int)  # 新增
```

並加入對應連線：
```python
self._s2t_done.connect(self._on_s2t_result)
self._verify_done.connect(self._on_verify_result)
self._supplement_done.connect(self._on_supplement_result)
```

- [ ] **Step 6：實作新 Slot 方法**

在 `_on_regenerate_clicked` 之後新增：

```python
def _on_banner_upload_clicked(self) -> None:
    path, _ = QFileDialog.getOpenFileName(
        self, "選擇橫幅底圖", "", "圖片檔 (*.png *.jpg *.jpeg);;全部檔案 (*.*)"
    )
    if path:
        from pathlib import Path
        self._banner_image_bytes = Path(path).read_bytes()
        self._banner_label.setText(f"底圖：{Path(path).name}")

def _on_month_changed(self) -> None:
    self._reminder_list.clear()

def _on_reminder_add_clicked(self) -> None:
    from PySide6.QtWidgets import QInputDialog
    text, ok = QInputDialog.getText(self, "新增排班提醒", "提醒內容：")
    if ok and text.strip():
        self._reminder_list.addItem(QListWidgetItem(text.strip()))

def _on_reminder_del_clicked(self) -> None:
    for item in self._reminder_list.selectedItems():
        self._reminder_list.takeItem(self._reminder_list.row(item))

def _get_schedule_reminders(self) -> list[str]:
    return [self._reminder_list.item(i).text() for i in range(self._reminder_list.count())]

def _on_s2t_clicked(self) -> None:
    if not self._scan_dir and not self._patch_id:
        return
    scan_dir = self._scan_dir
    conn = self._conn
    self._s2t_btn.setEnabled(False)
    self._append_log("🔤 S2T 簡轉繁掃描中…")

    def work() -> dict:
        from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
        eng = MonthlyPatchEngine(conn)
        try:
            return {"result": eng.run_s2t(scan_dir or ""), "error": None}
        except Exception as e:
            return {"result": {}, "error": str(e)}

    threading.Thread(target=lambda: self._s2t_done.emit(work()), daemon=True).start()

def _on_s2t_result(self, data: dict) -> None:
    self._s2t_btn.setEnabled(True)
    if data.get("error"):
        self._append_log(f"❌ S2T 失敗：{data['error']}")
        return
    result = data.get("result", {})
    if not result:
        self._append_log("🔤 無 .docx 檔案需轉換")
        self._set_step(5)
        return
    for fname, count in result.items():
        if count > 0:
            self._append_log(f"🔤 {fname} → 已轉換 {count} 字")
        elif count == 0:
            self._append_log(f"🔤 {fname} → 無需轉換")
        else:
            self._append_log(f"❌ {fname} → 轉換失敗")
    self._set_step(5)
    # 接著自動抓 Mantis 補充說明
    self._fetch_supplements_async()

def _fetch_supplements_async(self) -> None:
    if not self._patch_id and not self._scan_patch_ids:
        return
    conn = self._conn
    patch_ids_list = list(self._scan_patch_ids.values()) if self._scan_patch_ids else [self._patch_id]
    self._append_log("📋 從 Mantis 取得補充說明（Claude 分析中）…")

    def work() -> int:
        from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
        eng = MonthlyPatchEngine(conn)
        total = 0
        for pid in patch_ids_list:
            if pid is not None:
                total += eng.fetch_supplements(pid)
        return total

    threading.Thread(target=lambda: self._supplement_done.emit(work()), daemon=True).start()

def _on_supplement_result(self, count: int) -> None:
    if count > 0:
        self._append_log(f"✅ 補充說明已更新：{count} 筆")
    else:
        self._append_log("⚠️ 補充說明：無 Mantis 連線或無資料")

def _on_verify_clicked(self) -> None:
    if not self._scan_dir:
        self._append_log("⚠️ 請先掃描資料夾再驗證超連結")
        return
    scan_dir = self._scan_dir
    conn = self._conn
    self._verify_btn.setEnabled(False)
    self._append_log("🔗 驗證超連結…")

    def work() -> dict:
        from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
        eng = MonthlyPatchEngine(conn)
        try:
            return {"result": eng.verify_patch_links(scan_dir), "error": None}
        except Exception as e:
            return {"result": {}, "error": str(e)}

    threading.Thread(target=lambda: self._verify_done.emit(work()), daemon=True).start()

def _on_verify_result(self, data: dict) -> None:
    self._verify_btn.setEnabled(True)
    if data.get("error"):
        self._append_log(f"❌ 驗證失敗：{data['error']}")
        return
    result = data.get("result", {})
    all_ok = True
    for ver, stats in result.items():
        ok = stats["ok"]
        total = stats["total"]
        if ok == total:
            self._append_log(f"✅ {ver}：{total}/{total} 條超連結正常")
        else:
            all_ok = False
            self._append_log(f"❌ {ver}：{ok}/{total} 條正常，失敗：")
            for f in stats["failed"]:
                self._append_log(f"   → {f}")
    if all_ok:
        self._set_step(7)
```

- [ ] **Step 7：更新 `_on_import_result` 使匯入後自動觸發 S2T**

在 `_on_import_result` 末尾（`self._set_step(3)` 之後）加入：

```python
    self._set_step(3)
    # 自動觸發 S2T（若有 scan_dir）
    if self._scan_dir:
        self._on_s2t_clicked()
```

- [ ] **Step 8：更新 `_on_generate_html_clicked` 傳入新參數**

在 `_on_generate_html_clicked` 中，找到呼叫 `generate_notify_html` 的地方，加入新參數：

掃描模式（`if scan_patch_ids`）：
```python
paths = engine.generate_notify_html_from_dir(
    scan_patch_ids, scan_dir, month_str,
    schedule_reminders=schedule_reminders,
    banner_image_bytes=banner_image_bytes,
)
```

非掃描模式：
```python
path = engine.generate_notify_html(
    patch_id, output_dir, month_str, notify_body=notify_body,
    schedule_reminders=schedule_reminders,
    banner_image_bytes=banner_image_bytes,
)
```

在 `_on_generate_html_clicked` 開頭擷取這兩個值：
```python
schedule_reminders = self._get_schedule_reminders()
banner_image_bytes = self._banner_image_bytes
```

- [ ] **Step 9：執行程式確認 UI 正常**

```
.venv/Scripts/python.exe -m hcp_cms
```

確認：
- Tab 顯示 9 步驟條
- 月份列有「🖼 上傳橫幅底圖」按鈕
- 按鈕列有「🔤 S2T 轉換」和「🔗 驗證超連結」
- Log 上方有「排班提醒」區塊（可新增、刪除）

- [ ] **Step 10：執行全部測試**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```
Expected: 全部 PASS

- [ ] **Step 11：Commit**

```bash
git add src/hcp_cms/ui/patch_monthly_tab.py
git commit -m "feat(ui): 更新 MonthlyPatchTab（9步驟、S2T、驗證、排班提醒、底圖上傳）"
```
