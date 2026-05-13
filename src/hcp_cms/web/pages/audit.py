"""稽核 log 頁 — /audit (admin only)."""
from __future__ import annotations

import sqlite3

from nicegui import ui

from hcp_cms.data.models import Staff
from hcp_cms.data.repositories import StaffRepository, WebAuditLogRepository


def build_audit_page(conn: sqlite3.Connection, staff: Staff) -> None:
    if staff.role != "admin":
        ui.label("您無權限查看稽核紀錄").classes("text-red-500 text-2xl p-8")
        return

    audit_repo = WebAuditLogRepository(conn)
    staff_repo = StaffRepository(conn)
    rows = audit_repo.list_all(limit=200)
    staff_names = {s.staff_id: s.name for s in staff_repo.list_all()}

    with ui.row().classes("w-full items-center p-4"):
        ui.label("Web Portal 稽核紀錄").classes("text-2xl font-bold")
        ui.space()
        ui.link("回案件清單", "/cases").classes("text-blue-300")

    ui.label(f"最近 {len(rows)} 筆").classes("text-slate-500 p-2")

    columns = "200px 100px 180px 200px"
    with ui.grid(columns=columns).classes("w-full gap-1 p-4"):
        ui.label("時間").classes("font-bold")
        ui.label("操作人").classes("font-bold")
        ui.label("案件").classes("font-bold")
        ui.label("欄位").classes("font-bold")
        for r in rows:
            ui.label(r.occurred_at)
            ui.label(staff_names.get(r.staff_id, r.staff_id))
            ui.link(r.case_id, f"/cases/{r.case_id}")
            ui.label(r.field_name)
