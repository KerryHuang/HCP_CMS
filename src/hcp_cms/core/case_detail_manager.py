"""CaseDetailManager — 案件詳情維護業務邏輯。"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from hcp_cms.core.case_manager import CaseManager
from hcp_cms.data.models import Case, CaseLog, CaseMantisLink, MantisTicket
from hcp_cms.data.repositories import (
    CaseLogRepository,
    CaseMantisRepository,
    CaseRepository,
    MantisRepository,
)
from hcp_cms.services.mantis.base import MantisClient


class CaseDetailManager:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._case_repo = CaseRepository(conn)
        self._log_repo = CaseLogRepository(conn)
        self._case_mantis_repo = CaseMantisRepository(conn)
        self._mantis_repo = MantisRepository(conn)
        self._case_manager = CaseManager(conn)

    # ------------------------------------------------------------------
    # 案件
    # ------------------------------------------------------------------

    def get_case(self, case_id: str) -> Case | None:
        return self._case_repo.get_by_id(case_id)

    def update_case(self, case: Case) -> None:
        self._case_repo.update(case)

    def mark_replied(self, case_id: str) -> None:
        self._case_manager.mark_replied(case_id)

    def close_case(self, case_id: str) -> None:
        self._case_manager.close_case(case_id)

    # ------------------------------------------------------------------
    # 補充記錄
    # ------------------------------------------------------------------

    def add_log(
        self,
        case_id: str,
        direction: str,
        content: str,
        mantis_ref: str | None = None,
        logged_by: str | None = None,
    ) -> CaseLog:
        log_id = self._log_repo.next_log_id()
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        log = CaseLog(
            log_id=log_id,
            case_id=case_id,
            direction=direction,
            content=content,
            mantis_ref=mantis_ref,
            logged_by=logged_by,
            logged_at=now,
        )
        self._log_repo.insert(log)
        return log

    def list_logs(self, case_id: str) -> list[CaseLog]:
        return self._log_repo.list_by_case(case_id)

    def delete_log(self, log_id: str) -> None:
        self._log_repo.delete(log_id)

    # ------------------------------------------------------------------
    # Mantis 關聯
    # ------------------------------------------------------------------

    def link_mantis(self, case_id: str, ticket_id: str) -> bool:
        """關聯 Mantis ticket。若 ticket 不在本地則回傳 False。"""
        if self._mantis_repo.get_by_id(ticket_id) is None:
            return False
        self._case_mantis_repo.link(CaseMantisLink(case_id=case_id, ticket_id=ticket_id))
        return True

    def unlink_mantis(self, case_id: str, ticket_id: str) -> None:
        self._case_mantis_repo.unlink(case_id, ticket_id)

    def list_linked_tickets(self, case_id: str) -> list[MantisTicket]:
        ticket_ids = self._case_mantis_repo.get_tickets_for_case(case_id)
        result = []
        for tid in ticket_ids:
            ticket = self._mantis_repo.get_by_id(tid)
            if ticket is not None:
                result.append(ticket)
        return result

    def sync_mantis_ticket(
        self,
        ticket_id: str,
        client: MantisClient | None = None,
    ) -> MantisTicket | None:
        """呼叫 MantisClient 同步單一 ticket，更新本地快取。"""
        if client is None:
            return None
        issue = client.get_issue(ticket_id)
        if issue is None:
            return None
        ticket = MantisTicket(
            ticket_id=issue.id,
            summary=issue.summary,
            status=issue.status,
            priority=issue.priority,
            handler=issue.handler,
            notes=issue.notes,
        )
        self._mantis_repo.upsert(ticket)
        return self._mantis_repo.get_by_id(ticket_id)
