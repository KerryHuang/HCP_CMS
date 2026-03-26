"""案件詳情維護對話框 — 3 分頁 QDialog。"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.case_detail_manager import CaseDetailManager
from hcp_cms.data.models import Case


class CaseDetailDialog(QDialog):
    """3 分頁案件詳情維護對話框。"""

    case_updated = Signal()

    def __init__(
        self,
        conn: sqlite3.Connection,
        case_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
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
        outer.addLayout(cols)

        # 下方全寬
        self._f_progress = QTextEdit()
        self._f_progress.setMaximumHeight(80)
        self._f_notes = QTextEdit()
        self._f_notes.setMaximumHeight(80)
        self._f_actual_reply = QTextEdit()
        self._f_actual_reply.setMaximumHeight(80)

        pf = QFormLayout()
        pf.addRow("處理進度：", self._f_progress)
        pf.addRow("備註：", self._f_notes)
        pf.addRow("實際回覆：", self._f_actual_reply)
        self._extra_form = pf
        self._extra_field_widgets: dict[str, QLineEdit] = {}
        outer.addLayout(pf)

        # 按鈕列
        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾 儲存")
        save_btn.clicked.connect(self._on_save)
        replied_btn = QPushButton("✅ 標記已回覆")
        replied_btn.clicked.connect(self._on_mark_replied)
        close_btn = QPushButton("🔒 結案")
        close_btn.clicked.connect(self._on_close_case)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(replied_btn)
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

    def _build_tab3(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # 工具列
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

        self._mantis_table = QTableWidget(0, 7)
        self._mantis_table.setHorizontalHeaderLabels(
            ["票號", "摘要", "狀態", "優先", "處理人", "預計修復", "最後同步"]
        )
        self._mantis_table.horizontalHeader().setStretchLastSection(True)
        self._mantis_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._mantis_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._mantis_table)

        return w

    def _refresh_mantis_table(self) -> None:
        tickets = self._manager.list_linked_tickets(self._case_id)
        self._mantis_table.setRowCount(len(tickets))
        for i, t in enumerate(tickets):
            self._mantis_table.setItem(i, 0, QTableWidgetItem(t.ticket_id))
            self._mantis_table.setItem(i, 1, QTableWidgetItem(t.summary or ""))
            self._mantis_table.setItem(i, 2, QTableWidgetItem(t.status or ""))
            self._mantis_table.setItem(i, 3, QTableWidgetItem(t.priority or ""))
            self._mantis_table.setItem(i, 4, QTableWidgetItem(t.handler or ""))
            self._mantis_table.setItem(i, 5, QTableWidgetItem(t.planned_fix or ""))
            self._mantis_table.setItem(i, 6, QTableWidgetItem(t.synced_at or ""))

    def _on_link_mantis(self) -> None:
        ticket_id = self._ticket_input.text().strip()
        if not ticket_id:
            return
        ok = self._manager.link_mantis(self._case_id, ticket_id)
        if ok:
            self._ticket_input.clear()
            self._refresh_mantis_table()
        else:
            QMessageBox.warning(
                self, "找不到 Ticket",
                f"Ticket {ticket_id} 不在本地資料庫。\n請先使用『同步選取』或前往 Mantis 同步頁面同步後再連結。"
            )

    def _on_unlink_mantis(self) -> None:
        rows = self._mantis_table.selectionModel().selectedRows()
        if not rows:
            return
        ticket_id = self._mantis_table.item(rows[0].row(), 0).text()
        self._manager.unlink_mantis(self._case_id, ticket_id)
        self._refresh_mantis_table()

    def _on_sync_mantis(self) -> None:
        rows = self._mantis_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "提示", "請先選取要同步的 Ticket。")
            return
        ticket_id = self._mantis_table.item(rows[0].row(), 0).text()
        # 嘗試從 MantisView 取得 client（無 client 時提示）
        try:
            from hcp_cms.services.credential import CredentialManager
            from hcp_cms.services.mantis.soap import MantisSoapClient
            creds = CredentialManager()
            url = creds.retrieve("mantis_url") or ""
            user = creds.retrieve("mantis_user") or ""
            pwd = creds.retrieve("mantis_password") or ""
            if url:
                client = MantisSoapClient(url, user, pwd)
                if not client.connect():
                    client = None
            else:
                client = None
        except Exception:
            client = None

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

    def _on_mark_replied(self) -> None:
        try:
            self._manager.mark_replied(self._case_id)
            self._load_case()
            self.case_updated.emit()
        except Exception as e:
            QMessageBox.critical(self, "操作失敗", str(e))

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
