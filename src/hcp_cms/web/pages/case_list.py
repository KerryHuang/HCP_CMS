"""案件清單頁 — /cases。"""
from __future__ import annotations

import sqlite3

from nicegui import ui

from hcp_cms.data.models import Staff
from hcp_cms.data.repositories import CaseRepository
from hcp_cms.services.mantis.base import MantisClient
from hcp_cms.core.mantis_push import MantisPushManager
from hcp_cms.web.visibility import CaseVisibilityFilter

STATUS_COLORS = {
    "處理中": ("amber", "amber-100"),
    "已回覆": ("blue", "blue-100"),
    "已完成": ("green", "green-100"),
    "已結案": ("slate", "slate-300"),
}


def build_case_list_page(
    conn: sqlite3.Connection,
    staff: Staff,
    mantis_client: MantisClient | None = None,
    mantis_project_id: str = "",
    mantis_category: str = "General",
) -> None:
    visibility = CaseVisibilityFilter(conn)
    cases = visibility.visible_cases(staff)

    # 頂部 nav
    with ui.row().classes("w-full items-center p-4 bg-slate-900"):
        ui.label("我的案件").classes("text-2xl font-bold")
        ui.space()
        ui.label(f"身分：{staff.name}").classes("text-slate-300")
        ui.button("登出", on_click=lambda: ui.navigate.to("/logout")).props("flat")

    with ui.column().classes("p-4 w-full"):
        if not cases:
            ui.label("目前沒有指派給您的案件").classes("text-slate-500 italic")
            return

        selected_ids: set[str] = set()
        batch_button = ui.button("推到 Mantis（0 筆）").props("disable")

        def _on_select_change(case_id: str, is_selected: bool) -> None:
            if is_selected:
                selected_ids.add(case_id)
            else:
                selected_ids.discard(case_id)
            batch_button.text = f"推到 Mantis（{len(selected_ids)} 筆）"
            if selected_ids:
                batch_button.props(remove="disable")
            else:
                batch_button.props("disable")

        def _on_batch_push() -> None:
            if not selected_ids:
                return
            if mantis_client is None or not mantis_project_id:
                ui.notify("Mantis 未設定", type="warning")
                return
            case_repo = CaseRepository(conn)
            selected_cases = [case_repo.get_by_id(cid) for cid in selected_ids]
            selected_cases = [c for c in selected_cases if c]
            _show_batch_confirm_dialog(
                conn, selected_cases, staff,
                mantis_client, mantis_project_id, mantis_category,
            )

        batch_button.on_click(_on_batch_push)

        # 案件表格
        columns = "60px 180px 1fr 90px 80px 160px"
        with ui.grid(columns=columns).classes("w-full gap-1"):
            ui.label("選").classes("font-bold")
            ui.label("案件編號").classes("font-bold")
            ui.label("主旨").classes("font-bold")
            ui.label("狀態").classes("font-bold")
            ui.label("優先度").classes("font-bold")
            ui.label("更新時間").classes("font-bold")

            for c in cases:
                cb = ui.checkbox(value=False)
                cb.on_value_change(
                    lambda e, cid=c.case_id: _on_select_change(cid, e.value)
                )
                ui.link(c.case_id, f"/cases/{c.case_id}")
                ui.label(c.subject or "")
                _render_status_chip(c.status or "")
                ui.label(c.priority or "")
                ui.label(c.updated_at or "")


def _render_status_chip(status: str) -> None:
    color, bg = STATUS_COLORS.get(status, ("neutral", "neutral-100"))
    ui.label(status).classes(f"px-2 py-1 rounded text-{color}-700 bg-{bg}")


def _show_batch_confirm_dialog(
    conn, selected_cases, staff,
    mantis_client, mantis_project_id, mantis_category,
) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-[600px]"):
        ui.label(f"將推送以下 {len(selected_cases)} 筆案件為新 Mantis ticket：").classes("font-bold")
        ui.label("（已連結 ticket 的案件會自動略過）").classes("text-slate-500 text-sm")
        with ui.column().classes("max-h-80 overflow-auto w-full"):
            for c in selected_cases:
                ui.label(f"• {c.case_id}  {c.subject or ''}（客戶: {c.company_id or '—'}）")
        with ui.row():
            ui.button("取消", on_click=dialog.close).props("flat")

            def confirm():
                push_mgr = MantisPushManager(
                    conn, mantis_client,
                    project_id=mantis_project_id, category=mantis_category,
                )
                results = push_mgr.push_cases_batch(
                    [c.case_id for c in selected_cases], staff.staff_id,
                )
                ok = sum(1 for r in results if r[1] == "success")
                fail = sum(1 for r in results if r[1] == "failed")
                skip = sum(1 for r in results if r[1] == "skipped")
                ui.notify(
                    f"成功 {ok} 筆 / 失敗 {fail} 筆 / 略過 {skip} 筆",
                    type="positive" if fail == 0 else "warning",
                )
                dialog.close()
                ui.navigate.to("/cases")

            ui.button("確認推送", on_click=confirm).classes("bg-blue-600 text-white")
    dialog.open()
