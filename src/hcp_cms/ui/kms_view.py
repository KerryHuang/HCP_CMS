"""KMS knowledge base view — search, CRUD."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.kms_engine import KMSEngine


class KMSView(QWidget):
    """KMS knowledge base page."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._kms = KMSEngine(conn) if conn else None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("📚 KMS 知識庫")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f1f5f9;")
        layout.addWidget(title)

        # Search bar
        search_layout = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜尋知識庫（支援同義詞擴展）...")
        self._search_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self._search_input)

        search_btn = QPushButton("🔍 搜尋")
        search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(search_btn)

        new_btn = QPushButton("➕ 新增 QA")
        new_btn.clicked.connect(self._on_new_qa)
        search_layout.addWidget(new_btn)

        layout.addLayout(search_layout)

        # Results table + detail splitter
        splitter = QSplitter(Qt.Orientation.Vertical)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["QA 編號", "問題", "產品", "類型", "來源"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self._table)

        # Detail panel
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

        layout.addWidget(splitter)

    def _on_search(self) -> None:
        query = self._search_input.text().strip()
        if not query or not self._kms:
            return
        results = self._kms.search(query)
        self._results = results
        self._table.setRowCount(len(results))
        for i, qa in enumerate(results):
            self._table.setItem(i, 0, QTableWidgetItem(qa.qa_id))
            self._table.setItem(i, 1, QTableWidgetItem(qa.question or ""))
            self._table.setItem(i, 2, QTableWidgetItem(qa.system_product or ""))
            self._table.setItem(i, 3, QTableWidgetItem(qa.issue_type or ""))
            self._table.setItem(i, 4, QTableWidgetItem(qa.source or ""))

    def _on_selection_changed(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows or not hasattr(self, '_results'):
            return
        row = rows[0].row()
        if row < 0 or row >= len(self._results):
            return
        qa = self._results[row]
        self._detail_question.setPlainText(qa.question or "")
        self._detail_answer.setPlainText(qa.answer or "")
        self._detail_solution.setPlainText(qa.solution or "")

    def _on_new_qa(self) -> None:
        pass  # Will be implemented with dialog
