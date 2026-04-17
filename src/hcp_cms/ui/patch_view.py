"""PatchView — Patch 整理主頁，包含單次 Patch 與每月大 PATCH 兩個 Tab。"""

from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab
from hcp_cms.ui.patch_single_tab import SinglePatchTab
from hcp_cms.ui.theme import ThemeManager


class PatchView(QWidget):
    """Patch 整理頁面 — 頂部 Tab 切換 SinglePatchTab / MonthlyPatchTab。"""

    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        theme_mgr: ThemeManager | None = None,
    ) -> None:
        super().__init__()
        self._conn = conn
        self._theme_mgr = theme_mgr
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("📦 Patch 整理")
        layout.addWidget(title)

        self._tabs = QTabWidget()
        self._tabs.addTab(SinglePatchTab(conn=self._conn), "單次 Patch")
        self._tabs.addTab(MonthlyPatchTab(conn=self._conn), "每月大 PATCH")
        layout.addWidget(self._tabs)
