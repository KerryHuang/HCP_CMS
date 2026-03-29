"""Excel report writer — writes structured data to styled .xlsx files."""

from __future__ import annotations

from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

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
