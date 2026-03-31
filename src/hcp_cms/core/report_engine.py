"""Excel report generation — tracking table and monthly report."""

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from hcp_cms.core.mantis_classifier import MantisClassifier
from hcp_cms.core.report_writer import ReportWriter
from hcp_cms.data.repositories import (
    CaseMantisRepository,
    CaseRepository,
    CompanyRepository,
    MantisRepository,
    QARepository,
)

# XML 1.0 不允許的控制字元（openpyxl IllegalCharacterError 的根源）
_ILLEGAL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean(v: Any) -> Any:
    """過濾 XML 1.0 非法控制字元，避免 openpyxl IllegalCharacterError。"""
    if isinstance(v, str):
        return _ILLEGAL_CHARS_RE.sub("", v)
    return v


def _clean_row(row: list[Any]) -> list[Any]:
    """對整列每個值套用 _clean()。"""
    return [_clean(v) for v in row]


def _reply_hours(sent: str | None, replied: str | None) -> str:
    """計算首次回覆時效（小時），無法計算時回傳空字串。"""
    if not sent or not replied:
        return ""
    fmt = "%Y/%m/%d %H:%M:%S"
    try:
        delta = datetime.strptime(replied, fmt) - datetime.strptime(sent, fmt)
        hours = delta.total_seconds() / 3600
        return f"{hours:.1f}"
    except ValueError:
        return ""


class ReportEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._case_repo = CaseRepository(conn)
        self._qa_repo = QARepository(conn)
        self._mantis_repo = MantisRepository(conn)
        self._company_repo = CompanyRepository(conn)
        self._case_mantis_repo = CaseMantisRepository(conn)
        from hcp_cms.core.custom_column_manager import CustomColumnManager
        self._custom_col_mgr = CustomColumnManager(conn)

    def generate_tracking_table(self, start_date: str, end_date: str, output_path: Path) -> Path:
        """Generate tracking table Excel with multiple sheets."""
        data = self.build_tracking_table(start_date, end_date)
        ReportWriter.write_excel(data, output_path)
        return output_path

    def build_tracking_table(self, start_date: str, end_date: str) -> dict[str, list[list]]:
        """組裝問題追蹤總表的所有工作表資料，回傳純資料結構（無 Excel 依賴）。

        Args:
            start_date: 起始日期，格式 YYYY/MM/DD
            end_date:   結束日期，格式 YYYY/MM/DD（含當天）

        Returns:
            dict，key 為工作表名稱，value 為 list of rows（第 0 列為表頭）。
        """
        cases = self._case_repo.list_by_date_range(start_date, end_date)
        qas = self._qa_repo.list_all()
        _all_companies = self._company_repo.list_all()
        # 過濾掉 domain == name 的無效記錄（信件顯示名稱誤存為公司）
        # 有效域名特徵：包含 "."、不含空格、不含中文
        import re as _re
        _valid_domain = _re.compile(r'^[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$')
        companies = [
            c for c in _all_companies
            if c.domain and _valid_domain.match(c.domain.strip())
        ]
        mantis_tickets = self._mantis_repo.list_all()

        # 建立公司 id → Company 快取
        company_map = {c.company_id: c for c in companies}

        # 預先計算各公司頁籤名稱
        company_cases: dict[str, list] = {}
        for case in cases:
            cid = case.company_id or "unknown"
            company_cases.setdefault(cid, []).append(case)

        # 工作表名稱不可含 \ / * ? : [ ]，一律替換為 -
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

        # ── Sheet 1: 客戶索引 ──────────────────────────────────────────
        index_rows: list[list] = [["#", "公司名稱", "Email 域名", "聯絡方式", "案件數", "快速連結"]]
        for i, comp in enumerate(companies, 1):
            count = sum(1 for c in cases if c.company_id == comp.company_id)
            if comp.company_id in company_sheet_names:
                link_text = f"→ {comp.name}問題記錄"
            else:
                link_text = ""
            index_rows.append(_clean_row([i, comp.name, comp.domain, comp.contact_info or "", count, link_text]))
        result["📋 客戶索引"] = index_rows

        # ── Sheet 2: 問題追蹤總表 ──────────────────────────────────────
        custom_cols = self._custom_col_mgr.list_columns()
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

        # ── Sheet 3: QA知識庫 ──────────────────────────────────────────
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

        # ── 個別公司頁籤 ───────────────────────────────────────────────
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
            # Row 0：返回客戶索引（純文字）
            # Row 1：表頭
            # Row 2+：資料
            comp_rows: list[list] = [
                ["↩ 返回客戶索引"],
                comp_case_headers,
            ]
            for case in comp_cases:
                closed_at = case.updated_at if case.status in ("已完成", "Closed") else ""
                comp_rows.append(_clean_row([
                    case.case_id, case.contact_method, case.status, case.priority,
                    case.sent_time, case.subject, case.system_product,
                    case.issue_type, case.error_type,
                    case.impact_period, case.progress, case.actual_reply,
                    closed_at, case.notes or "",
                ] + [_clean(case.extra_fields.get(col.col_key, "")) for col in custom_cols]))
            result[sheet_name] = comp_rows

        # ── Mantis提單追蹤 ─────────────────────────────────────────────
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

        # ── 客制需求 ───────────────────────────────────────────────────
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
                ] + [_clean(case.extra_fields.get(col.col_key, "")) for col in custom_cols]))
            result["客制需求"] = custom_rows

        return result

    def build_monthly_report(self, start_date: str, end_date: str) -> dict[str, list[list]]:
        """組裝月報的所有工作表資料，回傳純資料結構（無 Excel 依賴）。

        Args:
            start_date: 起始日期，格式 YYYY/MM/DD
            end_date:   結束日期，格式 YYYY/MM/DD（含當天）

        Returns:
            dict，key 為工作表名稱，value 為 list of rows。
            - "📊 月報摘要": row[0] 標題列、row[1] 表頭、row[2:5] KPI、
              row[6] 空行、row[7] 類型標題、row[8] 類型表頭、row[9+] 類型統計
            - "📋 案件明細": row[0] 表頭、row[1:] 案件資料
            - "🏢 客戶分析": row[0] 表頭、row[1:] 各公司統計
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

        # ── Sheet 1: 月報摘要 ──────────────────────────────────────────
        summary_rows: list[list] = [
            # row 0: 標題列
            [f"📊 客服報表摘要 — {start_date} ～ {end_date}", f"產生日期：{datetime.now().strftime('%Y/%m/%d %H:%M')}"],
            # row 1: 表頭
            ["指標", "數值", "說明"],
            # row 2-5: KPI
            ["案件總數", total, f"{start_date} ～ {end_date}"],
            ["已回覆", replied, "replied = 是"],
            ["待處理", pending, "狀態非已完成/Closed"],
            ["回覆率", f"{reply_rate:.1f}%", "已回覆 ÷ 總數 × 100%"],
            # row 6: 空行
            [],
            # row 7: 問題類型統計標題
            ["問題類型統計"],
            # row 8: 類型表頭
            ["問題類型", "件數", "佔比"],
        ]
        # row 9+: 問題類型明細
        issue_counts: dict[str, int] = {}
        for c in cases:
            it = c.issue_type or "其他"
            issue_counts[it] = issue_counts.get(it, 0) + 1
        for it, count in sorted(issue_counts.items(), key=lambda x: -x[1]):
            pct = count / total * 100 if total > 0 else 0
            summary_rows.append([it, count, f"{pct:.1f}%"])

        # ── Mantis 統計 ────────────────────────────────────────────────
        mantis_rows_all = self.build_mantis_sheet()
        if mantis_rows_all:
            mantis_counts: dict[str, int] = {"high": 0, "salary": 0, "normal": 0, "closed": 0}
            for mr in mantis_rows_all:
                mantis_counts[mr["category"]] = mantis_counts.get(mr["category"], 0) + 1
            summary_rows.append([])
            summary_rows.append(["📌 Mantis 追蹤統計"])
            summary_rows.append(["分類", "件數"])
            summary_rows.append(["高優先度 🔴", mantis_counts["high"]])
            summary_rows.append(["薪資相關 🟡", mantis_counts["salary"]])
            summary_rows.append(["一般處理中", mantis_counts["normal"]])
            summary_rows.append(["已結案", mantis_counts["closed"]])
            summary_rows.append(["合計", len(mantis_rows_all)])

        result["📊 月報摘要"] = summary_rows

        # ── Sheet 2: 案件明細 ──────────────────────────────────────────
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

        # ── Sheet 3: 客戶分析 ──────────────────────────────────────────
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

    def build_mantis_sheet(self) -> list[dict]:
        """組裝 Mantis 追蹤工作表資料列。

        Returns:
            list of dict，每列含：
            ticket_id, summary, status, priority,
            unresolved_days, last_updated, handler, category
            排序：high → salary → normal → closed
        """
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

    def generate_monthly_report(self, start_date: str, end_date: str, output_path: Path) -> Path:
        """Generate monthly report Excel with KPI summary and Mantis tracking sheet."""
        data = self.build_monthly_report(start_date, end_date)
        ReportWriter.write_excel(data, output_path)
        mantis_rows = self.build_mantis_sheet()
        ReportWriter.append_mantis_sheet(output_path, "📌 Mantis 追蹤", mantis_rows)
        return output_path
