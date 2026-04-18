# src/hcp_cms/ui/customer_view.py
"""Customer & Staff management view."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
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
from hcp_cms.services.credential import CredentialManager
from hcp_cms.services.mantis.soap import MantisSoapClient
from hcp_cms.ui.theme import ColorPalette, ThemeManager

# 客戶公司固定欄（不含負責客服/業務，後者用 QComboBox）
_COMPANY_FIXED_COLS: list[tuple[str, str]] = [
    ("公司名稱 *", "name"),
    ("網域 *（@後）", "domain"),
    ("別名", "alias"),
    ("聯絡資訊", "contact_info"),
]
_COMPANY_TOTAL_COLS = len(_COMPANY_FIXED_COLS) + 3  # +負責客服 +負責業務 +HcpVersion

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

        # 全域工具列（不分 tab）
        global_bar = QWidget()
        glay = QHBoxLayout(global_bar)
        glay.setContentsMargins(0, 4, 0, 0)
        glay.setSpacing(6)
        reassoc_btn = QPushButton("🔄 重新比對案件公司")
        reassoc_btn.setToolTip(
            "將 company_id 遺失的案件，依 contact_person email 網域或公司名稱重新比對"
        )
        reassoc_btn.clicked.connect(self._on_reassociate_cases)
        glay.addWidget(reassoc_btn)
        glay.addStretch()
        layout.addWidget(global_bar)

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
        # 在工具列右側加入 Mantis 同步按鈕
        sync_btn = QPushButton("🔄 從 Mantis 同步 HcpVersion")
        sync_btn.setToolTip("連線 Mantis，依使用者 email 網域比對公司，同步 HcpVersion 欄位")
        sync_btn.clicked.connect(self._on_sync_hcp_version)
        toolbar.layout().insertWidget(toolbar.layout().count() - 1, sync_btn)
        layout.addWidget(toolbar)
        headers = ["HcpVersion"] + [c[0] for c in _COMPANY_FIXED_COLS] + ["負責客服", "負責業務"]
        self._company_table = QTableWidget(0, _COMPANY_TOTAL_COLS)
        self._company_table.setHorizontalHeaderLabels(headers)
        self._company_table.horizontalHeader().setStretchLastSection(True)
        self._company_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # 設定各欄初始寬度：HcpVersion、公司名稱、網域、別名、聯絡資訊、負責客服、負責業務
        for col, width in enumerate([80, 180, 160, 120, 200, 130, 130]):
            self._company_table.setColumnWidth(col, width)
        self._company_table.verticalHeader().setDefaultSectionSize(28)
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
            # 設定各欄寬：姓名、Email、電話、備註
            for col, width in enumerate([150, 220, 140, 300]):
                self._cs_table.setColumnWidth(col, width)
            self._cs_table.verticalHeader().setDefaultSectionSize(28)
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
            # 設定各欄寬：姓名、Email、電話、備註
            for col, width in enumerate([150, 220, 140, 300]):
                self._sales_table.setColumnWidth(col, width)
            self._sales_table.verticalHeader().setDefaultSectionSize(28)
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

        # 依負責客服排列（JILL → YOGA → 其他），再依網域字母排列
        _CS_ORDER = {"JILL": 0, "YOGA": 1}
        cs_id_to_name = {sid: name.upper() for name, sid in self._cs_staff_options if sid}

        def _sort_key(comp):
            cs_name = cs_id_to_name.get(comp.cs_staff_id or "", "")
            return (_CS_ORDER.get(cs_name, 2), (comp.domain or "").lower())

        companies.sort(key=_sort_key)

        tbl = self._company_table
        tbl.setRowCount(0)
        for comp in companies:
            row = tbl.rowCount()
            tbl.insertRow(row)
            # Col 0: HcpVersion（唯讀）
            hcp_item = QTableWidgetItem(comp.hcp_version or "")
            hcp_item.setFlags(hcp_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            hcp_item.setForeground(QColor("#93c5fd"))
            tbl.setItem(row, 0, hcp_item)
            # Col 1-4: 固定欄位
            vals = [comp.name, comp.domain or "", comp.alias or "", comp.contact_info or ""]
            for offset, val in enumerate(vals):
                col = offset + 1
                item = QTableWidgetItem(val)
                if col == 1:
                    # 將 company_id 藏入 UserRole，供儲存時直接定位記錄
                    item.setData(Qt.ItemDataRole.UserRole, comp.company_id)
                tbl.setItem(row, col, item)
            # Col 5-6: 人員 ComboBox
            cs_cb = self._make_staff_combo(self._cs_staff_options, comp.cs_staff_id)
            tbl.setCellWidget(row, 5, cs_cb)
            sales_cb = self._make_staff_combo(self._sales_staff_options, comp.sales_staff_id)
            tbl.setCellWidget(row, 6, sales_cb)

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
        # Col 0: HcpVersion（唯讀，新增列預設空白）
        hcp_item = QTableWidgetItem("")
        hcp_item.setFlags(hcp_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        hcp_item.setForeground(QColor("#93c5fd"))
        tbl.setItem(row, 0, hcp_item)
        # Col 1-4: 固定欄位
        for col in range(1, len(_COMPANY_FIXED_COLS) + 1):
            tbl.setItem(row, col, QTableWidgetItem(""))
        cs_cb = self._make_staff_combo(self._cs_staff_options, None)
        tbl.setCellWidget(row, 5, cs_cb)
        sales_cb = self._make_staff_combo(self._sales_staff_options, None)
        tbl.setCellWidget(row, 6, sales_cb)

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
            name_item = tbl.item(r, 1)
            cs_cb = tbl.cellWidget(r, 5)
            sales_cb = tbl.cellWidget(r, 6)
            rows.append({
                "company_id":    name_item.data(Qt.ItemDataRole.UserRole) if name_item else None,
                "name":          (name_item.text() if name_item else "").strip(),
                "domain":        (tbl.item(r, 2).text() if tbl.item(r, 2) else "").strip(),
                "alias":         (tbl.item(r, 3).text() if tbl.item(r, 3) else "").strip(),
                "contact_info":  (tbl.item(r, 4).text() if tbl.item(r, 4) else "").strip(),
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
        hint = (
            "公司名稱\t網域（@後）\t別名\t聯絡資訊\t負責客服姓名\t負責業務姓名\n"
            "（後兩欄可省略，省略時保留現有指派）"
        )
        dlg = PasteImportDialog(hint, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        paste_rows = dlg.get_rows()
        if not paste_rows:
            return

        # 建立姓名 → staff_id 對照表（略過「未指定」選項）
        cs_by_name = {name: sid for name, sid in self._cs_staff_options if sid}
        sales_by_name = {name: sid for name, sid in self._sales_staff_options if sid}

        col_keys = [c[1] for c in _COMPANY_FIXED_COLS]
        rows: list[dict] = []
        unmatched: list[str] = []
        for pr in paste_rows:
            row: dict = {"cs_staff_id": None, "sales_staff_id": None}
            for i, key in enumerate(col_keys):
                row[key] = pr[i].strip() if i < len(pr) else ""
            # 第 5 欄：負責客服姓名
            if len(pr) >= 5 and pr[4].strip():
                cs_name = pr[4].strip()
                if cs_name in cs_by_name:
                    row["cs_staff_id"] = cs_by_name[cs_name]
                else:
                    unmatched.append(f"客服「{cs_name}」")
            # 第 6 欄：負責業務姓名
            if len(pr) >= 6 and pr[5].strip():
                sales_name = pr[5].strip()
                if sales_name in sales_by_name:
                    row["sales_staff_id"] = sales_by_name[sales_name]
                else:
                    unmatched.append(f"業務「{sales_name}」")
            rows.append(row)

        mgr = CustomerManager(self._conn)
        inserted, updated = mgr.bulk_upsert_companies(rows)

        msg = f"新增 {inserted} 筆，更新 {updated} 筆。"
        if unmatched:
            msg += "\n\n⚠ 以下姓名找不到對應人員，該欄位未指派：\n" + "\n".join(unmatched)
            msg += "\n\n請先至「客服人員」或「業務人員」頁籤新增人員後，再重新貼上。"
        QMessageBox.information(self, "批次貼上完成", msg)
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
        try:
            for index in sorted(rows, key=lambda i: i.row(), reverse=True):
                domain_item = tbl.item(index.row(), 2)
                if domain_item:
                    company = mgr.get_company_by_domain(domain_item.text().strip())
                    if company:
                        mgr.delete_company(company.company_id)
        except Exception as exc:
            QMessageBox.critical(self, "刪除失敗", f"刪除時發生錯誤：{exc}")
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

    def _on_sync_hcp_version(self) -> None:
        """從 Mantis 同步所有使用者的 HcpVersion 至 companies 表。"""
        if not self._conn:
            return
        creds = CredentialManager()
        url = creds.retrieve("mantis_url") or ""
        user = creds.retrieve("mantis_user") or ""
        pwd = creds.retrieve("mantis_password") or ""
        if not url:
            QMessageBox.warning(
                self, "尚未設定",
                "請先至「系統設定」→「Mantis SOAP 連線設定」填寫連線資訊。"
            )
            return
        # 萃取 base URL
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path
        if ".php" in path:
            path = path[:path.rfind("/")]
        base_url = f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/")

        client = MantisSoapClient(base_url, username=user, password=pwd)
        if not client.connect():
            QMessageBox.critical(self, "連線失敗", f"無法連線至 Mantis：{client.last_error}")
            return

        mgr = CustomerManager(self._conn)
        updated, err = mgr.sync_hcp_version_from_mantis(client)
        if err:
            QMessageBox.warning(self, "同步失敗", f"同步時發生錯誤：{err}")
        else:
            QMessageBox.information(
                self, "同步完成",
                f"成功更新 {updated} 筆公司的 HcpVersion。" if updated
                else "所有公司的 HcpVersion 均已是最新，無需更新。"
            )
        self.refresh()

    def _on_reassociate_cases(self) -> None:
        if not self._conn:
            return
        mgr = CustomerManager(self._conn)
        try:
            count = mgr.reassociate_case_companies()
        except Exception as exc:
            QMessageBox.critical(self, "比對失敗", f"比對時發生錯誤：{exc}")
            return
        if count:
            QMessageBox.information(
                self, "比對完成",
                f"成功比對 {count} 筆案件的公司對應關係。"
            )
        else:
            QMessageBox.information(
                self, "比對完成",
                "沒有找到可比對的案件。\n\n"
                "可能原因：\n"
                "• 案件的 contact_person 欄位未填寫 email\n"
                "• 所有案件的公司對應已完整，無需補齊"
            )

    def _on_tab_changed(self, _index: int) -> None:
        pass

    def _apply_theme(self, p: ColorPalette) -> None:
        pass
