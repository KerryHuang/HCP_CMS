"""High-level case management — create, update, status transitions."""

import sqlite3
from datetime import datetime

from hcp_cms.core.classifier import Classifier
from hcp_cms.core.thread_tracker import ThreadTracker
from hcp_cms.data.fts import FTSManager
from hcp_cms.data.models import Case
from hcp_cms.data.repositories import CaseRepository


class CaseManager:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._case_repo = CaseRepository(conn)
        self._fts = FTSManager(conn)
        self._classifier = Classifier(conn)
        self._tracker = ThreadTracker(conn)

    def create_case(
        self,
        subject: str,
        body: str,
        sender_email: str = "",
        sent_time: str | None = None,
        contact_person: str | None = None,
        handler: str | None = None,
    ) -> Case:
        """Create a new case from email data, with auto-classification and thread detection."""
        # Classify
        classification = self._classifier.classify(subject, body, sender_email)

        # Generate case ID
        case_id = self._case_repo.next_case_id()

        now = datetime.now().strftime("%Y/%m/%d %H:%M")

        case = Case(
            case_id=case_id,
            subject=subject,
            sent_time=sent_time or now,
            company_id=classification["company_id"],
            contact_person=contact_person,
            system_product=classification["system_product"],
            issue_type=classification["issue_type"],
            error_type=classification["error_type"],
            priority=classification["priority"],
            handler=handler,
            source="email",
        )

        # Thread detection
        parent = self._tracker.find_thread_parent(
            classification["company_id"], subject
        )
        if parent:
            self._tracker.link_to_parent(case_id, parent.case_id)
            case.linked_case_id = parent.case_id
            # Reopen parent if it was replied
            if parent.status == "已回覆":
                self.reopen_case(parent.case_id, f"後續來信: {subject}")

        self._case_repo.insert(case)
        self._fts.index_case(case_id, subject, None, None)

        return case

    def mark_replied(self, case_id: str, reply_time: str | None = None) -> None:
        """Mark case as replied."""
        case = self._case_repo.get_by_id(case_id)
        if case:
            case.status = "已回覆"
            case.replied = "是"
            case.actual_reply = reply_time or datetime.now().strftime("%Y/%m/%d %H:%M")
            self._case_repo.update(case)

    def reopen_case(self, case_id: str, reason: str = "") -> None:
        """Reopen a replied case back to processing."""
        case = self._case_repo.get_by_id(case_id)
        if case:
            case.status = "處理中"
            case.reply_count += 1
            if reason:
                existing = case.notes or ""
                case.notes = f"{existing}\n[重開] {reason}".strip()
            self._case_repo.update(case)

    def close_case(self, case_id: str) -> None:
        """Mark case as completed."""
        self._case_repo.update_status(case_id, "已完成")

    def get_dashboard_stats(self, year: int, month: int) -> dict:
        """Get KPI stats for a given month."""
        cases = self._case_repo.list_by_month(year, month)
        total = len(cases)
        replied = sum(1 for c in cases if c.replied == "是")
        pending = sum(1 for c in cases if c.status == "處理中")
        reply_rate = (replied / total * 100) if total > 0 else 0.0

        # FRT calculation
        frt_hours = []
        for c in cases:
            frt = self._calc_frt(c)
            if frt is not None and frt < 720:
                frt_hours.append(frt)

        avg_frt = sum(frt_hours) / len(frt_hours) if frt_hours else None

        return {
            "total": total,
            "replied": replied,
            "pending": pending,
            "reply_rate": round(reply_rate, 1),
            "avg_frt": round(avg_frt, 1) if avg_frt is not None else None,
        }

    @staticmethod
    def _calc_frt(case: Case) -> float | None:
        """Calculate First Response Time in hours."""
        if not case.sent_time or not case.actual_reply:
            return None
        try:
            fmt = "%Y/%m/%d %H:%M"
            sent = datetime.strptime(case.sent_time, fmt)
            reply = datetime.strptime(case.actual_reply, fmt)
            return (reply - sent).total_seconds() / 3600
        except ValueError:
            return None
