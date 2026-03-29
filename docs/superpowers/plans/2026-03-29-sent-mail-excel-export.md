# 寄件備份匯出 Excel 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在「寄件備份」分頁加入「匯出 Excel」按鈕，將公司彙總與寄件清單匯出為 `.xlsx` 兩個工作表。

**Architecture:** 新增 Core 層 `ExcelExporter` 類別處理 xlsx 寫出邏輯；UI 層 `SentMailTab` 儲存最新資料並呼叫 exporter，彈出系統對話框讓使用者選擇儲存路徑。

**Tech Stack:** Python 3.14、openpyxl 3.1+、PySide6 QFileDialog

---

## 檔案清單

| 動作 | 路徑 |
|------|------|
| 新增 | `src/hcp_cms/core/excel_exporter.py` |
| 新增 | `tests/unit/test_excel_exporter.py` |
| 修改 | `src/hcp_cms/ui/sent_mail_tab.py` |

---

### Task 1：ExcelExporter — TDD

**Files:**
- Create: `src/hcp_cms/core/excel_exporter.py`
- Create: `tests/unit/test_excel_exporter.py`

- [ ] **Step 1：撰寫測試（先讓它失敗）**

建立 `tests/unit/test_excel_exporter.py`：

```python
"""Unit tests for ExcelExporter."""

from __future__ import annotations

import openpyxl
import pytest

from hcp_cms.core.excel_exporter import ExcelExporter
from hcp_cms.core.sent_mail_manager import EnrichedSentMail


def _make_mail(
    date: str = "2026/03/27 10:00:00",
    recipients: list[str] | None = None,
    subject: str = "測試主旨",
    company_id: str | None = "C001",
    company_name: str | None = "測試公司",
    linked_case_id: str | None = None,
    company_reply_count: int = 3,
) -> EnrichedSentMail:
    return EnrichedSentMail(
        date=date,
        recipients=recipients or ["test@example.com"],
        subject=subject,
        company_id=company_id,
        company_name=company_name,
        linked_case_id=linked_case_id,
        company_reply_count=company_reply_count,
    )


class TestExcelExporter:
    def test_creates_file(self, tmp_path):
        path = str(tmp_path / "output.xlsx")
        ExcelExporter().export_sent_mail([_make_mail()], path)
        assert (tmp_path / "output.xlsx").exists()

    def test_sheet_names(self, tmp_path):
        path = str(tmp_path / "output.xlsx")
        ExcelExporter().export_sent_mail([_make_mail()], path)
        wb = openpyxl.load_workbook(path)
        assert wb.sheetnames == ["公司彙總", "寄件清單"]

    def test_summary_header(self, tmp_path):
        path = str(tmp_path / "output.xlsx")
        ExcelExporter().export_sent_mail([_make_mail()], path)
        wb = openpyxl.load_workbook(path)
        ws = wb["公司彙總"]
        assert ws.cell(1, 1).value == "公司名稱"
        assert ws.cell(1, 2).value == "次數"

    def test_summary_rows_count(self, tmp_path):
        mails = [
            _make_mail(company_id="C001", company_name="甲公司", company_reply_count=5),
            _make_mail(company_id="C002", company_name="乙公司", company_reply_count=2),
            _make_mail(company_id="C001", company_name="甲公司", company_reply_count=5),
        ]
        path = str(tmp_path / "output.xlsx")
        ExcelExporter().export_sent_mail(mails, path)
        wb = openpyxl.load_workbook(path)
        ws = wb["公司彙總"]
        # 2 間公司 + 1 標題列
        assert ws.max_row == 3

    def test_summary_sorted_by_count_desc(self, tmp_path):
        mails = [
            _make_mail(company_id="C001", company_name="甲公司", company_reply_count=2),
            _make_mail(company_id="C002", company_name="乙公司", company_reply_count=5),
        ]
        path = str(tmp_path / "output.xlsx")
        ExcelExporter().export_sent_mail(mails, path)
        wb = openpyxl.load_workbook(path)
        ws = wb["公司彙總"]
        assert ws.cell(2, 1).value == "乙公司"
        assert ws.cell(3, 1).value == "甲公司"

    def test_list_header(self, tmp_path):
        path = str(tmp_path / "output.xlsx")
        ExcelExporter().export_sent_mail([_make_mail()], path)
        wb = openpyxl.load_workbook(path)
        ws = wb["寄件清單"]
        headers = [ws.cell(1, c).value for c in range(1, 7)]
        assert headers == ["日期", "收件人", "主旨", "公司", "案件", "次數"]

    def test_list_rows_count(self, tmp_path):
        mails = [_make_mail(), _make_mail(), _make_mail()]
        path = str(tmp_path / "output.xlsx")
        ExcelExporter().export_sent_mail(mails, path)
        wb = openpyxl.load_workbook(path)
        ws = wb["寄件清單"]
        # 3 封信 + 1 標題列
        assert ws.max_row == 4

    def test_list_recipients_joined(self, tmp_path):
        mail = _make_mail(recipients=["a@x.com", "b@x.com"])
        path = str(tmp_path / "output.xlsx")
        ExcelExporter().export_sent_mail([mail], path)
        wb = openpyxl.load_workbook(path)
        ws = wb["寄件清單"]
        assert ws.cell(2, 2).value == "a@x.com, b@x.com"

    def test_list_empty_case_filled_dash(self, tmp_path):
        mail = _make_mail(linked_case_id=None)
        path = str(tmp_path / "output.xlsx")
        ExcelExporter().export_sent_mail([mail], path)
        wb = openpyxl.load_workbook(path)
        ws = wb["寄件清單"]
        assert ws.cell(2, 5).value == "—"

    def test_list_empty_company_id_no_count(self, tmp_path):
        mail = _make_mail(company_id=None, company_name=None, company_reply_count=0)
        path = str(tmp_path / "output.xlsx")
        ExcelExporter().export_sent_mail([mail], path)
        wb = openpyxl.load_workbook(path)
        ws = wb["寄件清單"]
        assert ws.cell(2, 6).value == "—"
```

