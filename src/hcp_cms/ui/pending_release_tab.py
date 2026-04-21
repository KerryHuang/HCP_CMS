"""待發清單 Tab — 顯示待發布的 Patch 確認項目，支援月份篩選與標記已發布。"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from hcp_cms.core.release_manager import ReleaseManager


class PendingReleaseTab(QWidget):
    """待發清單分頁：依月份顯示待發項目，可標記已發布。"""

    def __init__(self, conn: sqlite3.Connection | None = None, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._items: list = []
        self._setup_ui()
        if conn:
            self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        # 工具列
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("月份："))
        self._month_combo = QComboBox()
        self._month_combo.setMinimumWidth(120)
        self._populate_months()
        self._month_combo.currentIndexChanged.connect(self.refresh)
        toolbar.addWidget(self._month_combo)

        refresh_btn = QPushButton("🔄 重新整理")
        refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch()

        self._release_btn = QPushButton("✅ 標記已發布")
        self._release_btn.setEnabled(False)
        self._release_btn.clicked.connect(self._on_mark_released)
        toolbar.addWidget(self._release_btn)
        layout.addLayout(toolbar)

        # 表格
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "ID", "案件編號", "Mantis 票號", "客戶", "指派人", "備注", "狀態"
        ])
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table)

    def _populate_months(self) -> None:
        now = datetime.now()
        for i in range(12):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            ms = f"{y}{m:02d}"
            self._month_combo.addItem(f"{ms[:4]}/{ms[4:]}", ms)

    def refresh(self) -> None:
        if not self._conn:
            return
        month_str = self._month_combo.currentData()
        if not month_str:
            return
        mgr = ReleaseManager(self._conn)
        self._items = mgr.list_by_month(month_str)
        self._table.setRowCount(0)
        for item in self._items:
            row = self._table.rowCount()
            self._table.insertRow(row)
            vals = [
                str(item.id or ""),
                item.case_id or "",
                item.mantis_ticket_id or "",
                item.client_name or "",
                item.assignee or "",
                item.note or "",
                item.status,
            ]
            for col, v in enumerate(vals):
                cell = QTableWidgetItem(v)
                if item.status == "已發布":
                    cell.setForeground(Qt.GlobalColor.gray)
                self._table.setItem(row, col, cell)
        self._release_btn.setEnabled(False)

    def _on_selection_changed(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            self._release_btn.setEnabled(False)
            return
        row = rows[0].row()
        if 0 <= row < len(self._items):
            self._release_btn.setEnabled(self._items[row].status == "待發")

    def _on_mark_released(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows or not self._conn:
            return
        row = rows[0].row()
        if row < 0 or row >= len(self._items):
            return
        item = self._items[row]
        ReleaseManager(self._conn).mark_released(item.id)
        self.refresh()
        QMessageBox.information(
            self, "完成",
            f"已將 {item.mantis_ticket_id or item.case_id or 'item'} 標記為已發布。"
        )
