"""Mantis sync view."""

from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget, QComboBox, QLineEdit,
)

from hcp_cms.data.repositories import MantisRepository


class MantisView(QWidget):
    """Mantis sync page."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("🔧 Mantis 同步")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f1f5f9;")
        layout.addWidget(title)

        # Connection
        conn_group = QGroupBox("連線設定")
        conn_layout = QHBoxLayout(conn_group)
        self._api_combo = QComboBox()
        self._api_combo.addItems(["REST API", "SOAP API"])
        conn_layout.addWidget(self._api_combo)
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("Mantis URL...")
        conn_layout.addWidget(self._url_input)
        self._sync_btn = QPushButton("🔄 立即同步")
        conn_layout.addWidget(self._sync_btn)
        layout.addWidget(conn_group)

        # Ticket table
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(["票號", "摘要", "狀態", "優先", "負責人", "同步時間"])
        self._table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._table)

        # Log
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(80)
        layout.addWidget(self._log)
