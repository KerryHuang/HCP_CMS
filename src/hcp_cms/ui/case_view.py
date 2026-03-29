"""Case management view — list, detail, CRUD."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.case_manager import CaseManager
from hcp_cms.data.fts import FTSManager
from hcp_cms.data.repositories import CaseRepository, CompanyRepository
from hcp_cms.ui.theme import ColorPalette, ThemeManager

_FIXED_COL_COUNT = 9


class CaseView(QWidget):
    """Case management page."""

    cases_changed = Signal()  # 案件有異動時發射，供儀表板同步

    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        db_path: Path | None = None,
        theme_mgr: ThemeManager | None = None,
    ) -> None:
        super().__init__()
        self._conn = conn
        self._db_path = db_path
        self._theme_mgr = theme_mgr
        from hcp_cms.core.custom_column_manager import CustomColumnManager
        self._custom_col_mgr = CustomColumnManager(conn) if conn else None
        self._setup_ui()
        if theme_mgr:
            self._apply_theme(theme_mgr.current_palette())
            theme_mgr.theme_changed.connect(self._apply_theme)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QHBoxLayout()
        self._title = QLabel("📋 案件管理")
        header.addWidget(self._title)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜尋案件...")
        self._search_input.setFixedWidth(300)
        self._search_input.returnPressed.connect(self.refresh)
        header.addWidget(self._search_input)

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["全部", "處理中", "已回覆", "已完成", "Closed", "最近匯入"])
        header.addWidget(self._filter_combo)

        refresh_btn = QPushButton("🔄 重新整理")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)

        new_btn = QPushButton("➕ 手動建案")
        new_btn.clicked.connect(self._on_new_case)
        header.addWidget(new_btn)

        import_btn = QPushButton("📥 匯入 CSV")
        import_btn.clicked.connect(self._on_import_csv)
        header.addWidget(import_btn)

        self._delete_btn = QPushButton("🗑 刪除案件")
        self._delete_btn.setObjectName("dangerBtn")
        self._delete_btn.clicked.connect(self._on_delete_cases)
        header.addWidget(self._delete_btn)

        layout.addLayout(header)

        # Splitter: table + detail
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Case table
        self._table = QTableWidget(0, _FIXED_COL_COUNT)
        self._table.setHorizontalHeaderLabels([
            "案件編號", "狀態", "優先", "公司", "主旨", "問題類型", "回覆", "來回次數", "時間"
        ])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.itemDoubleClicked.connect(self._on_row_double_clicked)
        self._setup_context_menu()
        splitter.addWidget(self._table)

        # Detail panel
        detail = QWidget()
        detail_layout = QFormLayout(detail)
        self._detail_id = QLabel()
        self._detail_subject = QLabel()
        self._detail_status = QLabel()
        self._detail_system_product = QLabel()
        self._detail_error_type = QLabel()
        self._detail_handler = QLabel()
        self._detail_reply_count = QLabel()
        self._detail_linked_case = QLabel()
        self._detail_progress = QTextEdit()
        self._detail_progress.setMaximumHeight(80)

        detail_layout.addRow("案件編號:", self._detail_id)
        detail_layout.addRow("主旨:", self._detail_subject)
        detail_layout.addRow("狀態:", self._detail_status)
        detail_layout.addRow("系統產品:", self._detail_system_product)
        detail_layout.addRow("功能模組:", self._detail_error_type)
        detail_layout.addRow("技術人員:", self._detail_handler)
        detail_layout.addRow("來回次數:", self._detail_reply_count)
        detail_layout.addRow("關聯案件:", self._detail_linked_case)
        detail_layout.addRow("處理進度:", self._detail_progress)

        # Action buttons
        btn_layout = QHBoxLayout()
        self._btn_reply = QPushButton("✅ 標記已回覆")
        self._btn_reply.clicked.connect(self._on_mark_replied)
        btn_layout.addWidget(self._btn_reply)

        self._btn_close = QPushButton("🔒 結案")
        self._btn_close.clicked.connect(self._on_close_case)
        btn_layout.addWidget(self._btn_close)

        detail_layout.addRow(btn_layout)
        splitter.addWidget(detail)

        layout.addWidget(splitter)

    def refresh(self) -> None:
        if not self._conn:
            return
        try:
            repo = CaseRepository(self._conn)
            keyword = self._search_input.text().strip()
            status_filter = self._filter_combo.currentText()

            if keyword:
                fts = FTSManager(self._conn)
                matched_ids = {r["case_id"] for r in fts.search_cases(keyword)}
                # 同時比對公司名稱（含 alias）
                company_repo = CompanyRepository(self._conn)
                matched_company_ids = {
                    c.company_id for c in company_repo.list_all()
                    if keyword in (c.name or "") or keyword in (c.alias or "")
                }
                all_cases = repo.list_all()
                cases = [
                    c for c in all_cases
                    if c.case_id in matched_ids
                    or c.company_id in matched_company_ids
                    or keyword in (c.subject or "")
                ]
            elif status_filter == "全部":
                cases = repo.list_all()
            elif status_filter == "最近匯入":
                cases = repo.list_recently_created(minutes=10)
            else:
                cases = repo.list_by_status(status_filter)

            self._cases = cases
            # 取得自訂欄（visible_in_list=True）
            custom_cols = self._custom_col_mgr.list_columns() if self._custom_col_mgr else []
            visible_cols = [c for c in custom_cols if c.visible_in_list]

            # 預先建立 company_id → 公司名稱的對照表
            company_repo = CompanyRepository(self._conn)
            company_map: dict[str, str] = {
                c.company_id: c.name for c in company_repo.list_all()
            }

            total_cols = _FIXED_COL_COUNT + len(visible_cols)
            self._table.setColumnCount(total_cols)
            headers = ["案件編號", "狀態", "優先", "公司", "主旨", "問題類型", "回覆", "來回次數", "時間"]
            headers += [col.col_label for col in visible_cols]
            self._table.setHorizontalHeaderLabels(headers)

            self._table.setRowCount(len(cases))
            for i, case in enumerate(cases):
                self._table.setItem(i, 0, QTableWidgetItem(case.case_id))
                self._table.setItem(i, 1, QTableWidgetItem(case.status))
                self._table.setItem(i, 2, QTableWidgetItem(case.priority))
                # 公司欄：優先顯示公司中文名稱，其次顯示 company_id
                company_display = company_map.get(case.company_id or "", case.company_id or "")
                self._table.setItem(i, 3, QTableWidgetItem(company_display))
                self._table.setItem(i, 4, QTableWidgetItem(case.subject or ""))
                self._table.setItem(i, 5, QTableWidgetItem(case.issue_type or ""))
                self._table.setItem(i, 6, QTableWidgetItem("是" if case.status == "已回覆" else "否"))
                reply_item = QTableWidgetItem(str(case.reply_count) if case.reply_count else "")
                reply_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(i, 7, reply_item)
                self._table.setItem(i, 8, QTableWidgetItem(case.sent_time or ""))
                for j, col in enumerate(visible_cols):
                    val = case.extra_fields.get(col.col_key) or ""
                    self._table.setItem(i, _FIXED_COL_COUNT + j, QTableWidgetItem(val))
        except Exception:
            pass

    def _on_selection_changed(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows or not hasattr(self, '_cases'):
            return
        row = rows[0].row()
        if row < 0 or row >= len(self._cases):
            return
        case = self._cases[row]
        self._detail_id.setText(case.case_id)
        self._detail_subject.setText(case.subject or "")
        self._detail_status.setText(case.status)
        self._detail_system_product.setText(case.system_product or "")
        self._detail_error_type.setText(case.error_type or "")
        self._detail_handler.setText(case.handler or "")
        reply_display = str(case.reply_count) if case.reply_count else "0"
        self._detail_reply_count.setText(reply_display)
        self._detail_linked_case.setText(case.linked_case_id or "")
        self._detail_progress.setPlainText(case.progress or "")

    def _on_new_case(self) -> None:
        pass  # Will be implemented with dialog

    def _on_import_csv(self) -> None:
        if not self._db_path:
            return
        from hcp_cms.ui.csv_import_dialog import CsvImportDialog
        dialog = CsvImportDialog(
            self._db_path,
            parent=self,
            palette=self._theme_mgr.current_palette() if self._theme_mgr else None,
        )
        dialog.exec()
        self.refresh()

    def _setup_context_menu(self) -> None:
        """設定右鍵選單。"""
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)

    def _on_context_menu(self, pos) -> None:
        """顯示右鍵選單。"""
        row = self._table.currentRow()
        if row < 0:
            return
        menu = QMenu(self)
        delete_action = menu.addAction("🗑 刪除此案件")
        action = menu.exec(self._table.viewport().mapToGlobal(pos))
        if action == delete_action:
            self._on_delete_single_case()

    def _on_delete_single_case(self) -> None:
        """單筆刪除目前選取的案件。"""
        if not self._conn:
            return
        row = self._table.currentRow()
        if row < 0:
            return
        item = self._table.item(row, 0)
        if item is None:
            return
        case_id = item.text()
        reply = QMessageBox.warning(
            self,
            "確認刪除",
            f"確定刪除案件 {case_id}？\n此操作無法復原。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        CaseManager(self._conn).delete_case(case_id)
        self.refresh()
        self.cases_changed.emit()

    def _on_delete_cases(self) -> None:
        if not self._conn:
            return
        from hcp_cms.ui.delete_cases_dialog import DeleteCasesDialog
        dlg = DeleteCasesDialog(self._conn, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self.cases_changed.emit()

    def _on_mark_replied(self) -> None:
        if not self._conn or not self._detail_id.text():
            return
        CaseManager(self._conn).mark_replied(self._detail_id.text())
        self.refresh()

    def _on_close_case(self) -> None:
        if not self._conn or not self._detail_id.text():
            return
        CaseManager(self._conn).close_case(self._detail_id.text())
        self.refresh()

    def _on_row_double_clicked(self, item) -> None:
        if not self._conn or not hasattr(self, '_cases'):
            return
        row = item.row()
        if row < 0 or row >= len(self._cases):
            return
        case_id = self._cases[row].case_id
        from hcp_cms.ui.case_detail_dialog import CaseDetailDialog
        dlg = CaseDetailDialog(
            self._conn,
            case_id,
            parent=self,
            palette=self._theme_mgr.current_palette() if self._theme_mgr else None,
        )
        dlg.case_updated.connect(self.refresh)
        dlg.exec()

    def _apply_theme(self, p: ColorPalette) -> None:
        """套用主題色彩。"""
        self._title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p.text_primary};")
