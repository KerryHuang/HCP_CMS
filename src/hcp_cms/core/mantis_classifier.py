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
    CLOSED_STATUSES: tuple[str, ...] = ("resolved", "closed", "已解決", "已關閉", "已結案")

    # 預計算小寫集合，避免每次 classify() 呼叫重新建立
    _CLOSED_LOWER: frozenset[str] = frozenset(
        s.lower() for s in ("resolved", "closed", "已解決", "已關閉", "已結案")
    )
    _HIGH_LOWER: frozenset[str] = frozenset(p.lower() for p in ("high", "urgent", "immediate"))
    _SALARY_LOWER: tuple[str, ...] = tuple(
        kw.lower() for kw in ("薪資", "薪水", "payroll", "工資", "salary")
    )

    def classify(self, ticket: MantisTicket) -> str:
        """回傳 'closed' | 'salary' | 'high' | 'normal'。"""
        status = (ticket.status or "").lower()
        if status in self._CLOSED_LOWER:
            return "closed"
        summary_lower = (ticket.summary or "").lower()
        if any(kw in summary_lower for kw in self._SALARY_LOWER):
            return "salary"
        priority = (ticket.priority or "").lower()
        if priority in self._HIGH_LOWER:
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
