"""Custom status bar widget."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class StatusWidget(QWidget):
    """Status indicator widget for the status bar."""

    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)

        self._db_status = QLabel("🟢 DB 已連線")
        self._db_status.setStyleSheet("color: #34d399; font-size: 11px;")
        layout.addWidget(self._db_status)

        self._scheduler_status = QLabel("⏰ 排程停止")
        self._scheduler_status.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(self._scheduler_status)

    def set_db_connected(self, connected: bool) -> None:
        if connected:
            self._db_status.setText("🟢 DB 已連線")
            self._db_status.setStyleSheet("color: #34d399; font-size: 11px;")
        else:
            self._db_status.setText("🔴 DB 未連線")
            self._db_status.setStyleSheet("color: #ef4444; font-size: 11px;")

    def set_scheduler_status(self, text: str) -> None:
        self._scheduler_status.setText(text)
