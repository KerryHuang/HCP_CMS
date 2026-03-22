"""Excel report generation — tracking table and monthly report."""

import sqlite3
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from hcp_cms.data.models import Case, QAKnowledge
from hcp_cms.data.repositories import (
    CaseRepository, QARepository, MantisRepository, CompanyRepository,
)


# Style constants
FONT_HEADER = Font(name="微軟正黑體", size=11, bold=True, color="FFFFFF")
FILL_HEADER = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
FILL_ALT_ROW = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
BORDER_THIN = Border(
    left=Side(style="thin", color="CCCCCC"),
    right=Side(style="thin", color="CCCCCC"),
    top=Side(style="thin", color="CCCCCC"),
    bottom=Side(style="thin", color="CCCCCC"),
)


class ReportEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._case_repo = CaseRepository(conn)
        self._qa_repo = QARepository(conn)
        self._mantis_repo = MantisRepository(conn)
        self._company_repo = CompanyRepository(conn)

    def generate_tracking_table(self, year: int, month: int, output_path: Path) -> Path:
        """Generate tracking table Excel with multiple sheets."""
        cases = self._case_repo.list_by_month(year, month)
        qas = self._qa_repo.list_all()
        companies = self._company_repo.list_all()

        wb = openpyxl.Workbook()

        # Sheet 1: 客戶索引
        ws = wb.active
        ws.title = "客戶索引"
        self._write_header(ws, ["#", "公司名稱", "Email域名", "案件數"])
        for i, comp in enumerate(companies, 1):
            count = sum(1 for c in cases if c.company_id == comp.company_id)
            row = [i, comp.name, comp.domain, count]
            ws.append(row)
            self._style_data_row(ws, i + 1)

        # Sheet 2: 問題追蹤總表
        ws2 = wb.create_sheet("問題追蹤總表")
        case_headers = [
            "案件編號", "狀態", "優先", "已回覆", "寄件時間", "公司",
            "聯絡人", "主旨", "系統產品", "問題類型", "錯誤類型",
            "處理進度", "回覆時間", "來回次數", "負責人",
        ]
        self._write_header(ws2, case_headers)
        for i, case in enumerate(cases, 1):
            company_name = self._get_company_name(case.company_id)
            ws2.append([
                case.case_id, case.status, case.priority, case.replied,
                case.sent_time, company_name, case.contact_person, case.subject,
                case.system_product, case.issue_type, case.error_type,
                case.progress, case.actual_reply, case.reply_count, case.handler,
            ])
            self._style_data_row(ws2, i + 1)

        # Sheet 3: QA知識庫
        ws3 = wb.create_sheet("QA知識庫")
        qa_headers = ["QA編號", "問題", "回覆", "解決方案", "產品", "問題類型", "錯誤類型", "來源", "建立日期"]
        self._write_header(ws3, qa_headers)
        for i, qa in enumerate(qas, 1):
            ws3.append([
                qa.qa_id, qa.question, qa.answer, qa.solution,
                qa.system_product, qa.issue_type, qa.error_type, qa.source, qa.created_at,
            ])
            self._style_data_row(ws3, i + 1)

        # Per-company sheets
        company_cases: dict[str, list[Case]] = {}
        for case in cases:
            cid = case.company_id or "unknown"
            company_cases.setdefault(cid, []).append(case)

        for comp in companies:
            comp_cases = company_cases.get(comp.company_id, [])
            if not comp_cases:
                continue
            sheet_name = comp.name[:28] + "_問題" if comp.name else comp.company_id
            ws_c = wb.create_sheet(sheet_name[:31])  # Excel limit 31 chars
            self._write_header(ws_c, case_headers)
            for i, case in enumerate(comp_cases, 1):
                ws_c.append([
                    case.case_id, case.status, case.priority, case.replied,
                    case.sent_time, comp.name, case.contact_person, case.subject,
                    case.system_product, case.issue_type, case.error_type,
                    case.progress, case.actual_reply, case.reply_count, case.handler,
                ])
                self._style_data_row(ws_c, i + 1)

        # Custom requirements sheet
        custom_cases = [c for c in cases if c.issue_type and "客制" in c.issue_type]
        if custom_cases:
            ws_custom = wb.create_sheet("客制需求")
            self._write_header(ws_custom, case_headers)
            for i, case in enumerate(custom_cases, 1):
                ws_custom.append([
                    case.case_id, case.status, case.priority, case.replied,
                    case.sent_time, self._get_company_name(case.company_id),
                    case.contact_person, case.subject,
                    case.system_product, case.issue_type, case.error_type,
                    case.progress, case.actual_reply, case.reply_count, case.handler,
                ])
                self._style_data_row(ws_custom, i + 1)

        wb.save(str(output_path))
        return output_path

    def generate_monthly_report(self, year: int, month: int, output_path: Path) -> Path:
        """Generate monthly report Excel with KPI summary."""
        cases = self._case_repo.list_by_month(year, month)

        wb = openpyxl.Workbook()

        # Sheet 1: 月報摘要
        ws = wb.active
        ws.title = "月報摘要"

        _CLOSED_STATUSES = {"已完成", "Closed", "已回覆"}
        total = len(cases)
        replied = sum(1 for c in cases if c.replied == "是")
        pending = sum(1 for c in cases if c.status not in _CLOSED_STATUSES)
        reply_rate = (replied / total * 100) if total > 0 else 0.0

        # KPI rows
        self._write_header(ws, ["指標", "數值", "說明"], row_num=1)
        ws.append(["案件總數", total, f"{year}/{month:02d} 所有案件"])
        ws.append(["已回覆", replied, "replied = 是"])
        ws.append(["待處理", pending, "狀態非已完成/Closed"])
        ws.append(["回覆率", f"{reply_rate:.1f}%", "已回覆 ÷ 總數 × 100%"])

        # Issue type stats
        ws.append([])
        ws.append(["問題類型統計"])
        issue_counts: dict[str, int] = {}
        for c in cases:
            it = c.issue_type or "OTH"
            issue_counts[it] = issue_counts.get(it, 0) + 1
        for it, count in sorted(issue_counts.items()):
            pct = count / total * 100 if total > 0 else 0
            ws.append([it, count, f"{pct:.1f}%"])

        # Sheet 2: 案件明細
        ws2 = wb.create_sheet("案件明細")
        headers = [
            "案件編號", "狀態", "優先", "已回覆", "寄件時間", "公司",
            "主旨", "問題類型", "錯誤類型", "回覆時間", "負責人",
        ]
        self._write_header(ws2, headers)
        for i, case in enumerate(cases, 1):
            ws2.append([
                case.case_id, case.status, case.priority, case.replied,
                case.sent_time, self._get_company_name(case.company_id),
                case.subject, case.issue_type, case.error_type,
                case.actual_reply, case.handler,
            ])
            self._style_data_row(ws2, i + 1)

        # Sheet 3: 未結案清單
        ws3 = wb.create_sheet("未結案清單")
        _CLOSED_STATUSES = {"已完成", "Closed", "已回覆"}
        open_cases = [c for c in cases if c.status not in _CLOSED_STATUSES]
        self._write_header(ws3, headers)
        for i, case in enumerate(open_cases, 1):
            ws3.append([
                case.case_id, case.status, case.priority, case.replied,
                case.sent_time, self._get_company_name(case.company_id),
                case.subject, case.issue_type, case.error_type,
                case.actual_reply, case.handler,
            ])
            self._style_data_row(ws3, i + 1)

        wb.save(str(output_path))
        return output_path

    def _get_company_name(self, company_id: str | None) -> str:
        if not company_id:
            return ""
        company = self._company_repo.get_by_id(company_id)
        return company.name if company else company_id

    def _write_header(self, ws, headers: list[str], row_num: int = 1) -> None:
        """Write styled header row."""
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=row_num, column=col, value=header)
            cell.font = FONT_HEADER
            cell.fill = FILL_HEADER
            cell.alignment = Alignment(horizontal="center")
            cell.border = BORDER_THIN

    def _style_data_row(self, ws, row_num: int) -> None:
        """Apply alternating row style and borders."""
        for col in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_num, column=col)
            cell.border = BORDER_THIN
            if row_num % 2 == 0:
                cell.fill = FILL_ALT_ROW
