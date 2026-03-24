"""High-level case management — create, update, status transitions."""

import sqlite3
from datetime import datetime
from email.utils import parseaddr
from pathlib import Path

from hcp_cms.core.classifier import OUR_DOMAIN, Classifier
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

    def import_email(
        self,
        subject: str,
        body: str,
        sender_email: str = "",
        to_recipients: list[str] | None = None,
        sent_time: str | None = None,
        source_filename: str | None = None,
    ) -> tuple[Case | None, str]:
        """智慧匯入：自動判斷客戶來信或我方回覆。

        Returns:
            (case, action) — action 為 'created' / 'replied' / 'skipped'
        """
        recipients = to_recipients or []

        # 判斷是否為我方寄件
        _, addr = parseaddr(sender_email)
        if not addr:
            addr = sender_email
        sender_domain = addr.split("@")[1].lower() if "@" in addr else ""
        is_our_side = sender_domain == OUR_DOMAIN or sender_domain.endswith(f".{OUR_DOMAIN}")

        if is_our_side:
            # 我方回覆：呼叫 Classifier 公開方法取得客戶公司，再比對父案件
            company_id, _ = self._classifier.resolve_external_company(recipients)
            parent = self._tracker.find_thread_parent(company_id, subject)
            if not parent:
                return None, "skipped"
            self.mark_replied(parent.case_id, sent_time)
            updated = self._case_repo.get_by_id(parent.case_id)
            return updated, "replied"

        # 客戶來信：走正常建案流程（帶 to_recipients 給 Classifier）
        case = self.create_case(
            subject=subject,
            body=body,
            sender_email=sender_email,
            to_recipients=recipients,
            sent_time=sent_time,
            source_filename=source_filename,
        )
        return case, "created"

    def create_case(
        self,
        subject: str,
        body: str,
        sender_email: str = "",
        to_recipients: list[str] | None = None,
        sent_time: str | None = None,
        contact_person: str | None = None,
        handler: str | None = None,
        source_filename: str | None = None,
    ) -> Case:
        """Create a new case from email data, with auto-classification and thread detection."""
        # Classify
        classification = self._classifier.classify(subject, body, sender_email, to_recipients or [])

        # 解析檔名標記（ISSUE#/RD handler/進度）優先於 email 主旨標記
        # 舊系統會將 ISSUE 前綴和 (RD_XXX)(進度) 加在 .msg 檔名中
        if source_filename:
            stem = Path(source_filename).stem
            fn_tags = self._classifier._parse_subject_tags(stem)
            if fn_tags.get("issue_number") and not classification.get("issue_number"):
                classification["issue_number"] = fn_tags["issue_number"]
            if fn_tags.get("handler") and not classification.get("handler"):
                classification["handler"] = fn_tags["handler"]
            if fn_tags.get("progress") and not classification.get("progress"):
                classification["progress"] = fn_tags["progress"]

        # Generate case ID
        case_id = self._case_repo.next_case_id()

        now = datetime.now().strftime("%Y/%m/%d %H:%M")

        issue_number = classification.get("issue_number")
        notes = f"ISSUE#{issue_number}" if issue_number else None

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
            handler=handler or classification.get("handler"),
            progress=classification.get("progress"),
            notes=notes,
            source="email",
        )

        # Thread detection（先偵測，設定 linked_case_id，再 insert）
        parent = self._tracker.find_thread_parent(
            classification["company_id"], subject
        )
        if parent:
            case.linked_case_id = parent.case_id

        self._case_repo.insert(case)
        self._fts.index_case(case_id, subject, None, None)

        # link_to_parent 需要子案件已在 DB 中才能更新，故在 insert 後執行
        if parent:
            self._tracker.link_to_parent(case_id, parent.case_id)
            # Reopen parent if it was replied
            if parent.status == "已回覆":
                self.reopen_case(parent.case_id, f"後續來信: {subject}")

        return case

    def mark_replied(self, case_id: str, reply_time: str | None = None) -> None:
        """Mark case as replied.

        每次 CS 完成回覆，reply_count +1（參考舊版 _link_and_update_case 邏輯）。
        """
        case = self._case_repo.get_by_id(case_id)
        if case:
            case.status = "已回覆"
            case.replied = "是"
            case.actual_reply = reply_time or datetime.now().strftime("%Y/%m/%d %H:%M")
            case.reply_count += 1
            self._case_repo.update(case)

    def reopen_case(self, case_id: str, reason: str = "") -> None:
        """Reopen a replied case back to processing.

        重開案件本身不額外增加 reply_count（舊版 _reopen_existing_case 不修改此欄位）。
        reply_count 的遞增由 link_to_parent()（新來信關聯）及 mark_replied()（CS回覆）負責。
        """
        case = self._case_repo.get_by_id(case_id)
        if case:
            case.status = "處理中"
            # 注意：不在此處 +1，避免與 link_to_parent 雙重計算
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
