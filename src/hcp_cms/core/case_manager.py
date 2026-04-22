"""High-level case management — create, update, status transitions."""

import re
import sqlite3
from datetime import datetime
from pathlib import Path

from hcp_cms.core.classifier import Classifier
from hcp_cms.core.thread_tracker import ThreadTracker
from hcp_cms.data.fts import FTSManager
from hcp_cms.data.models import Case, CaseLog, CaseMantisLink, MantisTicket
from hcp_cms.data.repositories import (
    CaseLogRepository,
    CaseMantisRepository,
    CaseRepository,
    MantisRepository,
)

_SLASH_FMT = re.compile(r"^\d{4}/\d{2}/\d{2}")
_FMT_LONG = "%Y/%m/%d %H:%M:%S"
_FMT_SHORT = "%Y/%m/%d %H:%M"


def _parse_dt(s: str) -> datetime:
    try:
        return datetime.strptime(s[:19], _FMT_LONG)
    except ValueError:
        return datetime.strptime(s[:16], _FMT_SHORT)


def _calc_elapsed_str(start: str | None, end: str | None) -> str | None:
    """計算兩個時間點之間的差距，回傳如 '2時30分' 的字串。差距不足 1 分鐘時回傳 None。"""
    if not start or not end:
        return None
    try:
        total_minutes = max(0, int((_parse_dt(end) - _parse_dt(start)).total_seconds() / 60))
        hours, minutes = divmod(total_minutes, 60)
        days, hours = divmod(hours, 24)
        if days:
            return f"{days}天{hours}時" if hours else f"{days}天"
        if hours:
            return f"{hours}時{minutes}分" if minutes else f"{hours}時"
        return f"{minutes}分" if minutes else None
    except Exception:
        return None


def _normalize_sent_time(value: str | None) -> str | None:
    """將任意格式的日期時間字串正規化為 YYYY/MM/DD HH:MM。

    支援：
    - 已正確格式 2026/03/17 09:34（直接回傳）
    - ISO 8601（含或不含時區）：2026-03-17 09:34:03+08:00 / 2026-03-17T14:22:05Z
    """
    if not value:
        return None
    s = str(value)
    if _SLASH_FMT.match(s):
        return s  # 已是正確格式
    try:
        dt = datetime.fromisoformat(s)
        return dt.strftime("%Y/%m/%d %H:%M")
    except ValueError:
        pass
    # 最後 fallback：取前 16 碼後強制替換分隔符
    return s[:16].replace("-", "/").replace("T", " ")


def _detect_direction(sender: str, subject: str) -> str:
    """判斷信件方向：以寄件者網域為唯一依據。

    ⚠ 主旨前綴（RE:/FW:）不列入判斷——客戶回信也帶 RE: 前綴，
    以前綴判斷會大量誤判客戶來信為 HCP 信件回覆。
    """
    sender_lower = sender.lower()
    if "@ares.com.tw" in sender_lower or "hcpservice" in sender_lower:
        return "HCP 信件回覆"
    return "客戶來信"


