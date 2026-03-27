"""DeleteCasesDialog — 按日期範圍刪除案件的確認對話框。"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from hcp_cms.core.case_manager import CaseManager


class DeleteCasesDialog(QDialog):
    """依日期範圍刪除案件對話框。"""

    def __init__(self, conn: sqlite3.Connection, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._mgr = CaseManager(conn)
        self.setWindowTitle("刪除案件")
        self.setMinimumWidth(400)
        self._count: int = 0
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 說明
        info = QLabel(
            "選擇要刪除的案件日期範圍。\n"
            "⚠️ 刪除後無法復原，請先確認已備份。\n"
            "KMS 知識庫中已發布的條目不會被刪除。"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # 日期範圍
        group = QGroupBox("建立日期範圍")
        g_layout = QHBoxLayout(group)

        self._start_date = QDateEdit()
        self._start_date.setCalendarPopup(True)
        self._start_date.setDate(QDate.currentDate().addMonths(-1))
        self._start_date.setDisplayFormat("yyyy/MM/dd")

        self._end_date = QDateEdit()
        self._end_date.setCalendarPopup(True)
        self._end_date.setDate(QDate.currentDate())
        self._end_date.setDisplayFormat("yyyy/MM/dd")

        g_layout.addWidget(QLabel("從"))
        g_layout.addWidget(self._start_date)
        g_layout.addWidget(QLabel("至"))
        g_layout.addWidget(self._end_date)
        layout.addWidget(group)

        # 預覽按鈕 + 計數標籤
        preview_row = QHBoxLayout()
        self._preview_btn = QPushButton("預覽筆數")
        self._preview_btn.clicked.connect(self._on_preview)
        self._count_label = QLabel("—")
        preview_row.addWidget(self._preview_btn)
        preview_row.addWidget(self._count_label)
        preview_row.addStretch()
        layout.addLayout(preview_row)

        # 確認 / 取消
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("確認刪除")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        buttons.accepted.connect(self._on_confirm_delete)
        buttons.rejected.connect(self.reject)
        self._ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        layout.addWidget(buttons)

    def _on_preview(self) -> None:
        start = self._start_date.date().toString("yyyy/MM/dd")
        end = self._end_date.date().toString("yyyy/MM/dd")
        rows = self._conn.execute(
            "SELECT COUNT(*) FROM cs_cases WHERE created_at >= :s AND created_at <= :e || ' 23:59:59'",
            {"s": start, "e": end},
        ).fetchone()
        self._count = rows[0] if rows else 0
        self._count_label.setText(f"符合 <b>{self._count}</b> 筆案件")
        self._ok_btn.setEnabled(self._count > 0)

    def _on_confirm_delete(self) -> None:
        if self._count == 0:
            return
        reply = QMessageBox.warning(
            self,
            "確認刪除",
            f"即將刪除 {self._count} 筆案件，此操作無法復原。\n確定繼續？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        start = self._start_date.date().toString("yyyy/MM/dd")
        end = self._end_date.date().toString("yyyy/MM/dd")
        deleted = self._mgr.delete_cases_by_date_range(start, end)
        QMessageBox.information(self, "完成", f"已刪除 {deleted} 筆案件。")
        self.accept()
