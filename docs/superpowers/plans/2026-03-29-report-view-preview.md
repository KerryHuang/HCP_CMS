# 報表中心檢視與下載分離 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將報表中心的「產生並下載」拆為「檢視」預覽（QTabWidget 多 sheet）與「下載」匯出兩個獨立動作。

**Architecture:** 重構 ReportEngine 抽出 `build_*` 方法回傳結構化資料 `dict[str, list[list]]`，新增 ReportWriter 負責 Excel 寫入與格式化，UI 層 ReportView 改為雙按鈕（檢視/下載）+ QTabWidget 預覽。

**Tech Stack:** Python 3.14, PySide6 6.10.2, openpyxl, SQLite, pytest

---

## 檔案結構

| 檔案 | 動作 | 職責 |
|------|------|------|
| `src/hcp_cms/core/report_engine.py` | 修改 | 新增 `build_tracking_table` / `build_monthly_report` 回傳結構化資料，`generate_*` 改為呼叫 build + write |
| `src/hcp_cms/core/report_writer.py` | 新增 | `ReportWriter.write_excel(data, path)` — 從 ReportEngine 抽出 Excel 寫入與樣式邏輯 |
| `src/hcp_cms/ui/report_view.py` | 修改 | 拆為檢視/下載按鈕，加入 QTabWidget 預覽區 |
| `tests/unit/test_report_writer.py` | 新增 | ReportWriter 單元測試 |
| `tests/unit/test_report_engine.py` | 修改 | 補充 `build_*` 方法測試 |

---

### Task 1: ReportEngine — 抽出 build_tracking_table

**Files:**
- Modify: `src/hcp_cms/core/report_engine.py:72-251`
- Modify: `tests/unit/test_report_engine.py`

- [ ] **Step 1: 寫 build_tracking_table 的失敗測試**

在 `tests/unit/test_report_engine.py` 的 `TestReportEngine` 類別新增：

```python
def test_build_tracking_table_returns_dict(self, seeded_db):
    engine = ReportEngine(seeded_db.connection)
    data = engine.build_tracking_table("2026/03/01", "2026/03/31")
    assert isinstance(data, dict)
    assert "📋 客戶索引" in data
    assert "問題追蹤總表" in data
    assert "QA知識庫" in data
    assert "Mantis提單追蹤" in data

def test_build_tracking_table_sheet_structure(self, seeded_db):
    engine = ReportEngine(seeded_db.connection)
    data = engine.build_tracking_table("2026/03/01", "2026/03/31")
    # 每個 sheet 第一列是表頭
    index_sheet = data["📋 客戶索引"]
    assert index_sheet[0] == ["#", "公司名稱", "Email 域名", "聯絡方式", "案件數", "快速連結"]
    # 3 cases = seeded_db 有 3 筆案件
    tracking_sheet = data["問題追蹤總表"]
    assert len(tracking_sheet) == 4  # 1 header + 3 data rows

def test_build_tracking_table_custom_sheet(self, seeded_db):
    engine = ReportEngine(seeded_db.connection)
    data = engine.build_tracking_table("2026/03/01", "2026/03/31")
    assert "客制需求" in data
    assert len(data["客制需求"]) == 2  # 1 header + 1 custom case

def test_build_tracking_table_company_sheets(self, seeded_db):
    engine = ReportEngine(seeded_db.connection)
    data = engine.build_tracking_table("2026/03/01", "2026/03/31")
    # 日月光有 2 筆案件、欣興有 1 筆
    ase_key = [k for k in data if "日月光" in k]
    assert len(ase_key) == 1
    # 公司頁籤：第一列返回連結文字、第二列表頭、第三列起資料
    ase_rows = data[ase_key[0]]
    assert ase_rows[0][0] == "↩ 返回客戶索引"  # 返回連結
    assert ase_rows[1][0] == "案件編號"  # 表頭
    assert len(ase_rows) == 4  # link + header + 2 cases
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_report_engine.py::TestReportEngine::test_build_tracking_table_returns_dict -v`
Expected: FAIL — `AttributeError: 'ReportEngine' object has no attribute 'build_tracking_table'`

- [ ] **Step 3: 實作 build_tracking_table**

在 `src/hcp_cms/core/report_engine.py` 的 `ReportEngine` 類別新增方法。從現有 `generate_tracking_table` 抽出資料組裝邏輯，回傳 `dict[str, list[list]]`。

