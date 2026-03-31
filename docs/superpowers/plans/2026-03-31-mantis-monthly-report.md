# Mantis 月報整合與同步頁面強化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在月報 Excel 新增「📌 Mantis 追蹤」工作表，並在 Mantis 同步頁面加入統計方塊與行分色，共用 `MantisClassifier` 分類邏輯。

**Architecture:** 新增 `MantisClassifier`（Core 層）集中管理 closed / salary / high / normal 四種分類；`ReportEngine` 呼叫 Classifier 組裝 Mantis 工作表資料，`ReportWriter` 新增 `append_mantis_sheet()` 在已存在的 workbook 上附加帶色彩的 Mantis 工作表；`MantisView` 同樣呼叫 Classifier 完成行分色與統計方塊。

**Tech Stack:** Python 3.14、openpyxl（PatternFill / Font）、PySide6（QFrame / QColor）、pytest

---

## 檔案異動總覽

| 路徑 | 動作 |
|------|------|
| `src/hcp_cms/core/mantis_classifier.py` | **新增** |
| `src/hcp_cms/core/report_engine.py` | 修改：新增 `build_mantis_sheet()`，更新 `generate_monthly_report()` |
| `src/hcp_cms/core/report_writer.py` | 修改：新增 `append_mantis_sheet()` |
| `src/hcp_cms/ui/mantis_view.py` | 修改：統計方塊 + 行分色 |
| `tests/unit/test_mantis_classifier.py` | **新增** |
| `tests/unit/test_report_engine.py` | 修改：新增 3 個測試 |
| `tests/unit/test_report_writer.py` | 修改：新增 2 個測試 |

---

## Task 1: MantisClassifier — Core 層分類器

**Files:**
- Create: `src/hcp_cms/core/mantis_classifier.py`
- Create: `tests/unit/test_mantis_classifier.py`

- [ ] **Step 1: 建立測試檔案**

```python
# tests/unit/test_mantis_classifier.py
"""Tests for MantisClassifier."""

from hcp_cms.core.mantis_classifier import MantisClassifier
from hcp_cms.data.models import MantisTicket


def _ticket(**kwargs) -> MantisTicket:
    """快速建立 MantisTicket（只填必要欄位）。"""
    return MantisTicket(ticket_id="MT-0001", summary=kwargs.get("summary", "一般問題"), **{k: v for k, v in kwargs.items() if k != "summary"})


class TestMantisClassifier:
    def setup_method(self):
        self.clf = MantisClassifier()

    def test_classify_closed_resolved(self):
        t = _ticket(status="resolved")
        assert self.clf.classify(t) == "closed"

    def test_classify_closed_chinese(self):
        t = _ticket(status="已關閉")
        assert self.clf.classify(t) == "closed"

    def test_classify_closed_beats_high_priority(self):
        """已結案優先於高優先度——不應顯示紅色。"""
        t = _ticket(status="closed", priority="urgent")
        assert self.clf.classify(t) == "closed"

    def test_classify_salary_keyword_chinese(self):
        t = _ticket(summary="薪資計算錯誤", status="assigned")
        assert self.clf.classify(t) == "salary"

    def test_classify_salary_keyword_english(self):
        t = _ticket(summary="Payroll module error", status="assigned")
        assert self.clf.classify(t) == "salary"

    def test_classify_high_urgent(self):
        t = _ticket(priority="urgent", status="assigned")
        assert self.clf.classify(t) == "high"

    def test_classify_high_immediate(self):
        t = _ticket(priority="immediate", status="assigned")
        assert self.clf.classify(t) == "high"

    def test_classify_normal(self):
        t = _ticket(priority="normal", status="assigned")
        assert self.clf.classify(t) == "normal"

    def test_classify_none_summary_no_error(self):
        """summary=None 時不拋例外，應回傳 normal。"""
        t = MantisTicket(ticket_id="MT-0001", summary=None, status="assigned")
        assert self.clf.classify(t) == "normal"

    def test_calc_unresolved_days_closed_returns_dash(self):
        t = _ticket(status="resolved", last_updated="2026/03/01 10:00:00")
        assert self.clf.calc_unresolved_days(t) == "—"

    def test_calc_unresolved_days_no_last_updated(self):
        t = _ticket(status="assigned", last_updated=None)
        assert self.clf.calc_unresolved_days(t) == ""

    def test_calc_unresolved_days_returns_days_string(self):
        """使用固定日期驗證計算邏輯正確（不依賴今日）。"""
        from datetime import datetime, timedelta
        three_days_ago = (datetime.now() - timedelta(days=3)).strftime("%Y/%m/%d %H:%M:%S")
        t = _ticket(status="assigned", last_updated=three_days_ago)
        result = self.clf.calc_unresolved_days(t)
        assert result == "3 天"
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_classifier.py -v
```

