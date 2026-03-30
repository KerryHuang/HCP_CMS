"""CaseDetailManager — 案件詳情維護業務邏輯。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from hcp_cms.core.case_manager import CaseManager, _calc_elapsed_str
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
        reply_time: str | None = None,
    ) -> CaseLog:
        log_id = self._log_repo.next_log_id()
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        # HCP 回覆類型自動計算回應時長（使用者未指定時）
        if reply_time is None and direction in ("HCP 信件回覆", "HCP 線上回覆"):
            prior_logs = self._log_repo.list_by_case(case_id)
            customer_times = [
                lg.logged_at for lg in prior_logs
                if lg.direction == "客戶來信" and lg.logged_at
            ]
            if customer_times:
                start_time = max(customer_times)
            else:
                case_obj = self._case_repo.get_by_id(case_id)
                start_time = case_obj.sent_time if case_obj else None
            reply_time = _calc_elapsed_str(start_time, now)
        log = CaseLog(
            log_id=log_id,
            case_id=case_id,
            direction=direction,
            content=content,
            mantis_ref=mantis_ref,
            logged_by=logged_by,
            logged_at=now,
            reply_time=reply_time,
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

        synced_at = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

        ticket = MantisTicket(
            ticket_id=issue.id,
            summary=issue.summary,
            status=issue.status,
            priority=issue.priority,
            handler=issue.handler,
            severity=issue.severity,
            reporter=issue.reporter,
            created_time=issue.date_submitted,
            planned_fix=issue.target_version,
            actual_fix=issue.fixed_in_version,
            description=issue.description,
            last_updated=issue.last_updated,
            notes_json=json.dumps(
                [
                    {
                        "reporter": n.reporter,
                        "text": n.text,
                        "date_submitted": n.date_submitted,
                    }
                    for n in issue.notes_list
                ],
                ensure_ascii=False,
            ),
            notes_count=issue.notes_count,
            synced_at=synced_at,
        )
        self._mantis_repo.upsert(ticket)
        return self._mantis_repo.get_by_id(ticket_id)

    def get_mantis_ticket(self, ticket_id: str) -> MantisTicket | None:
        """依 ticket_id 取得本地快取的 Ticket 資料。"""
        return self._mantis_repo.get_by_id(ticket_id)

    # ------------------------------------------------------------------
    # 自訂欄位
    # ------------------------------------------------------------------

    def update_extra_field(self, case_id: str, col_key: str, value: str | None) -> None:
        """更新案件自訂欄位值，委託 CaseRepository。"""
        self._case_repo.update_extra_field(case_id, col_key, value)
