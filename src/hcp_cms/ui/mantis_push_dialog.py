"""推到 Mantis 確認對話框（thread-aware 三組分類）。"""
from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QVBoxLayout,
)

from hcp_cms.core.thread_tracker import ThreadTracker
from hcp_cms.data.repositories import CaseMantisRepository, CaseRepository
from hcp_cms.ui.theme import DARK_PALETTE, ColorPalette


class PushToMantisConfirmDialog(QDialog):
    """選取案件 → 依 thread 關係分三組：
    - new_ticket：thread root 且尚未連結 Mantis → 建新 ticket
    - bugnote：thread child（未連結 Mantis）→ 附加為 root ticket 的 bugnote
    - skipped：已連結 Mantis ticket → 略過

    使用者若只選 child 未選 root，root 會自動加入 new_ticket 群組。
    """

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
        self.setMinimumWidth(640)

        case_repo = CaseRepository(conn)
        link_repo = CaseMantisRepository(conn)
        tracker = ThreadTracker(conn)

        self.new_ticket_case_ids: list[str] = []
        self.bugnote_case_ids: list[str] = []
        self.skipped_case_ids: list[str] = []
        self._cases_by_id: dict = {}
        self._bugnote_targets: dict[str, str] = {}  # child_case_id -> root_case_id
        self._skip_reasons: dict[str, str] = {}     # case_id -> reason

        # 1. 依 thread root 分群
        thread_groups: dict[str, list[str]] = {}
        for cid in case_ids:
            case = case_repo.get_by_id(cid)
            if case is None:
                continue
            self._cases_by_id[cid] = case
            root = tracker._find_root(case)
            if root.case_id != cid and root.case_id not in self._cases_by_id:
                self._cases_by_id[root.case_id] = root
            thread_groups.setdefault(root.case_id, []).append(cid)

        # 2. 每串分類
        for root_id, members in thread_groups.items():
            root_case = self._cases_by_id.get(root_id)
            if root_case is None:
                continue
            root_links = link_repo.list_by_case_id(root_id)

            if root_links:
                # root 已連結 → 不重建；root 本身列為 skipped
                self.skipped_case_ids.append(root_id)
                self._skip_reasons[root_id] = f"已連結 ticket #{root_links[0].ticket_id}"
                target_ticket = root_links[0].ticket_id
                for cid in members:
                    if cid == root_id:
                        continue
                    cid_links = link_repo.list_by_case_id(cid)
                    if cid_links:
                        self.skipped_case_ids.append(cid)
                        self._skip_reasons[cid] = f"已連結 ticket #{cid_links[0].ticket_id}"
                    else:
                        self.bugnote_case_ids.append(cid)
                        self._bugnote_targets[cid] = f"{root_id} (ticket #{target_ticket})"
            else:
                # root 未連結 → 新建 ticket
                self.new_ticket_case_ids.append(root_id)
                for cid in members:
                    if cid == root_id:
                        continue
                    cid_links = link_repo.list_by_case_id(cid)
                    if cid_links:
                        self.skipped_case_ids.append(cid)
                        self._skip_reasons[cid] = f"已連結 ticket #{cid_links[0].ticket_id}"
                    else:
                        self.bugnote_case_ids.append(cid)
                        self._bugnote_targets[cid] = f"{root_id} 的新 ticket"

        # 3. 標記哪些 root 是「自動帶入」（使用者未選但因有子案件而加入）
        self._auto_included_roots = {
            rid for rid in self.new_ticket_case_ids if rid not in case_ids
        }

        self._setup_ui(project_label)

    def _setup_ui(self, project_label: str) -> None:
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"將推送以下案件到 {project_label}："))

        # 新建 ticket 區
        new_label = QLabel(
            f"新建 Mantis ticket（thread root）— {len(self.new_ticket_case_ids)} 筆："
        )
        new_label.setStyleSheet(
            f"font-weight: bold; color: {self._palette.accent}; margin-top: 8px;"
        )
        layout.addWidget(new_label)
        new_list = QListWidget()
        new_list.setMaximumHeight(140)
        for cid in self.new_ticket_case_ids:
            case = self._cases_by_id[cid]
            suffix = "（自動帶入：使用者只選了子案件）" if cid in self._auto_included_roots else ""
            new_list.addItem(
                f"  • {cid}  {case.subject or ''}{suffix}"
            )
        if not self.new_ticket_case_ids:
            new_list.addItem("  （無）")
        layout.addWidget(new_list)

        # bugnote 區
        bugnote_label = QLabel(
            f"附加為 bugnote — {len(self.bugnote_case_ids)} 筆："
        )
        bugnote_label.setStyleSheet(
            f"font-weight: bold; color: {self._palette.accent}; margin-top: 8px;"
        )
        layout.addWidget(bugnote_label)
        bugnote_list = QListWidget()
        bugnote_list.setMaximumHeight(140)
        for cid in self.bugnote_case_ids:
            case = self._cases_by_id[cid]
            target = self._bugnote_targets.get(cid, "")
            bugnote_list.addItem(
                f"  • {cid}  {case.subject or ''}  → 附到 {target}"
            )
        if not self.bugnote_case_ids:
            bugnote_list.addItem("  （無）")
        layout.addWidget(bugnote_list)

        # 略過區
        skipped_label = QLabel(
            f"自動略過 — {len(self.skipped_case_ids)} 筆："
        )
        skipped_label.setStyleSheet(
            f"font-weight: bold; color: {self._palette.text_muted}; margin-top: 8px;"
        )
        layout.addWidget(skipped_label)
        skipped_list = QListWidget()
        skipped_list.setMaximumHeight(100)
        for cid in self.skipped_case_ids:
            case = self._cases_by_id.get(cid)
            reason = self._skip_reasons.get(cid, "")
            subj = (case.subject or "") if case else ""
            skipped_list.addItem(f"  • {cid}  {subj}  ({reason})")
        if not self.skipped_case_ids:
            skipped_list.addItem("  （無）")
        layout.addWidget(skipped_list)

        # 按鈕區
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.confirm_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.confirm_button.setText("確認推送")
        # 至少要有一筆 new_ticket 或 bugnote 才能推
        self.confirm_button.setEnabled(
            bool(self.new_ticket_case_ids or self.bugnote_case_ids)
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def confirmed_case_ids(self) -> list[str]:
        """回傳要實際傳給 push_cases_thread_aware 的 case_id（含自動帶入的 root）。

        排除 skipped；包含 new_ticket + bugnote。
        push_cases_thread_aware 內部會再次分群處理。
        """
        return list(self.new_ticket_case_ids) + list(self.bugnote_case_ids)
