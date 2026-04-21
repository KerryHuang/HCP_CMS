"""Excel report writer — writes structured data to styled .xlsx files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.hyperlink import Hyperlink


@dataclass
class HyperlinkCell:
    """Excel 內部超連結格子：顯示 text，點擊跳轉至同檔案的 target_sheet 工作表。"""

    text: str
    target_sheet: str

    def __str__(self) -> str:
        return self.text

FONT_HEADER = Font(name="微軟正黑體", size=11, bold=True, color="FFFFFF")
FILL_HEADER = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
FILL_ALT_ROW = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
BORDER_THIN = Border(
    left=Side(style="thin", color="CCCCCC"),
    right=Side(style="thin", color="CCCCCC"),
    top=Side(style="thin", color="CCCCCC"),
    bottom=Side(style="thin", color="CCCCCC"),
)

# Mantis 追蹤工作表分類色彩（背景色, 字體色）
_MANTIS_COLORS: dict[str, tuple[str, str]] = {
    "high":   ("FECACA", "7F1D1D"),
    "salary": ("FEF3C7", "78350F"),
    "normal": ("FFFFFF", "111827"),
    "closed": ("F3F4F6", "6B7280"),
}


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
                if isinstance(value, HyperlinkCell):
                    cell = ws.cell(row=1, column=col, value=value.text)
                    escaped = value.target_sheet.replace("'", "''")
                    cell.hyperlink = Hyperlink(ref=cell.coordinate, location=f"'{escaped}'!A1")
                    cell.font = Font(name="微軟正黑體", size=11, bold=True, color="0563C1", underline="single")
                else:
                    cell = ws.cell(row=1, column=col, value=value)
                    cell.font = FONT_HEADER
                    cell.fill = FILL_HEADER
                cell.alignment = Alignment(horizontal="center")
                cell.border = BORDER_THIN

            # Data rows
            for row_idx, row in enumerate(rows[1:], 2):
                for col, value in enumerate(row, 1):
                    if isinstance(value, HyperlinkCell):
                        cell = ws.cell(row=row_idx, column=col, value=value.text)
                        escaped = value.target_sheet.replace("'", "''")
                        cell.hyperlink = Hyperlink(
                            ref=cell.coordinate,
                            location=f"'{escaped}'!A1",
                        )
                        cell.font = Font(name="微軟正黑體", size=10, color="0563C1", underline="single")
                    else:
                        cell = ws.cell(row=row_idx, column=col, value=value)
                    cell.border = BORDER_THIN
                    if row_idx % 2 == 0 and not isinstance(value, HyperlinkCell):
                        cell.fill = FILL_ALT_ROW

        # 自動調整欄寬（依內容最大長度，上限 50 字元）
        for ws in wb.worksheets:
            for col_cells in ws.columns:
                max_length = 0
                for cell in col_cells:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                adjusted = min(max_length + 2, 50)
                if adjusted > 0:
                    col_letter = col_cells[0].column_letter
                    ws.column_dimensions[col_letter].width = adjusted

        wb.save(str(path))

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
