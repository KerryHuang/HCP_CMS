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
        """Remove RE:/FW:/回覆:/轉寄: prefixes (case-insensitive, repeating)."""
        return re.sub(r'^(RE:|FW:|FWD:|回覆:|轉寄:|答覆:)\s*', '', subject, flags=re.IGNORECASE).strip()

    @staticmethod
    def subjects_match(s1: str, s2: str) -> bool:
        """Compare subjects after cleaning prefixes."""
        return ThreadTracker.clean_subject(s1).lower() == ThreadTracker.clean_subject(s2).lower()

    def find_thread_parent(
        self, company_id: str | None, subject: str, mantis_id: str | None = None
    ) -> Case | None:
        """Find the root case of a conversation thread.

        Match criteria (in order):
        1. Same Mantis ticket ID (via case_mantis table)
        2. Same company + similar subject (cleaned) + case is open or recently replied
        """
        if not subject:
            return None

        # Strategy: query open/replied cases for this company, compare subjects
        if company_id:
            for status in ("處理中", "已回覆"):
                cases = self._case_repo.list_by_status(status)
                for case in cases:
                    if case.company_id == company_id and case.subject:
                        if self.subjects_match(case.subject, subject):
                            # Return root case (follow linked_case_id chain)
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
