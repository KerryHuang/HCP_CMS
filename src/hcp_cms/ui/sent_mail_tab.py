"""Sent mail backup tab widget."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from typing import cast

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.excel_exporter import ExcelExporter
from hcp_cms.core.sent_mail_manager import EnrichedSentMail, SentMailManager
from hcp_cms.services.mail.base import MailProvider


class SentMailTab(QWidget):
    """寄件備份分頁：顯示寄件清單與公司彙總統計。"""

    _worker_done = Signal(object)
    _worker_error = Signal(str)

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._provider: MailProvider | None = None
        self._current_mails: list[EnrichedSentMail] = []
        self._setup_ui()

    def set_provider(self, provider: MailProvider | None) -> None:
        """由 EmailView 在連線成功後呼叫。"""
        self._provider = provider

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)

        # --- 日期導航列（同收件分頁） ---
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("日期:"))

        prev_week_btn = QPushButton("◀◀")
        prev_week_btn.setFixedWidth(42)
        prev_week_btn.setToolTip("前七天")
        prev_week_btn.clicked.connect(self._on_prev_week)
        filter_layout.addWidget(prev_week_btn)

        prev_btn = QPushButton("◀")
        prev_btn.setFixedWidth(36)
        prev_btn.setToolTip("前一天")
        prev_btn.clicked.connect(self._on_prev_day)
        filter_layout.addWidget(prev_btn)

        self._date_edit = QDateEdit(QDate.currentDate())
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy/MM/dd")
        filter_layout.addWidget(self._date_edit)

        next_btn = QPushButton("▶")
        next_btn.setFixedWidth(36)
        next_btn.setToolTip("後一天")
        next_btn.clicked.connect(self._on_next_day)
        filter_layout.addWidget(next_btn)

        next_week_btn = QPushButton("▶▶")
        next_week_btn.setFixedWidth(42)
        next_week_btn.setToolTip("後七天")
        next_week_btn.clicked.connect(self._on_next_week)
        filter_layout.addWidget(next_week_btn)

        today_btn = QPushButton("今天")
        today_btn.setFixedWidth(50)
        today_btn.clicked.connect(self._on_today)
        filter_layout.addWidget(today_btn)

        self._refresh_btn = QPushButton("🔄 重新整理")
        self._refresh_btn.clicked.connect(self._on_refresh)
        filter_layout.addWidget(self._refresh_btn)

        self._export_btn = QPushButton("📥 匯出 Excel")
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._on_export)
        filter_layout.addWidget(self._export_btn)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # --- 公司彙總表 ---
        summary_label = QLabel("公司彙總")
        summary_label.setStyleSheet("font-weight: bold; color: #f1f5f9;")
        layout.addWidget(summary_label)

        self._summary_table = QTableWidget(0, 2)
        self._summary_table.setHorizontalHeaderLabels(["公司名稱", "次數"])
        self._summary_table.setFixedHeight(120)
        self._summary_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._summary_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._summary_table.horizontalHeader().resizeSection(1, 60)
        layout.addWidget(self._summary_table)

        # --- 寄件清單 ---
        list_label = QLabel("寄件清單")
        list_label.setStyleSheet("font-weight: bold; color: #f1f5f9;")
        layout.addWidget(list_label)

        self._list_table = QTableWidget(0, 6)
        self._list_table.setHorizontalHeaderLabels(["日期", "收件人", "主旨", "公司", "案件", "第幾封"])
        self._list_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self._list_table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for col in [0, 1, 3, 4, 5]:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        self._list_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self._list_table, stretch=1)

        # --- 日誌 ---
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(80)
        self._log.setPlaceholderText("處理日誌...")
        layout.addWidget(self._log)

        self._worker_done.connect(self._on_worker_done, Qt.ConnectionType.QueuedConnection)
        self._worker_error.connect(self._on_worker_error, Qt.ConnectionType.QueuedConnection)

    # --- 日期導航 ---

    def _on_prev_week(self) -> None:
        d = self._date_edit.date()
        start = d.addDays(-6)
        until = datetime(d.year(), d.month(), d.day(), 23, 59, 59)
        since = datetime(start.year(), start.month(), start.day())
        self._date_edit.setDate(start)
        self._fetch(since=since, until=until)

    def _on_prev_day(self) -> None:
        self._date_edit.setDate(self._date_edit.date().addDays(-1))
        self._on_refresh()

    def _on_next_day(self) -> None:
        self._date_edit.setDate(self._date_edit.date().addDays(1))
        self._on_refresh()

    def _on_next_week(self) -> None:
        d = self._date_edit.date()
        end = d.addDays(6)
        since = datetime(d.year(), d.month(), d.day())
        until = datetime(end.year(), end.month(), end.day(), 23, 59, 59)
        self._date_edit.setDate(end)
        self._fetch(since=since, until=until)

    def _on_today(self) -> None:
        self._date_edit.setDate(QDate.currentDate())
        self._on_refresh()

    def _on_refresh(self) -> None:
        d = self._date_edit.date()
        self._fetch(
            since=datetime(d.year(), d.month(), d.day()),
            until=datetime(d.year(), d.month(), d.day(), 23, 59, 59),
        )

    # --- 背景抓取 ---

    def _fetch(self, since: datetime, until: datetime) -> None:
        if not self._conn:
            self._log.append("⚠️ 資料庫未連線。")
            return
        if not self._provider:
            self._log.append("⚠️ 請先連線信箱。")
            return
        self._refresh_btn.setEnabled(False)
        if since.date() == until.date():
            self._log.append(f"正在取得 {since.strftime('%Y/%m/%d')} 的寄件備份...")
        else:
            self._log.append(f"正在取得 {since.strftime('%Y/%m/%d')} ~ {until.strftime('%Y/%m/%d')} 的寄件備份...")

        conn = self._conn
        provider = self._provider

        def _work() -> list[EnrichedSentMail]:
            return SentMailManager(conn, provider).fetch_and_enrich(since, until)

        def _thread() -> None:
            try:
                self._worker_done.emit(_work())
            except Exception as e:
                self._worker_error.emit(str(e))

        threading.Thread(target=_thread, daemon=True).start()

    def _on_worker_done(self, results: object) -> None:
        mails = cast(list[EnrichedSentMail], results)
        self._refresh_btn.setEnabled(True)
        self._current_mails = mails
        self._export_btn.setEnabled(len(mails) > 0)
        self._log.append(f"✅ 取得 {len(mails)} 封寄件備份。")
        self._populate_tables(mails)

    def _on_worker_error(self, msg: str) -> None:
        self._refresh_btn.setEnabled(True)
        self._log.append(f"❌ 錯誤：{msg}")

    # --- 渲染 ---

    def _populate_tables(self, mails: list[EnrichedSentMail]) -> None:
        # 彙總表（去重後依次數降冪）
        seen: dict[str, tuple[str, int]] = {}
        for m in mails:
            if m.company_id and m.company_id not in seen:
                seen[m.company_id] = (m.company_name or m.company_id, m.company_reply_count)
        ranked = sorted(seen.values(), key=lambda x: x[1], reverse=True)
        self._summary_table.setRowCount(len(ranked))
        for row, (name, count) in enumerate(ranked):
            self._summary_table.setItem(row, 0, QTableWidgetItem(name))
            self._summary_table.setItem(row, 1, QTableWidgetItem(str(count)))

        # 寄件清單
        self._list_table.setRowCount(len(mails))
        company_counters: dict[str, int] = {}
        for row, m in enumerate(mails):
            self._list_table.setItem(row, 0, QTableWidgetItem(m.date if m.date else ""))
            self._list_table.setItem(row, 1, QTableWidgetItem(", ".join(m.recipients)))
            self._list_table.setItem(row, 2, QTableWidgetItem(m.subject))
            self._list_table.setItem(row, 3, QTableWidgetItem(m.company_name or "未知"))
            case_text = m.linked_case_id or "—"
            case_item = QTableWidgetItem(case_text)
            if m.linked_case_id:
                case_item.setToolTip("雙擊複製案件編號")
            self._list_table.setItem(row, 4, case_item)
            if m.company_id:
                company_counters[m.company_id] = company_counters.get(m.company_id, 0) + 1
                count_text = str(company_counters[m.company_id])
            else:
                count_text = "—"
            self._list_table.setItem(row, 5, QTableWidgetItem(count_text))

    def _on_export(self) -> None:
        d = self._date_edit.date()
        default_name = f"寄件備份_{d.toString('yyyy-MM-dd')}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "匯出 Excel",
            default_name,
            "Excel 檔案 (*.xlsx)",
        )
        if not path:
            return
        try:
            ExcelExporter().export_sent_mail(self._current_mails, path)
            self._log.append(f"✅ 已匯出至 {path}")
        except Exception as e:
            self._log.append(f"❌ 匯出失敗：{e}")

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        if col == 4:
            item = self._list_table.item(row, col)
            if item and item.text() != "—":
                QApplication.clipboard().setText(item.text())
                self._log.append(f"📋 已複製案件編號：{item.text()}")