快速連結欄位在結構化資料中以純文字 `"→ {公司名}問題記錄"` 表示（HYPERLINK 公式由 ReportWriter 處理）。公司頁籤第一列用 `["↩ 返回客戶索引"]` 代替 HYPERLINK 公式。

```python
def build_tracking_table(self, start_date: str, end_date: str) -> dict[str, list[list]]:
    """Build tracking table as structured data.

    Returns:
        dict mapping sheet_name to list of rows (first row = header).
    """
    cases = self._case_repo.list_by_date_range(start_date, end_date)
    qas = self._qa_repo.list_all()
    companies = self._company_repo.list_all()
    mantis_tickets = self._mantis_repo.list_all()
    company_map = {c.company_id: c for c in companies}
    custom_cols = self._custom_col_mgr.list_columns()

    # 按公司分組
    company_cases: dict[str, list[Case]] = {}
    for case in cases:
        cid = case.company_id or "unknown"
        company_cases.setdefault(cid, []).append(case)

    _INVALID_SHEET_CHARS = re.compile(r'[\\/*?:\[\]]')

    def _safe_sheet_name(raw: str, suffix: str = "_問題") -> str:
        sanitized = _INVALID_SHEET_CHARS.sub("-", raw)
        return (sanitized[:28] + suffix)[:31]

    company_sheet_names: dict[str, str] = {}
    for comp in companies:
        if company_cases.get(comp.company_id):
            raw = f"{comp.domain}({comp.name})" if comp.domain else comp.name
            company_sheet_names[comp.company_id] = _safe_sheet_name(raw)

    result: dict[str, list[list]] = {}

    # Sheet 1: 客戶索引
    index_header = ["#", "公司名稱", "Email 域名", "聯絡方式", "案件數", "快速連結"]
    index_rows: list[list] = [index_header]
    for i, comp in enumerate(companies, 1):
        count = sum(1 for c in cases if c.company_id == comp.company_id)
        link = f"→ {comp.name}問題記錄" if comp.company_id in company_sheet_names else ""
        index_rows.append(_clean_row([i, comp.name, comp.domain, comp.contact_info or "", count, link]))
    result["📋 客戶索引"] = index_rows

    # Sheet 2: 問題追蹤總表
    main_headers = [
        "案件編號", "聯絡方式", "問題狀態", "優先等級",
        "寄件時間", "首次回覆時效(hr)", "客戶", "客戶公司", "客戶聯絡電話",
        "主旨", "系統／產品", "問題類型", "錯誤類型",
        "受影響員工人數", "影響期間", "處理進度", "負責人",
        "預計回覆時間", "實際回覆時間", "結案時間",
        "是否需升級", "是否有附圖", "QA文件名稱", "備註",
    ] + [col.col_label for col in custom_cols]
    tracking_rows: list[list] = [main_headers]
    for case in cases:
        comp = company_map.get(case.company_id or "")
        company_name = comp.name if comp else (case.company_id or "")
        company_phone = comp.contact_info if comp else ""
        closed_at = case.updated_at if case.status in ("已完成", "Closed") else ""
        tracking_rows.append(_clean_row([
            case.case_id, case.contact_method, case.status, case.priority,
            case.sent_time, _reply_hours(case.sent_time, case.actual_reply),
            case.contact_person, company_name, company_phone or "",
            case.subject, case.system_product, case.issue_type, case.error_type,
            "", case.impact_period, case.progress, case.handler,
            "", case.actual_reply, closed_at,
            "", "", "", case.notes or "",
        ] + [_clean(case.extra_fields.get(col.col_key, "")) for col in custom_cols]))
    result["問題追蹤總表"] = tracking_rows

    # Sheet 3: QA知識庫
    qa_headers = [
        "QA編號", "系統／產品", "問題類型", "錯誤類型",
        "Q｜客戶問題描述", "A｜標準回覆內容",
        "附圖說明", "Word文件名稱", "建立日期", "建立人", "備註",
    ]
    qa_rows: list[list] = [qa_headers]
    for qa in qas:
        qa_rows.append(_clean_row([
            qa.qa_id, qa.system_product, qa.issue_type, qa.error_type,
            qa.question, qa.answer,
            qa.has_image, qa.doc_name or "", qa.created_at or "",
            qa.created_by or "", qa.notes or "",
        ]))
    result["QA知識庫"] = qa_rows

    # 個別公司頁籤
    comp_case_headers = [
        "案件編號", "聯絡方式", "問題狀態", "優先等級",
        "寄件時間", "主旨", "系統／產品", "問題類型", "錯誤類型",
        "影響期間", "處理進度", "實際回覆時間", "結案時間", "備註",
    ] + [col.col_label for col in custom_cols]

    for comp in companies:
        comp_cases = company_cases.get(comp.company_id, [])
        if not comp_cases:
            continue
        sheet_name = company_sheet_names[comp.company_id]
        rows: list[list] = [["↩ 返回客戶索引"], comp_case_headers]
        for case in comp_cases:
            closed_at = case.updated_at if case.status in ("已完成", "Closed") else ""
            rows.append(_clean_row([
                case.case_id, case.contact_method, case.status, case.priority,
                case.sent_time, case.subject, case.system_product,
                case.issue_type, case.error_type,
                case.impact_period, case.progress, case.actual_reply,
                closed_at, case.notes or "",
            ] + [_clean(case.extra_fields.get(col.col_key, "")) for col in custom_cols]))
        result[sheet_name] = rows

    # Mantis提單追蹤
    mantis_headers = [
        "Mantis票號", "建立時間", "客戶", "問題摘要", "關聯CS案件",
        "優先等級", "狀態", "類型", "相關程式/模組",
        "內部確認進度", "負責人", "預計修復日期", "實際修復日期", "備註",
    ]
    mantis_rows: list[list] = [mantis_headers]
    for ticket in mantis_tickets:
        comp = company_map.get(ticket.company_id or "")
        company_name = comp.name if comp else (ticket.company_id or "")
        linked = ", ".join(self._case_mantis_repo.get_cases_for_ticket(ticket.ticket_id))
        mantis_rows.append(_clean_row([
            ticket.ticket_id, ticket.created_time or "", company_name,
            ticket.summary, linked,
            ticket.priority or "", ticket.status or "", ticket.issue_type or "",
            ticket.module or "", ticket.progress or "", ticket.handler or "",
            ticket.planned_fix or "", ticket.actual_fix or "", ticket.notes or "",
        ]))
    result["Mantis提單追蹤"] = mantis_rows

    # 客制需求
    custom_cases = [c for c in cases if c.issue_type and "客制" in c.issue_type]
    if custom_cases:
        custom_rows: list[list] = [comp_case_headers]
        for case in custom_cases:
            closed_at = case.updated_at if case.status in ("已完成", "Closed") else ""
            custom_rows.append(_clean_row([
                case.case_id, case.contact_method, case.status, case.priority,
                case.sent_time, case.subject, case.system_product,
                case.issue_type, case.error_type,
                case.impact_period, case.progress, case.actual_reply,
                closed_at, case.notes or "",
            ]))
        result["客制需求"] = custom_rows

    return result
```

