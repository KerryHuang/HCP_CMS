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
        self._load_case()

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
        # 實作於 Task 5
        return QWidget()

    def _build_tab3(self) -> QWidget:
        # 實作於 Task 6
        return QWidget()

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
