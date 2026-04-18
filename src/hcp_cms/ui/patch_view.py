"""PatchView — Patch 整理主頁，包含單次 Patch 與每月大 PATCH 兩個 Tab。"""

from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab
from hcp_cms.ui.patch_single_tab import SinglePatchTab
from hcp_cms.ui.supplement_editor_widget import SupplementEditorWidget


class PatchView(QWidget):
    """Patch 整理頁面 — 頂部 Tab 切換 SinglePatchTab / MonthlyPatchTab / 補充說明。"""

    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        theme_mgr: object | None = None,
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

        monthly_tab = MonthlyPatchTab(conn=self._conn)
        self._supplement_tab = SupplementEditorWidget(conn=self._conn)

        self._tabs = QTabWidget()
        self._tabs.addTab(SinglePatchTab(conn=self._conn), "單次 Patch")
        self._tabs.addTab(monthly_tab, "每月大 PATCH")
        self._tabs.addTab(self._supplement_tab, "📋 補充說明")
        layout.addWidget(self._tabs)

        # MonthlyPatchTab → SupplementEditorWidget
        monthly_tab.open_supplement_editor.connect(self._on_open_supplement_editor)
        monthly_tab.supplement_data_updated.connect(self._supplement_tab.load_issues)
        monthly_tab.supplement_display_updated.connect(self._on_supplement_display_updated)

        # SupplementEditorWidget → MonthlyPatchTab
        self._supplement_tab.supplement_saved.connect(monthly_tab._on_supplement_saved)
        self._supplement_tab.reanalyze_requested.connect(monthly_tab._on_reanalyze_single)
        self._supplement_tab.reanalyze_all_requested.connect(monthly_tab._on_reanalyze_all)

        # 切換到補充說明 Tab 時自動載入 Issue 清單
        self._monthly_tab = monthly_tab
        self._tabs.currentChanged.connect(self._on_tab_changed)

    def _on_open_supplement_editor(self, issues: list) -> None:
        self._supplement_tab.load_issues(issues)
        self._tabs.setCurrentWidget(self._supplement_tab)

    def _on_tab_changed(self, index: int) -> None:
        if self._tabs.widget(index) is self._supplement_tab:
            self._supplement_tab.load_issues(self._monthly_tab._get_current_issues())

    def _on_supplement_display_updated(self, issue_id: int, supplement: object, edited: bool) -> None:
        self._supplement_tab.update_issue_display(issue_id, supplement, edited=edited)  # type: ignore[arg-type]