- [ ] **Step 2：執行測試，確認失敗**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_excel_exporter.py -v
```

預期輸出：`ModuleNotFoundError: No module named 'hcp_cms.core.excel_exporter'`

- [ ] **Step 3：實作 ExcelExporter**

建立 `src/hcp_cms/core/excel_exporter.py`：

```python
"""Excel 匯出工具 — 寄件備份。"""

from __future__ import annotations

from openpyxl import Workbook
from openpyxl.styles import Font

from hcp_cms.core.sent_mail_manager import EnrichedSentMail


class ExcelExporter:
    """將 EnrichedSentMail 列表匯出為 xlsx（兩個工作表）。"""

    def export_sent_mail(self, mails: list[EnrichedSentMail], path: str) -> None:
        """匯出寄件備份至 xlsx。

        Args:
            mails: 已抓取並豐富化的寄件清單。
            path: 輸出檔案路徑（含副檔名 .xlsx）。
        """
        wb = Workbook()
        self._write_summary(wb, mails)
        self._write_list(wb, mails)
        # 刪除預設空白工作表
        if "Sheet" in wb.sheetnames:
            del wb["Sheet"]
        wb.save(path)

    def _write_summary(self, wb: Workbook, mails: list[EnrichedSentMail]) -> None:
        ws = wb.create_sheet("公司彙總")
        bold = Font(bold=True)

        # 標題列
        for col, title in enumerate(["公司名稱", "次數"], start=1):
            cell = ws.cell(1, col, title)
            cell.font = bold

        # 去重並依次數降冪
        seen: dict[str, tuple[str, int]] = {}
        for m in mails:
            if m.company_id and m.company_id not in seen:
                seen[m.company_id] = (m.company_name or m.company_id, m.company_reply_count)
        ranked = sorted(seen.values(), key=lambda x: x[1], reverse=True)

        for row, (name, count) in enumerate(ranked, start=2):
            ws.cell(row, 1, name)
            ws.cell(row, 2, count)

    def _write_list(self, wb: Workbook, mails: list[EnrichedSentMail]) -> None:
        ws = wb.create_sheet("寄件清單")
        bold = Font(bold=True)

        headers = ["日期", "收件人", "主旨", "公司", "案件", "次數"]
        for col, title in enumerate(headers, start=1):
            cell = ws.cell(1, col, title)
            cell.font = bold

        for row, m in enumerate(mails, start=2):
            ws.cell(row, 1, m.date[:10] if m.date else "")
            ws.cell(row, 2, ", ".join(m.recipients))
            ws.cell(row, 3, m.subject)
            ws.cell(row, 4, m.company_name or "未知")
            ws.cell(row, 5, m.linked_case_id or "—")
            ws.cell(row, 6, str(m.company_reply_count) if m.company_id else "—")
