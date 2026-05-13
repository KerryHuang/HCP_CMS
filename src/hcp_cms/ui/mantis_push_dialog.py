"""推到 Mantis 確認對話框。"""
from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QVBoxLayout,
)

from hcp_cms.data.repositories import CaseMantisRepository, CaseRepository
from hcp_cms.ui.theme import DARK_PALETTE, ColorPalette


class PushToMantisConfirmDialog(QDialog):
    """選取案件 → 分類未連結 / 已連結 → 確認推送。"""

    def __init__(
        self,
        conn: sqlite3.Connection,
        case_ids: list[str],
        project_label: str = "Mantis",
        parent=None,
        palette: ColorPalette | None = None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._palette = palette or DARK_PALETTE
        self.setWindowTitle("推到 Mantis 確認")
        self.setMinimumWidth(600)

        # 分類
        case_repo = CaseRepository(conn)
        link_repo = CaseMantisRepository(conn)
        self.unlinked_case_ids: list[str] = []
        self.linked_case_ids: list[str] = []
        self._cases_by_id = {}
        self._links_by_id: dict[str, list] = {}
        for cid in case_ids:
            case = case_repo.get_by_id(cid)
            if case is None:
                continue
            self._cases_by_id[cid] = case
            links = link_repo.list_by_case_id(cid)
            self._links_by_id[cid] = links
            if links:
                self.linked_case_ids.append(cid)
            else:
                self.unlinked_case_ids.append(cid)

        self._setup_ui(project_label)

    def _setup_ui(self, project_label: str) -> None:
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"將推送以下案件到 {project_label}："))

        # 未連結區
        unlinked_label = QLabel(
            f"未連結（將建立新 Mantis ticket）— {len(self.unlinked_case_ids)} 筆："
        )
        unlinked_label.setStyleSheet(f"font-weight: bold; color: {self._palette.accent}; margin-top: 8px;")
        layout.addWidget(unlinked_label)
        unlinked_list = QListWidget()
        unlinked_list.setMaximumHeight(180)
        for cid in self.unlinked_case_ids:
            case = self._cases_by_id[cid]
            unlinked_list.addItem(
                f"  • {cid}  {case.subject or ''}  (客戶: {case.company_id or '—'})"
            )
        if not self.unlinked_case_ids:
            unlinked_list.addItem("  （無）")
        layout.addWidget(unlinked_list)

        # 已連結區
        linked_label = QLabel(
            f"已連結（自動略過）— {len(self.linked_case_ids)} 筆："
        )
        linked_label.setStyleSheet(f"font-weight: bold; color: {self._palette.text_muted}; margin-top: 8px;")
        layout.addWidget(linked_label)
        linked_list = QListWidget()
        linked_list.setMaximumHeight(120)
        for cid in self.linked_case_ids:
            case = self._cases_by_id[cid]
            tickets = self._links_by_id.get(cid, [])
            ticket_id = tickets[0].ticket_id if tickets else "?"
            linked_list.addItem(f"  • {cid}  {case.subject or ''}  → ticket #{ticket_id}")
        if not self.linked_case_ids:
            linked_list.addItem("  （無）")
        layout.addWidget(linked_list)

        # 按鈕區
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.confirm_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.confirm_button.setText("確認推送")
        self.confirm_button.setEnabled(bool(self.unlinked_case_ids))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def confirmed_case_ids(self) -> list[str]:
        """回傳要實際推送的案件 ID（僅未連結部分）。"""
        return list(self.unlinked_case_ids)
