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
