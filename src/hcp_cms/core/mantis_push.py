"""Mantis 手動推送管理器 — 案件 → Mantis ticket / bugnote 三模式。

⚠ Live POC（2026-05-13）確認：Mantis project 強制要 category，
   MVP 預設 category='General'（HCPSERVICE_測試 project 唯一可用 category）。

⚠ 技術債（TODO）：本模組在 Core 層卻依賴 hcp_cms.web.audit.AuditLogger，
   違反 6 層架構 Law 2。MVP 階段接受，後續應把 AuditLogger 也搬到 Core，
   或改為依賴注入（DI）由呼叫端傳入。
"""
from __future__ import annotations

import sqlite3

from hcp_cms.core.case_formatter import format_case_header
from hcp_cms.core.thread_tracker import ThreadTracker
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
        self._tracker = ThreadTracker(conn)

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

        # 格式化 summary（缺漏會拋 ValueError）
        try:
            summary = format_case_header(case)
        except ValueError as e:
            return False, f"案件格式不完整：{e}"

        ticket_id = self._client.create_issue(
            project_id=self._project_id,
            summary=summary,
            description=self._build_description(case),
            category=self._category,
            priority=_PRIORITY_MAP.get(case.priority or "中", "normal"),
            severity="minor",
            handler=case.handler if case.handler else None,
            custom_fields=(
                {"客戶提問人員": case.contact_person}
                if case.contact_person else None
            ),
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

    # ---- 模式 (d) thread-aware 批次推送 ----

    def push_cases_thread_aware(
        self,
        case_ids: list[str],
        operator_staff_id: str,
    ) -> list[dict]:
        """Thread-aware 批次推送：依 linked_case_id 串接關係分群。

        - 每串只建一張 Mantis ticket（以 thread root 為主）
        - 子案件以 bugnote 附加到 root 的 ticket，並建立 case_mantis 連結
        - 使用者若只選子案件，會自動把 root 一併推送
        - 若 root 已連結 Mantis ticket，沿用既有 ticket，不另建
        - 子案件已連結別張 ticket → 跳過

        Returns:
            list of {"case_id": str, "action": str, "payload": str} 其中
            action ∈ {"new_ticket", "bugnote", "already_linked", "skipped", "failed"}
        """
        if not case_ids:
            return []

        # Step 1: 依 thread root 分群
        thread_groups: dict[str, set[str]] = {}
        for cid in case_ids:
            case = self._case_repo.get_by_id(cid)
            if case is None:
                continue
            root = self._tracker._find_root(case)
            thread_groups.setdefault(root.case_id, set()).add(cid)

        # Step 2: 每串處理（root 推 ticket，子案件推 bugnote）
        results: list[dict] = []
        for root_case_id, members in thread_groups.items():
            root_links = self._link_repo.list_by_case_id(root_case_id)

            if root_links:
                # root 已連結 → 沿用既有 ticket
                ticket_id = root_links[0].ticket_id
                results.append({
                    "case_id": root_case_id, "action": "already_linked",
                    "payload": ticket_id,
                })
            else:
                # root 未連結 → 建新 ticket
                success, payload = self.push_case_as_new_ticket(
                    root_case_id, operator_staff_id
                )
                if not success:
                    results.append({
                        "case_id": root_case_id, "action": "failed", "payload": payload,
                    })
                    continue
                ticket_id = payload
                results.append({
                    "case_id": root_case_id, "action": "new_ticket", "payload": ticket_id,
                })

            # 子案件 → bugnote
            for cid in sorted(members):  # 排序確保可重現
                if cid == root_case_id:
                    continue
                existing = self._link_repo.list_by_case_id(cid)
                if existing:
                    results.append({
                        "case_id": cid, "action": "skipped",
                        "payload": f"已連結 ticket #{existing[0].ticket_id}",
                    })
                    continue
                success, note_payload = self._push_member_as_bugnote(
                    cid, ticket_id, operator_staff_id
                )
                results.append({
                    "case_id": cid,
                    "action": "bugnote" if success else "failed",
                    "payload": note_payload,
                })

        return results

    def _push_member_as_bugnote(
        self,
        member_case_id: str,
        ticket_id: str,
        operator_staff_id: str,
    ) -> tuple[bool, str]:
        """子案件以 bugnote 附加到指定 ticket，並建立 case_mantis 連結。"""
        case = self._case_repo.get_by_id(member_case_id)
        if case is None:
            return False, f"案件 {member_case_id} 不存在"

        text = self._build_bugnote_text(case)
        note_id = self._client.add_note(issue_id=ticket_id, text=text)
        if note_id is None:
            return False, getattr(self._client, "last_error", "未知 Mantis SOAP 錯誤")

        self._link_repo.insert(CaseMantisLink(
            case_id=member_case_id,
            ticket_id=ticket_id,
            summary=case.subject,
        ))
        self._auditor.log_mantis_push(
            staff_id=operator_staff_id,
            case_id=member_case_id,
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
        """description 用第一筆「客戶來信」case_log 內容，加 [HCP-CMS] header。

        若該案件無「客戶來信」case_log（如手動建案），fallback 為舊版結構化 description。
        list_by_case 排序為 logged_at ASC，第一筆 [0] 是最舊（原始來信）。
        """
        logs = self._log_repo.list_by_case(case.case_id)
        customer_logs = [log for log in logs if log.direction == "客戶來信"]

        if customer_logs:
            original = customer_logs[0]
            return f"[HCP-CMS: {case.case_id}]\n\n{original.content or ''}"

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
        """組裝 bugnote 文字：含 header、聯絡人、狀態、進度、完整對話記錄。

        對話記錄按 logged_at 順序顯示，每筆呈現 direction + 時間 + 內容。
        direction 隱含寄件方向（客戶來信 = 客戶→HCP；HCP 信件回覆 = HCP→客戶）。
        排除 'Mantis 推送' direction 以避免循環推送內容。
        """
        # 嘗試新格式 header，失敗 fallback 舊格式（bugnote 容忍度高，已有 ticket）
        try:
            header = format_case_header(case)
        except ValueError:
            header = f"[HCP-CMS: {case.case_id}] 更新"

        parts = [f"[HCP-CMS: {case.case_id}]\n{header}"]
        if case.contact_person:
            parts.append(f"【聯絡人】{case.contact_person}")
        if case.status:
            parts.append(f"【當前狀態】{case.status}")
        if case.progress:
            parts.append(f"【最新進度】\n{case.progress}")

        # 完整對話記錄（排除 Mantis 推送 避免循環）
        logs = self._log_repo.list_by_case(case.case_id)
        non_push_logs = [log for log in logs if log.direction != "Mantis 推送"]
        if non_push_logs:
            log_lines = ["─── 對話記錄 ───"]
            for log in non_push_logs:
                time_str = log.logged_at or ""
                direction = log.direction or ""
                content = log.content or ""
                log_lines.append(f"▼ {time_str} — {direction}\n{content}")
            parts.append("\n\n".join(log_lines))

        return "\n\n".join(parts)
