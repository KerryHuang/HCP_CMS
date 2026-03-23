"""Email processing view."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import QDate, Qt
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
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.case_manager import CaseManager
from hcp_cms.services.mail.msg_reader import MSGReader


class EmailView(QWidget):
    """Email processing page."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._pending_files: list[Path] = []
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
        self._date_from.setCalendarPopup(True)
        self._date_to = QDateEdit(QDate.currentDate())
        self._date_to.setCalendarPopup(True)
        filter_layout.addWidget(self._date_from)
        filter_layout.addWidget(QLabel("~"))
        filter_layout.addWidget(self._date_to)

        fetch_btn = QPushButton("📥 取得信件列表")
        filter_layout.addWidget(fetch_btn)

        import_btn = QPushButton("📁 匯入 .msg 檔案")
        import_btn.clicked.connect(self._on_import_msg)
        filter_layout.addWidget(import_btn)

        layout.addLayout(filter_layout)

        # Email list — 5 columns: checkbox + 寄件人 + 主旨 + 日期 + 狀態
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["✓", "寄件人", "主旨", "日期", "狀態"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(0, 30)
        layout.addWidget(self._table)

        # Actions
        action_layout = QHBoxLayout()
        self._import_selected_btn = QPushButton("✅ 匯入勾選")
        self._import_selected_btn.clicked.connect(self._on_import_selected)
        action_layout.addWidget(self._import_selected_btn)
        self._import_all_btn = QPushButton("📥 全部匯入")
        self._import_all_btn.clicked.connect(self._on_import_all)
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
        if not files:
            return

        self._pending_files = [Path(f) for f in files]
        self._log.append(f"已選擇 {len(files)} 個檔案，解析中...")

        reader = MSGReader()
        self._table.setRowCount(0)

        for file_path in self._pending_files:
            email = reader.read_single_file(file_path)
            row = self._table.rowCount()
            self._table.insertRow(row)

            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Checked)
            self._table.setItem(row, 0, chk_item)

            if email:
                self._table.setItem(row, 1, QTableWidgetItem(email.sender))
                self._table.setItem(row, 2, QTableWidgetItem(email.subject))
                self._table.setItem(row, 3, QTableWidgetItem(str(email.date) if email.date else ""))
                self._table.setItem(row, 4, QTableWidgetItem("待匯入"))
            else:
                self._table.setItem(row, 1, QTableWidgetItem(""))
                self._table.setItem(row, 2, QTableWidgetItem(file_path.name))
                self._table.setItem(row, 3, QTableWidgetItem(""))
                self._table.setItem(row, 4, QTableWidgetItem("無法讀取"))

        self._log.append(f"解析完成，共 {self._table.rowCount()} 封信件")

    def _on_import_selected(self) -> None:
        rows = [
            r for r in range(self._table.rowCount())
            if self._table.item(r, 0) is not None
            and self._table.item(r, 0).checkState() == Qt.CheckState.Checked
        ]
        self._do_import_rows(rows)

    def _on_import_all(self) -> None:
        self._do_import_rows(list(range(self._table.rowCount())))

    def _do_import_rows(self, rows: list[int]) -> None:
        if not rows:
            self._log.append("沒有可匯入的信件")
            return
        if not self._conn:
            self._log.append("❌ 資料庫未連線")
            return

        manager = CaseManager(self._conn)
        reader = MSGReader()
        success = 0
        fail = 0

        self._progress.setVisible(True)
        self._progress.setMaximum(len(rows))
        self._progress.setValue(0)

        for i, row in enumerate(rows):
            status_item = self._table.item(row, 4)
            if status_item and status_item.text() == "已匯入":
                self._progress.setValue(i + 1)
                continue

            if row >= len(self._pending_files):
                fail += 1
                self._progress.setValue(i + 1)
                continue

            file_path = self._pending_files[row]
            email = reader.read_single_file(file_path)

            if email:
                try:
                    manager.create_case(
                        subject=email.subject,
                        body=email.body,
                        sender_email=email.sender,
                        sent_time=str(email.date) if email.date else None,
                        source_filename=email.source_file,
                    )
                    self._table.setItem(row, 4, QTableWidgetItem("已匯入"))
                    success += 1
                except Exception as e:
                    self._table.setItem(row, 4, QTableWidgetItem("匯入失敗"))
                    self._log.append(f"❌ {file_path.name}: {e}")
                    fail += 1
            else:
                self._table.setItem(row, 4, QTableWidgetItem("讀取失敗"))
                fail += 1

            self._progress.setValue(i + 1)

        self._progress.setVisible(False)
        self._log.append(f"✅ 完成：成功 {success} 件，失敗 {fail} 件")
