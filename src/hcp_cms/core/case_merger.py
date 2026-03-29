"""CaseMerger — 整合重複案件（相同 company_id + clean_subject）。"""

from __future__ import annotations

import logging
import sqlite3

from hcp_cms.core.thread_tracker import ThreadTracker
from hcp_cms.data.models import Case
from hcp_cms.data.repositories import CaseLogRepository, CaseRepository

logger = logging.getLogger(__name__)


class CaseMerger:
    """整合同公司、同主旨（去 RE:/FW: 前綴後相同）的重複案件。

    職責一：find_duplicate_groups() — 找出重複群組
    職責二：merge_group() — 合併單一群組
    職責三：merge_all_duplicates() — 批次合併所有重複群組
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._case_repo = CaseRepository(conn)
        self._log_repo = CaseLogRepository(conn)

    def find_duplicate_groups(self) -> list[list[Case]]:
        """找出所有 (company_id, clean_subject) 相同的案件群組（每群組 ≥ 2 筆）。"""
        cases = self._case_repo.list_all()
        groups: dict[tuple[str, str], list[Case]] = {}
        for case in cases:
            if not case.company_id:
                continue
            key = (case.company_id, ThreadTracker.clean_subject(case.subject))
            groups.setdefault(key, []).append(case)
        return [g for g in groups.values() if len(g) >= 2]

    def merge_group(self, cases: list[Case]) -> Case:
        """保留 sent_time 最早的案件，其餘 CaseLog 移轉後刪除。回傳 primary 案件。

        排序準則：sent_time ASC，若相同則 case_id ASC（字典序）。
        """
        sorted_cases = sorted(cases, key=lambda c: (c.sent_time or "", c.case_id))
        primary = sorted_cases[0]
        secondary = sorted_cases[1:]

        for sec in secondary:
            self._log_repo.transfer_logs(sec.case_id, primary.case_id)
            primary.reply_count += sec.reply_count

        self._case_repo.update(primary)

        for sec in secondary:
            self._case_repo.delete(sec.case_id)

        return primary

    def merge_all_duplicates(self) -> int:
        """執行全部群組合併，回傳刪除的案件筆數。

        每個群組獨立執行；某群組失敗時記錄錯誤並繼續處理其餘群組。
        """
        groups = self.find_duplicate_groups()
        deleted = 0
        for group in groups:
            try:
                self.merge_group(group)
                deleted += len(group) - 1
            except Exception:
                logger.exception(
                    "合併案件群組失敗：%s",
                    [c.case_id for c in group],
                )
        return deleted
