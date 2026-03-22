"""Classification rules management view."""

from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from hcp_cms.data.models import ClassificationRule
from hcp_cms.data.repositories import RuleRepository


class RulesView(QWidget):
    """Classification rules management page."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("📏 規則設定")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f1f5f9;")
        layout.addWidget(title)

        # Filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("規則類型:"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(["product", "issue", "error", "priority", "broadcast"])
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        filter_layout.addWidget(self._type_combo)

        refresh_btn = QPushButton("🔄 重新整理")
        refresh_btn.clicked.connect(self.refresh)
        filter_layout.addWidget(refresh_btn)
        layout.addLayout(filter_layout)

        # Rules table
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["ID", "正則表達式", "匹配值", "優先級"])
        self._table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._table)

        # Add rule form
        form_group = QFormLayout()
        self._pattern_input = QLineEdit()
        self._pattern_input.setPlaceholderText("正則表達式 (如: bug|錯誤|異常)")
        self._value_input = QLineEdit()
        self._value_input.setPlaceholderText("匹配值 (如: BUG)")
        self._priority_spin = QSpinBox()
        self._priority_spin.setRange(0, 999)

        form_group.addRow("Pattern:", self._pattern_input)
        form_group.addRow("Value:", self._value_input)
        form_group.addRow("Priority:", self._priority_spin)

        add_btn = QPushButton("➕ 新增規則")
        add_btn.clicked.connect(self._on_add_rule)
        form_group.addRow(add_btn)

        layout.addLayout(form_group)

    def refresh(self) -> None:
        if not self._conn:
            return
        repo = RuleRepository(self._conn)
        rule_type = self._type_combo.currentText()
        rules = repo.list_by_type(rule_type)
        self._table.setRowCount(len(rules))
        for i, rule in enumerate(rules):
            self._table.setItem(i, 0, QTableWidgetItem(str(rule.rule_id)))
            self._table.setItem(i, 1, QTableWidgetItem(rule.pattern))
            self._table.setItem(i, 2, QTableWidgetItem(rule.value))
            self._table.setItem(i, 3, QTableWidgetItem(str(rule.priority)))

    def _on_type_changed(self, _: str) -> None:
        self.refresh()

    def _on_add_rule(self) -> None:
        if not self._conn:
            return
        pattern = self._pattern_input.text().strip()
        value = self._value_input.text().strip()
        if not pattern or not value:
            return
        repo = RuleRepository(self._conn)
        repo.insert(ClassificationRule(
            rule_type=self._type_combo.currentText(),
            pattern=pattern,
            value=value,
            priority=self._priority_spin.value(),
        ))
        self._pattern_input.clear()
        self._value_input.clear()
        self.refresh()
