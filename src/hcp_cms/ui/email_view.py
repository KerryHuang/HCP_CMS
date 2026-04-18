"""Email processing view."""

from __future__ import annotations

import contextlib
import sqlite3
import threading
import traceback
import warnings
from html import escape
from pathlib import Path

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.case_manager import CaseManager
from hcp_cms.core.kms_engine import KMSEngine
from hcp_cms.data.repositories import ProcessedFileRepository
from hcp_cms.services.credential import CredentialManager
from hcp_cms.services.mail.base import MailProvider, RawEmail
from hcp_cms.services.mail.msg_reader import MSGReader
from hcp_cms.ui.sent_mail_tab import SentMailTab
from hcp_cms.ui.theme import ColorPalette, ThemeManager


class EmailView(QWidget):
    """Email processing page."""

    navigate_to_cases = Signal()  # 匯入完成後請求跳轉至案件管理
    _worker_done = Signal(object)  # 背景工作完成（跨線程安全）
    _worker_error = Signal(str)  # 背景工作失敗
    _worker_log = Signal(str)   # 背景執行緒的中間診斷訊息
    _mail_arrived = Signal(object)  # 逐封信件串流顯示

    def _build_base_style(self, p: ColorPalette) -> str:
        """根據當前主題生成 HTML 預覽 CSS。"""
        return (
            f"body{{margin:16px;font-family:'Segoe UI',Arial,sans-serif;"
            f"font-size:13px;background:{p.bg_secondary};color:{p.text_secondary};line-height:1.6;}}"
            f"pre{{white-space:pre-wrap;word-break:break-word;}}"
            f"a{{color:{p.accent};}}"
            f"blockquote{{border-left:3px solid {p.border_primary};"
            f"margin:0;padding-left:12px;color:{p.text_tertiary};}}"
            f"img{{max-width:100%;}}"
        )

    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        kms: KMSEngine | None = None,
        theme_mgr: ThemeManager | None = None,
    ) -> None:
        super().__init__()
        self._conn = conn
        self._kms = kms
        self._theme_mgr = theme_mgr
        self._creds = CredentialManager()
        self._provider: MailProvider | None = None
        self._pending_files: list[Path] = []
        self._emails: list[RawEmail | None] = []  # 與 _pending_files 平行
        self._auto_connected = False
        self._auto_fetch_after_connect = False
        self._setup_ui()
        if theme_mgr:
            self._apply_theme(theme_mgr.current_palette())
            theme_mgr.theme_changed.connect(self._apply_theme)

    def try_auto_connect(self) -> None:
        """由外部（如 MainWindow）呼叫，首次進入頁面時自動連線。"""
        if self._auto_connected:
            return
        self._auto_connected = True
        from PySide6.QtCore import QTimer

        QTimer.singleShot(300, self._auto_connect_if_configured)

    def _auto_connect_if_configured(self) -> None:
        """若有設定帳密，自動觸發連線。"""
        has_imap = bool(self._creds.retrieve("mail_imap_host"))
        has_exchange = bool(self._creds.retrieve("mail_exchange_email"))
        if has_imap or has_exchange:
            if has_imap:
                self._provider_combo.setCurrentText("IMAP")
            else:
                self._provider_combo.setCurrentText("Exchange")
            self._auto_fetch_after_connect = True
            self._on_connect()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        self._title = QLabel("📧 信件處理")
        layout.addWidget(self._title)

        # 可折疊連線設定
        self._conn_toggle_btn = QPushButton("⚙ 連線設定  ▲")
        self._conn_toggle_btn.clicked.connect(self._on_toggle_conn)
        layout.addWidget(self._conn_toggle_btn)

        self._conn_content = QWidget()
        conn_layout = QHBoxLayout(self._conn_content)
        conn_layout.setContentsMargins(0, 4, 0, 4)

        self._provider_combo = QComboBox()
        self._provider_combo.addItems(["IMAP", "Exchange", ".msg 手動匯入"])
        conn_layout.addWidget(QLabel("來源:"))
        conn_layout.addWidget(self._provider_combo)

        self._connect_btn = QPushButton("🔗 連線")
        self._connect_btn.clicked.connect(self._on_connect)
        conn_layout.addWidget(self._connect_btn)

        layout.addWidget(self._conn_content)
        layout.addSpacing(4)

        self._connected_proto: str = ""
        self._connected_user: str = ""

        # Tab widget：收件處理 / 寄件備份
        self._tab_widget = QTabWidget()
        inbox_widget = QWidget()
        inbox_layout = QVBoxLayout(inbox_widget)
        inbox_layout.setContentsMargins(0, 8, 0, 0)

        # Date navigator — ← [日期] →
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("日期:"))

        prev_week_btn = QPushButton("◀◀")
        prev_week_btn.setFixedWidth(42)
        prev_week_btn.setToolTip("前一週")
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
        next_week_btn.setToolTip("後一週")
        next_week_btn.clicked.connect(self._on_next_week)
        filter_layout.addWidget(next_week_btn)

        today_btn = QPushButton("今天")
        today_btn.setFixedWidth(50)
        today_btn.clicked.connect(self._on_today)
        filter_layout.addWidget(today_btn)

        self._fetch_btn = QPushButton("📥 取得信件列表")
        self._fetch_btn.clicked.connect(self._on_fetch)
        filter_layout.addWidget(self._fetch_btn)

        import_btn = QPushButton("📁 匯入 .msg 檔案")
        import_btn.clicked.connect(self._on_import_msg)
        filter_layout.addWidget(import_btn)

        inbox_layout.addLayout(filter_layout)

        # 自訂區間列 — 起 [DateEdit] ~ 迄 [DateEdit] [載入]
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("區間：起"))
        self._range_start_edit = QDateEdit(QDate.currentDate().addDays(-30))
        self._range_start_edit.setCalendarPopup(True)
        self._range_start_edit.setDisplayFormat("yyyy/MM/dd")
        range_layout.addWidget(self._range_start_edit)
        range_layout.addWidget(QLabel("~  迄"))
        self._range_end_edit = QDateEdit(QDate.currentDate())
        self._range_end_edit.setCalendarPopup(True)
        self._range_end_edit.setDisplayFormat("yyyy/MM/dd")
        range_layout.addWidget(self._range_end_edit)
        range_load_btn = QPushButton("📥 載入區間")
        range_load_btn.setToolTip("依指定起迄日期載入信件")
        range_load_btn.clicked.connect(self._on_range_fetch)
        range_layout.addWidget(range_load_btn)
        range_layout.addStretch()
        inbox_layout.addLayout(range_layout)

        # Email list — 5 columns: checkbox + 寄件人 + 主旨 + 日期 + 狀態
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["✓", "寄件人", "主旨", "日期", "狀態"])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 30)
        header.setStretchLastSection(False)
        # 1~4 欄用 Stretch，透過 resizeEvent 設定比例
        for col in range(1, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        self._table.resizeEvent = self._on_table_resize

        # 全選 / 全不選
        select_row = QHBoxLayout()
        select_all_btn = QPushButton("☑ 全選")
        select_all_btn.setFixedWidth(80)
        select_all_btn.clicked.connect(lambda: self._toggle_all_checks(True))
        select_none_btn = QPushButton("☐ 全不選")
        select_none_btn.setFixedWidth(80)
        select_none_btn.clicked.connect(lambda: self._toggle_all_checks(False))
        select_row.addWidget(select_all_btn)
        select_row.addWidget(select_none_btn)
        select_row.addStretch()
        inbox_layout.addLayout(select_row)

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
        inbox_layout.addWidget(self._splitter, stretch=1)

        # Actions
        action_layout = QHBoxLayout()
        self._import_selected_btn = QPushButton("✅ 匯入勾選")
        self._import_selected_btn.clicked.connect(self._on_import_selected)
        action_layout.addWidget(self._import_selected_btn)
        self._import_all_btn = QPushButton("📥 全部匯入")
        self._import_all_btn.clicked.connect(self._on_import_all)
        action_layout.addWidget(self._import_all_btn)
        inbox_layout.addLayout(action_layout)

        # Progress
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        inbox_layout.addWidget(self._progress)

        # Log
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(120)
        self._log.setPlaceholderText("處理日誌...")
        inbox_layout.addWidget(self._log)
        self._worker_log.connect(self._log.append, Qt.ConnectionType.QueuedConnection)

        # Schedule settings（屬於收件排程，放在收件 tab 內）
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
        inbox_layout.addWidget(schedule_group)

        self._tab_widget.addTab(inbox_widget, "📥 收件處理")

        # 寄件備份 tab
        self._sent_tab = SentMailTab(conn=self._conn, theme_mgr=self._theme_mgr)
        self._tab_widget.addTab(self._sent_tab, "📤 寄件備份")

        layout.addWidget(self._tab_widget, stretch=1)

    def _run_in_background(self, fn: object, on_done: object, on_error: object) -> None:
        """用 threading.Thread 在背景執行 fn，完成後透過 Signal 回到 UI 線程。"""
        self._connect_btn.setEnabled(False)
        self._fetch_btn.setEnabled(False)
        self._progress.setMaximum(0)
        self._progress.setVisible(True)

        # 先斷開舊 slot 再建新連線（首次無連線時靜默跳過）
        with warnings.catch_warnings(), contextlib.suppress(RuntimeError):
            warnings.simplefilter("ignore", RuntimeWarning)
            self._worker_done.disconnect()
        with warnings.catch_warnings(), contextlib.suppress(RuntimeError):
            warnings.simplefilter("ignore", RuntimeWarning)
            self._worker_error.disconnect()
        self._worker_done.connect(on_done, Qt.ConnectionType.QueuedConnection)
        self._worker_error.connect(on_error, Qt.ConnectionType.QueuedConnection)

        def _thread_target() -> None:
            try:
                result = fn()
                self._worker_done.emit(result)
            except Exception as e:
                self._worker_error.emit(str(e))

        t = threading.Thread(target=_thread_target, daemon=True)
        t.start()

    def _restore_ui(self) -> None:
        """恢復 UI 狀態。"""
        self._progress.setVisible(False)
        self._progress.setMaximum(100)
        self._connect_btn.setEnabled(True)
        self._fetch_btn.setEnabled(True)

    def _on_toggle_conn(self) -> None:
        """切換連線設定面板展開/收合。"""
        self._conn_content.setVisible(not self._conn_content.isVisible())
        self._update_conn_toggle()

    def _update_conn_toggle(self) -> None:
        """更新折疊按鈕文字與樣式。"""
        from hcp_cms.ui.theme import DARK_PALETTE

        p = getattr(self, "_current_palette", None) or DARK_PALETTE
        arrow = "▲" if self._conn_content.isVisible() else "▼"
        if self._connected_proto:
            self._conn_toggle_btn.setText(f"✅ {self._connected_proto}  {self._connected_user}  {arrow}")
            self._conn_toggle_btn.setStyleSheet(
                f"QPushButton {{ text-align: left; padding: 6px 12px;"
                f" background: {p.bg_secondary}; color: {p.success};"
                f" border: 1px solid #166534; border-radius: 6px; font-size: 13px; }}"
                f"QPushButton:hover {{ background: {p.bg_hover}; }}"
            )
        else:
            self._conn_toggle_btn.setText(f"⚙ 連線設定  {arrow}")
            self._conn_toggle_btn.setStyleSheet(
                f"QPushButton {{ text-align: left; padding: 6px 12px;"
                f" background: {p.bg_secondary}; color: {p.text_tertiary};"
                f" border: 1px solid {p.border_primary}; border-radius: 6px; font-size: 13px; }}"
                f"QPushButton:hover {{ background: {p.bg_hover}; color: {p.text_secondary}; }}"
            )

    def _on_connect(self) -> None:
        """根據所選協定建立信件連線。"""
        proto = self._provider_combo.currentText()

        if proto == ".msg 手動匯入":
            self._log.append("📁 .msg 模式不需連線，請直接使用「匯入 .msg 檔案」按鈕。")
            return

        # 斷開舊連線
        if self._provider:
            try:
                self._provider.disconnect()
            except Exception:
                pass
            self._provider = None

        pending_user: str = ""
        if proto == "IMAP":
            host = self._creds.retrieve("mail_imap_host")
            if not host:
                self._log.append("❌ 尚未設定 IMAP 帳密，請先至「系統設定」頁面填寫。")
                return
            port_str = self._creds.retrieve("mail_imap_port") or "993"
            ssl_str = self._creds.retrieve("mail_imap_ssl") or "true"
            user = self._creds.retrieve("mail_imap_user") or ""
            pwd = self._creds.retrieve("mail_imap_password") or ""
            pending_user = user

            from hcp_cms.services.mail.imap import IMAPProvider

            provider = IMAPProvider(
                host=host,
                port=int(port_str),
                use_ssl=ssl_str.lower() == "true",
            )
            provider.set_credentials(user, pwd)
            self._log.append(f"正在連線 IMAP {host}:{port_str} ...")
        else:  # Exchange
            email_addr = self._creds.retrieve("mail_exchange_email")
            if not email_addr:
                self._log.append("❌ 尚未設定 Exchange 帳密，請先至「系統設定」頁面填寫。")
                return
            server = self._creds.retrieve("mail_exchange_server") or ""
            user = self._creds.retrieve("mail_exchange_user") or ""
            pwd = self._creds.retrieve("mail_exchange_password") or ""
            pending_user = email_addr

            from hcp_cms.services.mail.exchange import ExchangeProvider

            provider = ExchangeProvider(server=server, email_address=email_addr)
            provider.set_credentials(user, pwd)
            self._log.append(f"正在連線 Exchange {email_addr} ...")

        self._connect_btn.setText("⏳ 連線中...")

        def do_connect() -> dict:
            ok = provider.connect()
            return {"ok": ok, "provider": provider}

        def on_done(result: object) -> None:
            self._restore_ui()
            self._connect_btn.setText("🔗 連線")
            if result["ok"]:
                self._provider = result["provider"]
                self._log.append(f"✅ {proto} 連線成功！")
                self._sent_tab.set_provider(self._provider)
                self._connected_proto = proto
                self._connected_user = pending_user
                self._conn_content.hide()
                self._update_conn_toggle()
                if self._auto_fetch_after_connect:
                    self._auto_fetch_after_connect = False
                    self._on_fetch()
            else:
                self._auto_fetch_after_connect = False
                self._log.append(f"❌ {proto} 連線失敗，請確認帳密是否正確。")

        def on_error(msg: str) -> None:
            self._restore_ui()
            self._connect_btn.setText("🔗 連線")
            self._auto_fetch_after_connect = False
            self._log.append(f"❌ 連線發生例外：{msg}")

        self._run_in_background(do_connect, on_done, on_error)

    def _on_prev_week(self) -> None:
        """查詢當前日期起往前 7 天的範圍，並將日期移到起始日。"""
        if self._provider and self._fetch_btn.isEnabled():
            from datetime import datetime

            d = self._date_edit.date()
            until = datetime(d.year(), d.month(), d.day(), 23, 59, 59)
            start = d.addDays(-6)
            since = datetime(start.year(), start.month(), start.day())
            self._date_edit.setDate(start)
            self._on_fetch(since=since, until=until)

    def _on_prev_day(self) -> None:
        """切到前一天並自動取得列表。"""
        if not self._fetch_btn.isEnabled():
            return
        self._date_edit.setDate(self._date_edit.date().addDays(-1))
        if self._provider:
            self._on_fetch()

    def _on_next_day(self) -> None:
        """切到後一天並自動取得列表。"""
        if not self._fetch_btn.isEnabled():
            return
        self._date_edit.setDate(self._date_edit.date().addDays(1))
        if self._provider:
            self._on_fetch()

    def _on_next_week(self) -> None:
        """查詢當前日期起往後 7 天的範圍，並將日期移到結束日。"""
        if self._provider and self._fetch_btn.isEnabled():
            from datetime import datetime

            d = self._date_edit.date()
            since = datetime(d.year(), d.month(), d.day())
            end = d.addDays(6)
            until = datetime(end.year(), end.month(), end.day(), 23, 59, 59)
            self._date_edit.setDate(end)
            self._on_fetch(since=since, until=until)

    def _on_today(self) -> None:
        """回到今天並自動取得列表。"""
        self._date_edit.setDate(QDate.currentDate())
        if self._provider:
            self._on_fetch()

    def _on_range_fetch(self) -> None:
        """依自訂起迄日期載入信件。"""
        if not self._provider:
            return
        from datetime import datetime
        s = self._range_start_edit.date()
        e = self._range_end_edit.date()
        if s > e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "日期錯誤", "起始日期不可晚於迄日期。")
            return
        since = datetime(s.year(), s.month(), s.day())
        until = datetime(e.year(), e.month(), e.day(), 23, 59, 59)
        self._on_fetch(since=since, until=until)

    def _on_fetch(
        self,
        since: object = None,
        until: object = None,
    ) -> None:
        """透過已連線的 provider 取得信件列表。"""
        if not self._provider:
            self._log.append("❌ 請先點「連線」建立連線。")
            return

        from datetime import datetime

        if since is None or until is None:
            d = self._date_edit.date()
            since = datetime(d.year(), d.month(), d.day())
            until = datetime(d.year(), d.month(), d.day(), 23, 59, 59)

        if since.date() == until.date():
            self._log.append(f"正在取得 {since.strftime('%Y/%m/%d')} 的信件...")
        else:
            self._log.append(f"正在取得 {since.strftime('%Y/%m/%d')} ~ {until.strftime('%Y/%m/%d')} 的信件...")
        self._fetch_btn.setText("⏳ 取得中...")

        # 清空表格，準備串流接收
        self._pending_files = []
        self._emails = []
        self._table.setRowCount(0)
        self._fetch_imported_count = 0

        provider = self._provider
        processed_repo = ProcessedFileRepository(self._conn) if self._conn else None

        def on_mail(mail: object) -> None:
            """每收到一封信就即時加入表格。"""
            self._emails.append(mail)
            row = self._table.rowCount()
            self._table.insertRow(row)

            already = False
            if processed_repo and mail.message_id:
                already = processed_repo.exists_by_message_id(mail.message_id)

            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Unchecked if already else Qt.CheckState.Checked)
            self._table.setItem(row, 0, chk_item)

            self._table.setItem(row, 1, QTableWidgetItem(mail.sender))
            self._table.setItem(row, 2, QTableWidgetItem(mail.subject))
            self._table.setItem(row, 3, QTableWidgetItem(str(mail.date) if mail.date else ""))
            self._table.setItem(row, 4, QTableWidgetItem("已匯入" if already else "待匯入"))
            if already:
                self._fetch_imported_count += 1

        # 連接串流 signal
        with warnings.catch_warnings(), contextlib.suppress(RuntimeError):
            warnings.simplefilter("ignore", RuntimeWarning)
            self._mail_arrived.disconnect()
        self._mail_arrived.connect(on_mail, Qt.ConnectionType.QueuedConnection)

        def do_fetch() -> dict:
            # 每次呼叫時重新對 self._mail_arrived 求值，避免 PySide6 BoundSignal
            # 暫存物件被 GC 回收後拋出「Signal source has been deleted」
            def _emit_mail(mail: object) -> None:
                try:
                    self._mail_arrived.emit(mail)
                except RuntimeError:
                    pass  # widget 已關閉，靜默略過

            def _log(msg: str) -> None:
                try:
                    self._worker_log.emit(msg)
                except RuntimeError:
                    pass

            emails = provider.fetch_messages(
                since=since, until=until, on_message=_emit_mail, log_cb=_log
            )
            return {"count": len(emails)}

        def on_done(result: object) -> None:
            self._restore_ui()
            self._fetch_btn.setText("📥 取得信件列表")
            total = self._table.rowCount()
            imported = self._fetch_imported_count
            new_count = total - imported
            self._log.append(f"📥 取得 {total} 封信件（{new_count} 封待匯入，{imported} 封已匯入）")

        def on_error(msg: str) -> None:
            self._restore_ui()
            self._fetch_btn.setText("📥 取得信件列表")
            self._log.append(f"❌ 取得信件失敗：{msg}")

        self._run_in_background(do_fetch, on_done, on_error)

    def _on_table_resize(self, event: object) -> None:
        """依 35:35:15:15 比例調整欄寬。"""
        w = self._table.viewport().width() - 30  # 扣除 ✓ 欄
        if w > 0:
            self._table.setColumnWidth(1, int(w * 0.35))
            self._table.setColumnWidth(2, int(w * 0.35))
            self._table.setColumnWidth(3, int(w * 0.15))
            self._table.setColumnWidth(4, int(w * 0.15))
        QTableWidget.resizeEvent(self._table, event)

    def _toggle_all_checks(self, checked: bool) -> None:
        """全選或全不選所有列的勾選框。全選時跳過狀態為「已匯入」的列。"""
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item:
                if checked:
                    status_item = self._table.item(row, 4)
                    if status_item and status_item.text() == "已匯入":
                        continue
                item.setCheckState(state)

    def _on_import_msg(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "選擇 .msg 檔案", "", "Outlook Messages (*.msg)")
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
        self._log.append("解析完成，依日期排序中...")
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
        from hcp_cms.ui.theme import DARK_PALETTE

        p = getattr(self, "_current_palette", None) or DARK_PALETTE
        style = self._build_base_style(p)
        return (
            f"<html><head><style>{style}</style></head>"
            f"<body><p style='color:{p.text_muted}'>點選信件以預覽內容…</p></body></html>"
        )

    def _wrap_plain(self, text: str) -> str:
        from hcp_cms.ui.theme import DARK_PALETTE

        p = getattr(self, "_current_palette", None) or DARK_PALETTE
        style = self._build_base_style(p)
        return f"<html><head><style>{style}</style></head><body><pre>{escape(text)}</pre></body></html>"

    def _inject_style(self, html: str) -> str:
        """在信件 HTML 中注入背景 CSS。"""
        from hcp_cms.ui.theme import DARK_PALETTE

        p = getattr(self, "_current_palette", None) or DARK_PALETTE
        style = self._build_base_style(p)
        tag = f"<style>{style}</style>"
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
            r
            for r in range(self._table.rowCount())
            if self._table.item(r, 0) is not None and self._table.item(r, 0).checkState() == Qt.CheckState.Checked
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
                    # 取消勾選已匯入的
                    chk = self._table.item(row, 0)
                    if chk:
                        chk.setCheckState(Qt.CheckState.Unchecked)
                    case_id = case.case_id if case else "?"
                    self._log.append(f"  ✅ {case_id} {label}：{email.subject[:40]}")
                    # 記錄到 processed_files 避免重複匯入
                    self._record_processed(email)
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

        if success > 0:
            reply = QMessageBox.question(
                self,
                "匯入完成",
                f"成功匯入 {success} 件案件，是否跳轉至案件管理查看？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.navigate_to_cases.emit()

    def _record_processed(self, email: RawEmail) -> None:
        """將信件記錄到 processed_files，避免重複匯入。"""
        if not self._conn:
            return
        import hashlib

        from hcp_cms.data.models import ProcessedFile

        key = email.message_id or (email.subject + email.sender)
        file_hash = hashlib.sha256(key.encode()).hexdigest()
        repo = ProcessedFileRepository(self._conn)
        repo.insert(
            ProcessedFile(
                file_hash=file_hash,
                filename=email.source_file or "",
                message_id=email.message_id,
            )
        )

    def _apply_theme(self, p: ColorPalette) -> None:
        """套用主題色彩。"""
        self._title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p.text_primary};")
        self._tab_widget.setStyleSheet(
            f"QTabWidget::pane {{ border: none; background: transparent; }}"
            f"QTabBar::tab {{ background: {p.bg_secondary}; color: {p.text_tertiary};"
            f"  padding: 6px 16px; border-bottom: 2px solid transparent; }}"
            f"QTabBar::tab:selected {{ background: {p.bg_secondary}; color: {p.text_primary};"
            f"  border-bottom: 2px solid #3b82f6; }}"
            f"QTabBar::tab:hover:!selected {{ background: {p.bg_hover}; color: {p.text_secondary}; }}"
        )
        self._update_conn_toggle()
        self._current_palette = p
        # 重新套用預覽區的 placeholder HTML
        self._preview.setHtml(self._placeholder_html())