class CaseManager:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._case_repo = CaseRepository(conn)
        self._log_repo = CaseLogRepository(conn)
        self._fts = FTSManager(conn)
        self._classifier = Classifier(conn)
        self._tracker = ThreadTracker(conn)
        self._mantis_repo = MantisRepository(conn)
        self._case_mantis_repo = CaseMantisRepository(conn)

    def _ensure_mantis_link(self, case_id: str, ticket_id: str) -> bool:
        """確保案件與 Mantis 票單已建立關聯。

        若票單不在 mantis_tickets 中，先建立 stub 暫存（待同步後覆蓋）。
        若關聯已存在則不重複建立。

        Returns:
            True  — 本次建立了新關聯
            False — 關聯已存在或票號為空
        """
        if not ticket_id:
            return False
        # 確保 mantis_tickets 中有此票單（FK 約束要求）
        if self._mantis_repo.get_by_id(ticket_id) is None:
            stub = MantisTicket(ticket_id=ticket_id, summary=f"#{ticket_id}（待同步）")
            self._mantis_repo.upsert(stub)
        # 確保 case_mantis 中有此關聯
        existing_links = self._case_mantis_repo.list_by_case_id(case_id)
        if any(lk.ticket_id == ticket_id for lk in existing_links):
            return False
        self._case_mantis_repo.link(CaseMantisLink(case_id=case_id, ticket_id=ticket_id))
        return True

    def import_email(
        self,
        subject: str,
        body: str,
        sender_email: str = "",
        to_recipients: list[str] | None = None,
        sent_time: str | None = None,
        source_filename: str | None = None,
        progress_note: str | None = None,
        message_id: str | None = None,
    ) -> tuple[Case | None, str]:
        """匯入信件並建案（Find-or-Create）。

        若同公司、同主旨（去 RE:/FW: 前綴後相同）已有案件，
        則新增 CaseLog 並更新 reply_count，不另建案件（action='merged'）。
        否則走原有建案流程（action='created'）。

        Returns:
            (case, action) — action 為 'created' 或 'merged'
        """
        recipients = to_recipients or []

        # Find-or-Create：先以分類器取得 company_id
        classification = self._classifier.classify(subject, body, sender_email, recipients)
        company_id = classification.get("company_id")

        if company_id:
            clean = ThreadTracker.clean_subject(subject)
            existing = self._case_repo.find_by_company_and_subject(company_id, clean)
            if existing:
                direction = _detect_direction(sender_email, subject)
                _base = _normalize_sent_time(sent_time)
                if _base:
                    log_time = _base if len(_base) >= 19 else f"{_base}:00"
                else:
                    log_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                # 計算回應時長：找最近一筆客戶來信的時間點作為起點
                elapsed: str | None = None
                if direction == "HCP 信件回覆":
                    prior_logs = self._log_repo.list_by_case(existing.case_id)
                    customer_times = [
                        lg.logged_at for lg in prior_logs
                        if lg.direction == "客戶來信" and lg.logged_at
                    ]
                    start_time = max(customer_times) if customer_times else existing.sent_time
                    elapsed = _calc_elapsed_str(start_time, log_time)
                log = CaseLog(
                    log_id=self._log_repo.next_log_id(),
                    case_id=existing.case_id,
                    direction=direction,
                    content=body,
                    logged_at=log_time,
                    reply_time=elapsed,
                )
                self._log_repo.insert(log)
                existing.reply_count += 1
                if progress_note and progress_note.strip():
                    existing.progress = progress_note.strip()
                self._case_repo.update(existing)
                # 重新匯入時也補建 Mantis 關聯（若尚未連結）
                auto_ticket_id: str | None = None
                if source_filename:
                    stem = Path(source_filename).stem
                    fn_tags = self._classifier.parse_tags(stem)
                    auto_ticket_id = fn_tags.get("issue_number") or classification.get("mantis_ticket_id")
                if not auto_ticket_id:
                    auto_ticket_id = classification.get("mantis_ticket_id")
                if auto_ticket_id:
                    self._ensure_mantis_link(existing.case_id, auto_ticket_id)
                # 待發清單偵測（信件含確認+出貨關鍵字時自動記錄）
                try:
                    from hcp_cms.core.release_manager import ReleaseManager
                    month_str = datetime.now().strftime("%Y%m")
                    comp = None
                    if existing and existing.company_id:
                        from hcp_cms.data.repositories import CompanyRepository
                        comp = CompanyRepository(self._conn).get_by_id(existing.company_id)
                    mantis_id = classification.get("mantis_ticket_id") if isinstance(classification, dict) else None
                    ReleaseManager(self._conn).detect_and_record(
                        body=body,
                        case_id=existing.case_id if existing else None,
                        mantis_ticket_id=mantis_id,
                        client_name=comp.name if comp else None,
                        month_str=month_str,
                    )
                except Exception:
                    pass  # 偵測失敗不影響主流程
                return existing, "merged"

        # 沒有 existing → 原有建案流程（不變）
        case = self.create_case(
            subject=subject,
            body=body,
            sender_email=sender_email,
            to_recipients=recipients,
            sent_time=sent_time,
            source_filename=source_filename,
            progress_note=progress_note,
            message_id=message_id,
        )
        # 待發清單偵測（信件含確認+出貨關鍵字時自動記錄）
        try:
            from hcp_cms.core.release_manager import ReleaseManager
            month_str = datetime.now().strftime("%Y%m")
            comp = None
            if case and case.company_id:
                from hcp_cms.data.repositories import CompanyRepository
                comp = CompanyRepository(self._conn).get_by_id(case.company_id)
            mantis_id = classification.get("mantis_ticket_id") if isinstance(classification, dict) else None
            ReleaseManager(self._conn).detect_and_record(
                body=body,
                case_id=case.case_id if case else None,
                mantis_ticket_id=mantis_id,
                client_name=comp.name if comp else None,
                month_str=month_str,
            )
        except Exception:
            pass  # 偵測失敗不影響主流程
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
        progress_note: str | None = None,
        message_id: str | None = None,
    ) -> Case:
        """Create a new case from email data, with auto-classification and thread detection."""
        # Classify
        classification = self._classifier.classify(subject, body, sender_email, to_recipients or [])

        # 解析檔名標記（ISSUE#/RD handler/進度）優先於 email 主旨標記
        # 舊系統會將 ISSUE 前綴和 (RD_XXX)(進度) 加在 .msg 檔名中
        if source_filename:
            stem = Path(source_filename).stem
            fn_tags = self._classifier.parse_tags(stem)
            if fn_tags.get("issue_number") and not classification.get("issue_number"):
                classification["issue_number"] = fn_tags["issue_number"]
            # 若主旨未解析到 mantis_ticket_id，補用檔名的 issue_number
            if fn_tags.get("issue_number") and not classification.get("mantis_ticket_id"):
                classification["mantis_ticket_id"] = fn_tags["issue_number"]
            if fn_tags.get("handler") and not classification.get("handler"):
                classification["handler"] = fn_tags["handler"]
            if fn_tags.get("progress") and not classification.get("progress"):
                classification["progress"] = fn_tags["progress"]

        # Generate case ID
        case_id = self._case_repo.next_case_id()

        now = datetime.now().strftime("%Y/%m/%d %H:%M")

        issue_number = classification.get("issue_number")
        notes = f"ISSUE#{issue_number}" if issue_number else None

        # body ==進度== 標記優先；若無則用主旨/檔名解析結果
        final_progress = progress_note.strip() if progress_note else classification.get("progress")

        case = Case(
            case_id=case_id,
            subject=subject,
            sent_time=_normalize_sent_time(sent_time) or now,
            company_id=classification["company_id"],
            contact_person=contact_person,
            system_product=classification["system_product"],
            issue_type=classification["issue_type"],
            error_type=classification["error_type"],
            priority=classification["priority"],
            handler=handler or classification.get("handler"),
            progress=final_progress,
            notes=notes,
            source="email",
            message_id=message_id,
            reply_count=1,  # 第一封信本身算一次往返
        )

        # Thread detection（先偵測，設定 linked_case_id，再 insert）
        parent = self._tracker.find_thread_parent(
            classification["company_id"], subject
        )
        if parent:
            case.linked_case_id = parent.case_id

        self._case_repo.insert(case)
        self._fts.index_case(case_id, subject, None, None)

        # 建立初始對話記錄（信件本文）
        log_time = _normalize_sent_time(sent_time) or now
        if len(log_time) == 16:  # "YYYY/MM/DD HH:MM" → 補秒
            log_time = f"{log_time}:00"
        direction = _detect_direction(sender_email, subject)
        init_log = CaseLog(
            log_id=self._log_repo.next_log_id(),
            case_id=case_id,
            direction=direction,
            content=body,
            logged_at=log_time,
        )
        self._log_repo.insert(init_log)

        # 自動建立 Mantis 關聯（若檔名/主旨解析到 ticket ID）
        auto_ticket_id = classification.get("mantis_ticket_id")
        if auto_ticket_id:
            self._ensure_mantis_link(case_id, auto_ticket_id)

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
            case.actual_reply = reply_time or datetime.now().strftime("%Y/%m/%d %H:%M")
            case.reply_count += 1
            self._case_repo.update(case)

    def batch_assign_company_and_merge(
        self, case_ids: list[str], company_id: str
    ) -> dict[str, int]:
        """批次設定 company_id 並整併同公司同主旨的案件。

        1. 更新指定案件的 company_id。
        2. 以 clean_subject 分組，每組取最早案件為根，其餘設 linked_case_id。

        Returns:
            {"updated": 成功更新 company_id 筆數, "merged": 設定 linked_case_id 筆數}
        """
        updated = self._case_repo.bulk_update_company_id(case_ids, company_id)

        # 按 clean_subject 分組
        groups: dict[str, tuple[str, list[Case]]] = {}
        for cid in case_ids:
            case = self._case_repo.get_by_id(cid)
            if not case:
                continue
            clean_subj = ThreadTracker.clean_subject(case.subject)
            group_key = clean_subj.lower()
            if group_key not in groups:
                groups[group_key] = (clean_subj, [])
            groups[group_key][1].append(case)

        merged = 0
        for group_key, (clean_subj, group_cases) in groups.items():
            if len(group_cases) < 2:
                continue
            # 找同公司同主旨全部案件（含非選取的舊案件）
            all_matching = self._case_repo.list_by_company_and_subject(company_id, clean_subj)
            if not all_matching:
                all_matching = sorted(group_cases, key=lambda c: (c.sent_time or "", c.case_id))

            root = all_matching[0]
            for case in all_matching[1:]:
                if case.linked_case_id:
                    continue  # 已連結，跳過
                self._tracker.link_to_parent(case.case_id, root.case_id)
                merged += 1

        return {"updated": updated, "merged": merged}

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

    def delete_case(self, case_id: str) -> None:
        """刪除單一案件（含 KMS 待審查條目）。"""
        self._case_repo.delete(case_id)

    def delete_all_cases(self) -> int:
        """刪除所有案件並清空 processed_files，回傳刪除筆數。用於重新收信前重置。"""
        return self._case_repo.delete_all()

    def delete_cases_by_date_range(self, start: str, end: str) -> int:
        """刪除指定日期範圍內的案件，回傳刪除筆數。start/end 格式 'YYYY/MM/DD'。"""
        return self._case_repo.delete_by_date_range(start, end)

    def get_dashboard_stats(self, year: int, month: int) -> dict:
        """Get KPI stats for a given month."""
        cases = self._case_repo.list_by_month(year, month)
        total = len(cases)
        replied = sum(1 for c in cases if c.status == "已回覆")
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

    def relink_threads(self) -> dict[str, int]:
        """重新掃描所有案件，依 company_id + subjects_match 建立 linked_case_id 關聯，
        並同步串中最新案件的狀態至整串所有案件。

        不刪除任何案件。
        回傳 {"linked": 新建關聯數, "status_synced": 狀態同步案件數}
        """
        cases = self._case_repo.list_all()

        # 按 company_id 分群
        by_company: dict[str, list[Case]] = {}
        for c in cases:
            if c.company_id:
                by_company.setdefault(c.company_id, []).append(c)

        linked = 0
        status_synced = 0
        closed_statuses = {"已完成", "Closed"}

        for company_cases in by_company.values():
            sorted_cases = sorted(company_cases, key=lambda c: (c.sent_time or "", c.case_id))

            # ── 步驟 1：建立 linked_case_id 關聯 ──
            for i, child in enumerate(sorted_cases):
                if child.linked_case_id:
                    continue
                for parent in sorted_cases[:i]:
                    if parent.subject and child.subject:
                        if ThreadTracker.subjects_match(parent.subject, child.subject):
                            root = self._tracker._find_root(parent)
                            if root.case_id != child.case_id:
                                self._tracker.link_to_parent(child.case_id, root.case_id)
                                linked += 1
                            break

            # ── 步驟 2：按主旨分群，同步最新案件狀態至整串 ──
            # 重新載入以取得最新 linked_case_id
            refreshed = {
                c.case_id: self._case_repo.get_by_id(c.case_id)
                for c in sorted_cases
            }
            refreshed_list = [v for v in refreshed.values() if v]

            thread_groups: dict[str, list[Case]] = {}
            for c in refreshed_list:
                # 找同群主旨的代表 key（以最早案件的 case_id 為 key）
                placed = False
                for key_case_id, group in thread_groups.items():
                    rep = group[0]
                    if rep.subject and c.subject and ThreadTracker.subjects_match(rep.subject, c.subject):
                        group.append(c)
                        placed = True
                        break
                if not placed:
                    thread_groups[c.case_id] = [c]

            for group in thread_groups.values():
                if len(group) < 2:
                    continue
                latest = max(group, key=lambda c: (c.sent_time or "", c.case_id))
                if latest.status not in closed_statuses:
                    continue
                for c in group:
                    if c.status not in closed_statuses:
                        c.status = "已完成"
                        self._case_repo.update(c)
                        status_synced += 1

        return {"linked": linked, "status_synced": status_synced}

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
