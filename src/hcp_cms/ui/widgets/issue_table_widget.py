"""IssueTableWidget — 可編輯 Issue 清單，供 SinglePatchTab / MonthlyPatchTab 共用。"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.data.models import PatchIssue
from hcp_cms.data.repositories import PatchRepository

_COLUMNS = [
    ("issue_no",       "Issue No"),
    ("issue_type",     "類型"),
    ("program_code",   "程式代號"),
    ("program_name",   "程式名稱"),
    ("region",         "區域"),
    ("description",    "功能說明"),
    ("impact",         "影響說明"),
    ("test_direction", "測試方向"),
]
_COL_KEYS    = [c[0] for c in _COLUMNS]
_COL_HEADERS = [c[1] for c in _COLUMNS]


class IssueTableWidget(QWidget):
    issues_changed = Signal()

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._patch_id: int | None = None
        self._loading = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        btn_bar = QHBoxLayout()
        self._add_btn    = QPushButton("＋ 新增 Issue")
        self._delete_btn = QPushButton("🗑 刪除")
        btn_bar.addWidget(self._add_btn)
        btn_bar.addWidget(self._delete_btn)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COL_HEADERS)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove
        )
        self._table.setDragDropOverwriteMode(False)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._table)

        self._add_btn.clicked.connect(self._on_add_clicked)
        self._delete_btn.clicked.connect(self._on_delete_clicked)
        self._table.cellChanged.connect(self._on_cell_changed)
        self._table.model().rowsMoved.connect(self._on_rows_moved)

    # ── Public API ─────────────────────────────────────────────────────────

    def load_issues(self, patch_id: int,
                    conn: sqlite3.Connection | None = None) -> None:
        if conn:
            self._conn = conn
        self._patch_id = patch_id
        self._reload()

    # ── Internal ───────────────────────────────────────────────────────────

    def _reload(self) -> None:
        if not self._conn or self._patch_id is None:
            return
        repo = PatchRepository(self._conn)
        issues = repo.list_issues_by_patch(self._patch_id)
        self._loading = True
        try:
            self._table.setRowCount(0)
            for iss in issues:
                self._append_row(iss)
        finally:
            self._loading = False

    def _append_row(self, issue: PatchIssue) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        for col, key in enumerate(_COL_KEYS):
            value = getattr(issue, key, "") or ""
            item = QTableWidgetItem(str(value))
            item.setData(Qt.ItemDataRole.UserRole, issue.issue_id)
            self._table.setItem(row, col, item)

    def _on_add_clicked(self) -> None:
        if not self._conn or self._patch_id is None:
            return
        repo = PatchRepository(self._conn)
        new_issue = PatchIssue(
            patch_id=self._patch_id,
            issue_no="",
            issue_type="BugFix",
            region="共用",
            sort_order=self._table.rowCount(),
            source="manual",
        )
        repo.insert_issue(new_issue)
        self._reload()
        last = self._table.rowCount() - 1
        self._table.setCurrentCell(last, 0)
        self._table.editItem(self._table.item(last, 0))
        self.issues_changed.emit()

    def _on_delete_clicked(self) -> None:
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        if not rows:
            return
        if not self._conn:
            return
        answer = QMessageBox.question(
            self, "確認刪除",
            f"確定刪除選取的 {len(rows)} 筆 Issue？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        repo = PatchRepository(self._conn)
        for row in sorted(rows, reverse=True):
            item = self._table.item(row, 0)
            if item:
                issue_id = item.data(Qt.ItemDataRole.UserRole)
                if issue_id is not None:
                    repo.delete_issue(issue_id)
        self._reload()
        self.issues_changed.emit()

    def _on_cell_changed(self, row: int, _col: int) -> None:
        if self._loading or not self._conn or self._patch_id is None:
            return
        item = self._table.item(row, 0)
        if not item:
            return
        issue_id = item.data(Qt.ItemDataRole.UserRole)
        if issue_id is None:
            return
        repo = PatchRepository(self._conn)
        existing = repo.get_issue_by_id(issue_id)
        if not existing:
            return
        for col, key in enumerate(_COL_KEYS):
            cell = self._table.item(row, col)
            if cell:
                setattr(existing, key, cell.text())
        repo.update_issue(existing)
        self.issues_changed.emit()

    def _on_rows_moved(self) -> None:
        if self._loading or not self._conn or self._patch_id is None:
            return
        repo = PatchRepository(self._conn)
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if not item:
                continue
            issue_id = item.data(Qt.ItemDataRole.UserRole)
            if issue_id is None:
                continue
            existing = repo.get_issue_by_id(issue_id)
            if existing:
                existing.sort_order = row
                repo.update_issue(existing)
        self.issues_changed.emit()
