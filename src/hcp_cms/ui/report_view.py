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
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.report_engine import ReportEngine
from hcp_cms.core.report_writer import ReportWriter
from hcp_cms.ui.theme import ColorPalette, ThemeManager


class ReportView(QWidget):
    """Report center page."""

    def __init__(self, conn: sqlite3.Connection | None = None, theme_mgr: ThemeManager | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._theme_mgr = theme_mgr
        self._preview_data: dict[str, list[list]] | None = None
        self._setup_ui()
        if theme_mgr:
            self._apply_theme(theme_mgr.current_palette())
            theme_mgr.theme_changed.connect(self._apply_theme)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self._title = QLabel("📊 報表中心")
        layout.addWidget(self._title)

        # ── 控制列 ──────────────────────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)

        ctrl.addWidget(QLabel("報表類型:"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(["追蹤表", "月報"])
        self._type_combo.setFixedWidth(100)
        self._type_combo.currentIndexChanged.connect(self._on_params_changed)
        ctrl.addWidget(self._type_combo)

        ctrl.addSpacing(12)

        ctrl.addWidget(QLabel("起始日期:"))
        self._start_date = QDateEdit()
        self._start_date.setCalendarPopup(True)
        self._start_date.setDisplayFormat("yyyy/MM/dd")
        today = QDate.currentDate()
        self._start_date.setDate(QDate(today.year(), today.month(), 1))
        self._start_date.setFixedWidth(130)
        self._start_date.dateChanged.connect(self._on_params_changed)
        ctrl.addWidget(self._start_date)

        ctrl.addWidget(QLabel("～"))

        ctrl.addWidget(QLabel("結束日期:"))
        self._end_date = QDateEdit()
        self._end_date.setCalendarPopup(True)
        self._end_date.setDisplayFormat("yyyy/MM/dd")
        self._end_date.setDate(today)
        self._end_date.setFixedWidth(130)
        self._end_date.dateChanged.connect(self._on_params_changed)
        ctrl.addWidget(self._end_date)

        ctrl.addSpacing(12)

        self._preview_btn = QPushButton("🔍 檢視")
        self._preview_btn.clicked.connect(self._on_preview)
        ctrl.addWidget(self._preview_btn)

        self._download_btn = QPushButton("📥 下載")
        self._download_btn.setEnabled(False)
        self._download_btn.clicked.connect(self._on_download)
        ctrl.addWidget(self._download_btn)

        ctrl.addStretch()
        layout.addLayout(ctrl)

        # ── 預覽區 QTabWidget ────────────────────────────────────────────
        self._tab_widget = QTabWidget()
        layout.addWidget(self._tab_widget)

        # ── 狀態列 ──────────────────────────────────────────────────────
        self._status = QLabel("就緒")
        layout.addWidget(self._status)

    def _on_params_changed(self) -> None:
        """報表類型或日期變更時清空預覽。"""
        self._preview_data = None
        self._tab_widget.clear()
        self._download_btn.setEnabled(False)
        self._status.setText("就緒")

    def _on_preview(self) -> None:
        if not self._conn:
            return

        start = self._start_date.date().toString("yyyy/MM/dd")
        end = self._end_date.date().toString("yyyy/MM/dd")

        if self._start_date.date() > self._end_date.date():
            QMessageBox.warning(self, "日期錯誤", "起始日期不可晚於結束日期。")
            return

        self._status.setText("⏳ 正在載入報表，請稍候...")
        self._status.repaint()

        try:
            engine = ReportEngine(self._conn)
            report_type = self._type_combo.currentText()
            if report_type == "追蹤表":
                data = engine.build_tracking_table(start, end)
            else:
                data = engine.build_monthly_report(start, end)

            has_data = any(len(rows) > 1 for rows in data.values())

            self._preview_data = data
            self._fill_preview(data)
            self._download_btn.setEnabled(has_data)

            if has_data:
                self._status.setText("✅ 預覽完成")
            else:
                self._status.setText("⚠️ 查詢範圍內無資料")

        except Exception as e:
            self._status.setText(f"❌ 載入失敗：{e}")
            QMessageBox.critical(self, "載入失敗", str(e))

    def _fill_preview(self, data: dict[str, list[list]]) -> None:
        """將結構化資料填入 QTabWidget。"""
        self._tab_widget.clear()

        for sheet_name, rows in data.items():
            table = QTableWidget()
            if rows:
                col_count = max(len(r) for r in rows)

                # 判斷第一列是否為正式欄位標題：
                # 若只有一列、或第一列欄數少於第二列，視為標題列（非標頭），全部列當資料顯示
                has_proper_header = len(rows) < 2 or len(rows[0]) >= len(rows[1])

                if has_proper_header:
                    # 第一列作為 QTableWidget 橫向標頭
                    table.setColumnCount(col_count)
                    table.setRowCount(max(0, len(rows) - 1))
                    table.setHorizontalHeaderLabels([str(h) for h in rows[0]])
                    for row_idx, row in enumerate(rows[1:]):
                        for col_idx, value in enumerate(row):
                            table.setItem(row_idx, col_idx, QTableWidgetItem(str(value) if value else ""))
                else:
                    # 第一列為標題列（如月報摘要），全部列當資料顯示，使用預設數字標頭
                    table.setColumnCount(col_count)
                    table.setRowCount(len(rows))
                    for row_idx, row in enumerate(rows):
                        for col_idx, value in enumerate(row):
                            table.setItem(row_idx, col_idx, QTableWidgetItem(str(value) if value else ""))

                table.resizeColumnsToContents()
            self._tab_widget.addTab(table, sheet_name)

    def _on_download(self) -> None:
        if not self._preview_data:
            return

        start = self._start_date.date().toString("yyyy/MM/dd")
        end = self._end_date.date().toString("yyyy/MM/dd")
        report_type = self._type_combo.currentText()

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

        try:
            ReportWriter.write_excel(self._preview_data, Path(path))
            self._status.setText(f"✅ 報表已儲存：{path}")

            reply = QMessageBox.question(
                self,
                "報表下載完成",
                f"報表已儲存至：\n{path}\n\n是否立即開啟？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                os.startfile(path)  # type: ignore[attr-defined]

        except Exception as e:
            self._status.setText(f"❌ 下載失敗：{e}")
            QMessageBox.critical(self, "下載失敗", str(e))

    def _apply_theme(self, p: ColorPalette) -> None:
        """套用主題色彩。"""
        self._title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p.text_primary};")
        self._status.setStyleSheet(f"color: {p.text_muted};")
