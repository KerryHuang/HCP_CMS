# src/hcp_cms/ui/customer_view.py
"""Customer & Staff management view."""

from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.customer_manager import CustomerManager
from hcp_cms.ui.theme import ColorPalette, ThemeManager

# 客戶公司固定欄（不含負責客服/業務，後者用 QComboBox）
_COMPANY_FIXED_COLS: list[tuple[str, str]] = [
    ("公司名稱 *", "name"),
    ("網域 *（@後）", "domain"),
    ("別名", "alias"),
    ("聯絡資訊", "contact_info"),
]
_COMPANY_TOTAL_COLS = len(_COMPANY_FIXED_COLS) + 2  # +負責客服 +負責業務

_STAFF_COLS: list[tuple[str, str]] = [
    ("姓名 *", "name"),
    ("Email *", "email"),
    ("電話", "phone"),
    ("備註", "notes"),
]

_NO_ASSIGN = "（未指定）"


class PasteImportDialog(QDialog):
    """批次貼上對話框——從 Excel 複製 Tab 分隔資料後貼入。"""

    def __init__(self, col_hints: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("批次貼上更新")
        self.resize(640, 400)
        layout = QVBoxLayout(self)
        hint = QLabel(
            f"請貼入 Tab 分隔的資料（可從 Excel 直接複製）\n"
            f"欄位順序：{col_hints}"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._text = QPlainTextEdit()
        self._text.setPlaceholderText("在此貼入資料…")
        layout.addWidget(self._text)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_rows(self) -> list[list[str]]:
        lines = self._text.toPlainText().splitlines()
        result = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            result.append(line.split("\t"))
        return result


class CustomerView(QWidget):
    """客戶管理頁面：客戶公司 / 客服人員 / 業務人員。"""

    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        theme_mgr: ThemeManager | None = None,
    ) -> None:
        super().__init__()
        self._conn = conn
        self._theme_mgr = theme_mgr
        self._cs_staff_options: list[tuple[str, str]] = []
        self._sales_staff_options: list[tuple[str, str]] = []
        self._setup_ui()
        if theme_mgr:
            self._apply_theme(theme_mgr.current_palette())
            theme_mgr.theme_changed.connect(self._apply_theme)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("🏢 客戶管理")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_company_tab(), "🏢 客戶公司")
        self._tabs.addTab(self._build_staff_tab("cs"), "👩‍💼 客服人員")
        self._tabs.addTab(self._build_staff_tab("sales"), "🤝 業務人員")
        layout.addWidget(self._tabs)

        self._tabs.currentChanged.connect(self._on_tab_changed)
        self.refresh()

    def _make_toolbar(self, save_slot, paste_slot, add_slot, delete_slot) -> QWidget:
        bar = QWidget()
        hlay = QHBoxLayout(bar)
        hlay.setContentsMargins(0, 0, 0, 4)
        hlay.setSpacing(6)
        save_btn = QPushButton("💾 儲存變更")
        save_btn.clicked.connect(save_slot)
        hlay.addWidget(save_btn)
        add_btn = QPushButton("➕ 新增一列")
        add_btn.clicked.connect(add_slot)
        hlay.addWidget(add_btn)
        paste_btn = QPushButton("📋 批次貼上")
        paste_btn.clicked.connect(paste_slot)
        hlay.addWidget(paste_btn)
        del_btn = QPushButton("🗑 刪除選取")
        del_btn.setObjectName("dangerBtn")
        del_btn.clicked.connect(delete_slot)
        hlay.addWidget(del_btn)
        hlay.addStretch()
        return bar

    def _build_company_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 8, 0, 0)
        toolbar = self._make_toolbar(
            self._on_save_companies,
            self._on_paste_companies,
            self._on_add_company_row,
            self._on_delete_company,
        )
        layout.addWidget(toolbar)
        headers = [c[0] for c in _COMPANY_FIXED_COLS] + ["負責客服", "負責業務"]
        self._company_table = QTableWidget(0, _COMPANY_TOTAL_COLS)
        self._company_table.setHorizontalHeaderLabels(headers)
        self._company_table.horizontalHeader().setStretchLastSection(True)
        self._company_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._company_table)
        return w

    def _build_staff_tab(self, role: str) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 8, 0, 0)
        if role == "cs":
            toolbar = self._make_toolbar(
                self._on_save_cs_staff, self._on_paste_cs_staff,
                self._on_add_cs_row, self._on_delete_cs_staff,
            )
            self._cs_table = QTableWidget(0, len(_STAFF_COLS))
            self._cs_table.setHorizontalHeaderLabels([c[0] for c in _STAFF_COLS])
            self._cs_table.horizontalHeader().setStretchLastSection(True)
            self._cs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            layout.addWidget(toolbar)
            layout.addWidget(self._cs_table)
        else:
            toolbar = self._make_toolbar(
                self._on_save_sales_staff, self._on_paste_sales_staff,
                self._on_add_sales_row, self._on_delete_sales_staff,
            )
            self._sales_table = QTableWidget(0, len(_STAFF_COLS))
            self._sales_table.setHorizontalHeaderLabels([c[0] for c in _STAFF_COLS])
            self._sales_table.horizontalHeader().setStretchLastSection(True)
            self._sales_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            layout.addWidget(toolbar)
            layout.addWidget(self._sales_table)
        return w

    def refresh(self) -> None:
        if not self._conn:
            return
        mgr = CustomerManager(self._conn)
        cs_list = mgr.list_staff("cs")
        sales_list = mgr.list_staff("sales")
        self._cs_staff_options = [(_NO_ASSIGN, "")] + [(s.name, s.staff_id) for s in cs_list]
        self._sales_staff_options = [(_NO_ASSIGN, "")] + [(s.name, s.staff_id) for s in sales_list]
        self._load_companies()
        self._load_staff_table("cs")
        self._load_staff_table("sales")

    def _load_companies(self) -> None:
        if not self._conn:
            return
        mgr = CustomerManager(self._conn)
        companies = mgr.list_companies()
        tbl = self._company_table
        tbl.setRowCount(0)
        for comp in companies:
            row = tbl.rowCount()
            tbl.insertRow(row)
            vals = [comp.name, comp.domain, comp.alias or "", comp.contact_info or ""]
            for col, val in enumerate(vals):
                tbl.setItem(row, col, QTableWidgetItem(val))
            cs_cb = self._make_staff_combo(self._cs_staff_options, comp.cs_staff_id)
            tbl.setCellWidget(row, 4, cs_cb)
            sales_cb = self._make_staff_combo(self._sales_staff_options, comp.sales_staff_id)
            tbl.setCellWidget(row, 5, sales_cb)

    def _make_staff_combo(self, options: list[tuple[str, str]], current_id: str | None) -> QComboBox:
        cb = QComboBox()
        for name, sid in options:
            cb.addItem(name, sid)
        if current_id:
            for i, (_, sid) in enumerate(options):
                if sid == current_id:
                    cb.setCurrentIndex(i)
                    break
        return cb

    def _load_staff_table(self, role: str) -> None:
        if not self._conn:
            return
        mgr = CustomerManager(self._conn)
        staff_list = mgr.list_staff(role)
        tbl = self._cs_table if role == "cs" else self._sales_table
        tbl.setRowCount(0)
        for s in staff_list:
            row = tbl.rowCount()
            tbl.insertRow(row)
            vals = [s.name, s.email, s.phone or "", s.notes or ""]
            for col, val in enumerate(vals):
                tbl.setItem(row, col, QTableWidgetItem(val))

    def _on_add_company_row(self) -> None:
        tbl = self._company_table
        row = tbl.rowCount()
        tbl.insertRow(row)
        for col in range(len(_COMPANY_FIXED_COLS)):
            tbl.setItem(row, col, QTableWidgetItem(""))
        cs_cb = self._make_staff_combo(self._cs_staff_options, None)
        tbl.setCellWidget(row, 4, cs_cb)
        sales_cb = self._make_staff_combo(self._sales_staff_options, None)
        tbl.setCellWidget(row, 5, sales_cb)

    def _on_add_cs_row(self) -> None:
        row = self._cs_table.rowCount()
        self._cs_table.insertRow(row)
        for col in range(len(_STAFF_COLS)):
            self._cs_table.setItem(row, col, QTableWidgetItem(""))

    def _on_add_sales_row(self) -> None:
        row = self._sales_table.rowCount()
        self._sales_table.insertRow(row)
        for col in range(len(_STAFF_COLS)):
            self._sales_table.setItem(row, col, QTableWidgetItem(""))

    def _collect_company_rows(self) -> list[dict]:
        tbl = self._company_table
        rows = []
        for r in range(tbl.rowCount()):
            cs_cb = tbl.cellWidget(r, 4)
            sales_cb = tbl.cellWidget(r, 5)
            rows.append({
                "name":          (tbl.item(r, 0).text() if tbl.item(r, 0) else "").strip(),
                "domain":        (tbl.item(r, 1).text() if tbl.item(r, 1) else "").strip(),
                "alias":         (tbl.item(r, 2).text() if tbl.item(r, 2) else "").strip(),
                "contact_info":  (tbl.item(r, 3).text() if tbl.item(r, 3) else "").strip(),
                "cs_staff_id":   cs_cb.currentData() if cs_cb else None,
                "sales_staff_id": sales_cb.currentData() if sales_cb else None,
            })
        return rows

    def _collect_staff_rows(self, role: str) -> list[dict]:
        tbl = self._cs_table if role == "cs" else self._sales_table
        rows = []
        for r in range(tbl.rowCount()):
            rows.append({
                "name":  (tbl.item(r, 0).text() if tbl.item(r, 0) else "").strip(),
                "email": (tbl.item(r, 1).text() if tbl.item(r, 1) else "").strip(),
                "phone": (tbl.item(r, 2).text() if tbl.item(r, 2) else "").strip(),
                "notes": (tbl.item(r, 3).text() if tbl.item(r, 3) else "").strip(),
                "role":  role,
            })
        return rows

    def _on_save_companies(self) -> None:
        if not self._conn:
            return
        rows = self._collect_company_rows()
        mgr = CustomerManager(self._conn)
        inserted, updated = mgr.bulk_upsert_companies(rows)
        QMessageBox.information(self, "儲存完成", f"新增 {inserted} 筆，更新 {updated} 筆。")
        self.refresh()

    def _on_save_cs_staff(self) -> None:
        self._save_staff("cs")

    def _on_save_sales_staff(self) -> None:
        self._save_staff("sales")

    def _save_staff(self, role: str) -> None:
        if not self._conn:
            return
        rows = self._collect_staff_rows(role)
        mgr = CustomerManager(self._conn)
        inserted, updated = mgr.bulk_upsert_staff(rows)
        QMessageBox.information(self, "儲存完成", f"新增 {inserted} 筆，更新 {updated} 筆。")
        self.refresh()

    def _on_paste_companies(self) -> None:
        if not self._conn:
            return
        hint = "公司名稱\t網域（@後）\t別名\t聯絡資訊"
        dlg = PasteImportDialog(hint, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        paste_rows = dlg.get_rows()
        if not paste_rows:
            return
        col_keys = [c[1] for c in _COMPANY_FIXED_COLS]
        rows = []
        for pr in paste_rows:
            row: dict = {"cs_staff_id": None, "sales_staff_id": None}
            for i, key in enumerate(col_keys):
                row[key] = pr[i].strip() if i < len(pr) else ""
            rows.append(row)
        mgr = CustomerManager(self._conn)
        inserted, updated = mgr.bulk_upsert_companies(rows)
        QMessageBox.information(
            self, "批次貼上完成",
            f"新增 {inserted} 筆，更新 {updated} 筆。\n負責客服/業務請在表格中手動選取後再儲存。"
        )
        self.refresh()

    def _on_paste_cs_staff(self) -> None:
        self._paste_staff("cs")

    def _on_paste_sales_staff(self) -> None:
        self._paste_staff("sales")

    def _paste_staff(self, role: str) -> None:
        if not self._conn:
            return
        hint = "姓名\tEmail\t電話\t備註"
        dlg = PasteImportDialog(hint, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        paste_rows = dlg.get_rows()
        if not paste_rows:
            return
        col_keys = [c[1] for c in _STAFF_COLS]
        rows = []
        for pr in paste_rows:
            row: dict = {"role": role}
            for i, key in enumerate(col_keys):
                row[key] = pr[i].strip() if i < len(pr) else ""
            rows.append(row)
        mgr = CustomerManager(self._conn)
        inserted, updated = mgr.bulk_upsert_staff(rows)
        QMessageBox.information(self, "批次貼上完成", f"新增 {inserted} 筆，更新 {updated} 筆。")
        self.refresh()

    def _on_delete_company(self) -> None:
        tbl = self._company_table
        rows = tbl.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "未選取", "請先選取要刪除的列。")
            return
        reply = QMessageBox.warning(
            self, "確認刪除", f"確定刪除選取的 {len(rows)} 筆客戶？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        mgr = CustomerManager(self._conn)
        for index in sorted(rows, key=lambda i: i.row(), reverse=True):
            domain_item = tbl.item(index.row(), 1)
            if domain_item:
                company = mgr.get_company_by_domain(domain_item.text().strip())
                if company:
                    mgr.delete_company(company.company_id)
        self.refresh()

    def _on_delete_cs_staff(self) -> None:
        self._delete_staff("cs")

    def _on_delete_sales_staff(self) -> None:
        self._delete_staff("sales")

    def _delete_staff(self, role: str) -> None:
        tbl = self._cs_table if role == "cs" else self._sales_table
        rows = tbl.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "未選取", "請先選取要刪除的列。")
            return
        reply = QMessageBox.warning(
            self, "確認刪除", f"確定刪除選取的 {len(rows)} 筆人員？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        mgr = CustomerManager(self._conn)
        for index in sorted(rows, key=lambda i: i.row(), reverse=True):
            email_item = tbl.item(index.row(), 1)
            if email_item:
                staff = mgr.get_staff_by_email(email_item.text().strip())
                if staff:
                    mgr.delete_staff(staff.staff_id)
        self.refresh()

    def _on_tab_changed(self, _index: int) -> None:
        pass

    def _apply_theme(self, p: ColorPalette) -> None:
        pass
