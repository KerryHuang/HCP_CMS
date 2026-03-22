"""Dashboard view — KPI cards, recent cases, alerts."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.case_manager import CaseManager
from hcp_cms.data.repositories import CaseRepository


class KPICard(QFrame):
    """A single KPI metric card."""

    def __init__(self, title: str, value: str, subtitle: str = "", color: str = "#3b82f6") -> None:
        super().__init__()
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet(f"""
            QFrame {{ background-color: #1e293b; border-radius: 8px;
                     border-left: 3px solid {color}; padding: 8px; }}
        """)

        layout = QVBoxLayout(self)

        title_label = QLabel(title)
        title_label.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(title_label)

        self._value_label = QLabel(value)
        self._value_label.setStyleSheet("color: #f1f5f9; font-size: 24px; font-weight: bold;")
        layout.addWidget(self._value_label)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setStyleSheet("color: #34d399; font-size: 10px;")
            layout.addWidget(sub)

    def set_value(self, value: str) -> None:
        self._value_label.setText(value)


class DashboardView(QWidget):
    """Dashboard with KPI cards and recent cases."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._setup_ui()
        if conn:
            self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("📊 儀表板")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f1f5f9;")
        layout.addWidget(title)

        # KPI cards grid
        kpi_layout = QGridLayout()
        self._kpi_total = KPICard("本月案件", "0", color="#3b82f6")
        self._kpi_reply_rate = KPICard("回覆率", "0%", color="#10b981")
        self._kpi_pending = KPICard("待處理", "0", color="#f59e0b")
        self._kpi_frt = KPICard("平均 FRT", "---", color="#8b5cf6")

        kpi_layout.addWidget(self._kpi_total, 0, 0)
        kpi_layout.addWidget(self._kpi_reply_rate, 0, 1)
        kpi_layout.addWidget(self._kpi_pending, 0, 2)
        kpi_layout.addWidget(self._kpi_frt, 0, 3)
        layout.addLayout(kpi_layout)

        # Recent cases table
        recent_label = QLabel("最近案件")
        recent_label.setStyleSheet("color: #94a3b8; font-weight: bold; margin-top: 16px;")
        layout.addWidget(recent_label)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["案件編號", "公司", "主旨", "狀態", "時間"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._table)

    def refresh(self) -> None:
        """Refresh dashboard data from database."""
        if not self._conn:
            return
        try:
            now = datetime.now()
            mgr = CaseManager(self._conn)
            stats = mgr.get_dashboard_stats(now.year, now.month)

            self._kpi_total.set_value(str(stats["total"]))
            self._kpi_reply_rate.set_value(f"{stats['reply_rate']}%")
            self._kpi_pending.set_value(str(stats["pending"]))
            frt = stats.get("avg_frt")
            self._kpi_frt.set_value(f"{frt}h" if frt is not None else "---")

            # Recent cases
            repo = CaseRepository(self._conn)
            cases = repo.list_by_month(now.year, now.month)[:10]
            self._table.setRowCount(len(cases))
            for i, case in enumerate(cases):
                self._table.setItem(i, 0, QTableWidgetItem(case.case_id))
                self._table.setItem(i, 1, QTableWidgetItem(case.company_id or ""))
                self._table.setItem(i, 2, QTableWidgetItem(case.subject or ""))
                self._table.setItem(i, 3, QTableWidgetItem(case.status))
                self._table.setItem(i, 4, QTableWidgetItem(case.sent_time or ""))
        except Exception:
            pass