```

- [ ] **Step 4：執行測試，確認全過**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/unit/test_excel_exporter.py -v
```

預期輸出：所有測試 `PASSED`

- [ ] **Step 5：Lint 檢查**

```bash
cd D:/CMS && .venv/Scripts/ruff.exe check src/hcp_cms/core/excel_exporter.py tests/unit/test_excel_exporter.py
```

預期輸出：無錯誤

- [ ] **Step 6：Commit**

```bash
cd D:/CMS && git add src/hcp_cms/core/excel_exporter.py tests/unit/test_excel_exporter.py
git commit -m "feat(core): 新增 ExcelExporter — 寄件備份匯出兩工作表"
```

---

### Task 2：SentMailTab UI 整合

**Files:**
- Modify: `src/hcp_cms/ui/sent_mail_tab.py`

- [ ] **Step 1：新增 import 與實例變數**

在 `src/hcp_cms/ui/sent_mail_tab.py` 頂端加入 import：

```python
from PySide6.QtWidgets import (
    QApplication,
    QDateEdit,
    QFileDialog,          # ← 新增
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.excel_exporter import ExcelExporter    # ← 新增
from hcp_cms.core.sent_mail_manager import EnrichedSentMail, SentMailManager
from hcp_cms.services.mail.base import MailProvider
```

在 `SentMailTab.__init__` 中，於 `self._provider` 那行之後加入：

```python
self._current_mails: list[EnrichedSentMail] = []
```

- [ ] **Step 2：在日期列加「匯出 Excel」按鈕**

在 `_setup_ui` 的 `filter_layout.addStretch()` **之前**加入：

```python
self._export_btn = QPushButton("📥 匯出 Excel")
self._export_btn.setEnabled(False)
self._export_btn.clicked.connect(self._on_export)
filter_layout.addWidget(self._export_btn)
```

- [ ] **Step 3：在 `_on_worker_done` 儲存資料並啟用按鈕**

找到 `_on_worker_done` 方法，在 `self._refresh_btn.setEnabled(True)` 之後加入：

```python
self._current_mails = mails
self._export_btn.setEnabled(len(mails) > 0)
```

完整方法如下：

```python
def _on_worker_done(self, results: object) -> None:
    mails = cast(list[EnrichedSentMail], results)
    self._refresh_btn.setEnabled(True)
    self._current_mails = mails
    self._export_btn.setEnabled(len(mails) > 0)
    self._log.append(f"✅ 取得 {len(mails)} 封寄件備份。")
    self._populate_tables(mails)
```

- [ ] **Step 4：實作 `_on_export` 方法**

在 `_on_cell_double_clicked` 之後加入：

```python
def _on_export(self) -> None:
    d = self._date_edit.date()
    default_name = f"寄件備份_{d.toString('yyyy-MM-dd')}.xlsx"
    path, _ = QFileDialog.getSaveFileName(
        self,
        "匯出 Excel",
        default_name,
        "Excel 檔案 (*.xlsx)",
    )
    if not path:
        return
    try:
        ExcelExporter().export_sent_mail(self._current_mails, path)
        self._log.append(f"✅ 已匯出至 {path}")
    except Exception as e:
        self._log.append(f"❌ 匯出失敗：{e}")
```

- [ ] **Step 5：Lint 檢查**

```bash
cd D:/CMS && .venv/Scripts/ruff.exe check src/hcp_cms/ui/sent_mail_tab.py
```

預期輸出：無錯誤

- [ ] **Step 6：格式化**

```bash
cd D:/CMS && .venv/Scripts/ruff.exe format src/hcp_cms/ui/sent_mail_tab.py
```

- [ ] **Step 7：跑完整測試套件確認無回歸**

```bash
cd D:/CMS && .venv/Scripts/python.exe -m pytest tests/ -v --tb=short
```

預期輸出：所有測試 `PASSED`

- [ ] **Step 8：Commit**

```bash
cd D:/CMS && git add src/hcp_cms/ui/sent_mail_tab.py
git commit -m "feat(ui): 寄件備份分頁加入匯出 Excel 按鈕"
```
