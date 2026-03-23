"""Report center view."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
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
        layout.setSpacing(12)

        title = QLabel("📊 報表中心")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f1f5f9;")
        layout.addWidget(title)

        # ── 控制列 ──────────────────────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)

        # 報表類型
        ctrl.addWidget(QLabel("報表類型:"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(["追蹤表", "月報"])
        self._type_combo.setFixedWidth(100)
        ctrl.addWidget(self._type_combo)

        ctrl.addSpacing(12)

        # 起始日期
        ctrl.addWidget(QLabel("起始日期:"))
        self._start_date = QDateEdit()
        self._start_date.setCalendarPopup(True)
        self._start_date.setDisplayFormat("yyyy/MM/dd")
        today = QDate.currentDate()
        self._start_date.setDate(QDate(today.year(), today.month(), 1))
        self._start_date.setFixedWidth(130)
        ctrl.addWidget(self._start_date)

        ctrl.addWidget(QLabel("～"))

        # 結束日期
        ctrl.addWidget(QLabel("結束日期:"))
        self._end_date = QDateEdit()
        self._end_date.setCalendarPopup(True)
        self._end_date.setDisplayFormat("yyyy/MM/dd")
        self._end_date.setDate(today)
        self._end_date.setFixedWidth(130)
        ctrl.addWidget(self._end_date)

        ctrl.addSpacing(12)

        generate_btn = QPushButton("📥 產生並下載")
        generate_btn.clicked.connect(self._on_generate)
        ctrl.addWidget(generate_btn)

        ctrl.addStretch()
        layout.addLayout(ctrl)

        # ── 預覽表格 ─────────────────────────────────────────────────────
        self._preview = QTableWidget()
        layout.addWidget(self._preview)

        # ── 狀態列 ──────────────────────────────────────────────────────
        self._status = QLabel("就緒")
        self._status.setStyleSheet("color: #64748b;")
        layout.addWidget(self._status)

    def _on_generate(self) -> None:
        if not self._conn:
            return

        start = self._start_date.date().toString("yyyy/MM/dd")
        end = self._end_date.date().toString("yyyy/MM/dd")
        report_type = self._type_combo.currentText()

        if self._start_date.date() > self._end_date.date():
            QMessageBox.warning(self, "日期錯誤", "起始日期不可晚於結束日期。")
            return

        # 預設檔名：報表類型_起始_結束.xlsx
        type_prefix = "追蹤表" if report_type == "追蹤表" else "月報"
        start_tag = start.replace("/", "")
        end_tag = end.replace("/", "")
        default_name = f"HCP_{type_prefix}_{start_tag}_{end_tag}.xlsx"

        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            desktop = Path.home()
        default_path = str(desktop / default_name)

        path, _ = QFileDialog.getSaveFileName(
            self, "儲存報表", default_path, "Excel 檔案 (*.xlsx)"
        )
        if not path:
            return

        self._status.setText("⏳ 正在產生報表，請稍候...")
        self._status.repaint()

        try:
            engine = ReportEngine(self._conn)
            if report_type == "追蹤表":
                engine.generate_tracking_table(start, end, Path(path))
            else:
                engine.generate_monthly_report(start, end, Path(path))

            self._status.setText(f"✅ 報表已儲存：{path}")

            reply = QMessageBox.question(
                self,
                "報表產生完成",
                f"報表已儲存至：\n{path}\n\n是否立即開啟？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                os.startfile(path)  # type: ignore[attr-defined]

        except Exception as e:
            self._status.setText(f"❌ 產生失敗：{e}")
            QMessageBox.critical(self, "產生失敗", str(e))
