"""手動建案對話框。"""
from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
)

from hcp_cms.data.repositories import CaseRepository, CompanyRepository


class NewCaseDialog(QDialog):
    """手動建立新案件的輸入對話框。"""

    def __init__(self, conn: sqlite3.Connection, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("手動建案")
        self.setMinimumWidth(480)
        self._conn = conn
        self._created_case_id: str | None = None
        companies = CompanyRepository(conn).list_all()
        self._companies = sorted(companies, key=lambda c: c.name or "")
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        hint = QLabel("填寫案件基本資訊，系統將自動分類並建立案件。")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()

        self._subject = QLineEdit()
        self._subject.setPlaceholderText("必填")
        form.addRow("主旨 *：", self._subject)

        self._company_combo = QComboBox()
        self._company_combo.addItem("-- 自動辨識 --", None)
        for c in self._companies:
            self._company_combo.addItem(c.name, c.company_id)
        form.addRow("公司：", self._company_combo)

        self._contact = QLineEdit()
        self._contact.setPlaceholderText("選填")
        form.addRow("聯絡人：", self._contact)

        self._body = QTextEdit()
        self._body.setPlaceholderText("選填，案件描述內容")
        self._body.setFixedHeight(120)
        form.addRow("描述：", self._body)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("建立")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        subject = self._subject.text().strip()
        if not subject:
            QMessageBox.warning(self, "欄位缺漏", "主旨為必填欄位。")
            return

        try:
            from hcp_cms.core.case_manager import CaseManager
            mgr = CaseManager(self._conn)
            case = mgr.create_case(
                subject=subject,
                body=self._body.toPlainText().strip(),
                contact_person=self._contact.text().strip() or None,
            )

            company_id = self._company_combo.currentData()
            if company_id:
                repo = CaseRepository(self._conn)
                repo.update_company_id(case.case_id, company_id)
                self._conn.commit()

            self._created_case_id = case.case_id
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "建案失敗", f"建立案件時發生錯誤：\n{e}")

    @property
    def created_case_id(self) -> str | None:
        return self._created_case_id