預期結果：`ImportError: cannot import name 'MantisClassifier'`

- [ ] **Step 3: 實作 MantisClassifier**

```python
# src/hcp_cms/core/mantis_classifier.py
"""Mantis ticket classifier — maps tickets to display categories."""

from __future__ import annotations

from datetime import datetime

from hcp_cms.data.models import MantisTicket

_DATE_FORMATS: list[tuple[str, int]] = [
    ("%Y-%m-%dT%H:%M:%S", 19),
    ("%Y/%m/%d %H:%M:%S", 19),
    ("%Y-%m-%d %H:%M:%S", 19),
    ("%Y/%m/%d", 10),
    ("%Y-%m-%d", 10),
]


class MantisClassifier:
    """將 MantisTicket 分類為 'closed' | 'salary' | 'high' | 'normal'。

    分類優先序：closed > salary > high > normal
    """

    SALARY_KEYWORDS: tuple[str, ...] = ("薪資", "薪水", "Payroll", "工資", "salary")
    HIGH_PRIORITY: tuple[str, ...] = ("high", "urgent", "immediate")
    CLOSED_STATUSES: tuple[str, ...] = ("resolved", "closed", "已解決", "已關閉")

    def classify(self, ticket: MantisTicket) -> str:
        """回傳 'closed' | 'salary' | 'high' | 'normal'。"""
        status = (ticket.status or "").lower()
        closed_lower = {s.lower() for s in self.CLOSED_STATUSES}
        if status in closed_lower:
            return "closed"
        summary = ticket.summary or ""
        if any(kw in summary for kw in self.SALARY_KEYWORDS):
            return "salary"
        priority = (ticket.priority or "").lower()
        high_lower = {p.lower() for p in self.HIGH_PRIORITY}
        if priority in high_lower:
            return "high"
        return "normal"

    def calc_unresolved_days(self, ticket: MantisTicket) -> str:
        """計算未處理天數；已結案回傳 '—'，無法計算回傳 ''。"""
        if self.classify(ticket) == "closed":
            return "—"
        if not ticket.last_updated:
            return ""
        for fmt, length in _DATE_FORMATS:
            try:
                dt = datetime.strptime(ticket.last_updated[:length], fmt)
                days = (datetime.now() - dt).days
                return f"{days} 天" if days >= 0 else ""
            except ValueError:
                continue
        return ""
```

- [ ] **Step 4: 執行測試確認全部通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_classifier.py -v
```

預期結果：12 個測試全部 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/core/mantis_classifier.py tests/unit/test_mantis_classifier.py
git commit -m "feat: 新增 MantisClassifier Core 層分類器"
```

---

## Task 2: ReportEngine.build_mantis_sheet() — 月報 Mantis 資料組裝

**Files:**
- Modify: `src/hcp_cms/core/report_engine.py`
- Modify: `tests/unit/test_report_engine.py`

- [ ] **Step 1: 在 test_report_engine.py 新增 Mantis 相關 fixture 與測試**

在檔案尾端加入以下程式碼：

