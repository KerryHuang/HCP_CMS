"""Report center view."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSpinBox,
    QTableWidget, QVBoxLayout, QWidget, QFileDialog,
)

from hcp_cms.core.report_engine import ReportEngine


class ReportView(QWidget):
    """Report center page."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("📊 報表中心")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f1f5f9;")
        layout.addWidget(title)

        # Report type
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("報表類型:"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(["追蹤表", "月報"])
        type_layout.addWidget(self._type_combo)

        type_layout.addWidget(QLabel("年:"))
        self._year_spin = QSpinBox()
        self._year_spin.setRange(2020, 2030)
        self._year_spin.setValue(2026)
        type_layout.addWidget(self._year_spin)

        type_layout.addWidget(QLabel("月:"))
        self._month_spin = QSpinBox()
        self._month_spin.setRange(1, 12)
        self._month_spin.setValue(3)
        type_layout.addWidget(self._month_spin)

        generate_btn = QPushButton("📥 產生並下載")
        generate_btn.clicked.connect(self._on_generate)
        type_layout.addWidget(generate_btn)

        layout.addLayout(type_layout)

        # Preview table
        self._preview = QTableWidget()
        layout.addWidget(self._preview)

        # Status
        self._status = QLabel("就緒")
        self._status.setStyleSheet("color: #64748b;")
        layout.addWidget(self._status)

    def _on_generate(self) -> None:
        if not self._conn:
            return
        path, _ = QFileDialog.getSaveFileName(self, "儲存報表", "", "Excel (*.xlsx)")
        if not path:
            return
        engine = ReportEngine(self._conn)
        year = self._year_spin.value()
        month = self._month_spin.value()
        if self._type_combo.currentText() == "追蹤表":
            engine.generate_tracking_table(year, month, Path(path))
        else:
            engine.generate_monthly_report(year, month, Path(path))
        self._status.setText(f"報表已儲存至 {path}")
