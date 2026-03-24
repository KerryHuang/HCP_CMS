"""Email processing view."""

from __future__ import annotations

import sqlite3
import traceback
from html import escape
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWebEngineWidgets import QWebEngineView
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
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.case_manager import CaseManager
from hcp_cms.core.kms_engine import KMSEngine
from hcp_cms.services.mail.base import RawEmail
from hcp_cms.services.mail.msg_reader import MSGReader


class EmailView(QWidget):
    """Email processing page."""

    _BASE_STYLE = (
        "body{margin:16px;font-family:'Segoe UI',Arial,sans-serif;"
        "font-size:13px;background:#1e293b;color:#e2e8f0;line-height:1.6;}"
        "pre{white-space:pre-wrap;word-break:break-word;}"
        "a{color:#60a5fa;}"
        "blockquote{border-left:3px solid #4b5563;margin:0;padding-left:12px;color:#94a3b8;}"
        "img{max-width:100%;}"
    )

    def __init__(self, conn: sqlite3.Connection | None = None, kms: KMSEngine | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._kms = kms
        self._pending_files: list[Path] = []
        self._emails: list[RawEmail | None] = []   # 與 _pending_files 平行
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

        self._splitter = QSplitter(Qt.Orientation.Vertical)

        # 上半：信件列表
        self._table.itemSelectionChanged.connect(self._on_row_selected)
        self._splitter.addWidget(self._table)

        # 下半：信件內容預覽（QWebEngineView）
        self._preview = QWebEngineView()
        self._preview.setHtml(self._placeholder_html())
        self._splitter.addWidget(self._preview)

        self._splitter.setSizes([400, 300])
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 1)
        layout.addWidget(self._splitter, stretch=1)

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
        self._log.setFixedHeight(120)
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

        raw_files = [Path(f) for f in files]
        self._log.append(f"已選擇 {len(raw_files)} 個檔案，解析中...")

        reader = MSGReader()

        # 顯示解析進度條
        self._progress.setVisible(True)
        self._progress.setMaximum(len(raw_files))
        self._progress.setValue(0)

        # 先解析所有檔案，再按寄件日期排序（舊→新），確保 thread 偵測能正確連結
        parsed: list[tuple[Path, object, str | None]] = []
        for i, file_path in enumerate(raw_files):
            email, parse_err = reader.read_single_file_verbose(file_path)
            parsed.append((file_path, email, parse_err))
            self._progress.setValue(i + 1)
            # 強制刷新 UI，讓進度條即時更新
            self._progress.repaint()

        self._progress.setVisible(False)
        self._log.append(f"解析完成，依日期排序中...")
        parsed.sort(key=lambda t: (t[1] is None, str(t[1].date) if t[1] and t[1].date else ""))

        self._pending_files = [t[0] for t in parsed]
        self._emails = [t[1] for t in parsed]
        self._table.setRowCount(0)

        for file_path, email, parse_err in parsed:
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
                self._log.append(f"⚠️ {file_path.name} 解析失敗：{parse_err}")

        self._log.append(f"解析完成，共 {self._table.rowCount()} 封信件")

    def _placeholder_html(self) -> str:
        return (
            f"<html><head><style>{self._BASE_STYLE}</style></head>"
            "<body><p style='color:#64748b'>點選信件以預覽內容…</p></body></html>"
        )

    def _wrap_plain(self, text: str) -> str:
        return (
            f"<html><head><style>{self._BASE_STYLE}</style></head>"
            f"<body><pre>{escape(text)}</pre></body></html>"
        )

    def _inject_style(self, html: str) -> str:
        """在信件 HTML 中注入深色背景 CSS。"""
        tag = f"<style>{self._BASE_STYLE}</style>"
        lower = html.lower()
        if "<head>" in lower:
            pos = lower.index("<head>") + len("<head>")
            return html[:pos] + tag + html[pos:]
        return f"<html><head>{tag}</head><body>{html}</body></html>"

    def _on_row_selected(self) -> None:
        """顯示選中行的信件內容（HTML 優先，fallback 純文字）。"""
        selected = self._table.selectedItems()
        if not selected:
            return
        row = self._table.row(selected[0])
        if row >= len(self._emails):
            return
        email = self._emails[row]
        if email is None:
            self._preview.setHtml(self._wrap_plain("（無法讀取信件內容）"))
            return
        if email.html_body:
            self._preview.setHtml(self._inject_style(email.html_body))
        else:
            self._preview.setHtml(self._wrap_plain(email.body))

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

        label_map = {"created": "已匯入", "replied": "已回覆標記", "skipped": "略過（找不到父案件）"}
        done_statuses = set(label_map.values())

        manager = CaseManager(self._conn)
        success = 0
        fail = 0

        self._progress.setVisible(True)
        self._progress.setMaximum(len(rows))
        self._progress.setValue(0)

        for i, row in enumerate(rows):
            status_item = self._table.item(row, 4)
            if status_item and status_item.text() in done_statuses:
                self._progress.setValue(i + 1)
                continue

            if row >= len(self._emails):
                fail += 1
                self._progress.setValue(i + 1)
                continue

            file_path = self._pending_files[row] if row < len(self._pending_files) else Path("")
            email = self._emails[row]

            if email:
                try:
                    case, action = manager.import_email(
                        subject=email.subject,
                        body=email.body,
                        sender_email=email.sender,
                        to_recipients=email.to_recipients,
                        sent_time=str(email.date) if email.date else None,
                        source_filename=email.source_file,
                        progress_note=email.progress_note,
                    )
                    label = label_map.get(action, "已匯入")
                    self._table.setItem(row, 4, QTableWidgetItem(label))
                    if email.thread_question and self._kms:
                        self._kms.extract_qa_from_email(email, case.case_id if case else None)
                    success += 1
                except Exception as e:
                    self._table.setItem(row, 4, QTableWidgetItem("匯入失敗"))
                    tb = traceback.format_exc()
                    self._log.append(f"❌ {file_path.name}: {e}\n{tb}")
                    fail += 1
            else:
                self._table.setItem(row, 4, QTableWidgetItem("讀取失敗"))
                self._log.append(f"❌ {file_path.name}: 讀取 .msg 失敗（可能為加密或格式不支援）")
                fail += 1

            self._progress.setValue(i + 1)

        self._progress.setVisible(False)
        self._log.append(f"✅ 完成：成功 {success} 件，失敗 {fail} 件")