```python
# tests/unit/test_report_engine.py 尾端新增

from hcp_cms.data.models import MantisTicket
from hcp_cms.data.repositories import MantisRepository


@pytest.fixture
def mantis_seeded_db(db: DatabaseManager) -> DatabaseManager:
    repo = MantisRepository(db.connection)
    repo.upsert(MantisTicket(
        ticket_id="MT-0001", summary="系統當機", status="assigned",
        priority="urgent", handler="王小明", last_updated="2026/03/13 10:00:00",
    ))
    repo.upsert(MantisTicket(
        ticket_id="MT-0002", summary="薪資計算錯誤", status="assigned",
        priority="normal", handler="李大華", last_updated="2026/03/24 10:00:00",
    ))
    repo.upsert(MantisTicket(
        ticket_id="MT-0003", summary="登入頁跑版", status="resolved",
        priority="low", handler="張三", last_updated="2026/03/10 10:00:00",
    ))
    return db


class TestBuildMantisSheet:
    def test_returns_list_of_dicts(self, mantis_seeded_db):
        engine = ReportEngine(mantis_seeded_db.connection)
        rows = engine.build_mantis_sheet()
        assert isinstance(rows, list)
        assert len(rows) == 3

    def test_each_row_has_category(self, mantis_seeded_db):
        engine = ReportEngine(mantis_seeded_db.connection)
        rows = engine.build_mantis_sheet()
        for row in rows:
            assert "category" in row
            assert row["category"] in ("closed", "salary", "high", "normal")

    def test_sorting_high_before_closed(self, mantis_seeded_db):
        """high 優先度排在 closed 之前。"""
        engine = ReportEngine(mantis_seeded_db.connection)
        rows = engine.build_mantis_sheet()
        categories = [r["category"] for r in rows]
        assert categories.index("high") < categories.index("closed")
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_report_engine.py::TestBuildMantisSheet -v
```

預期結果：`AttributeError: 'ReportEngine' object has no attribute 'build_mantis_sheet'`

- [ ] **Step 3: 在 report_engine.py 新增 build_mantis_sheet()**

在 `build_monthly_report()` 方法結束後（第 326 行後），`generate_monthly_report()` 之前插入：

```python
    def build_mantis_sheet(self) -> list[dict]:
        """組裝 Mantis 追蹤工作表資料列。

        Returns:
            list of dict，每列含：
            ticket_id, summary, status, priority,
            unresolved_days, last_updated, handler, category
            排序：high → salary → normal → closed
        """
        from hcp_cms.core.mantis_classifier import MantisClassifier

        classifier = MantisClassifier()
        tickets = self._mantis_repo.list_all()

        _SORT_ORDER = {"high": 0, "salary": 1, "normal": 2, "closed": 3}

        rows = []
        for ticket in tickets:
            category = classifier.classify(ticket)
            rows.append({
                "ticket_id": ticket.ticket_id,
                "summary": _clean(ticket.summary or ""),
                "status": ticket.status or "",
                "priority": ticket.priority or "",
                "unresolved_days": classifier.calc_unresolved_days(ticket),
                "last_updated": ticket.last_updated or "",
                "handler": ticket.handler or "",
                "category": category,
            })

        rows.sort(key=lambda r: _SORT_ORDER[r["category"]])
        return rows
```

- [ ] **Step 4: 執行測試確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_report_engine.py::TestBuildMantisSheet -v
```

預期結果：3 個測試全部 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/core/report_engine.py tests/unit/test_report_engine.py
git commit -m "feat: ReportEngine 新增 build_mantis_sheet()"
```

---

## Task 3: ReportWriter.append_mantis_sheet() — 帶分色的 Excel 工作表

**Files:**
- Modify: `src/hcp_cms/core/report_writer.py`
- Modify: `tests/unit/test_report_writer.py`

- [ ] **Step 1: 在 test_report_writer.py 新增測試**

在檔案尾端加入：

```python
# tests/unit/test_report_writer.py 尾端新增

import openpyxl


class TestAppendMantisSheet:
    def test_mantis_sheet_created(self, tmp_path):
        """append_mantis_sheet() 在既有 workbook 新增工作表。"""
        path = tmp_path / "report.xlsx"
        # 先建立一個基礎 workbook
        ReportWriter.write_excel({"摘要": [["欄位"], ["值"]]}, path)

        mantis_rows = [
            {"ticket_id": "MT-001", "summary": "問題A", "status": "assigned",
             "priority": "urgent", "unresolved_days": "5 天",
             "last_updated": "2026/03/26", "handler": "王小明", "category": "high"},
        ]
        ReportWriter.append_mantis_sheet(path, "📌 Mantis 追蹤", mantis_rows)

        wb = openpyxl.load_workbook(str(path))
        assert "📌 Mantis 追蹤" in wb.sheetnames

    def test_mantis_high_row_fill_color(self, tmp_path):
        """high 分類的列背景色應為 #450a0a。"""
        path = tmp_path / "report.xlsx"
        ReportWriter.write_excel({"摘要": [["欄位"], ["值"]]}, path)

        mantis_rows = [
            {"ticket_id": "MT-001", "summary": "急件", "status": "assigned",
             "priority": "urgent", "unresolved_days": "5 天",
             "last_updated": "2026/03/26", "handler": "王小明", "category": "high"},
        ]
        ReportWriter.append_mantis_sheet(path, "📌 Mantis 追蹤", mantis_rows)

        wb = openpyxl.load_workbook(str(path))
        ws = wb["📌 Mantis 追蹤"]
        # 第 1 列為表頭，第 2 列為資料
        fill = ws.cell(row=2, column=1).fill
        assert fill.fgColor.rgb.upper().endswith("450A0A")
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_report_writer.py::TestAppendMantisSheet -v
```

