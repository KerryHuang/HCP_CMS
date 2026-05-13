"""NiceGUI Web Portal app factory."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from nicegui import app, ui

from hcp_cms.data.repositories import StaffRepository
from hcp_cms.services.mantis.soap import MantisSoapClient
from hcp_cms.web.auth import WebAuthManager
from hcp_cms.web.pages.audit import build_audit_page
from hcp_cms.web.pages.case_detail import build_case_detail_page
from hcp_cms.web.pages.case_list import build_case_list_page
from hcp_cms.web.pages.login import build_login_page


def create_app(
    conn: sqlite3.Connection,
    db_dir: Path,
    mantis_base_url: str = "",
    mantis_user: str = "",
    mantis_password: str = "",
    mantis_project_id: str = "",
    mantis_category: str = "General",
) -> None:
    """建立 NiceGUI app 並註冊所有路由，最後啟動 uvicorn server。"""
    auth = WebAuthManager(conn)

    # 初始化 Mantis client（若 credentials 完整）
    mantis_client: MantisSoapClient | None = None
    if mantis_base_url and mantis_user and mantis_password:
        mantis_client = MantisSoapClient(mantis_base_url, mantis_user, mantis_password)
        mantis_client.connect()

    @ui.page("/")
    def home_page():
        staff_id = app.storage.user.get("staff_id")
        if not staff_id or auth.get_staff_by_id(staff_id) is None:
            ui.navigate.to("/login")
            return
        ui.navigate.to("/cases")

    @ui.page("/login")
    def login_page():
        build_login_page(auth)

    @ui.page("/logout")
    def logout_page():
        app.storage.user.clear()
        ui.navigate.to("/login")

    @ui.page("/cases")
    def case_list_page():
        staff_id = app.storage.user.get("staff_id")
        if not staff_id:
            ui.navigate.to("/login")
            return
        staff = auth.get_staff_by_id(staff_id)
        if staff is None:
            app.storage.user.clear()
            ui.navigate.to("/login")
            return
        build_case_list_page(
            conn,
            staff,
            mantis_client=mantis_client,
            mantis_project_id=mantis_project_id,
            mantis_category=mantis_category,
        )

    @ui.page("/cases/{case_id}")
    def case_detail_page(case_id: str):
        staff_id = app.storage.user.get("staff_id")
        if not staff_id:
            ui.navigate.to("/login")
            return
        staff = auth.get_staff_by_id(staff_id)
        if staff is None:
            ui.navigate.to("/login")
            return
        build_case_detail_page(
            conn,
            staff,
            case_id,
            mantis_client=mantis_client,
            mantis_project_id=mantis_project_id,
            mantis_category=mantis_category,
        )

    @ui.page("/audit")
    def audit_page():
        staff_id = app.storage.user.get("staff_id")
        if not staff_id:
            ui.navigate.to("/login")
            return
        s = StaffRepository(conn).get_by_id(staff_id)
        if s is None or s.role != "admin":
            ui.label("您無權限查看稽核紀錄").classes("text-red-500 text-2xl p-8")
            return
        build_audit_page(conn, s)

    ui.run(
        host="0.0.0.0",
        port=8080,
        title="HCP CMS 客服 Portal",
        favicon="🛟",
        dark=True,
        storage_secret="hcp-cms-secret-change-me-in-production",
        reload=False,
        show=False,
    )
