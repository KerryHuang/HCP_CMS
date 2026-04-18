"""補充說明編輯器 — 左右分割逐筆維護 Issue 補充欄位。"""

from __future__ import annotations

import json
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.data.models import PatchIssue

_SUPPLEMENT_KEYS = ("修改原因", "原問題", "範例說明", "修正後", "注意事項")

_CLR_COMPLETE = QColor("#22c55e")
_CLR_INSUFFICIENT = QColor("#f97316")
_CLR_EMPTY = QColor("#94a3b8")
_CLR_EDITED = QColor("#3b82f6")


class SupplementEditorWidget(QWidget):
    supplement_saved = Signal(int, dict)   # (issue_id, supplement)
    reanalyze_requested = Signal(int)      # issue_id
    reanalyze_all_requested = Signal()

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._issues: list[PatchIssue] = []
        self._current_issue_id: int | None = None
        self._edits: dict[str, QTextEdit] = {}
        self._dirty = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        top_bar = QHBoxLayout()
        self._reanalyze_all_btn = QPushButton("🔄 重新從 Mantis 分析全部")
        top_bar.addWidget(self._reanalyze_all_btn)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._list = QListWidget()
        self._list.setMaximumWidth(220)
        splitter.addWidget(self._list)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 8, 8, 8)

        self._title_label = QLabel("請從左側選擇 Issue")
        self._title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        right_layout.addWidget(self._title_label)

        for key in _SUPPLEMENT_KEYS:
            right_layout.addWidget(QLabel(key))
            edit = QTextEdit()
            edit.setFixedHeight(80)
            self._edits[key] = edit
            right_layout.addWidget(edit)
            edit.textChanged.connect(self._on_text_changed)

        btn_row = QHBoxLayout()
        self._reanalyze_btn = QPushButton("🔄 重新分析此 Issue")
        self._save_btn = QPushButton("💾 儲存")
        btn_row.addWidget(self._reanalyze_btn)
        btn_row.addWidget(self._save_btn)
        btn_row.addStretch()
        right_layout.addLayout(btn_row)
        right_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(right_widget)
        scroll.setWidgetResizable(True)
        splitter.addWidget(scroll)
        splitter.setSizes([200, 600])

        layout.addWidget(splitter, stretch=1)

        self._list.currentRowChanged.connect(self._on_issue_selected)
        self._reanalyze_all_btn.clicked.connect(self.reanalyze_all_requested)
        self._reanalyze_btn.clicked.connect(self._on_reanalyze_clicked)
        self._save_btn.clicked.connect(self._on_save_clicked)

        self._set_right_enabled(False)

    def load_issues(self, issues: list[PatchIssue]) -> None:
        """載入 Issue 清單，更新左側列表。"""
        self._issues = issues
        self._list.clear()
        for iss in issues:
            detail = self._parse_detail(iss)
            supplement = detail.get("supplement") or {}
            edited = detail.get("supplement_edited", False)
            status = self.supplement_status(supplement, edited)
            item = QListWidgetItem(f"{self._status_icon(status)} {iss.issue_no}")
            item.setForeground(self._status_color(status))
            item.setData(Qt.ItemDataRole.UserRole, iss.issue_id)
            self._list.addItem(item)

    def update_issue_display(
        self, issue_id: int, supplement: dict, edited: bool = False
    ) -> None:
        """外部（Mantis 分析完成後）更新指定 Issue 的清單圖示與右側欄位。"""
        iss = next((x for x in self._issues if x.issue_id == issue_id), None)
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == issue_id:
                if iss is not None:
                    status = self.supplement_status(supplement, edited)
                    item.setText(f"{self._status_icon(status)} {iss.issue_no}")
                    item.setForeground(self._status_color(status))
                break
        if self._current_issue_id == issue_id:
            self._load_supplement(supplement)

    @staticmethod
    def supplement_status(supplement: dict | None, edited: bool) -> str:
        """回傳 'edited' | 'complete' | 'insufficient' | 'empty'。"""
        if edited:
            return "edited"
        if not supplement:
            return "empty"
        if any("⚠" in str(v) for v in supplement.values()):
            return "insufficient"
        if all(supplement.get(k, "").strip() for k in _SUPPLEMENT_KEYS):
            return "complete"
        return "insufficient"

    @staticmethod
    def _status_icon(status: str) -> str:
        return {"edited": "✏", "complete": "✅", "insufficient": "⚠", "empty": "○"}.get(status, "○")

    @staticmethod
    def _status_color(status: str) -> QColor:
        return {
            "edited": _CLR_EDITED,
            "complete": _CLR_COMPLETE,
            "insufficient": _CLR_INSUFFICIENT,
            "empty": _CLR_EMPTY,
        }.get(status, _CLR_EMPTY)

    def _on_issue_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._issues):
            self._set_right_enabled(False)
            return
        if self._dirty:
            reply = QMessageBox.question(
                self, "未儲存的變更", "目前有未儲存的變更，是否放棄？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                # 還原列表視覺選取，避免焦點與右側顯示內容不一致
                prev_row = next(
                    (i for i, iss in enumerate(self._issues)
                     if iss.issue_id == self._current_issue_id),
                    -1,
                )
                self._list.blockSignals(True)
                self._list.setCurrentRow(prev_row)
                self._list.blockSignals(False)
                return
        iss = self._issues[row]
        self._current_issue_id = iss.issue_id
        detail = self._parse_detail(iss)
        supplement = detail.get("supplement") or {}
        self._title_label.setText(f"Issue {iss.issue_no} — {iss.description or ''}")
        self._load_supplement(supplement)
        self._set_right_enabled(True)
        self._dirty = False

    def _load_supplement(self, supplement: dict) -> None:
        for key, edit in self._edits.items():
            edit.blockSignals(True)
            edit.setPlainText(supplement.get(key, ""))
            edit.blockSignals(False)
        self._dirty = False

    def _on_text_changed(self) -> None:
        self._dirty = True

    def _on_save_clicked(self) -> None:
        if self._current_issue_id is None:
            return
        supplement = {k: self._edits[k].toPlainText() for k in _SUPPLEMENT_KEYS}
        self.supplement_saved.emit(self._current_issue_id, supplement)
        self._dirty = False

    def _on_reanalyze_clicked(self) -> None:
        if self._current_issue_id is not None:
            self.reanalyze_requested.emit(self._current_issue_id)

    def _set_right_enabled(self, enabled: bool) -> None:
        for edit in self._edits.values():
            edit.setEnabled(enabled)
        self._save_btn.setEnabled(enabled)
        self._reanalyze_btn.setEnabled(enabled)

    @staticmethod
    def _parse_detail(iss: PatchIssue) -> dict:
        if not iss.mantis_detail:
            return {}
        try:
            return json.loads(iss.mantis_detail)
        except (json.JSONDecodeError, TypeError):
            return {}