- [ ] **Step 4: 執行測試確認通過**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_report_engine.py -k "build_tracking" -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/core/report_engine.py tests/unit/test_report_engine.py
git commit -m "feat(core): ReportEngine 新增 build_tracking_table 回傳結構化資料"
```

---

### Task 2: ReportEngine — 抽出 build_monthly_report

**Files:**
- Modify: `src/hcp_cms/core/report_engine.py:253-344`
- Modify: `tests/unit/test_report_engine.py`

- [ ] **Step 1: 寫 build_monthly_report 的失敗測試**

在 `tests/unit/test_report_engine.py` 的 `TestReportEngine` 類別新增：

```python
def test_build_monthly_report_returns_dict(self, seeded_db):
    engine = ReportEngine(seeded_db.connection)
    data = engine.build_monthly_report("2026/03/01", "2026/03/31")
    assert isinstance(data, dict)
    assert "📊 月報摘要" in data
    assert "📋 案件明細" in data
    assert "🏢 客戶分析" in data

def test_build_monthly_report_kpi(self, seeded_db):
    engine = ReportEngine(seeded_db.connection)
    data = engine.build_monthly_report("2026/03/01", "2026/03/31")
    summary = data["📊 月報摘要"]
    # summary[0] = 標題列, summary[1] = 表頭, summary[2:] = KPI 資料列
    # 案件總數 row
    total_row = summary[2]
    assert total_row[0] == "案件總數"
    assert total_row[1] == 3

def test_build_monthly_report_case_detail(self, seeded_db):
    engine = ReportEngine(seeded_db.connection)
    data = engine.build_monthly_report("2026/03/01", "2026/03/31")
    detail = data["📋 案件明細"]
    assert detail[0][0] == "案件編號"  # header
    assert len(detail) == 4  # 1 header + 3 cases

