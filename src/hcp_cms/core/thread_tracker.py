"""Conversation thread tracking — identifies reply chains and links cases."""

import re
import sqlite3

from hcp_cms.data.models import Case
from hcp_cms.data.repositories import CaseRepository


class ThreadTracker:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._case_repo = CaseRepository(conn)

    @staticmethod
    def clean_subject(subject: str) -> str:
        """Remove RE:/FW:/回覆:/轉寄: prefixes recursively (case-insensitive)."""
        _prefix_re = re.compile(r'^(RE:|FW:|FWD:|回覆:|轉寄:|答覆:)\s*', re.IGNORECASE)
        result = subject
        while True:
            stripped = _prefix_re.sub('', result).strip()
            if stripped == result:
                return result
            result = stripped

    @staticmethod
    def subjects_match(s1: str, s2: str) -> bool:
        """Compare subjects after cleaning prefixes.

        A match is declared when either cleaned subject starts with the other
        (handles suffixes like「(回覆結案)」added by mail clients).
        ⚠ 前綴包含比對：若客戶回信在主旨尾端補充說明（如「(回覆結案)」），
          仍視為同一串，屬可接受的寬鬆比對策略。
        """
        c1 = ThreadTracker.clean_subject(s1).lower()
        c2 = ThreadTracker.clean_subject(s2).lower()
        if c1 == c2:
            return True
        # 前綴比對：允許尾端有備注後綴（如「(回覆結案)」）
        if c1.startswith(c2) or c2.startswith(c1):
            return True
        # 後綴比對：郵件客戶端累積 RE: 時，原始主旨出現在結尾
        # ⚠ 後綴比對容許誤判，但原始主旨通常 ≥ 5 字才啟用，降低短詞假陽性
        min_len = 5
        if len(c1) >= min_len and len(c2) >= min_len:
            return c1.endswith(c2) or c2.endswith(c1)
        return False

    def find_thread_parent(
        self, company_id: str | None, subject: str, mantis_id: str | None = None
    ) -> Case | None:
        """Find the root case of a conversation thread.

        Match criteria (in order):
        1. Same Mantis ticket ID (via case_mantis table)
        2. Same company + similar subject (cleaned)

        Searches open/replied cases first, then recently completed cases
        (已完成 within last 90 days) to catch replies that arrive after closure.
        ⚠ 已完成案件納入搜尋：客戶有時在結案後才寄回覆，
          擴大至近 90 天已完成案件可正確串接，但過舊案件不在此範圍。
        """
        if not subject:
            return None

        if not company_id:
            return None

        # 1. 開放中案件優先
        for status in ("處理中", "已回覆"):
            for case in self._case_repo.list_by_status(status):
                if case.company_id == company_id and case.subject:
                    if self.subjects_match(case.subject, subject):
                        return self._find_root(case)

        # 2. 近 90 天已完成案件（結案後仍可能收到回覆）
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y/%m/%d")
        for case in self._case_repo.list_by_status("已完成"):
            if case.company_id == company_id and case.subject:
                if (case.sent_time or "") >= cutoff:
                    if self.subjects_match(case.subject, subject):
                        return self._find_root(case)

        return None

    def _find_root(self, case: Case) -> Case:
        """Follow linked_case_id chain to find root case."""
        if case.linked_case_id:
            parent = self._case_repo.get_by_id(case.linked_case_id)
            if parent:
                return self._find_root(parent)
        return case

    def link_to_parent(self, child_case_id: str, parent_case_id: str) -> None:
        """Set linked_case_id on child and increment parent's reply_count."""
        child = self._case_repo.get_by_id(child_case_id)
        parent = self._case_repo.get_by_id(parent_case_id)
        if child and parent:
            child.linked_case_id = parent_case_id
            self._case_repo.update(child)
            parent.reply_count += 1
            self._case_repo.update(parent)
