"""CSReportEngine — 客服問題彙整報表產生器。

- 抓取全部 cs_cases
- 對映 10 欄：A 日期 / B 客戶 / C 問題原文 / D A|B|C / E 模組 /
  F TYPE(NEW|BUG|OP|OTH) / G 摘要 / H 建議回覆 / I Y|N 處理 / J 備註
- 優先使用手動欄位（problem / cause / solution / problem_level）；
  無則退回自動推論（error_type → classifier）或既有欄位（subject / actual_reply）
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from hcp_cms.core.problem_level_classifier import ProblemLevelClassifier
from hcp_cms.data.repositories import CaseRepository, CompanyRepository

HEADER: list[str] = [
    "日期",
    "客戶名稱",
    "問題原文",
    "問題類型",
    "問題所屬模組",
    "TYPE",
    "問題摘要",
    "建議回覆",
    "是否已處理",
    "備註",
]

_TYPE_MAP: dict[str, str] = {
    "BUG": "BUG",
    "BugFix": "BUG",
    "客制需求": "OP",
    "Enhancement": "OP",
    "一般問題": "NEW",
    "其他": "OTH",
}


@dataclass
class ReportRow:
    case_id: str
    date: str
    customer: str
    problem_raw: str
    problem_level: str
    module: str
    type_: str
    summary: str
    suggested_reply: str
    processed: str
    notes: str

    def as_list(self) -> list[str]:
        return [
            self.date,
            self.customer,
            self.problem_raw,
            self.problem_level,
            self.module,
            self.type_,
            self.summary,
            self.suggested_reply,
            self.processed,
            self.notes,
        ]


class CSReportEngine:
    """組成客服問題彙整報表 10 欄 row。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._cases = CaseRepository(conn)
        self._companies = CompanyRepository(conn)
        self._levels = ProblemLevelClassifier()

    def build_rows(self) -> list[ReportRow]:
        rows: list[ReportRow] = []
        for case in self._cases.list_all():
            company = self._companies.get_by_id(case.company_id) if case.company_id else None
            customer_name = company.name if company else (case.company_id or "")

            date = (case.sent_time or "").split(" ")[0]
            problem_raw = case.problem or case.subject or ""
            level = case.problem_level or self._levels.classify(case.error_type)
            module = case.error_type or ""
            type_ = _TYPE_MAP.get((case.issue_type or "").strip(), "NEW")
            summary = self._summarize(case.problem or case.subject or "")
            suggested_reply = case.solution or case.actual_reply or ""
            processed = "Y" if case.status == "已完成" else "N"
            notes = case.cause or case.notes or ""

            rows.append(
                ReportRow(
                    case_id=case.case_id,
                    date=date,
                    customer=customer_name,
                    problem_raw=problem_raw,
                    problem_level=level,
                    module=module,
                    type_=type_,
                    summary=summary,
                    suggested_reply=suggested_reply,
                    processed=processed,
                    notes=notes,
                )
            )
        return rows

    def to_sheet_values(self) -> list[list[str]]:
        """回傳可直接寫入 Google Sheet 的二維陣列（含 header）。"""
        values: list[list[str]] = [list(HEADER)]
        for row in self.build_rows():
            values.append(row.as_list())
        return values

    @staticmethod
    def _summarize(text: str, limit: int = 40) -> str:
        s = (text or "").strip().replace("\n", " ")
        if len(s) <= limit:
            return s
        return s[:limit] + "..."
