"""Sent mail enrichment manager."""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from hcp_cms.services.mail.base import MailProvider


@dataclass
class EnrichedSentMail:
    """寄件信件，附加公司與案件對應資訊。"""

    date: str
    recipients: list[str]
    subject: str
    company_id: str | None
    company_name: str | None
    linked_case_id: str | None
    company_reply_count: int = 0


class SentMailManager:
    """抓取寄件備份並補充公司/案件 metadata。"""

    def __init__(self, conn: sqlite3.Connection, provider: MailProvider) -> None:
        self._conn = conn
        self._provider = provider

    def fetch_and_enrich(self, since: datetime, until: datetime) -> list[EnrichedSentMail]:
        """從 MailProvider 抓取寄件，過濾日期範圍，補充公司與案件資訊。"""
        raw_list = self._provider.fetch_sent_messages(since=since)
        results: list[EnrichedSentMail] = []
        for raw in raw_list:
            if raw.date and not _date_in_range(raw.date, since, until):
                continue
            company_id, company_name = self._resolve_company(raw.subject, raw.to_recipients)
            linked_case_id = self._find_linked_case(raw.subject)
            results.append(
                EnrichedSentMail(
                    date=raw.date or "",
                    recipients=raw.to_recipients,
                    subject=raw.subject,
                    company_id=company_id,
                    company_name=company_name,
                    linked_case_id=linked_case_id,
                )
            )

        counts: Counter[str] = Counter(m.company_id for m in results if m.company_id)
        for mail in results:
            if mail.company_id:
                mail.company_reply_count = counts[mail.company_id]
        return results

    def _resolve_company(self, subject: str, recipients: list[str]) -> tuple[str | None, str | None]:
        """回傳 (company_id, company_name)。先查 cs_cases，再查 email domain。"""
        row = self._conn.execute(
            "SELECT c.company_id, co.name FROM cs_cases c "
            "LEFT JOIN companies co ON c.company_id = co.company_id "
            "WHERE c.subject = ? AND c.company_id IS NOT NULL LIMIT 1",
            (subject,),
        ).fetchone()
        if row and row[0]:
            return row[0], row[1]

        if recipients:
            domain = _extract_domain(recipients[0])
            if domain:
                row = self._conn.execute(
                    "SELECT company_id, name FROM companies WHERE domain = ? LIMIT 1",
                    (domain,),
                ).fetchone()
                if row:
                    return row[0], row[1]

        return None, None

    def _find_linked_case(self, subject: str) -> str | None:
        """若 cs_cases 有相同主旨，回傳 case_id，否則回傳 None。"""
        row = self._conn.execute(
            "SELECT case_id FROM cs_cases WHERE subject = ? LIMIT 1",
            (subject,),
        ).fetchone()
        return row[0] if row else None


def _extract_domain(email: str) -> str | None:
    if "@" in email:
        return email.split("@", 1)[1].lower().strip()
    return None


def _date_in_range(date_str: str, since: datetime, until: datetime) -> bool:
    """回傳 True 若 date_str 落在 [since, until]（以日期比較，忽略時區）。"""
    match = re.search(r"\d{4}[-/]\d{2}[-/]\d{2}", str(date_str))
    if not match:
        return True  # 無法解析則保留
    parts = re.split(r"[-/]", match.group())
    try:
        msg_date = datetime(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return True
    return since <= msg_date <= until