預期結果：`AttributeError: type object 'ReportWriter' has no attribute 'append_mantis_sheet'`

- [ ] **Step 3: 在 report_writer.py 新增色彩常數與 append_mantis_sheet()**

在檔案頂端的常數區（`BORDER_THIN` 之後）新增色彩映射，並在 `ReportWriter` class 內新增靜態方法：

在 `BORDER_THIN = ...` 之後插入：

```python
# Mantis 追蹤工作表分類色彩（背景色, 字體色）
_MANTIS_COLORS: dict[str, tuple[str, str]] = {
    "high":   ("450A0A", "FFFFFF"),
    "salary": ("422006", "FEF08A"),
    "normal": ("111827", "E2E8F0"),
    "closed": ("1A1A1A", "4B5563"),
}
```

在 `ReportWriter` class 的 `write_excel()` 之後新增：

```python
    @staticmethod
    def append_mantis_sheet(
        path: Path,
        sheet_name: str,
        rows: list[dict],
    ) -> None:
        """在已存在的 Excel 檔案中新增 Mantis 追蹤工作表（帶分色）。

        Args:
            path:       已存在的 .xlsx 檔案路徑。
            sheet_name: 工作表名稱，如「📌 Mantis 追蹤」。
            rows:       build_mantis_sheet() 回傳的 list[dict]，
                        每列需含 category 欄位。
        """
        headers = ["#", "票號", "摘要", "狀態", "優先", "未處理天數", "最後更新", "負責人"]

        wb = openpyxl.load_workbook(str(path))
        ws = wb.create_sheet(sheet_name)

        # 表頭列
        for col, value in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=value)
            cell.font = FONT_HEADER
            cell.fill = FILL_HEADER
            cell.alignment = Alignment(horizontal="center")
            cell.border = BORDER_THIN

        # 資料列
        for row_idx, row in enumerate(rows, 2):
            bg, fg = _MANTIS_COLORS.get(row.get("category", "normal"), ("111827", "E2E8F0"))
            fill = PatternFill(start_color=bg, end_color=bg, fill_type="solid")
            font = Font(name="微軟正黑體", size=10, color=fg)
            values = [
                row_idx - 1,
                row["ticket_id"],
                row["summary"],
                row["status"],
                row["priority"],
                row["unresolved_days"],
                row["last_updated"],
                row["handler"],
            ]
            for col, value in enumerate(values, 1):
                cell = ws.cell(row=row_idx, column=col, value=value)
                cell.fill = fill
                cell.font = font
                cell.border = BORDER_THIN

        # 凍結首列
        ws.freeze_panes = "A2"

        # 自動調整欄寬
        for col_cells in ws.columns:
            max_length = max(
                (len(str(c.value)) for c in col_cells if c.value), default=0
            )
            adjusted = min(max_length + 2, 50)
            if adjusted > 0:
                ws.column_dimensions[col_cells[0].column_letter].width = adjusted

        wb.save(str(path))
```

- [ ] **Step 4: 執行測試確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_report_writer.py::TestAppendMantisSheet -v
```

預期結果：2 個測試全部 PASSED

- [ ] **Step 5: 確認既有測試未破壞**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_report_writer.py -v
```

