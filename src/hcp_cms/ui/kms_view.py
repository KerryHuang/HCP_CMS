"""KMS knowledge base view — search, CRUD, 待審核審核。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.kms_engine import KMSEngine


class QAReviewDialog(QDialog):
    """待審核 QA 編輯對話框。"""

    def __init__(self, qa, parent=None) -> None:
        super().__init__(parent)
        self.qa = qa
        self._result_action: str | None = None
        self.setWindowTitle(f"QA 審核編輯 — {qa.qa_id}")
        self.setMinimumWidth(600)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._question = QTextEdit(self.qa.question or "")
        self._question.setFixedHeight(80)
        self._answer = QTextEdit(self.qa.answer or "")
        self._answer.setFixedHeight(80)
        self._solution = QTextEdit(self.qa.solution or "")
        self._solution.setFixedHeight(60)
        self._keywords = QLineEdit(self.qa.keywords or "")
        self._product = QLineEdit(self.qa.system_product or "")

        form.addRow("問題：", self._question)
        form.addRow("回覆：", self._answer)
        form.addRow("解決方案：", self._solution)
        form.addRow("關鍵字：", self._keywords)
        form.addRow("產品：", self._product)
        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        draft_btn = QPushButton("💾 儲存草稿")
        draft_btn.clicked.connect(self._on_draft)
        approve_btn = QPushButton("✅ 確認完成")
        approve_btn.clicked.connect(self._on_approve)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(draft_btn)
        btn_layout.addWidget(approve_btn)
        layout.addLayout(btn_layout)

    def _collect_fields(self) -> dict:
        return {
            "question": self._question.toPlainText().strip(),
            "answer": self._answer.toPlainText().strip(),
            "solution": self._solution.toPlainText().strip() or None,
            "keywords": self._keywords.text().strip() or None,
            "system_product": self._product.text().strip() or None,
        }

    def _on_draft(self) -> None:
        self._result_action = "draft"
        self._result_fields = self._collect_fields()
        self.accept()

    def _on_approve(self) -> None:
        self._result_action = "approve"
        self._result_fields = self._collect_fields()
        self.accept()

    def result_action(self) -> str | None:
        return self._result_action

    def result_fields(self) -> dict:
        return getattr(self, "_result_fields", {})


class KMSView(QWidget):
    """KMS knowledge base page."""

    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        kms: KMSEngine | None = None,
        db_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self._conn = conn
        self._kms = kms or (KMSEngine(conn) if conn else None)
        self._db_dir = db_dir
        self._results: list = []
        self._pending: list = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("📚 KMS 知識庫")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f1f5f9;")
        layout.addWidget(title)

        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # ── 全部 tab ──────────────────────────────────────────────────
        all_tab = QWidget()
        all_layout = QVBoxLayout(all_tab)

        search_layout = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜尋知識庫（支援同義詞擴展）...")
        self._search_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self._search_input)
        search_btn = QPushButton("🔍 搜尋")
        search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(search_btn)
        show_all_btn = QPushButton("📋 顯示全部")
        show_all_btn.clicked.connect(self._on_show_all)
        search_layout.addWidget(show_all_btn)
        new_btn = QPushButton("➕ 新增 QA")
        new_btn.clicked.connect(self._on_new_qa)
        search_layout.addWidget(new_btn)
        all_layout.addLayout(search_layout)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["QA 編號", "問題", "產品", "類型", "來源"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self._table)

        detail = QWidget()
        detail_layout = QFormLayout(detail)
        self._detail_question = QTextEdit()
        self._detail_question.setMaximumHeight(80)
        self._detail_question.setReadOnly(True)
        self._detail_answer = QTextEdit()
        self._detail_answer.setMaximumHeight(80)
        self._detail_answer.setReadOnly(True)
        self._detail_solution = QTextEdit()
        self._detail_solution.setMaximumHeight(80)
        self._detail_solution.setReadOnly(True)
        detail_layout.addRow("問題:", self._detail_question)
        detail_layout.addRow("回覆:", self._detail_answer)
        detail_layout.addRow("解決方案:", self._detail_solution)
        splitter.addWidget(detail)
        all_layout.addWidget(splitter)
        self._tabs.addTab(all_tab, "全部")

        # ── 待審核 tab ────────────────────────────────────────────────
        pending_tab = QWidget()
        pending_layout = QVBoxLayout(pending_tab)

        self._pending_table = QTableWidget(0, 3)
        self._pending_table.setHorizontalHeaderLabels(["QA 編號", "問題預覽", "來源案件"])
        self._pending_table.horizontalHeader().setStretchLastSection(True)
        self._pending_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._pending_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        pending_layout.addWidget(self._pending_table)

        pending_btn_layout = QHBoxLayout()
        review_btn = QPushButton("✏️ 編輯審核")
        review_btn.clicked.connect(self._on_review)
        delete_btn = QPushButton("🗑️ 刪除")
        delete_btn.clicked.connect(self._on_delete_pending)
        pending_btn_layout.addWidget(review_btn)
        pending_btn_layout.addWidget(delete_btn)
        pending_btn_layout.addStretch()
        pending_layout.addLayout(pending_btn_layout)
        self._tabs.addTab(pending_tab, "待審核")

        layout.addWidget(self._tabs)

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            self._refresh_pending()

    def _refresh_pending(self) -> None:
        if not self._kms:
            return
        self._pending = self._kms.list_pending()
        count = len(self._pending)
        self._tabs.setTabText(1, f"待審核{'  🔴' + str(count) if count else ''}")
        self._pending_table.setRowCount(count)
        for i, qa in enumerate(self._pending):
            self._pending_table.setItem(i, 0, QTableWidgetItem(qa.qa_id))
            self._pending_table.setItem(i, 1, QTableWidgetItem((qa.question or "")[:50]))
            self._pending_table.setItem(i, 2, QTableWidgetItem(qa.source_case_id or ""))

    def _on_show_all(self) -> None:
        """載入所有已完成 QA 顯示於全部 tab。"""
        if not self._kms:
            return
        self._results = self._kms.list_approved()
        self._table.setRowCount(len(self._results))
        for i, qa in enumerate(self._results):
            self._table.setItem(i, 0, QTableWidgetItem(qa.qa_id))
            self._table.setItem(i, 1, QTableWidgetItem(qa.question or ""))
            self._table.setItem(i, 2, QTableWidgetItem(qa.system_product or ""))
            self._table.setItem(i, 3, QTableWidgetItem(qa.issue_type or ""))
            self._table.setItem(i, 4, QTableWidgetItem(qa.source or ""))

    def _on_search(self) -> None:
        query = self._search_input.text().strip()
        if not query or not self._kms:
            return
        self._results = self._kms.search(query)
        self._table.setRowCount(len(self._results))
        for i, qa in enumerate(self._results):
            self._table.setItem(i, 0, QTableWidgetItem(qa.qa_id))
            self._table.setItem(i, 1, QTableWidgetItem(qa.question or ""))
            self._table.setItem(i, 2, QTableWidgetItem(qa.system_product or ""))
            self._table.setItem(i, 3, QTableWidgetItem(qa.issue_type or ""))
            self._table.setItem(i, 4, QTableWidgetItem(qa.source or ""))

    def _on_selection_changed(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows or not self._results:
            return
        row = rows[0].row()
        if row < 0 or row >= len(self._results):
            return
        qa = self._results[row]
        self._detail_question.setPlainText(qa.question or "")
        self._detail_answer.setPlainText(qa.answer or "")
        self._detail_solution.setPlainText(qa.solution or "")

    def _on_new_qa(self) -> None:
        pass  # 預留給新增 QA 對話框

    def _on_review(self) -> None:
        if not self._kms:
            return
        rows = self._pending_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if row >= len(self._pending):
            return
        qa = self._pending[row]
        dlg = QAReviewDialog(qa, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dlg.result_fields()
        if dlg.result_action() == "draft":
            self._kms.update_qa(qa.qa_id, **fields)
        elif dlg.result_action() == "approve":
            self._kms.approve_qa(qa.qa_id, **fields)
        self._refresh_pending()

    def _on_delete_pending(self) -> None:
        if not self._kms:
            return
        rows = self._pending_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if row >= len(self._pending):
            return
        qa = self._pending[row]
        self._kms.delete_qa(qa.qa_id)
        self._refresh_pending()
