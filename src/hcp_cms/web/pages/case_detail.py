"""案件詳情頁 — /cases/{case_id}。"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from nicegui import ui

from hcp_cms.data.models import Case, CaseLog, CaseMantisLink, Staff
from hcp_cms.data.repositories import (
    CaseLogRepository,
    CaseMantisRepository,
    CaseRepository,
    StaffRepository,
)
from hcp_cms.services.mantis.base import MantisClient
from hcp_cms.web.audit import AuditLogger
from hcp_cms.web.mantis_push import MantisPushManager
from hcp_cms.web.visibility import CaseVisibilityFilter

STATUS_OPTIONS = ["處理中", "已回覆", "已完成", "已結案"]
PRIORITY_OPTIONS = ["高", "中", "低"]
LOG_DIRECTION_OPTIONS = ["內部討論", "HCP 線上回覆", "HCP 信件回覆"]


def build_case_detail_page(
    conn: sqlite3.Connection,
    staff: Staff,
    case_id: str,
    mantis_client: MantisClient | None = None,
    mantis_project_id: str = "",
    mantis_category: str = "General",
) -> None:
    case_repo = CaseRepository(conn)
    log_repo = CaseLogRepository(conn)
    link_repo = CaseMantisRepository(conn)
    staff_repo = StaffRepository(conn)
    auditor = AuditLogger(conn)

    case = case_repo.get_by_id(case_id)
    if case is None:
        ui.label(f"案件 {case_id} 不存在").classes("text-red-500 text-2xl p-8")
        return

    # 可視性檢查
    visibility = CaseVisibilityFilter(conn)
    visible_ids = {c.case_id for c in visibility.visible_cases(staff)}
    if case_id not in visible_ids:
        ui.label("您無權限查看此案件").classes("text-red-500 text-2xl p-8")
        return

    # 已結案 banner
    if case.status == "已結案":
        with ui.row().classes("w-full p-4 bg-slate-700 text-slate-100"):
            ui.icon("lock")
            ui.label(
                "本案件已結案，客戶後續回信不會重新開啟，僅會新增記錄"
            ).classes("font-semibold")

    # 表頭
    with ui.row().classes("w-full items-center p-4"):
        ui.label(f"案件 {case_id}").classes("text-2xl font-bold")
        ui.space()
        ui.link("← 回清單", "/cases")

    # 主旨資訊
    ui.label(f"主旨：{case.subject or ''}").classes("text-lg p-2")
    ui.label(f"寄件時間：{case.sent_time or ''}").classes("text-slate-500 p-2")

    # 編輯區
    cs_staff_names = [s.name for s in staff_repo.list_by_role("cs")]

    with ui.column().classes("gap-4 p-4 w-full max-w-3xl"):
        status_sel = ui.select(
            STATUS_OPTIONS,
            value=case.status if case.status in STATUS_OPTIONS else "處理中",
            label="狀態",
        ).classes("w-full")

        progress_input = ui.textarea(
            label="處理進度",
            value=case.progress or "",
        ).classes("w-full")

        handler_sel = ui.select(
            cs_staff_names,
            value=case.handler if case.handler in cs_staff_names else None,
            label="處理人員",
            with_input=True,
        ).classes("w-full")

        priority_sel = ui.select(
            PRIORITY_OPTIONS,
            value=case.priority if case.priority in PRIORITY_OPTIONS else "中",
            label="優先度",
        ).classes("w-full")

        rd_assignee_input = ui.input(
            label="技術負責人",
            value=case.rd_assignee or "",
        ).classes("w-full")

        def save() -> None:
            new_status = status_sel.value
            # 已結案需 confirm
            if new_status == "已結案" and case.status != "已結案":
                _confirm_close_case(
                    case_repo, auditor, case_id, staff,
                    new_status, progress_input.value,
                    handler_sel.value, priority_sel.value, rd_assignee_input.value,
                )
                return
            _apply_save(
                case_repo, auditor, case_id, staff,
                new_status, progress_input.value,
                handler_sel.value, priority_sel.value, rd_assignee_input.value,
            )

        ui.button("儲存", on_click=save).classes("bg-blue-600 text-white px-6 py-2")

    # case_logs 列表
    ui.separator()
    ui.label("補充紀錄").classes("text-xl font-bold p-4")
    logs = log_repo.list_by_case(case_id)
    for log in logs:
        with ui.card().classes("w-full max-w-3xl m-2"):
            ui.label(f"[{log.direction}] {log.logged_at}").classes("text-sm text-slate-400")
            ui.label(log.content or "").classes("whitespace-pre-wrap")

    # 新增 case_log
    with ui.column().classes("p-4 w-full max-w-3xl"):
        ui.label("新增補充記錄").classes("text-lg font-bold")
        new_log_text = ui.textarea(label="內容").classes("w-full")
        direction_sel = ui.select(
            LOG_DIRECTION_OPTIONS,
            value="內部討論",
            label="類型",
        ).classes("w-full")

        def add_log() -> None:
            content = (new_log_text.value or "").strip()
            if not content:
                ui.notify("內容不可為空", type="warning")
                return
            now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            log = CaseLog(
                log_id=log_repo.next_log_id(),
                case_id=case_id,
                direction=direction_sel.value,
                content=content,
                logged_by=staff.staff_id,
                logged_at=now,
            )
            log_repo.insert(log)
            ui.notify("已新增記錄", type="positive")
            ui.navigate.to(f"/cases/{case_id}")

        ui.button("新增", on_click=add_log).classes("bg-green-600 text-white")

    # 連結既有 Mantis ticket（手動）
    with ui.column().classes("p-4 w-full max-w-3xl"):
        ui.label("連結既有 Mantis ticket").classes("text-lg font-bold")
        ticket_input = ui.input(label="Mantis ticket id（已存在的）").classes("w-full")

        def link_existing() -> None:
            tid = (ticket_input.value or "").strip()
            if not tid:
                ui.notify("請輸入 ticket id", type="warning")
                return
            link_repo.insert(CaseMantisLink(case_id=case_id, ticket_id=tid))
            ui.notify(f"已連結 #{tid}", type="positive")
            ui.navigate.to(f"/cases/{case_id}")

        ui.button("連結", on_click=link_existing).classes("bg-slate-600 text-white")

    # Mantis 推送區
    _render_mantis_push_section(
        conn, case, staff, link_repo,
        mantis_client, mantis_project_id, mantis_category,
    )


def _apply_save(
    case_repo, auditor, case_id, staff,
    new_status, new_progress, new_handler, new_priority, new_rd,
) -> None:
    old = case_repo.get_by_id(case_id)
    if old is None:
        ui.notify("案件已被刪除", type="negative")
        return

    changes = {
        "status": (old.status, new_status),
        "progress": (old.progress or "", new_progress or ""),
        "handler": (old.handler, new_handler),
        "priority": (old.priority, new_priority),
        "rd_assignee": (old.rd_assignee, new_rd),
    }
    changed_any = False
    for field, (oldv, newv) in changes.items():
        if oldv != newv:
            auditor.log_field_change(staff.staff_id, case_id, field)
            setattr(old, field, newv)
            changed_any = True
    if changed_any:
        case_repo.update(old)
        ui.notify("已儲存", type="positive")
    else:
        ui.notify("沒有變更", type="info")


def _confirm_close_case(
    case_repo, auditor, case_id, staff,
    new_status, new_progress, new_handler, new_priority, new_rd,
) -> None:
    with ui.dialog() as dialog, ui.card():
        ui.label("確認標記為「已結案」？").classes("text-xl font-bold")
        ui.label(
            "已結案後，客戶後續回信不會重新開啟此案件，僅會新增記錄。"
        ).classes("text-slate-300")
        with ui.row():
            ui.button("取消", on_click=dialog.close).props("flat")

            def confirm():
                _apply_save(
                    case_repo, auditor, case_id, staff,
                    new_status, new_progress, new_handler, new_priority, new_rd,
                )
                dialog.close()
                ui.navigate.to(f"/cases/{case_id}")

            ui.button("確認結案", on_click=confirm).classes("bg-slate-700 text-white")
    dialog.open()


def _render_mantis_push_section(
    conn, case: Case, staff: Staff, link_repo: CaseMantisRepository,
    mantis_client, mantis_project_id, mantis_category,
) -> None:
    ui.separator()
    ui.label("Mantis 推送").classes("text-xl font-bold p-4")

    if mantis_client is None or not mantis_project_id:
        ui.label("⚠ Mantis 未設定（HCP_CMS_MANTIS_URL / HCP_CMS_MANTIS_PROJECT）").classes("text-amber-500 p-4")
        return

    links = link_repo.list_by_case_id(case.case_id)
    push_mgr = MantisPushManager(
        conn, mantis_client,
        project_id=mantis_project_id, category=mantis_category,
    )

    if not links:
        ui.label("本案件尚未連結 Mantis ticket").classes("text-slate-500 p-2")

        def on_create() -> None:
            with ui.dialog() as dialog, ui.card():
                ui.label(f"將案件 {case.case_id} 建為新 Mantis ticket？")
                with ui.row():
                    ui.button("取消", on_click=dialog.close).props("flat")

                    def confirm():
                        success, payload = push_mgr.push_case_as_new_ticket(
                            case.case_id, staff.staff_id,
                        )
                        if success:
                            ui.notify(f"已建立 Mantis ticket #{payload}", type="positive")
                            ui.navigate.to(f"/cases/{case.case_id}")
                        else:
                            ui.notify(f"失敗：{payload}", type="negative")
                        dialog.close()

                    ui.button("確認推送", on_click=confirm).classes("bg-blue-600 text-white")
            dialog.open()

        ui.button("建立 Mantis ticket", on_click=on_create).classes("bg-blue-600 text-white px-4 py-2")
    else:
        ticket_id = links[0].ticket_id
        ui.label(f"已連結 Mantis ticket #{ticket_id}").classes("p-2")

        def on_bugnote() -> None:
            with ui.dialog() as dialog, ui.card():
                ui.label(f"將當前進度推為 Mantis ticket #{ticket_id} 的留言？")
                with ui.row():
                    ui.button("取消", on_click=dialog.close).props("flat")

                    def confirm():
                        success, payload = push_mgr.push_case_as_bugnote(
                            case.case_id, staff.staff_id,
                        )
                        if success:
                            ui.notify(f"已新增留言 #{payload}", type="positive")
                            ui.navigate.to(f"/cases/{case.case_id}")
                        else:
                            ui.notify(f"失敗：{payload}", type="negative")
                        dialog.close()

                    ui.button("確認推送", on_click=confirm).classes("bg-blue-600 text-white")
            dialog.open()

        ui.button("推送更新為 bugnote", on_click=on_bugnote).classes("bg-blue-600 text-white px-4 py-2")
