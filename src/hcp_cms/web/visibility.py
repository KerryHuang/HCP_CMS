"""案件可視性過濾 — B+A 聯集 + G-3 排除未指派。"""
from __future__ import annotations

import sqlite3

from hcp_cms.data.models import Case, Staff
from hcp_cms.data.repositories import CaseRepository


class CaseVisibilityFilter:
    """依登入客服身分過濾可視案件。

    規則 (B+A 聯集 + G-3 排除未指派)：
        (LOWER(handler) = LOWER(staff.name)
         OR company_id IN (companies where cs_staff_id = staff.staff_id))
        AND handler IS NOT NULL AND handler != ''

    ⚠ G-3：未指派案件（handler 為空）不顯示於 Web Portal，
       即使公司在客服管轄範圍內也不出現，由 Jill 在桌面 App 處理後再 Web 可見。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._case_repo = CaseRepository(conn)

    def visible_cases(self, staff: Staff) -> list[Case]:
        rows = self._conn.execute(
            """
            SELECT c.* FROM cs_cases c
            WHERE (
                LOWER(c.handler) = LOWER(?)
                OR c.company_id IN (
                    SELECT company_id FROM companies WHERE cs_staff_id = ?
                )
            )
            AND c.handler IS NOT NULL
            AND c.handler != ''
            ORDER BY c.updated_at DESC
            """,
            (staff.name, staff.staff_id),
        ).fetchall()
        return [self._case_repo._row_to_case(r) for r in rows]
