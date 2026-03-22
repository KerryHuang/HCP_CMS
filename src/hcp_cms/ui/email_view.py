"""Email processing view."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class EmailView(QWidget):
    """Email processing page."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("📧 信件處理")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f1f5f9;")
        layout.addWidget(title)

        # Connection settings
        conn_group = QGroupBox("連線設定")
        conn_layout = QHBoxLayout(conn_group)

        self._provider_combo = QComboBox()
        self._provider_combo.addItems(["IMAP", "Exchange", ".msg 手動匯入"])
        conn_layout.addWidget(QLabel("來源:"))
        conn_layout.addWidget(self._provider_combo)

        self._connect_btn = QPushButton("🔗 連線")
        conn_layout.addWidget(self._connect_btn)

        layout.addWidget(conn_group)

        # Date filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("日期範圍:"))
        self._date_from = QDateEdit(QDate.currentDate().addMonths(-1))
        self._date_to = QDateEdit(QDate.currentDate())
        filter_layout.addWidget(self._date_from)
        filter_layout.addWidget(QLabel("~"))
        filter_layout.addWidget(self._date_to)

        fetch_btn = QPushButton("📥 取得信件列表")
        filter_layout.addWidget(fetch_btn)

        import_btn = QPushButton("📁 匯入 .msg 檔案")
        import_btn.clicked.connect(self._on_import_msg)
        filter_layout.addWidget(import_btn)

        layout.addLayout(filter_layout)

        # Email list
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["寄件人", "主旨", "日期", "狀態"])
        self._table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._table)

        # Actions
        action_layout = QHBoxLayout()
        self._import_selected_btn = QPushButton("✅ 匯入勾選")
        action_layout.addWidget(self._import_selected_btn)
        self._import_all_btn = QPushButton("📥 全部匯入")
        action_layout.addWidget(self._import_all_btn)
        layout.addLayout(action_layout)

        # Progress
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Log
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(100)
        self._log.setPlaceholderText("處理日誌...")
        layout.addWidget(self._log)

        # Schedule settings
        schedule_group = QGroupBox("自動排程")
        schedule_layout = QHBoxLayout(schedule_group)
        schedule_layout.addWidget(QLabel("每"))
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(1, 1440)
        self._interval_spin.setValue(15)
        schedule_layout.addWidget(self._interval_spin)
        schedule_layout.addWidget(QLabel("分鐘自動檢查"))
        self._auto_btn = QPushButton("啟動自動處理")
        schedule_layout.addWidget(self._auto_btn)
        layout.addWidget(schedule_group)

    def _on_import_msg(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "選擇 .msg 檔案", "", "Outlook Messages (*.msg)"
        )
        if files:
            self._log.append(f"已選擇 {len(files)} 個檔案")