預期結果：所有測試 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/hcp_cms/core/report_writer.py tests/unit/test_report_writer.py
git commit -m "feat: ReportWriter 新增 append_mantis_sheet() 帶分色工作表"
```

---

## Task 4: 串接月報生成（generate_monthly_report）

**Files:**
- Modify: `src/hcp_cms/core/report_engine.py`（僅修改 `generate_monthly_report()`）
- Modify: `tests/unit/test_report_engine.py`

- [ ] **Step 1: 新增整合測試**

在 `TestBuildMantisSheet` 後新增：

```python
class TestGenerateMonthlyReportWithMantis:
    def test_monthly_report_has_mantis_sheet(self, mantis_seeded_db, tmp_path):
        """generate_monthly_report() 生成的 Excel 應包含 Mantis 追蹤工作表。"""
        engine = ReportEngine(mantis_seeded_db.connection)
        path = engine.generate_monthly_report(
            "2026/03/01", "2026/03/31", tmp_path / "monthly.xlsx"
        )
        wb = openpyxl.load_workbook(str(path))
        assert "📌 Mantis 追蹤" in wb.sheetnames

    def test_mantis_sheet_row_count(self, mantis_seeded_db, tmp_path):
        """Mantis 工作表的資料列數應等於 ticket 總數。"""
        engine = ReportEngine(mantis_seeded_db.connection)
        path = engine.generate_monthly_report(
            "2026/03/01", "2026/03/31", tmp_path / "monthly.xlsx"
        )
        wb = openpyxl.load_workbook(str(path))
        ws = wb["📌 Mantis 追蹤"]
        # 第 1 列是表頭，第 2 列起是資料
        data_rows = ws.max_row - 1
        assert data_rows == 3
```

在測試檔案頂端的 import 區補上 `import openpyxl`（若尚未存在）。

- [ ] **Step 2: 執行測試確認失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_report_engine.py::TestGenerateMonthlyReportWithMantis -v
```

預期結果：AssertionError（Mantis 工作表不存在）

- [ ] **Step 3: 修改 generate_monthly_report() 串接 append_mantis_sheet()**

將 `report_engine.py` 第 328-332 行的 `generate_monthly_report()` 替換為：

```python
    def generate_monthly_report(self, start_date: str, end_date: str, output_path: Path) -> Path:
        """Generate monthly report Excel with KPI summary and Mantis tracking sheet."""
        data = self.build_monthly_report(start_date, end_date)
        ReportWriter.write_excel(data, output_path)
        mantis_rows = self.build_mantis_sheet()
        ReportWriter.append_mantis_sheet(output_path, "📌 Mantis 追蹤", mantis_rows)
        return output_path
```

- [ ] **Step 4: 執行測試確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_report_engine.py -v
```

預期結果：所有測試 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/core/report_engine.py tests/unit/test_report_engine.py
git commit -m "feat: 月報串接 Mantis 追蹤工作表"
```

---

## Task 5: MantisView 統計方塊 + 行分色

**Files:**
- Modify: `src/hcp_cms/ui/mantis_view.py`

> UI 層不做單元測試，請手動執行應用程式驗證視覺效果。

- [ ] **Step 1: 在 mantis_view.py 頂端 import 區補充所需模組**

在現有 import 區（第 7-24 行）找到 `from PySide6.QtWidgets import (` 這行，補充 `QFrame` 和 `QSizePolicy`：

```python
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.mantis_classifier import MantisClassifier
from hcp_cms.data.repositories import MantisRepository
from hcp_cms.services.credential import CredentialManager
from hcp_cms.services.mantis.soap import MantisSoapClient
from hcp_cms.ui.theme import ColorPalette, ThemeManager
```

- [ ] **Step 2: 新增 _make_stat_frame() helper 與色彩常數**

在 `class MantisView(QWidget):` class 定義內、`__init__` 之前插入：

```python
    # 分類色彩：(背景色 hex, 前景色 hex)
    _CATEGORY_COLORS: dict[str, tuple[str, str]] = {
        "high":   ("#450a0a", "#ffffff"),
        "salary": ("#422006", "#fef08a"),
        "normal": ("#111827", "#e2e8f0"),
        "closed": ("#1a1a1a", "#4b5563"),
    }

    @staticmethod
    def _make_stat_frame(label: str, bg: str, fg: str) -> tuple[QFrame, QLabel]:
        """建立統計方塊 QFrame，回傳 (frame, value_label)。"""
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {fg}; border-radius: 6px; }}"
        )
        frame.setFixedHeight(56)
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(2)
        value_lbl = QLabel("0")
        value_lbl.setStyleSheet(f"color: {fg}; font-size: 18px; font-weight: bold; border: none;")
        title_lbl = QLabel(label)
        title_lbl.setStyleSheet(f"color: {fg}; font-size: 10px; border: none;")
        layout.addWidget(value_lbl)
        layout.addWidget(title_lbl)
        return frame, value_lbl
```

