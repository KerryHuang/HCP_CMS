"""待發清單 Tab — 顯示待發布的 Patch 確認項目，支援月份篩選、異動月份與標記已發布。"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from PySide6.QtCore import Qt
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

from hcp_cms.core.release_manager import ReleaseManager

# 欄位定義：(標題, ReleaseItem 屬性名稱, 是否 Stretch)
_COLUMNS = [
    ("狀態",        "status",           False),
    ("客戶",        "client_name",      False),
    ("Mantis 票號", "mantis_ticket_id", False),
    ("案件編號",    "case_id",          False),
    ("指派人",      "assignee",         False),
    ("備注",        "note",             True),
]


class PendingReleaseTab(QWidget):
    """待發清單分頁：依月份顯示待發項目，可標記已發布或移至其他月份。"""

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
        layout.setSpacing(6)

        # ── 篩選列 ────────────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("檢視月份："))
        self._month_combo = QComboBox()
        self._month_combo.setMinimumWidth(120)
        self._populate_months(self._month_combo)
        self._month_combo.currentIndexChanged.connect(self.refresh)
        filter_row.addWidget(self._month_combo)

        refresh_btn = QPushButton("🔄 重新整理")
        refresh_btn.clicked.connect(self.refresh)
        filter_row.addWidget(refresh_btn)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # ── 操作列 ────────────────────────────────────────────────
        action_row = QHBoxLayout()

        self._release_btn = QPushButton("✅ 標記已發布")
        self._release_btn.setEnabled(False)
        self._release_btn.clicked.connect(self._on_mark_released)
        action_row.addWidget(self._release_btn)

        action_row.addSpacing(20)
        action_row.addWidget(QLabel("移至月份："))
        self._move_month_combo = QComboBox()
        self._move_month_combo.setMinimumWidth(120)
        self._populate_months(self._move_month_combo)
        action_row.addWidget(self._move_month_combo)

        self._move_btn = QPushButton("📅 確認移動")
        self._move_btn.setEnabled(False)
        self._move_btn.clicked.connect(self._on_move_month)
        action_row.addWidget(self._move_btn)

        action_row.addStretch()
        layout.addLayout(action_row)

        # ── 表格 ──────────────────────────────────────────────────
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels([c[0] for c in _COLUMNS])
        for i, (_, _, stretch) in enumerate(_COLUMNS):
            if stretch:
                self._table.horizontalHeader().setSectionResizeMode(
                    i, QHeaderView.ResizeMode.Stretch
                )
            else:
                self._table.horizontalHeader().setSectionResizeMode(
                    i, QHeaderView.ResizeMode.ResizeToContents
                )
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table)

    def _populate_months(self, combo: QComboBox) -> None:
        """填入未來 3 個月 + 當月 + 過去 12 個月，共 16 個月。"""
        now = datetime.now()
        combo.blockSignals(True)
        combo.clear()
        for i in range(-3, 13):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            while m > 12:
                m -= 12
                y += 1
            ms = f"{y}{m:02d}"
            combo.addItem(f"{ms[:4]}/{ms[4:]}", ms)
        combo.blockSignals(False)

    def refresh(self) -> None:
        if not self._conn:
            return
        month_str = self._month_combo.currentData()
        if not month_str:
            return
        mgr = ReleaseManager(self._conn)
        # 待發排前，已發布排後；同狀態依建立時間新→舊
        raw = mgr.list_by_month(month_str)
        self._items = sorted(raw, key=lambda x: (0 if x.status == "待發" else 1))

        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for item in self._items:
            row = self._table.rowCount()
            self._table.insertRow(row)
            for col, (_, attr, _) in enumerate(_COLUMNS):
                val = getattr(item, attr) or ""
                cell = QTableWidgetItem(val)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                if item.status == "已發布":
                    cell.setForeground(Qt.GlobalColor.gray)
                self._table.setItem(row, col, cell)
        self._table.setSortingEnabled(True)
        self._release_btn.setEnabled(False)
        self._move_btn.setEnabled(False)

    def _on_selection_changed(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            self._release_btn.setEnabled(False)
            self._move_btn.setEnabled(False)
            return
        row = rows[0].row()
        if 0 <= row < len(self._items):
            is_pending = self._items[row].status == "待發"
            self._release_btn.setEnabled(is_pending)
            self._move_btn.setEnabled(True)

    def _selected_item(self):
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def _on_mark_released(self) -> None:
        item = self._selected_item()
        if not item or not self._conn:
            return
        ReleaseManager(self._conn).mark_released(item.id)
        self.refresh()
        label = item.mantis_ticket_id or item.case_id or f"#{item.id}"
        QMessageBox.information(self, "完成", f"已將 {label} 標記為已發布。")

    def _on_move_month(self) -> None:
        item = self._selected_item()
        if not item or not self._conn:
            return
        target_month = self._move_month_combo.currentData()
        if not target_month:
            return
        current_month = self._month_combo.currentData()
        if target_month == current_month:
            QMessageBox.information(self, "提示", "目標月份與目前月份相同，無需移動。")
            return
        label = item.mantis_ticket_id or item.case_id or f"#{item.id}"
        target_display = self._move_month_combo.currentText()
        reply = QMessageBox.question(
            self, "確認移動",
            f"將「{label}」從 {self._month_combo.currentText()} 移至 {target_display}？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            ReleaseManager(self._conn).update_month(item.id, target_month)
            self.refresh()
            QMessageBox.information(self, "完成", f"已將 {label} 移至 {target_display}。")
