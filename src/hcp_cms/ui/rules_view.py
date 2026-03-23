"""Classification rules management view."""

from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.data.models import ClassificationRule
from hcp_cms.data.repositories import RuleRepository


class RulesView(QWidget):
    """Classification rules management page."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._editing_id: int | None = None
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
        self._type_combo.addItems(["product", "issue", "error", "priority", "broadcast", "handler", "progress"])
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        filter_layout.addWidget(self._type_combo)

        refresh_btn = QPushButton("🔄 重新整理")
        refresh_btn.clicked.connect(self.refresh)
        filter_layout.addWidget(refresh_btn)

        import_btn = QPushButton("📥 匯入 CSV")
        import_btn.clicked.connect(self._on_import_csv)
        filter_layout.addWidget(import_btn)

        export_btn = QPushButton("📤 匯出 CSV")
        export_btn.clicked.connect(self._on_export_csv)
        filter_layout.addWidget(export_btn)

        layout.addLayout(filter_layout)

        # Rules table
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["ID", "正則表達式", "匹配值", "優先級"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.clicked.connect(self._on_row_clicked)
        layout.addWidget(self._table)

        # Form
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

        btn_layout = QHBoxLayout()
        self._add_btn = QPushButton("➕ 新增規則")
        self._add_btn.clicked.connect(self._on_add_rule)
        btn_layout.addWidget(self._add_btn)

        self._save_btn = QPushButton("💾 儲存修改")
        self._save_btn.clicked.connect(self._on_save_edit)
        self._save_btn.setVisible(False)
        btn_layout.addWidget(self._save_btn)

        self._delete_btn = QPushButton("🗑️ 刪除")
        self._delete_btn.clicked.connect(self._on_delete_rule)
        self._delete_btn.setVisible(False)
        self._delete_btn.setStyleSheet("background-color: #7f1d1d;")
        btn_layout.addWidget(self._delete_btn)

        self._cancel_btn = QPushButton("✕ 取消")
        self._cancel_btn.clicked.connect(self._exit_edit_mode)
        self._cancel_btn.setVisible(False)
        btn_layout.addWidget(self._cancel_btn)

        form_group.addRow(btn_layout)
        layout.addLayout(form_group)

    def refresh(self) -> None:
        if not self._conn:
            return
        repo = RuleRepository(self._conn)
        rules = repo.list_by_type(self._type_combo.currentText())
        self._table.setRowCount(len(rules))
        for i, rule in enumerate(rules):
            self._table.setItem(i, 0, QTableWidgetItem(str(rule.rule_id)))
            self._table.setItem(i, 1, QTableWidgetItem(rule.pattern))
            self._table.setItem(i, 2, QTableWidgetItem(rule.value))
            self._table.setItem(i, 3, QTableWidgetItem(str(rule.priority)))
        self._exit_edit_mode()

    def _on_type_changed(self, _: str) -> None:
        self.refresh()

    def _on_row_clicked(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        self._editing_id = int(self._table.item(row, 0).text())
        self._pattern_input.setText(self._table.item(row, 1).text())
        self._value_input.setText(self._table.item(row, 2).text())
        self._priority_spin.setValue(int(self._table.item(row, 3).text()))
        self._add_btn.setVisible(False)
        self._save_btn.setVisible(True)
        self._delete_btn.setVisible(True)
        self._cancel_btn.setVisible(True)

    def _exit_edit_mode(self) -> None:
        self._editing_id = None
        self._pattern_input.clear()
        self._value_input.clear()
        self._priority_spin.setValue(0)
        self._table.clearSelection()
        self._add_btn.setVisible(True)
        self._save_btn.setVisible(False)
        self._delete_btn.setVisible(False)
        self._cancel_btn.setVisible(False)

    def _on_add_rule(self) -> None:
        if not self._conn:
            return
        pattern = self._pattern_input.text().strip()
        value = self._value_input.text().strip()
        if not pattern or not value:
            return
        RuleRepository(self._conn).insert(ClassificationRule(
            rule_type=self._type_combo.currentText(),
            pattern=pattern,
            value=value,
            priority=self._priority_spin.value(),
        ))
        self.refresh()

    def _on_save_edit(self) -> None:
        if not self._conn or self._editing_id is None:
            return
        pattern = self._pattern_input.text().strip()
        value = self._value_input.text().strip()
        if not pattern or not value:
            return
        RuleRepository(self._conn).update(ClassificationRule(
            rule_id=self._editing_id,
            rule_type=self._type_combo.currentText(),
            pattern=pattern,
            value=value,
            priority=self._priority_spin.value(),
        ))
        self.refresh()

    def _on_delete_rule(self) -> None:
        if not self._conn or self._editing_id is None:
            return
        RuleRepository(self._conn).delete(self._editing_id)
        self.refresh()

    def _on_import_csv(self) -> None:
        if not self._conn:
            return
        path, _ = QFileDialog.getOpenFileName(self, "匯入規則 CSV", "", "CSV 檔案 (*.csv)")
        if not path:
            return
        imported, skipped = RuleRepository(self._conn).import_csv(path)
        self.refresh()
        QMessageBox.information(
            self,
            "匯入完成",
            f"成功匯入 {imported} 筆規則，跳過 {skipped} 筆無效資料。",
        )

    def _on_export_csv(self) -> None:
        if not self._conn:
            return
        path, _ = QFileDialog.getSaveFileName(self, "匯出規則 CSV", "rules.csv", "CSV 檔案 (*.csv)")
        if not path:
            return
        RuleRepository(self._conn).export_csv(path)
        QMessageBox.information(self, "匯出完成", f"規則已匯出至：\n{path}")
