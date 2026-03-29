"""案件詳情維護對話框 — 3 分頁 QDialog。"""
from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hcp_cms.data.models import MantisTicket
    from hcp_cms.services.mantis.soap import MantisSoapClient

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.case_detail_manager import CaseDetailManager
from hcp_cms.data.models import Case
from hcp_cms.ui.theme import ColorPalette


class CaseDetailDialog(QDialog):
    """3 分頁案件詳情維護對話框。"""

    case_updated = Signal()

    def __init__(
        self,
        conn: sqlite3.Connection,
        case_id: str,
        parent: QWidget | None = None,
        palette: ColorPalette | None = None,
    ) -> None:
        super().__init__(parent)
        from hcp_cms.ui.theme import DARK_PALETTE
        self._palette = palette or DARK_PALETTE
        self._conn = conn
        self._case_id = case_id
        self._manager = CaseDetailManager(conn)
        self._case: Case | None = None
        self.setWindowTitle(f"案件詳情 — {case_id}")
        self.setMinimumSize(900, 650)
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI 建構
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_tab1(), "📋 案件資訊")
        self._tabs.addTab(self._build_tab2(), "📝 補充記錄")
        self._tabs.addTab(self._build_tab3(), "🔧 Mantis 關聯")
        layout.addWidget(self._tabs)
        self._load_case()
        self._tabs.currentChanged.connect(self._on_tab_changed)

    def _build_tab1(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── 捲動區域（含所有表單欄位）──────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 8, 8, 8)

        # 兩欄式表單
        cols = QHBoxLayout()
        left = QFormLayout()
        right = QFormLayout()

        # 左欄
        self._f_case_id = QLabel()
        self._f_subject = QLineEdit()
        self._f_company = QLineEdit()
        self._f_contact = QLineEdit()
        self._f_sent_time = QLineEdit()
        self._f_contact_method = QComboBox()
        self._f_contact_method.addItems(["Email", "電話", "現場"])
        self._f_source = QLabel()

        left.addRow("案件編號：", self._f_case_id)
        left.addRow("主旨：", self._f_subject)
        left.addRow("公司：", self._f_company)
        left.addRow("聯絡人：", self._f_contact)
        left.addRow("寄件時間：", self._f_sent_time)
        left.addRow("聯絡方式：", self._f_contact_method)
        left.addRow("來源：", self._f_source)

        # 右欄
        self._f_status = QComboBox()
        self._f_status.addItems(["處理中", "已回覆", "已完成", "Closed"])
        self._f_status.setEnabled(False)
        self._f_priority = QComboBox()
        self._f_priority.addItems(["高", "中", "低"])
        self._f_issue_type = QLineEdit()
        self._f_error_type = QLineEdit()
        self._f_system_product = QLineEdit()
        self._f_rd_assignee = QLineEdit()
        self._f_handler = QLineEdit()
        self._f_reply_time = QLineEdit()
        self._f_impact_period = QLineEdit()

        right.addRow("狀態：", self._f_status)
        right.addRow("優先：", self._f_priority)
        right.addRow("問題類型：", self._f_issue_type)
        right.addRow("功能模組：", self._f_error_type)
        right.addRow("系統產品：", self._f_system_product)
        right.addRow("技術負責人：", self._f_rd_assignee)
        right.addRow("處理人員：", self._f_handler)
        right.addRow("回覆時間：", self._f_reply_time)
        right.addRow("影響期間：", self._f_impact_period)

        cols.addLayout(left)
        cols.addSpacing(20)
        cols.addLayout(right)
        content_layout.addLayout(cols)

        # 下方全寬
        self._f_progress = QTextEdit()
        self._f_progress.setMinimumHeight(60)
        self._f_progress.setMaximumHeight(90)
        self._f_notes = QTextEdit()
        self._f_notes.setMinimumHeight(60)
        self._f_notes.setMaximumHeight(90)
        self._f_actual_reply = QTextEdit()
        self._f_actual_reply.setMinimumHeight(60)
        self._f_actual_reply.setMaximumHeight(90)

        pf = QFormLayout()
        pf.setVerticalSpacing(8)
        pf.addRow("處理進度：", self._f_progress)
        pf.addRow("備註：", self._f_notes)
        pf.addRow("實際回覆：", self._f_actual_reply)
        self._extra_form = pf
        self._extra_field_widgets: dict[str, QLineEdit] = {}
        content_layout.addLayout(pf)
        content_layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        # 按鈕列（固定在底部，不捲動）
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(8, 4, 8, 4)
        save_btn = QPushButton("💾 儲存")
        save_btn.clicked.connect(self._on_save)
        close_btn = QPushButton("🔒 結案")
        close_btn.clicked.connect(self._on_close_case)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(close_btn)
        outer.addLayout(btn_row)

        return w

    def _build_tab2(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        toolbar = QHBoxLayout()
        add_btn = QPushButton("➕ 新增記錄")
        add_btn.clicked.connect(self._on_add_log)
        toolbar.addWidget(add_btn)
        delete_btn = QPushButton("🗑 刪除記錄")
        delete_btn.clicked.connect(self._on_delete_log)
        toolbar.addWidget(delete_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._log_table = QTableWidget(0, 5)
        self._log_table.setHorizontalHeaderLabels(
            ["時間", "方向", "記錄人", "Mantis 參照", "內容摘要"]
        )
        self._log_table.horizontalHeader().setStretchLastSection(True)
        self._log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._log_table)

        return w

    def _refresh_log_table(self) -> None:
        logs = self._manager.list_logs(self._case_id)
        self._log_table.setRowCount(len(logs))
        for i, log in enumerate(logs):
            self._log_table.setItem(i, 0, QTableWidgetItem(log.logged_at))
            self._log_table.setItem(i, 1, QTableWidgetItem(log.direction))
            self._log_table.setItem(i, 2, QTableWidgetItem(log.logged_by or ""))
            self._log_table.setItem(i, 3, QTableWidgetItem(log.mantis_ref or ""))
            self._log_table.setItem(i, 4, QTableWidgetItem((log.content or "")[:60]))

    def _on_add_log(self) -> None:
        dlg = CaseLogAddDialog(parent=self)
        if dlg.exec():
            data = dlg.get_data()
            try:
                self._manager.add_log(
                    case_id=self._case_id,
                    direction=data["direction"],
                    content=data["content"],
                    mantis_ref=data["mantis_ref"] or None,
                    logged_by=data["logged_by"] or None,
                )
                self._refresh_log_table()
            except Exception as e:
                QMessageBox.critical(self, "新增記錄失敗", str(e))

    def _on_delete_log(self) -> None:
        rows = self._log_table.selectionModel().selectedRows()
        if not rows:
            return
        row_idx = rows[0].row()
        logs = self._manager.list_logs(self._case_id)
        if row_idx >= len(logs):
            return
        log_id = logs[row_idx].log_id
        try:
            self._manager.delete_log(log_id)
            self._refresh_log_table()
        except Exception as e:
            QMessageBox.critical(self, "刪除記錄失敗", str(e))

    @staticmethod
    def _status_colors(status: str) -> tuple[str, str]:
        """依 Mantis 狀態字串回傳 (背景色, 文字色)。"""
        s = status.lower()
        if "resolved" in s or "已解決" in s:
            return "#166534", "#bbf7d0"
        if "closed" in s or "已關閉" in s:
            return "#1f2937", "#9ca3af"
        if "assigned" in s or "in progress" in s or "處理中" in s:
            return "#7c2d12", "#fed7aa"
        if "acknowledged" in s or "confirmed" in s or "已確認" in s:
            return "#78350f", "#fde68a"
        if "feedback" in s or "回饋" in s:
            return "#3730a3", "#c7d2fe"
        # new / 其他
        return "#1e3a5f", "#93c5fd"

    def _build_tab3(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # ── 工具列 ──
        toolbar = QHBoxLayout()
        self._ticket_input = QLineEdit()
        self._ticket_input.setPlaceholderText("輸入 Ticket 編號")
        self._ticket_input.setFixedWidth(150)
        link_btn = QPushButton("🔗 連結")
        link_btn.clicked.connect(self._on_link_mantis)
        sync_btn = QPushButton("🔄 同步選取")
        sync_btn.clicked.connect(self._on_sync_mantis)
        unlink_btn = QPushButton("🗑 取消連結")
        unlink_btn.clicked.connect(self._on_unlink_mantis)
        toolbar.addWidget(self._ticket_input)
        toolbar.addWidget(link_btn)
        toolbar.addWidget(sync_btn)
        toolbar.addWidget(unlink_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ── 上方表格（5欄） ──
        self._mantis_table = QTableWidget(0, 5)
        self._mantis_table.setHorizontalHeaderLabels(
            ["票號", "狀態", "摘要", "處理人", "最後同步"]
        )
        self._mantis_table.horizontalHeader().setStretchLastSection(True)
        self._mantis_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._mantis_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._mantis_table.setColumnWidth(0, 70)
        self._mantis_table.setColumnWidth(1, 90)
        self._mantis_table.setColumnWidth(3, 80)
        self._mantis_table.setColumnWidth(4, 140)
        self._mantis_table.itemSelectionChanged.connect(
            lambda: self._on_mantis_table_row_changed(self._mantis_table.currentRow())
        )
        layout.addWidget(self._mantis_table)

        # ── 下方詳情面板（常駐） ──
        detail_frame = QFrame()
        detail_frame.setStyleSheet(
            f"QFrame {{ background-color: {self._palette.bg_secondary}; border: 1px solid {self._palette.border_primary}; border-radius: 6px; }}"
        )
        detail_layout = QVBoxLayout(detail_frame)
        detail_layout.setContentsMargins(12, 10, 12, 10)

        # 標題列
        self._detail_title = QLabel("請點選上方 Ticket 查看詳情")
        self._detail_title.setStyleSheet(f"color: {self._palette.text_faint}; font-size: 12px;")
        detail_layout.addWidget(self._detail_title)

        # 8格 Grid（3欄×3行，最後一行 2 格）
        self._detail_grid_widget = QWidget()
        grid = QGridLayout(self._detail_grid_widget)
        grid.setContentsMargins(0, 6, 0, 6)
        grid.setHorizontalSpacing(20)
        self._detail_grid_widget.setVisible(False)

        self._detail_labels: dict[str, QLabel] = {}
        fields = [
            ("嚴重性", "severity"), ("優先", "priority"), ("回報者", "reporter"),
            ("建立時間", "created_time"), ("🎯 目標版本", "planned_fix"), ("✅ 修復版本", "actual_fix"),
            ("🕐 最後更新", "last_updated"), ("處理人", "handler"),
        ]
        for idx, (label_text, key) in enumerate(fields):
            row, col = divmod(idx, 3)  # 每行 3 欄
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {self._palette.text_muted}; font-size: 10px;")
            val = QLabel("—")
            val.setStyleSheet(f"color: {self._palette.text_secondary}; font-size: 11px;")
            self._detail_labels[key] = val
            cell = QVBoxLayout()
            cell.addWidget(lbl)
            cell.addWidget(val)
            cell.setSpacing(1)
            container = QWidget()
            container.setLayout(cell)
            grid.addWidget(container, row, col)

        detail_layout.addWidget(self._detail_grid_widget)

        # 問題描述
        self._detail_desc_label = QLabel("📝 問題描述")
        self._detail_desc_label.setStyleSheet(f"color: {self._palette.text_muted}; font-size: 10px;")
        self._detail_desc_label.setVisible(False)
        detail_layout.addWidget(self._detail_desc_label)

        self._detail_desc = QTextEdit()
        self._detail_desc.setReadOnly(True)
        self._detail_desc.setMaximumHeight(90)
        self._detail_desc.setStyleSheet(
            f"QTextEdit {{ background: {self._palette.bg_code}; color: {self._palette.text_tertiary}; border: none; font-size: 11px; }}"
        )
        self._detail_desc.setVisible(False)
        detail_layout.addWidget(self._detail_desc)

        # Bug 筆記
        self._detail_notes_label = QLabel("💬 最後 5 條 Bug 筆記")
        self._detail_notes_label.setStyleSheet(f"color: {self._palette.text_muted}; font-size: 10px;")
        self._detail_notes_label.setVisible(False)
        detail_layout.addWidget(self._detail_notes_label)

        self._detail_notes = QTextEdit()
        self._detail_notes.setReadOnly(True)
        self._detail_notes.setMaximumHeight(110)
        self._detail_notes.setStyleSheet(
            f"QTextEdit {{ background: {self._palette.bg_code}; color: {self._palette.text_tertiary}; border: none; font-size: 11px; }}"
        )
        self._detail_notes.setVisible(False)
        detail_layout.addWidget(self._detail_notes)

        # 「查看更多」連結
        self._detail_more_link = QLabel()
        self._detail_more_link.setStyleSheet(f"color: {self._palette.accent}; font-size: 11px;")
        self._detail_more_link.setOpenExternalLinks(False)
        self._detail_more_link.linkActivated.connect(self._on_open_mantis_url)
        self._detail_more_link.setVisible(False)
        detail_layout.addWidget(self._detail_more_link)

        layout.addWidget(detail_frame)
        return w

    def _refresh_mantis_table(self) -> None:
        tickets = self._manager.list_linked_tickets(self._case_id)
        self._mantis_table.setRowCount(len(tickets))
        for i, t in enumerate(tickets):
            self._mantis_table.setItem(i, 0, QTableWidgetItem(t.ticket_id))

            # 狀態（帶背景色）
            status_item = QTableWidgetItem(t.status or "")
            bg, fg = self._status_colors(t.status or "")
            status_item.setBackground(QBrush(QColor(bg)))
            status_item.setForeground(QBrush(QColor(fg)))
            self._mantis_table.setItem(i, 1, status_item)

            self._mantis_table.setItem(i, 2, QTableWidgetItem(t.summary or ""))
            self._mantis_table.setItem(i, 3, QTableWidgetItem(t.handler or ""))
            self._mantis_table.setItem(i, 4, QTableWidgetItem(t.synced_at or ""))
        # 重設詳情面板
        self._refresh_detail_panel(None)

    def _on_mantis_table_row_changed(self, row: int) -> None:
        if row < 0:
            self._refresh_detail_panel(None)
            return
        ticket_id_item = self._mantis_table.item(row, 0)
        if ticket_id_item is None:
            self._refresh_detail_panel(None)
            return
        ticket_id = ticket_id_item.text()
        ticket = self._manager.get_mantis_ticket(ticket_id)
        self._refresh_detail_panel(ticket)

    def _refresh_detail_panel(self, ticket: MantisTicket | None) -> None:
        """填入詳情面板資料；ticket=None 時還原為提示狀態。"""
        no_data = ticket is None
        self._detail_grid_widget.setVisible(not no_data)
        self._detail_desc_label.setVisible(not no_data)
        self._detail_desc.setVisible(not no_data)
        self._detail_notes_label.setVisible(not no_data)
        self._detail_notes.setVisible(not no_data)
        self._detail_more_link.setVisible(False)

        if no_data:
            self._detail_title.setText("請點選上方 Ticket 查看詳情")
            self._detail_title.setStyleSheet(f"color: {self._palette.text_faint}; font-size: 12px;")
            return

        # 標題
        status_text = ticket.status or ""
        self._detail_title.setText(
            f"#{ticket.ticket_id}　{status_text}　{ticket.summary or ''}"
        )
        self._detail_title.setStyleSheet(f"color: {self._palette.accent}; font-weight: bold; font-size: 12px;")

        # 8格資訊
        values = {
            "severity": ticket.severity or "—",
            "priority": ticket.priority or "—",
            "reporter": ticket.reporter or "—",
            "created_time": ticket.created_time or "—",
            "planned_fix": ticket.planned_fix or "—",
            "actual_fix": ticket.actual_fix or "—",
            "last_updated": ticket.last_updated or "—",
            "handler": ticket.handler or "—",
        }
        for key, val in values.items():
            lbl = self._detail_labels.get(key)
            if lbl:
                lbl.setText(val)

        # 描述
        self._detail_desc.setPlainText(ticket.description or "（無描述）")

        # Bug 筆記
        notes_html = ""
        if ticket.notes_json:
            try:
                notes = json.loads(ticket.notes_json)
                for n in notes:
                    reporter = n.get("reporter", "")
                    date = n.get("date_submitted", "")
                    text = n.get("text", "")[:200]
                    notes_html += f"[{date}] {reporter}：{text}\n\n"
            except (json.JSONDecodeError, AttributeError):
                notes_html = "（筆記解析失敗）"
        self._detail_notes.setPlainText(notes_html or "（無筆記）")

        # 「查看更多」連結
        count = ticket.notes_count or 0
        if count > 5:
            self._detail_more_link.setVisible(True)
            self._detail_more_link.setText(
                f'<a href="{ticket.ticket_id}">📎 尚有更多筆記（共 {count} 條），點此在 Mantis 查看完整記錄</a>'
            )

    def _on_open_mantis_url(self, ticket_id: str) -> None:
        """開啟 Mantis 原始 Ticket 頁面。"""
        from hcp_cms.services.credential import CredentialManager
        creds = CredentialManager()
        base = creds.retrieve("mantis_url") or ""
        if not base:
            QMessageBox.warning(self, "未設定", "請先在系統設定填寫 Mantis URL。")
            return
        base = base.rstrip("/")
        url = f"{base}/view.php?id={ticket_id}"
        QDesktopServices.openUrl(QUrl(url))

    def _on_link_mantis(self) -> None:
        ticket_id = self._ticket_input.text().strip()
        if not ticket_id:
            return
        # 先嘗試直接連結（本地已有此 Ticket）
        ok = self._manager.link_mantis(self._case_id, ticket_id)
        if ok:
            self._ticket_input.clear()
            self._refresh_mantis_table()
            return
        # 本地沒有 → 嘗試從 Mantis SOAP 自動抓取再連結
        client = self._build_mantis_client()
        if client is None:
            QMessageBox.warning(
                self, "找不到 Ticket",
                f"Ticket {ticket_id} 不在本地資料庫，且尚未設定 Mantis 連線。\n"
                "請至「系統設定」→「Mantis SOAP 連線設定」填寫帳密後重試。"
            )
            return
        result = self._manager.sync_mantis_ticket(ticket_id, client=client)
        if result is None:
            err = getattr(client, "last_error", "") or "請確認票號是否正確。"
            QMessageBox.warning(
                self, "同步失敗",
                f"Ticket {ticket_id} 無法從 Mantis 取得。\n{err}"
            )
            return
        # 同步成功後再連結
        ok = self._manager.link_mantis(self._case_id, ticket_id)
        if ok:
            self._ticket_input.clear()
            self._refresh_mantis_table()
        else:
            QMessageBox.warning(self, "連結失敗", f"Ticket {ticket_id} 同步成功但連結失敗，請重試。")

    def _on_unlink_mantis(self) -> None:
        rows = self._mantis_table.selectionModel().selectedRows()
        if not rows:
            return
        ticket_id = self._mantis_table.item(rows[0].row(), 0).text()
        self._manager.unlink_mantis(self._case_id, ticket_id)
        self._refresh_mantis_table()

    def _build_mantis_client(self) -> MantisSoapClient | None:
        """從 keyring 讀取憑證並建立 MantisSoapClient，失敗時回傳 None。"""
        try:
            from urllib.parse import urlparse

            from hcp_cms.services.credential import CredentialManager
            from hcp_cms.services.mantis.soap import MantisSoapClient

            creds = CredentialManager()
            url = creds.retrieve("mantis_url") or ""
            user = creds.retrieve("mantis_user") or ""
            pwd = creds.retrieve("mantis_password") or ""
            if not url:
                return None
            # 自動萃取 base URL
            parsed = urlparse(url)
            path = parsed.path
            if ".php" in path:
                path = path[:path.rfind("/")]
            base_url = f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/")
            client = MantisSoapClient(base_url, user, pwd)
            client.connect()
            return client
        except Exception:
            return None

    def _on_sync_mantis(self) -> None:
        rows = self._mantis_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "提示", "請先選取要同步的 Ticket。")
            return
        ticket_id = self._mantis_table.item(rows[0].row(), 0).text()
        client = self._build_mantis_client()
        result = self._manager.sync_mantis_ticket(ticket_id, client=client)
        if result is None:
            QMessageBox.warning(self, "同步失敗", "無法連線至 Mantis，或 Mantis 設定未完成。")
        else:
            self._refresh_mantis_table()

    # ------------------------------------------------------------------
    # 資料載入
    # ------------------------------------------------------------------

    def _load_case(self) -> None:
        case = self._manager.get_case(self._case_id)
        if case is None:
            return
        self._case = case
        self._f_case_id.setText(case.case_id)
        self._f_subject.setText(case.subject or "")
        self._f_company.setText(case.company_id or "")
        self._f_contact.setText(case.contact_person or "")
        self._f_sent_time.setText(case.sent_time or "")
        idx = self._f_contact_method.findText(case.contact_method or "Email")
        self._f_contact_method.setCurrentIndex(max(idx, 0))
        self._f_source.setText(case.source or "")
        idx = self._f_status.findText(case.status)
        self._f_status.setCurrentIndex(max(idx, 0))
        idx = self._f_priority.findText(case.priority)
        self._f_priority.setCurrentIndex(max(idx, 0))
        self._f_issue_type.setText(case.issue_type or "")
        self._f_error_type.setText(case.error_type or "")
        self._f_system_product.setText(case.system_product or "")
        self._f_rd_assignee.setText(case.rd_assignee or "")
        self._f_handler.setText(case.handler or "")
        self._f_reply_time.setText(case.reply_time or "")
        self._f_impact_period.setText(case.impact_period or "")
        self._f_progress.setPlainText(case.progress or "")
        self._f_notes.setPlainText(case.notes or "")
        self._f_actual_reply.setPlainText(case.actual_reply or "")
        self._refresh_extra_fields()

    def _refresh_extra_fields(self) -> None:
        """清除舊自訂欄 widget，依目前 DB 自訂欄重新建立。"""
        from hcp_cms.core.custom_column_manager import CustomColumnManager

        # 清除舊 widget（從 form layout 底部移除 len(_extra_field_widgets) 列）
        for _ in range(len(self._extra_field_widgets)):
            self._extra_form.removeRow(self._extra_form.rowCount() - 1)
        self._extra_field_widgets.clear()

        if self._case is None:
            return

        custom_cols = CustomColumnManager(self._conn).list_columns()
        for col in custom_cols:
            le = QLineEdit(self._case.extra_fields.get(col.col_key) or "")
            le.setMinimumHeight(30)
            self._extra_form.addRow(f"{col.col_label}：", le)
            self._extra_field_widgets[col.col_key] = le

    def _collect_case(self) -> Case:
        if self._case is None:
            raise RuntimeError("案件資料尚未載入")
        case = self._case
        case.subject = self._f_subject.text()
        case.company_id = self._f_company.text() or None
        case.contact_person = self._f_contact.text() or None
        case.sent_time = self._f_sent_time.text() or None
        case.contact_method = self._f_contact_method.currentText()
        case.status = self._f_status.currentText()
        case.priority = self._f_priority.currentText()
        case.issue_type = self._f_issue_type.text() or None
        case.error_type = self._f_error_type.text() or None
        case.system_product = self._f_system_product.text() or None
        case.rd_assignee = self._f_rd_assignee.text() or None
        case.handler = self._f_handler.text() or None
        case.reply_time = self._f_reply_time.text() or None
        case.impact_period = self._f_impact_period.text() or None
        case.progress = self._f_progress.toPlainText() or None
        case.notes = self._f_notes.toPlainText() or None
        case.actual_reply = self._f_actual_reply.toPlainText() or None
        return case

    # ------------------------------------------------------------------
    # Slot
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        try:
            self._manager.update_case(self._collect_case())
            # 儲存自訂欄
            for col_key, le in self._extra_field_widgets.items():
                val = le.text().strip() or None
                self._manager.update_extra_field(self._case_id, col_key, val)
            self._load_case()
            self.case_updated.emit()
        except Exception as e:
            QMessageBox.critical(self, "儲存失敗", str(e))

    def _on_close_case(self) -> None:
        try:
            self._manager.close_case(self._case_id)
            self._load_case()
            self.case_updated.emit()
        except Exception as e:
            QMessageBox.critical(self, "操作失敗", str(e))

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            self._refresh_log_table()
        elif index == 2:
            self._refresh_mantis_table()


class CaseLogAddDialog(QDialog):
    """新增補充記錄的小對話框。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新增補充記錄")
        self.setMinimumWidth(500)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QFormLayout(self)

        self._direction = QComboBox()
        self._direction.addItems(["客戶來信", "CS 回覆", "內部討論"])
        layout.addRow("方向：", self._direction)

        self._content = QTextEdit()
        self._content.setMinimumHeight(120)
        self._content.textChanged.connect(self._on_content_changed)
        layout.addRow("內容：", self._content)

        self._mantis_ref = QLineEdit()
        self._mantis_ref.setPlaceholderText("可空")
        layout.addRow("Mantis 編號：", self._mantis_ref)

        self._logged_by = QLineEdit()
        self._logged_by.setPlaceholderText("可空")
        layout.addRow("記錄人：", self._logged_by)

        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("儲存")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._save_btn)
        layout.addRow(btn_row)

    def _on_content_changed(self) -> None:
        self._save_btn.setEnabled(bool(self._content.toPlainText().strip()))

    def get_data(self) -> dict[str, str | None]:
        return {
            "direction": self._direction.currentText(),
            "content": self._content.toPlainText().strip(),
            "mantis_ref": self._mantis_ref.text().strip(),
            "logged_by": self._logged_by.text().strip(),
        }
