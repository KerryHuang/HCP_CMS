"""Web Portal 認證管理 — 點名登入 + cookie 裝置綁定。"""
from __future__ import annotations

import sqlite3

from hcp_cms.data.models import Staff
from hcp_cms.data.repositories import StaffRepository

COOKIE_NAME = "cms_staff"
COOKIE_MAX_AGE_SECONDS = 365 * 24 * 60 * 60  # 1 年


class WebAuthManager:
    """提供 Web Portal 登入相關查詢，無密碼驗證（pick-from-list）。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._staff_repo = StaffRepository(conn)

    def list_cs_staff(self) -> list[Staff]:
        """列出 role='cs' 的 staff（登入頁顯示用）。"""
        return self._staff_repo.list_by_role("cs")

    def get_staff_by_id(self, staff_id: str) -> Staff | None:
        """依 staff_id 取 staff，僅回傳 role='cs' 者。

        非 cs role 不能透過此方法登入 Web Portal，admin / rd 等請走桌面 App。
        """
        s = self._staff_repo.get_by_id(staff_id)
        if s is None or s.role != "cs":
            return None
        return s
