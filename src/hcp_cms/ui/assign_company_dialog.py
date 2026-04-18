"""Dialog for selecting a company to assign to selected cases."""

from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from hcp_cms.data.repositories import CompanyRepository


class AssignCompanyDialog(QDialog):
    """公司選擇對話框，供批次指定公司使用。"""

    def __init__(self, conn: sqlite3.Connection, case_count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("指定公司")
        self.setMinimumWidth(340)
        self._selected_company_id: str | None = None
        self._case_count = case_count
        companies = CompanyRepository(conn).list_all()
        self._companies = sorted(companies, key=lambda c: (c.domain or "").lower())
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        info = QLabel(f"已選取 <b>{self._case_count}</b> 筆案件，請選擇要指定的公司：")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self._combo = QComboBox()
        self._combo.addItem("-- 請選擇 --", None)
        for company in self._companies:
            self._combo.addItem(f"{company.name}（{company.domain or ''}）", company.company_id)
        form.addRow("公司：", self._combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        company_id = self._combo.currentData()
        if not company_id:
            return  # 未選擇，不關閉
        self._selected_company_id = company_id
        self.accept()

    @property
    def selected_company_id(self) -> str | None:
        return self._selected_company_id