def test_build_monthly_report_customer_analysis(self, seeded_db):
    engine = ReportEngine(seeded_db.connection)
    data = engine.build_monthly_report("2026/03/01", "2026/03/31")
    analysis = data["🏢 客戶分析"]
    assert analysis[0] == ["客戶", "已回覆", "處理中", "合計"]
    assert len(analysis) == 3  # 1 header + 2 companies

def test_build_monthly_report_no_data(self, db):
    engine = ReportEngine(db.connection)
    data = engine.build_monthly_report("2026/01/01", "2026/01/31")
    summary = data["📊 月報摘要"]
    total_row = summary[2]
    assert total_row[1] == 0
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_report_engine.py::TestReportEngine::test_build_monthly_report_returns_dict -v`
Expected: FAIL — `TypeError` (build_monthly_report 目前需要 output_path 參數)

- [ ] **Step 3: 實作 build_monthly_report**

在 `src/hcp_cms/core/report_engine.py` 的 `ReportEngine` 類別新增方法。從現有 `generate_monthly_report` 抽出資料組裝邏輯。

月報摘要 sheet 結構較特殊（標題列 + 空行 + KPI 表頭 + KPI 行 + 空行 + 問題類型統計），結構化為：`[title_row, header_row, kpi_row_1, ..., empty_row, type_title_row, type_header_row, type_row_1, ...]`。

```python
def build_monthly_report(self, start_date: str, end_date: str) -> dict[str, list[list]]:
    """Build monthly report as structured data.

    Returns:
        dict mapping sheet_name to list of rows (first row varies by sheet).
    """
    cases = self._case_repo.list_by_date_range(start_date, end_date)
    companies = self._company_repo.list_all()
    company_map = {c.company_id: c for c in companies}

    closed_statuses = {"已完成", "Closed", "已回覆"}
    total = len(cases)
    replied = sum(1 for c in cases if c.status == "已回覆")
    pending = sum(1 for c in cases if c.status not in closed_statuses)
    reply_rate = (replied / total * 100) if total > 0 else 0.0

    result: dict[str, list[list]] = {}

    # Sheet 1: 月報摘要
    summary_rows: list[list] = []
    summary_rows.append([f"📊 客服報表摘要 — {start_date} ～ {end_date}",
                         f"產生日期：{datetime.now().strftime('%Y/%m/%d %H:%M')}"])
    summary_rows.append(["指標", "數值", "說明"])
    summary_rows.append(["案件總數", total, f"{start_date} ～ {end_date}"])
    summary_rows.append(["已回覆", replied, "replied = 是"])
    summary_rows.append(["待處理", pending, "狀態非已完成/Closed"])
    summary_rows.append(["回覆率", f"{reply_rate:.1f}%", "已回覆 ÷ 總數 × 100%"])
    summary_rows.append([])
    summary_rows.append(["問題類型統計"])
    summary_rows.append(["問題類型", "件數", "佔比"])
    issue_counts: dict[str, int] = {}
    for c in cases:
        it = c.issue_type or "其他"
        issue_counts[it] = issue_counts.get(it, 0) + 1
    for it, count in sorted(issue_counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100 if total > 0 else 0
        summary_rows.append([it, count, f"{pct:.1f}%"])
    result["📊 月報摘要"] = summary_rows

    # Sheet 2: 案件明細
    detail_headers = [
        "案件編號", "聯絡方式", "狀態", "優先", "寄送時間",
        "客戶", "聯絡人", "主旨", "系統/產品", "問題類型", "錯誤類型",
        "影響期間", "進度", "實際回覆時間", "備註",
        "RD 負責人", "處理人", "回覆次數", "關聯案件",
    ]
    detail_rows: list[list] = [detail_headers]
    for case in cases:
        comp = company_map.get(case.company_id or "")
        company_name = comp.name if comp else (case.company_id or "")
        detail_rows.append(_clean_row([
            case.case_id, case.contact_method, case.status, case.priority,
            case.sent_time,
            company_name, case.contact_person, case.subject,
            case.system_product, case.issue_type, case.error_type,
            case.impact_period, case.progress, case.actual_reply,
            case.notes or "", case.rd_assignee or "", case.handler or "",
            case.reply_count, case.linked_case_id or "",
        ]))
    result["📋 案件明細"] = detail_rows

    # Sheet 3: 客戶分析
    analysis_rows: list[list] = [["客戶", "已回覆", "處理中", "合計"]]
    company_stats: dict[str, dict[str, int]] = {}
    for case in cases:
        comp = company_map.get(case.company_id or "")
        cname = comp.name if comp else (case.company_id or "（未知）")
        if cname not in company_stats:
            company_stats[cname] = {"replied": 0, "pending": 0}
        if case.status == "已回覆":
            company_stats[cname]["replied"] += 1
        if case.status not in closed_statuses:
            company_stats[cname]["pending"] += 1
    for cname, stat in sorted(company_stats.items()):
        total_c = stat["replied"] + stat["pending"]
        analysis_rows.append(_clean_row([cname, stat["replied"], stat["pending"], total_c]))
    result["🏢 客戶分析"] = analysis_rows

    return result
```

- [ ] **Step 4: 執行測試確認通過**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_report_engine.py -k "build_monthly" -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/core/report_engine.py tests/unit/test_report_engine.py
git commit -m "feat(core): ReportEngine 新增 build_monthly_report 回傳結構化資料"
```

---

### Task 3: ReportWriter — Excel 寫入與格式化 [POC: 首次將 HYPERLINK 公式邏輯從結構化資料還原]

**Files:**
- Create: `src/hcp_cms/core/report_writer.py`
- Create: `tests/unit/test_report_writer.py`

- [ ] **Step 1: 寫 ReportWriter 的失敗測試**

建立 `tests/unit/test_report_writer.py`：

```python
"""Tests for ReportWriter."""

from pathlib import Path

import openpyxl
import pytest

from hcp_cms.core.report_writer import ReportWriter


class TestReportWriter:
    def test_write_excel_creates_file(self, tmp_path: Path):
        data = {"Sheet1": [["A", "B"], [1, 2]]}
        path = tmp_path / "test.xlsx"
        ReportWriter.write_excel(data, path)
        assert path.exists()

    def test_write_excel_sheet_names(self, tmp_path: Path):
        data = {
            "📋 客戶索引": [["#", "名稱"], [1, "A"]],
            "問題追蹤總表": [["案件編號"], ["CS-001"]],
        }
        path = tmp_path / "test.xlsx"
        ReportWriter.write_excel(data, path)
        wb = openpyxl.load_workbook(str(path))
        assert wb.sheetnames == ["📋 客戶索引", "問題追蹤總表"]
        wb.close()

    def test_write_excel_header_style(self, tmp_path: Path):
        data = {"Sheet1": [["A", "B"], [1, 2]]}
        path = tmp_path / "test.xlsx"
        ReportWriter.write_excel(data, path)
        wb = openpyxl.load_workbook(str(path))
        cell = wb["Sheet1"].cell(row=1, column=1)
        assert cell.font.bold is True
        assert cell.font.color.rgb == "00FFFFFF"
        wb.close()

    def test_write_excel_data_rows(self, tmp_path: Path):
        data = {"Sheet1": [["Name", "Value"], ["Alice", 10], ["Bob", 20]]}
        path = tmp_path / "test.xlsx"
        ReportWriter.write_excel(data, path)
        wb = openpyxl.load_workbook(str(path))
        ws = wb["Sheet1"]
        assert ws.cell(row=2, column=1).value == "Alice"
        assert ws.cell(row=3, column=2).value == 20
        assert ws.max_row == 3
        wb.close()

    def test_write_excel_alternating_row_fill(self, tmp_path: Path):
        data = {"Sheet1": [["A"], ["r1"], ["r2"], ["r3"]]}
        path = tmp_path / "test.xlsx"
        ReportWriter.write_excel(data, path)
        wb = openpyxl.load_workbook(str(path))
        ws = wb["Sheet1"]
        # Row 2 (even) should have alt fill
        assert ws.cell(row=2, column=1).fill.start_color.rgb == "00F9FAFB"
        # Row 3 (odd) should not have alt fill
        assert ws.cell(row=3, column=1).fill.start_color.rgb != "00F9FAFB"
        wb.close()

    def test_write_excel_empty_data(self, tmp_path: Path):
        data = {"EmptySheet": [["Header"]]}
        path = tmp_path / "test.xlsx"
        ReportWriter.write_excel(data, path)
        wb = openpyxl.load_workbook(str(path))
        assert wb["EmptySheet"].max_row == 1
        wb.close()
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_report_writer.py::TestReportWriter::test_write_excel_creates_file -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hcp_cms.core.report_writer'`

- [ ] **Step 3: 實作 ReportWriter**

建立 `src/hcp_cms/core/report_writer.py`：

```python
"""Excel report writer — writes structured data to styled .xlsx files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

# Style constants（與原 report_engine 一致）
FONT_HEADER = Font(name="微軟正黑體", size=11, bold=True, color="FFFFFF")
FILL_HEADER = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
FILL_ALT_ROW = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
BORDER_THIN = Border(
    left=Side(style="thin", color="CCCCCC"),
    right=Side(style="thin", color="CCCCCC"),
    top=Side(style="thin", color="CCCCCC"),
    bottom=Side(style="thin", color="CCCCCC"),
)


class ReportWriter:
    """Writes structured report data to Excel files with styling."""

    @staticmethod
    def write_excel(data: dict[str, list[list]], path: Path) -> None:
        """Write structured data to an Excel file.

        Args:
            data: dict mapping sheet_name to rows. First row of each sheet = header.
            path: Output file path.
        """
        wb = openpyxl.Workbook()
        first = True

        for sheet_name, rows in data.items():
            if first:
                ws = wb.active
                ws.title = sheet_name
                first = False
            else:
                ws = wb.create_sheet(sheet_name)

            if not rows:
                continue

            # Header row
            for col, value in enumerate(rows[0], 1):
                cell = ws.cell(row=1, column=col, value=value)
                cell.font = FONT_HEADER
                cell.fill = FILL_HEADER
                cell.alignment = Alignment(horizontal="center")
                cell.border = BORDER_THIN

            # Data rows
            for row_idx, row in enumerate(rows[1:], 2):
                for col, value in enumerate(row, 1):
                    cell = ws.cell(row=row_idx, column=col, value=value)
                    cell.border = BORDER_THIN
                    if row_idx % 2 == 0:
                        cell.fill = FILL_ALT_ROW

        wb.save(str(path))
```

- [ ] **Step 4: 執行測試確認通過**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_report_writer.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/core/report_writer.py tests/unit/test_report_writer.py
git commit -m "feat(core): 新增 ReportWriter — Excel 寫入與格式化"
```

---

### Task 4: ReportEngine.generate_* 改用 build + write

**Files:**
- Modify: `src/hcp_cms/core/report_engine.py`
- Run: `tests/unit/test_report_engine.py`, `tests/unit/test_report_engine_custom_cols.py`

- [ ] **Step 1: 重構 generate_tracking_table**

將 `generate_tracking_table` 改為呼叫 `build_tracking_table` + `ReportWriter.write_excel`：

```python
def generate_tracking_table(self, start_date: str, end_date: str, output_path: Path) -> Path:
    """Generate tracking table Excel with multiple sheets."""
    data = self.build_tracking_table(start_date, end_date)
    ReportWriter.write_excel(data, output_path)
    return output_path
```

同理重構 `generate_monthly_report`：

```python
def generate_monthly_report(self, start_date: str, end_date: str, output_path: Path) -> Path:
    """Generate monthly report Excel with KPI summary."""
    data = self.build_monthly_report(start_date, end_date)
    ReportWriter.write_excel(data, output_path)
    return output_path
```

在檔案頂部加入 import：

```python
from hcp_cms.core.report_writer import ReportWriter
```

刪除 ReportEngine 中不再使用的 `_write_header` 和 `_style_data_row` 私有方法，以及不再使用的 openpyxl 樣式常數（`FONT_HEADER`, `FILL_HEADER`, `FILL_ALT_ROW`, `BORDER_THIN`）和 `openpyxl` import。保留 `_clean`, `_clean_row`, `_reply_hours` 模組級函數。

- [ ] **Step 2: 執行全部 report 相關測試確認通過**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_report_engine.py tests/unit/test_report_engine_custom_cols.py -v`
Expected: 全部通過。注意：原有測試驗證 Excel 樣式（`test_report_header_style`）和 HYPERLINK（`test_customer_index_has_hyperlinks_to_company_sheets`, `test_company_sheet_has_back_link_to_index`）可能需要調整，因為 ReportWriter 使用統一格式化邏輯，不再產生 HYPERLINK 公式。

若 HYPERLINK 相關測試失敗，將這些測試改為驗證結構化資料中的純文字內容：

```python
def test_customer_index_has_link_text(self, seeded_db):
    engine = ReportEngine(seeded_db.connection)
    data = engine.build_tracking_table("2026/03/01", "2026/03/31")
    index_rows = data["📋 客戶索引"]
    # 日月光在第 2 列（index 1），快速連結在第 6 欄（index 5）
    assert "日月光" in str(index_rows[1][5])

def test_company_sheet_has_back_link_text(self, seeded_db):
    engine = ReportEngine(seeded_db.connection)
    data = engine.build_tracking_table("2026/03/01", "2026/03/31")
    ase_key = [k for k in data if "日月光" in k][0]
    assert data[ase_key][0][0] == "↩ 返回客戶索引"
```

- [ ] **Step 3: Commit**

```bash
git add src/hcp_cms/core/report_engine.py tests/unit/test_report_engine.py
git commit -m "refactor(core): generate_* 改用 build + ReportWriter.write_excel"
```

---

### Task 5: ReportView UI — 拆為檢視/下載按鈕 + QTabWidget 預覽

**Files:**
- Modify: `src/hcp_cms/ui/report_view.py`

- [ ] **Step 1: 重寫 ReportView**

修改 `src/hcp_cms/ui/report_view.py`，將單一按鈕拆為檢視與下載，加入 QTabWidget 預覽：

```python
"""Report center view."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.report_engine import ReportEngine
from hcp_cms.core.report_writer import ReportWriter


class ReportView(QWidget):
    """Report center page."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._preview_data: dict[str, list[list]] | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("📊 報表中心")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f1f5f9;")
        layout.addWidget(title)

        # ── 控制列 ──────────────────────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)

        ctrl.addWidget(QLabel("報表類型:"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(["追蹤表", "月報"])
        self._type_combo.setFixedWidth(100)
        self._type_combo.currentIndexChanged.connect(self._on_params_changed)
        ctrl.addWidget(self._type_combo)

        ctrl.addSpacing(12)

        ctrl.addWidget(QLabel("起始日期:"))
        self._start_date = QDateEdit()
        self._start_date.setCalendarPopup(True)
        self._start_date.setDisplayFormat("yyyy/MM/dd")
        today = QDate.currentDate()
        self._start_date.setDate(QDate(today.year(), today.month(), 1))
        self._start_date.setFixedWidth(130)
        self._start_date.dateChanged.connect(self._on_params_changed)
        ctrl.addWidget(self._start_date)

        ctrl.addWidget(QLabel("～"))

        ctrl.addWidget(QLabel("結束日期:"))
        self._end_date = QDateEdit()
        self._end_date.setCalendarPopup(True)
        self._end_date.setDisplayFormat("yyyy/MM/dd")
        self._end_date.setDate(today)
        self._end_date.setFixedWidth(130)
        self._end_date.dateChanged.connect(self._on_params_changed)
        ctrl.addWidget(self._end_date)

        ctrl.addSpacing(12)

        self._preview_btn = QPushButton("🔍 檢視")
        self._preview_btn.clicked.connect(self._on_preview)
        ctrl.addWidget(self._preview_btn)

        self._download_btn = QPushButton("📥 下載")
        self._download_btn.setEnabled(False)
        self._download_btn.clicked.connect(self._on_download)
        ctrl.addWidget(self._download_btn)

        ctrl.addStretch()
        layout.addLayout(ctrl)

        # ── 預覽區 QTabWidget ────────────────────────────────────────────
        self._tab_widget = QTabWidget()
        layout.addWidget(self._tab_widget)

        # ── 狀態列 ──────────────────────────────────────────────────────
        self._status = QLabel("就緒")
        self._status.setStyleSheet("color: #64748b;")
        layout.addWidget(self._status)

    def _on_params_changed(self) -> None:
        """報表類型或日期變更時清空預覽。"""
        self._preview_data = None
        self._tab_widget.clear()
        self._download_btn.setEnabled(False)
        self._status.setText("就緒")

    def _on_preview(self) -> None:
        if not self._conn:
            return

        start = self._start_date.date().toString("yyyy/MM/dd")
        end = self._end_date.date().toString("yyyy/MM/dd")

        if self._start_date.date() > self._end_date.date():
            QMessageBox.warning(self, "日期錯誤", "起始日期不可晚於結束日期。")
            return

        self._status.setText("⏳ 正在載入報表，請稍候...")
        self._status.repaint()

        try:
            engine = ReportEngine(self._conn)
            report_type = self._type_combo.currentText()
            if report_type == "追蹤表":
                data = engine.build_tracking_table(start, end)
            else:
                data = engine.build_monthly_report(start, end)

            # 檢查是否有資料（至少一個 sheet 有超過表頭的資料列）
            has_data = any(len(rows) > 1 for rows in data.values())

            self._preview_data = data
            self._fill_preview(data)
            self._download_btn.setEnabled(has_data)

            if has_data:
                self._status.setText("✅ 預覽完成")
            else:
                self._status.setText("⚠️ 查詢範圍內無資料")

        except Exception as e:
            self._status.setText(f"❌ 載入失敗：{e}")
            QMessageBox.critical(self, "載入失敗", str(e))

    def _fill_preview(self, data: dict[str, list[list]]) -> None:
        """將結構化資料填入 QTabWidget。"""
        self._tab_widget.clear()

        for sheet_name, rows in data.items():
            table = QTableWidget()
            if rows:
                col_count = max(len(r) for r in rows)
                table.setColumnCount(col_count)
                table.setRowCount(len(rows) - 1 if len(rows) > 1 else 0)

                # 表頭
                headers = rows[0] if rows else []
                table.setHorizontalHeaderLabels([str(h) for h in headers])

                # 資料列
                for row_idx, row in enumerate(rows[1:]):
                    for col_idx, value in enumerate(row):
                        table.setItem(row_idx, col_idx, QTableWidgetItem(str(value) if value else ""))

                table.resizeColumnsToContents()
            self._tab_widget.addTab(table, sheet_name)

    def _on_download(self) -> None:
        if not self._preview_data:
            return

        start = self._start_date.date().toString("yyyy/MM/dd")
        end = self._end_date.date().toString("yyyy/MM/dd")
        report_type = self._type_combo.currentText()

        type_prefix = "追蹤表" if report_type == "追蹤表" else "月報"
        start_tag = start.replace("/", "")
        end_tag = end.replace("/", "")
        default_name = f"HCP_{type_prefix}_{start_tag}_{end_tag}.xlsx"

        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            desktop = Path.home()
        default_path = str(desktop / default_name)

        path, _ = QFileDialog.getSaveFileName(
            self, "儲存報表", default_path, "Excel 檔案 (*.xlsx)"
        )
        if not path:
            return

        try:
            ReportWriter.write_excel(self._preview_data, Path(path))
            self._status.setText(f"✅ 報表已儲存：{path}")

            reply = QMessageBox.question(
                self,
                "報表下載完成",
                f"報表已儲存至：\n{path}\n\n是否立即開啟？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                os.startfile(path)  # type: ignore[attr-defined]

        except Exception as e:
            self._status.setText(f"❌ 下載失敗：{e}")
            QMessageBox.critical(self, "下載失敗", str(e))
```

- [ ] **Step 2: 手動驗證 UI**

Run: `.venv/Scripts/python.exe -m hcp_cms`

驗證項目：
1. 報表中心頁面顯示「檢視」和「下載」兩個按鈕
2. 下載按鈕初始為停用狀態
3. 選擇日期範圍後按「檢視」→ QTabWidget 顯示多 sheet 預覽
4. 切換報表類型或日期 → 預覽清空、下載按鈕停用
5. 有預覽資料時按「下載」→ 跳出儲存對話框

- [ ] **Step 3: Commit**

```bash
git add src/hcp_cms/ui/report_view.py
git commit -m "feat(ui): 報表中心拆為檢視預覽與下載匯出兩個動作"
```

---

### Task 6: 全部測試通過 + 清理

**Files:**
- All modified files

- [ ] **Step 1: 執行全部測試**

Run: `.venv/Scripts/python.exe -m pytest tests/ -v`
Expected: 全部通過

- [ ] **Step 2: 執行 lint**

Run: `.venv/Scripts/ruff.exe check src/hcp_cms/core/report_engine.py src/hcp_cms/core/report_writer.py src/hcp_cms/ui/report_view.py tests/unit/test_report_writer.py tests/unit/test_report_engine.py`
Expected: 無錯誤

- [ ] **Step 3: 清理 report_engine.py 中不再使用的 import 和常數**

確認以下已從 `report_engine.py` 移除：
- `import openpyxl` 及 `from openpyxl.styles import ...`
- `FONT_HEADER`, `FILL_HEADER`, `FILL_ALT_ROW`, `BORDER_THIN` 常數
- `_write_header`, `_style_data_row` 方法

保留：
- `_clean`, `_clean_row`, `_reply_hours` 模組級函數
- `re`, `sqlite3`, `datetime`, `Path`, `Any`, `Case` import

- [ ] **Step 4: 最終 commit**

```bash
git add -A
git commit -m "chore: 清理 ReportEngine 不再使用的 import 與樣式常數"
```
