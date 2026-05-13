"""Mantis 手動推送管理器 — 案件 → Mantis ticket / bugnote 三模式。

⚠ Live POC（2026-05-13）確認：Mantis project 強制要 category，
   MVP 預設 category='General'（HCPSERVICE_測試 project 唯一可用 category）。
"""
from __future__ import annotations

import sqlite3

from hcp_cms.data.models import Case, CaseMantisLink, MantisTicket
from hcp_cms.data.repositories import (
    CaseLogRepository,
    CaseMantisRepository,
    CaseRepository,
    MantisRepository,
)
from hcp_cms.services.mantis.base import MantisClient
from hcp_cms.web.audit import AuditLogger

_PRIORITY_MAP = {"高": "high", "中": "normal", "低": "low"}
_DEFAULT_CATEGORY = "General"


class MantisPushManager:
    """編排「案件 → Mantis」三種模式：建新 ticket / 批次建 / 推 bugnote。"""

    def __init__(
        self,
        conn: sqlite3.Connection,
        client: MantisClient,
        project_id: str,
        category: str = _DEFAULT_CATEGORY,
    ) -> None:
        self._conn = conn
        self._client = client
        self._project_id = project_id
        self._category = category
        self._case_repo = CaseRepository(conn)
        self._link_repo = CaseMantisRepository(conn)
        self._log_repo = CaseLogRepository(conn)
        self._mantis_repo = MantisRepository(conn)
        self._auditor = AuditLogger(conn)

    # ---- 模式 (a) 單筆建新 ticket ----

    def push_case_as_new_ticket(
        self,
        case_id: str,
        operator_staff_id: str,
    ) -> tuple[bool, str]:
        """單筆推：建新 Mantis ticket。

        Returns:
            (True, ticket_id) on success
            (False, error_message) on failure / skip
        """
        case = self._case_repo.get_by_id(case_id)
        if case is None:
            return False, f"案件 {case_id} 不存在"

        existing_links = self._link_repo.list_by_case_id(case_id)
        if existing_links:
            return (
                False,
                f"案件已連結 Mantis ticket #{existing_links[0].ticket_id}，請改用 push_as_bugnote",
            )

        ticket_id = self._client.create_issue(
            project_id=self._project_id,
            summary=case.subject or f"HCP CMS 案件 {case_id}",
            description=self._build_description(case),
            category=self._category,
            priority=_PRIORITY_MAP.get(case.priority or "中", "normal"),
            severity="minor",
            handler=case.handler if case.handler else None,
        )
        if ticket_id is None:
            return False, getattr(self._client, "last_error", "未知 Mantis SOAP 錯誤")

        # 先 upsert mantis_tickets（case_mantis 有 FK 依賴此表）
        self._mantis_repo.upsert(
            MantisTicket(
                ticket_id=ticket_id,
                summary=case.subject or "",
                company_id=case.company_id,
                priority=case.priority,
                handler=case.handler,
            )
        )
        self._link_repo.insert(
            CaseMantisLink(
                case_id=case_id,
                ticket_id=ticket_id,
                summary=case.subject,
            )
        )
        self._auditor.log_mantis_push(
            staff_id=operator_staff_id,
            case_id=case_id,
            ticket_id=ticket_id,
            mode="new_ticket",
        )
        return True, ticket_id

    # ---- 模式 (c) 推為 bugnote ----

    def push_case_as_bugnote(
        self,
        case_id: str,
        operator_staff_id: str,
    ) -> tuple[bool, str]:
        """若案件已連結某 ticket，把最新內容推為 bugnote。"""
        case = self._case_repo.get_by_id(case_id)
        if case is None:
            return False, f"案件 {case_id} 不存在"

        links = self._link_repo.list_by_case_id(case_id)
        if not links:
            return False, "案件尚未連結 Mantis ticket，請改用建新 ticket"

        # MVP：若多筆連結，取第一筆
        ticket_id = links[0].ticket_id

        note_id = self._client.add_note(
            issue_id=ticket_id,
            text=self._build_bugnote_text(case),
        )
        if note_id is None:
            return False, getattr(self._client, "last_error", "未知 Mantis SOAP 錯誤")

        self._auditor.log_mantis_push(
            staff_id=operator_staff_id,
            case_id=case_id,
            ticket_id=ticket_id,
            mode="bugnote",
        )
        return True, note_id

    # ---- 模式 (b) 批次建新 ticket ----

    def push_cases_batch(
        self,
        case_ids: list[str],
        operator_staff_id: str,
    ) -> list[tuple[str, str, str]]:
        """批次推。每筆獨立。

        Returns:
            list of (case_id, status, payload) where:
              status in ('success', 'failed', 'skipped')
              payload = ticket_id on success, error on failed, reason on skipped
        """
        results: list[tuple[str, str, str]] = []
        for case_id in case_ids:
            if self._link_repo.list_by_case_id(case_id):
                results.append((case_id, "skipped", "案件已連結 Mantis ticket"))
                continue
            success, payload = self.push_case_as_new_ticket(case_id, operator_staff_id)
            status = "success" if success else "failed"
            results.append((case_id, status, payload))
        return results

    # ---- 內部組裝 ----

    def _build_description(self, case: Case) -> str:
        """組裝 Mantis description：[HCP-CMS] header + 主旨 + 本文 + 進度。"""
        parts = [f"[HCP-CMS: {case.case_id}]"]
        if case.subject:
            parts.append(f"【主旨】{case.subject}")
        if case.progress:
            parts.append(f"【處理進度】\n{case.progress}")
        if case.company_id:
            parts.append(f"【客戶】{case.company_id}")
        if case.contact_person:
            parts.append(f"【聯絡人】{case.contact_person}")
        return "\n\n".join(parts)

    def _build_bugnote_text(self, case: Case) -> str:
        """組裝 bugnote 文字：當前狀態 + 進度 + 最新 case_log。"""
        parts = [f"[HCP-CMS: {case.case_id}] 更新"]
        if case.status:
            parts.append(f"【當前狀態】{case.status}")
        if case.progress:
            parts.append(f"【最新進度】\n{case.progress}")

        # 抓最新一筆非 Mantis 推送 case_log
        logs = self._log_repo.list_by_case(case.case_id)
        non_push_logs = [l for l in logs if l.direction != "Mantis 推送"]
        if non_push_logs:
            latest = non_push_logs[0]
            parts.append(f"【最新記錄 ({latest.direction})】\n{latest.content or ''}")

        return "\n\n".join(parts)
