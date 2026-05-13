"""Login page — pick-from-list."""
from __future__ import annotations

from nicegui import app, ui

from hcp_cms.data.models import Staff
from hcp_cms.web.auth import WebAuthManager


def build_login_page(auth: WebAuthManager) -> None:
    with ui.column().classes("w-full h-screen items-center justify-center"):
        ui.label("HCP CMS 客服 Portal").classes("text-3xl font-bold mb-4")
        ui.label("請點選您的身分").classes("text-lg mb-8 text-slate-400")

        cs_staff = auth.list_cs_staff()
        if not cs_staff:
            ui.label("⚠ 系統中沒有 role='cs' 的客服，請先在桌面 App 新增").classes(
                "text-amber-500"
            )
            return

        with ui.column().classes("gap-2 w-64"):
            for staff in cs_staff:
                _build_staff_button(staff)


def _build_staff_button(staff: Staff) -> None:
    def on_click() -> None:
        app.storage.user["staff_id"] = staff.staff_id
        ui.navigate.to("/cases")

    ui.button(staff.name, on_click=on_click).classes("w-full")