- [ ] **Step 3: 在 _setup_ui() 中加入統計方塊列**

找到 `_setup_ui()` 方法中 `layout.addWidget(conn_group)` 這行（第 127 行），在其後插入：

```python
        layout.addWidget(conn_group)

        # ── 統計方塊列 ───────────────────────────────────────────
        stats_widget = QWidget()
        stats_layout = QHBoxLayout(stats_widget)
        stats_layout.setContentsMargins(0, 4, 0, 4)
        stats_layout.setSpacing(8)

        high_frame, self._stat_high_lbl = self._make_stat_frame("高優先度", "#450a0a", "#fca5a5")
        salary_frame, self._stat_salary_lbl = self._make_stat_frame("薪資相關", "#422006", "#fef08a")
        open_frame, self._stat_open_lbl = self._make_stat_frame("處理中", "#1e3a5f", "#93c5fd")
        closed_frame, self._stat_closed_lbl = self._make_stat_frame("已結案", "#1a1a1a", "#6b7280")

        stats_layout.addWidget(high_frame)
        stats_layout.addWidget(salary_frame)
        stats_layout.addWidget(open_frame)
        stats_layout.addWidget(closed_frame)
        stats_layout.addStretch()
        layout.addWidget(stats_widget)
```

- [ ] **Step 4: 修改 refresh() 加入行分色與統計更新**

將現有 `refresh()` 方法（第 217-236 行）整體替換為：

```python
    def refresh(self) -> None:
        """從本地 DB 載入已同步過的 Ticket 到清單，並套用分色與更新統計。"""
        if not self._conn:
            return
        repo = MantisRepository(self._conn)
        tickets = repo.list_all()
        self._table.setRowCount(len(tickets))
        # 更新最後同步標籤
        sync_times = [t.synced_at for t in tickets if t.synced_at]
        if sync_times:
            self._last_sync_label.setText(f"最後同步：{max(sync_times)}")

        classifier = MantisClassifier()
        counts: dict[str, int] = {"high": 0, "salary": 0, "normal": 0, "closed": 0}

        for i, t in enumerate(tickets):
            self._table.setItem(i, 0, QTableWidgetItem(t.ticket_id))
            self._table.setItem(i, 1, QTableWidgetItem(t.summary or ""))
            self._table.setItem(i, 2, QTableWidgetItem(t.status or ""))
            self._table.setItem(i, 3, QTableWidgetItem(t.priority or ""))
            self._table.setItem(i, 4, QTableWidgetItem(t.handler or ""))
            self._table.setItem(i, 5, QTableWidgetItem(t.last_updated or "—"))
            days_str = self._calc_unresolved_days(t.status, t.last_updated)
            self._table.setItem(i, 6, QTableWidgetItem(days_str))

            # 套用分色
            category = classifier.classify(t)
            counts[category] += 1
            bg_hex, fg_hex = self._CATEGORY_COLORS[category]
            bg = QColor(bg_hex)
            fg = QColor(fg_hex)
            for col in range(7):
                item = self._table.item(i, col)
                if item:
                    item.setBackground(bg)
                    item.setForeground(fg)

        # 更新統計方塊
        self._stat_high_lbl.setText(str(counts["high"]))
        self._stat_salary_lbl.setText(str(counts["salary"]))
        open_count = counts["high"] + counts["salary"] + counts["normal"]
        self._stat_open_lbl.setText(str(open_count))
        self._stat_closed_lbl.setText(str(counts["closed"]))
```

- [ ] **Step 5: 執行應用程式，手動驗證**

```bash
.venv/Scripts/python.exe -m hcp_cms
```

確認：
1. Mantis 同步頁面頂部出現四個統計方塊
2. 清單列依分類顯示紅色（高優先）/ 黃橙色（薪資）/ 深藍（一般）/ 深灰（已結案）
3. 下載月報 Excel 後，工作表清單出現「📌 Mantis 追蹤」，列顏色正確

- [ ] **Step 6: 執行全部測試確認無回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v
```

預期結果：所有測試 PASSED

- [ ] **Step 7: Commit**

```bash
git add src/hcp_cms/ui/mantis_view.py
git commit -m "feat: Mantis 同步頁面新增統計方塊與行分色"
```
