"""超時案件檢查 — 找處理中但 HCP 太久未回覆的案件。

用途：避免 HCP 端忘記追蹤的客戶案件。
規則：
- 只看 status = '處理中' 的案件
- 計時起點：最後一筆 direction in ('HCP 信件回覆', 'HCP 線上回覆') 的 case_log
- 計時方式：工作時數（週一至週五全天，週六/週日不計）
- 完全沒 HCP 回覆的案件不列入（屬「首次回應 SLA」範疇，另案處理）

⚠ 已知限制：只排除週末，不排除國定假日。若有需要可後續加 holiday calendar。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from hcp_cms.data.repositories import (
    CaseLogRepository,
    CaseRepository,
    CompanyRepository,
    StaffRepository,
)

_HCP_DIRECTIONS = ("HCP 信件回覆", "HCP 線上回覆")
_DT_FORMATS = ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M")


def business_hours_between(start: datetime, end: datetime) -> float:
    """計算兩個時間點之間的工作時數（週六/週日不計）。

    週一至週五的時間都算（不限工作時間 9-18），週六/週日完全跳過。

    Args:
        start: 起始時間
        end: 結束時間

    Returns:
        工作時數（float，可帶小數）；end <= start 時回傳 0.0
    """
    if start >= end:
        return 0.0

    total = 0.0
    current = start
    while current < end:
        # 該日的隔天 00:00
        next_day = (
            current.replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=1)
        )
        period_end = min(next_day, end)
        # weekday(): 0=Mon, ..., 4=Fri, 5=Sat, 6=Sun
        if current.weekday() < 5:
            total += (period_end - current).total_seconds() / 3600
        current = period_end
    return total


def _parse_dt(s: str) -> datetime | None:
    """寬鬆解析 YYYY/MM/DD HH:MM 或 YYYY/MM/DD HH:MM:SS。"""
    if not s:
        return None
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


_LOG_SUMMARY_MAX_LEN = 60


def _extract_log_metadata(logs, fallback_inbound: str | None) -> tuple[str | None, str | None]:
    """從 case_logs（依 logged_at ASC）取出兩個欄位給警示清單使用：

    - last_customer_inbound_at：最近一筆「客戶來信」log 時間；無則用 fallback_inbound
    - last_log_summary：最後一筆 log 的 "[方向] 內容前 60 字"；logs 為空則 None
    """
    customer_logs = [lg for lg in logs if lg.direction == "客戶來信"]
    last_customer_inbound_at = (
        customer_logs[-1].logged_at if customer_logs else fallback_inbound
    )

    if not logs:
        return last_customer_inbound_at, None

    last_log = logs[-1]
    content = (last_log.content or "").strip().replace("\n", " ").replace("\r", " ")
    if len(content) > _LOG_SUMMARY_MAX_LEN:
        content = content[:_LOG_SUMMARY_MAX_LEN] + "…"
    summary = f"[{last_log.direction}] {content}" if content else f"[{last_log.direction}]"
    return last_customer_inbound_at, summary


class StalenessChecker:
    """檢查處理中案件是否超過閾值未有 HCP 回覆。"""

    def __init__(
        self,
        conn: sqlite3.Connection,
        now: datetime | None = None,
    ) -> None:
        self._case_repo = CaseRepository(conn)
        self._log_repo = CaseLogRepository(conn)
        self._staff_repo = StaffRepository(conn)
        self._company_repo = CompanyRepository(conn)
        self._now = now or datetime.now()

    def find_stale_cases(self, threshold_hours: float = 48.0) -> list[dict]:
        """找出超時案件清單。

        Args:
            threshold_hours: 工作時數閾值（預設 48 小時）

        Returns:
            list of dict（含 case_id / subject / company_* / handler* / case_type=overdue
            / last_hcp_reply / hours_since_last_reply / last_customer_inbound_at / last_log_summary）
        """
        results: list[dict] = []
        cases = self._case_repo.list_by_status("處理中")

        # 建 handler 名稱 → email 對照（一次查 staff 表，避免每筆 case 重複查）
        all_staff = self._staff_repo.list_all() if hasattr(self._staff_repo, "list_all") else []
        name_to_email: dict[str, str] = {s.name: s.email for s in all_staff}

        # 建 company_id → name 對照（一次查 companies 表）
        all_companies = (
            self._company_repo.list_all() if hasattr(self._company_repo, "list_all") else []
        )
        company_id_to_name: dict[str, str] = {c.company_id: c.name for c in all_companies}

        for case in cases:
            # 一次取 logs，從同一份 list 找：最後 HCP 回覆、最後客戶來信、最後活動
            logs = self._log_repo.list_by_case(case.case_id)  # logged_at ASC
            hcp_logs = [lg for lg in logs if lg.direction in _HCP_DIRECTIONS]
            if not hcp_logs:
                continue  # 無 HCP 回覆 → 屬首次回應 SLA，跳過
            last_hcp = hcp_logs[-1]
            last_dt = _parse_dt(last_hcp.logged_at)
            if last_dt is None:
                continue

            hours = business_hours_between(last_dt, self._now)
            if hours <= threshold_hours:
                continue

            last_customer_inbound_at, last_log_summary = _extract_log_metadata(
                logs, fallback_inbound=case.sent_time,
            )

            handler_email = (
                name_to_email.get(case.handler) if case.handler else None
            )
            company_name = (
                company_id_to_name.get(case.company_id) if case.company_id else None
            )
            results.append({
                "case_id": case.case_id,
                "subject": case.subject,
                "company_id": case.company_id,
                "company_name": company_name,
                "handler": case.handler,
                "handler_email": handler_email,
                "last_hcp_reply": last_hcp.logged_at,
                "hours_since_last_reply": hours,
                "case_type": "overdue",
                "last_customer_inbound_at": last_customer_inbound_at,
                "last_log_summary": last_log_summary,
            })
        return results

    def find_never_replied_cases(self, threshold_hours: float = 0.0) -> list[dict]:
        """找出「處理中 + HCP 從未回覆 + 自客戶來信至今 > 閾值工時」的案件。

        與 find_stale_cases 互補（後者要求曾有 HCP 回覆）。
        計時起點為 case.sent_time；sent_time 為 None 的案件因無法計算工時故跳過。

        Args:
            threshold_hours: 工作時數閾值（預設 0 → 全列）

        Returns:
            list of dict（結構同 find_stale_cases，但 last_hcp_reply=None、
            case_type="no_reply"，hours_since_last_reply 代表「自 sent_time 至今工時」）
        """
        results: list[dict] = []
        cases = self._case_repo.list_never_replied_by_hcp()

        all_staff = self._staff_repo.list_all() if hasattr(self._staff_repo, "list_all") else []
        name_to_email: dict[str, str] = {s.name: s.email for s in all_staff}
        all_companies = (
            self._company_repo.list_all() if hasattr(self._company_repo, "list_all") else []
        )
        company_id_to_name: dict[str, str] = {c.company_id: c.name for c in all_companies}

        for case in cases:
            if not case.sent_time:
                continue
            sent_dt = _parse_dt(case.sent_time)
            if sent_dt is None:
                continue

            hours = business_hours_between(sent_dt, self._now)
            if hours <= threshold_hours:
                continue

            logs = self._log_repo.list_by_case(case.case_id)
            last_customer_inbound_at, last_log_summary = _extract_log_metadata(
                logs, fallback_inbound=case.sent_time,
            )

            handler_email = (
                name_to_email.get(case.handler) if case.handler else None
            )
            company_name = (
                company_id_to_name.get(case.company_id) if case.company_id else None
            )
            results.append({
                "case_id": case.case_id,
                "subject": case.subject,
                "company_id": case.company_id,
                "company_name": company_name,
                "handler": case.handler,
                "handler_email": handler_email,
                "last_hcp_reply": None,
                "hours_since_last_reply": hours,
                "case_type": "no_reply",
                "first_inbound_at": case.sent_time,
                "last_customer_inbound_at": last_customer_inbound_at,
                "last_log_summary": last_log_summary,
            })
        return results

    def _find_latest_hcp_reply(self, case_id: str):
        """取案件最後一筆 HCP direction 的 case_log。"""
        logs = self._log_repo.list_by_case(case_id)
        hcp_logs = [lg for lg in logs if lg.direction in _HCP_DIRECTIONS]
        if not hcp_logs:
            return None
        # list_by_case 為 logged_at ASC，取最後一筆即最新
        return hcp_logs[-1]
