"""稽核紀錄 — 雙寫 web_audit_log + case_logs（Mantis 推送）。"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from hcp_cms.data.models import CaseLog
from hcp_cms.data.repositories import CaseLogRepository, WebAuditLogRepository


class AuditLogger:
    """提供統一介面記錄 Web Portal 操作稽核。

    - log_field_change: 單寫 web_audit_log
    - log_mantis_push: 雙寫 web_audit_log + case_logs（含 ticket_id 詳細）
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._audit_repo = WebAuditLogRepository(conn)
        self._log_repo = CaseLogRepository(conn)

    def log_field_change(self, staff_id: str, case_id: str, field_name: str) -> None:
        """記錄欄位變更到 web_audit_log。"""
        self._audit_repo.insert(staff_id=staff_id, case_id=case_id, field_name=field_name)

    def log_mantis_push(
        self,
        staff_id: str,
        case_id: str,
        ticket_id: str,
        mode: str,
    ) -> None:
        """記錄 Mantis 推送 — 雙寫。

        1. web_audit_log: field_name='mantis_push'（追蹤誰何時推）
        2. case_logs: direction='Mantis 推送' + content 含 ticket_id + mode
        """
        self._audit_repo.insert(
            staff_id=staff_id,
            case_id=case_id,
            field_name="mantis_push",
        )

        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        log = CaseLog(
            log_id=self._log_repo.next_log_id(),
            case_id=case_id,
            direction="Mantis 推送",
            content=f"{staff_id} 於 {now} 推送為 {mode}: ticket #{ticket_id}",
            mantis_ref=ticket_id,
            logged_by=staff_id,
            logged_at=now,
        )
        self._log_repo.insert(log)
