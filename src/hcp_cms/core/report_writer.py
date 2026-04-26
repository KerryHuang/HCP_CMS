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

    @staticmethod
    def append_stats_chart_sheet(path: Path, stats: dict, start: str, end: str) -> None:
        """將統計圖表（matplotlib PNG）嵌入 Excel 第一個工作表位置。"""
        import io

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.font_manager as fm
        import matplotlib.pyplot as plt
        from openpyxl.drawing.image import Image as XLImage

        _CJK = ["Microsoft JhengHei", "Microsoft YaHei", "SimHei", "PingFang TC"]
        _avail = {f.name for f in fm.fontManager.ttflist}
        _font = next((f for f in _CJK if f in _avail), None)
        if _font:
            plt.rcParams["font.family"] = _font
        plt.rcParams["axes.unicode_minus"] = False

        BG = "#FFFFFF"
        COLORS = ["#1E3A5F", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444", "#06b6d4"]

        cs_stats = stats["cs_stats"]
        issue_counts = stats["issue_type_counts"]
        monthly = stats["monthly_counts"]
        customer_counts = stats.get("customer_counts", {})
        reply_dist = stats.get("reply_dist", {})

        names = [s["name"] for s in cs_stats]
        totals = [s["total"] for s in cs_stats]
        actives = [s["active"] for s in cs_stats]
        dones = [s["done"] for s in cs_stats]
        companies_cnt = [s["companies"] for s in cs_stats]

        fig = plt.figure(figsize=(16, 18), facecolor=BG)
        fig.suptitle(f"客服統計儀表板  {start} ～ {end}", fontsize=14, fontweight="bold", y=0.99)

        def _style_xl(ax):
            ax.grid(axis="y", linestyle="--", alpha=0.4)

        ax1 = fig.add_subplot(3, 2, 1)
        x = range(len(names))
        w = 0.28
        ax1.bar([i - w for i in x], totals, width=w, label="總案件", color=COLORS[0])
        ax1.bar(list(x), actives, width=w, label="處理中", color=COLORS[2])
        ax1.bar([i + w for i in x], dones, width=w, label="已完成", color=COLORS[1])
        ax1.set_xticks(list(x))
        ax1.set_xticklabels(names)
        ax1.set_title("各客服案件數", fontsize=11)
        ax1.legend(fontsize=8)
        _style_xl(ax1)
        for i, v in enumerate(totals):
            ax1.text(i - w, v + 0.1, str(v), ha="center", fontsize=9)

        ax2 = fig.add_subplot(3, 2, 2)
        bars = ax2.bar(names, companies_cnt, color=COLORS[:len(names)])
        ax2.set_title("各客服負責客戶數", fontsize=11)
        _style_xl(ax2)
        for bar, v in zip(bars, companies_cnt):
            ax2.text(bar.get_x() + bar.get_width() / 2, v + 0.1, str(v), ha="center", fontsize=10)

        ax3 = fig.add_subplot(3, 2, 3)
        if issue_counts:
            sorted_issues = sorted(issue_counts.items(), key=lambda x: -x[1])
            top_n = sorted_issues[:6]
            other_sum = sum(v for _, v in sorted_issues[6:])
            if other_sum:
                top_n.append(("其他", other_sum))
            labels = [k for k, _ in top_n]
            sizes = [v for _, v in top_n]
            ax3.pie(sizes, labels=labels, autopct="%1.1f%%",
                    colors=COLORS[:len(labels)], startangle=140, textprops={"fontsize": 9})
        ax3.set_title("問題類型分佈", fontsize=11)

        ax4 = fig.add_subplot(3, 2, 4)
        if monthly:
            months = list(monthly.keys())
            counts = list(monthly.values())
            ax4.plot(months, counts, color=COLORS[0], marker="o", linewidth=2, markersize=6)
            ax4.fill_between(months, counts, alpha=0.1, color=COLORS[0])
            ax4.set_xticks(range(len(months)))
            ax4.set_xticklabels(months, rotation=45, ha="right", fontsize=8)
            for i, v in enumerate(counts):
                ax4.text(i, v + 0.2, str(v), ha="center", fontsize=8)
        ax4.set_title("月份案件量趨勢", fontsize=11)
        ax4.grid(linestyle="--", alpha=0.4)

        ax5 = fig.add_subplot(3, 2, 5)
        ax5.grid(axis="x", linestyle="--", alpha=0.4)
        if customer_counts:
            cnames = list(customer_counts.keys())
            ccounts = list(customer_counts.values())
            y_pos = range(len(cnames))
            ax5.barh(list(y_pos), ccounts, color=COLORS[0])
            ax5.set_yticks(list(y_pos))
            ax5.set_yticklabels(cnames, fontsize=8)
            for i, v in enumerate(ccounts):
                ax5.text(v + 0.1, i, str(v), va="center", fontsize=8)
        ax5.set_title("各客戶案件數 Top 15", fontsize=11)
        ax5.invert_yaxis()

        ax6 = fig.add_subplot(3, 2, 6)
        _style_xl(ax6)
        if reply_dist:
            r_labels = list(reply_dist.keys())
            r_vals = list(reply_dist.values())
            bars6 = ax6.bar(r_labels, r_vals, color=COLORS[3])
            for bar, v in zip(bars6, r_vals):
                ax6.text(bar.get_x() + bar.get_width() / 2, v + 0.1, str(v),
                         ha="center", fontsize=9)
        ax6.set_title("案件回覆次數分佈", fontsize=11)

        fig.tight_layout(rect=[0, 0, 1, 0.98])

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=130, facecolor=BG, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)

        wb = openpyxl.load_workbook(str(path))
        ws = wb.create_sheet("📊 統計圖表", 0)
        img = XLImage(buf)
        img.anchor = "A1"
        ws.add_image(img)
        wb.save(str(path))
