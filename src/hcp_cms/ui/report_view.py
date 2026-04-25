"""Report center view."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.report_engine import ReportEngine
from hcp_cms.ui.theme import ColorPalette, ThemeManager
from hcp_cms.ui.utils import open_file


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
        self._type_combo.addItems(["追蹤表", "月報", "客服問題彙整"])
        self._type_combo.setFixedWidth(130)
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

        self._sync_sheets_btn = QPushButton("☁️ 同步至 Google Sheets")
        self._sync_sheets_btn.clicked.connect(self._on_sync_to_sheets)
        ctrl.addWidget(self._sync_sheets_btn)
        self._sync_sheets_btn.setVisible(False)

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
        is_cs = self._type_combo.currentText() == "客服問題彙整"
        self._sync_sheets_btn.setVisible(is_cs)

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

        if self._type_combo.currentText() == "客服問題彙整":
            self._fill_cs_report_preview()
            return

        try:
            engine = ReportEngine(self._conn)
            report_type = self._type_combo.currentText()
            if report_type == "追蹤表":
                data = engine.build_tracking_table(start, end)
            else:
                data = engine.build_monthly_report(start, end)
                # 加入 Mantis 預覽分頁
                mantis_dict_rows = engine.build_mantis_sheet()
                if mantis_dict_rows:
                    _headers = ["#", "票號", "摘要", "狀態", "優先", "未處理天數", "最後更新", "負責人"]
                    _mantis_preview: list[list] = [_headers]
                    for _i, _r in enumerate(mantis_dict_rows, 1):
                        _mantis_preview.append(
                            [
                                _i,
                                _r["ticket_id"],
                                _r["summary"],
                                _r["status"],
                                _r["priority"],
                                _r["unresolved_days"],
                                _r["last_updated"],
                                _r["handler"],
                            ]
                        )
                    data["📌 Mantis 追蹤"] = _mantis_preview

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
        # 記錄 sheet_name → tab index 供快速連結使用
        self._sheet_tab_index: dict[str, int] = {}

        for tab_idx, (sheet_name, rows) in enumerate(data.items()):
            self._sheet_tab_index[sheet_name] = tab_idx
            table = QTableWidget()
            table.setWordWrap(True)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setAlternatingRowColors(True)
            if rows:
                col_count = max(len(r) for r in rows)

                # 判斷第一列是否為正式欄位標題
                has_proper_header = len(rows) < 2 or len(rows[0]) >= len(rows[1])

                if has_proper_header:
                    table.setColumnCount(col_count)
                    table.setRowCount(max(0, len(rows) - 1))
                    table.setHorizontalHeaderLabels([str(h) for h in rows[0]])
                    for row_idx, row in enumerate(rows[1:]):
                        for col_idx, value in enumerate(row):
                            item = QTableWidgetItem(str(value) if value else "")
                            # 快速連結欄：藍色文字提示可點擊
                            if str(rows[0][col_idx]) == "快速連結" and value:
                                item.setForeground(Qt.GlobalColor.cyan)
                            table.setItem(row_idx, col_idx, item)
                    # 「快速連結」欄 index
                    try:
                        self._quick_link_col = [str(h) for h in rows[0]].index("快速連結")
                    except ValueError:
                        self._quick_link_col = -1
                else:
                    table.setColumnCount(col_count)
                    table.setRowCount(len(rows))
                    for row_idx, row in enumerate(rows):
                        for col_idx, value in enumerate(row):
                            table.setItem(row_idx, col_idx, QTableWidgetItem(str(value) if value else ""))
                    self._quick_link_col = -1

                table.resizeColumnsToContents()
                table.resizeRowsToContents()

            # 互動連線
            table.cellDoubleClicked.connect(self._on_cell_double_clicked)
            if sheet_name == "📋 客戶索引":
                # 單擊快速連結 → 跳轉公司分頁
                table.cellClicked.connect(self._on_index_cell_clicked)
            else:
                # 公司分頁：單擊「↩ 返回客戶索引」或案件 row → 跳轉 / 開啟案件
                table.cellClicked.connect(self._on_company_cell_clicked)

            self._tab_widget.addTab(table, sheet_name)

    # ── 互動 handler ──────────────────────────────────────────────────

    def _navigate_to_sheet(self, link_text: str) -> bool:
        """依連結文字模糊比對分頁名稱並跳轉，成功回傳 True。"""
        company_name = link_text.lstrip("→↩ ").replace("問題記錄", "").replace("返回客戶索引", "").strip()
        for sheet_name, idx in getattr(self, "_sheet_tab_index", {}).items():
            if company_name and (company_name in sheet_name or sheet_name.replace("_問題", "") in link_text):
                self._tab_widget.setCurrentIndex(idx)
                return True
        # 「返回客戶索引」直接跳第 0 頁
        if "客戶索引" in link_text:
            self._tab_widget.setCurrentIndex(self._sheet_tab_index.get("📋 客戶索引", 0))
            return True
        return False

    def _on_index_cell_clicked(self, row: int, col: int) -> None:
        """客戶索引：單擊快速連結欄跳轉至對應公司分頁。"""
        table = self.sender()
        if not isinstance(table, QTableWidget):
            return
        # 動態判斷欄位標頭是否為「快速連結」
        header = table.horizontalHeaderItem(col)
        if not header or header.text() != "快速連結":
            return
        item = table.item(row, col)
        if item and item.text().strip():
            self._navigate_to_sheet(item.text().strip())

    def _on_company_cell_clicked(self, row: int, col: int) -> None:
        """公司分頁：單擊 Row 0（↩ 返回客戶索引）跳回索引。"""
        table = self.sender()
        if not isinstance(table, QTableWidget):
            return
        item = table.item(row, 0)
        if item and "返回客戶索引" in item.text():
            self._tab_widget.setCurrentIndex(self._sheet_tab_index.get("📋 客戶索引", 0))

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        """雙擊儲存格：
        - 客戶索引快速連結欄 → 跳轉（不彈 popup）
        - 公司分頁案件列（col 0 = case_id）→ 開啟案件詳情
        - 其他 → 彈出完整內容視窗
        """
        table = self.sender()
        if not isinstance(table, QTableWidget):
            return

        current_sheet = self._tab_widget.tabText(self._tab_widget.currentIndex())

        # 客戶索引 快速連結欄 → 跳轉（不彈 popup）
        if current_sheet == "📋 客戶索引":
            header = table.horizontalHeaderItem(col)
            if header and header.text() == "快速連結":
                item = table.item(row, col)
                if item and item.text().strip():
                    self._navigate_to_sheet(item.text().strip())
                return

        # 公司分頁 案件列（row >= 2，col 0 含 case_id）→ 開啟案件詳情
        if current_sheet not in ("📋 客戶索引", "問題追蹤總表", "QA知識庫", "Mantis提單追蹤"):
            item0 = table.item(row, 0)
            if item0 and item0.text().startswith("CS-") and self._conn:
                case_id = item0.text()
                self._open_case_detail(case_id)
                return

        # 預設：彈出完整內容視窗
        item = table.item(row, col)
        if not item or not item.text().strip():
            return
        header = table.horizontalHeaderItem(col)
        col_name = header.text() if header else f"欄 {col + 1}"
        dlg = QDialog(self)
        dlg.setWindowTitle(f"第 {row + 1} 列 — {col_name}")
        dlg.setMinimumSize(520, 320)
        layout = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setPlainText(item.text())
        te.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(te)
        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)
        dlg.exec()

    def _open_case_detail(self, case_id: str) -> None:
        """從報表中心開啟案件詳情對話框。"""
        try:
            from hcp_cms.ui.case_detail_dialog import CaseDetailDialog

            dlg = CaseDetailDialog(self._conn, case_id, parent=self.window())
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "開啟案件失敗", str(e))

    def _fill_cs_report_preview(self) -> None:
        """產生「客服問題彙整」報表並填入 QTabWidget 預覽。"""
        from hcp_cms.core.cs_report_engine import HEADER, CSReportEngine

        try:
            engine = CSReportEngine(self._conn)
            rows = engine.build_rows()

            # 轉成 _fill_preview 所需的 dict[str, list[list]] 格式
            header_row = list(HEADER)
            data_rows = [row.as_list() for row in rows]
            preview_data: dict[str, list[list]] = {
                "客服問題彙整": [header_row] + data_rows,
            }

            self._preview_data = preview_data
            self._fill_preview(preview_data)
            self._download_btn.setEnabled(False)  # 客服問題彙整目前不支援 xlsx 下載

            if rows:
                self._status.setText(f"✅ 預覽完成，共 {len(rows)} 筆")
            else:
                self._status.setText("⚠️ 目前無案件資料")

        except Exception as e:
            self._status.setText(f"❌ 載入失敗：{e}")
            QMessageBox.critical(self, "載入失敗", str(e))

    def _on_sync_to_sheets(self) -> None:
        """將客服問題彙整報表同步至 Google Sheets。"""
        from PySide6.QtCore import QSettings

        from hcp_cms.core.cs_report_engine import HEADER, CSReportEngine
        from hcp_cms.services.google_sheets_service import GoogleSheetsService

        settings = QSettings("HCP", "CMS")
        sheet_url = settings.value("google/sheet_url", "", type=str)
        client_secret = settings.value("google/client_secret_path", "", type=str)
        if not sheet_url or not client_secret:
            QMessageBox.warning(
                self,
                "未設定 Google Sheets",
                "請先於「設定」→「Google Sheets 同步」填寫 Sheet URL 與 client_secret 路徑。",
            )
            return

        self._status.setText("⏳ 正在同步至 Google Sheets，請稍候（瀏覽器可能會彈出授權視窗）...")
        self._status.repaint()

        try:
            svc = GoogleSheetsService(
                client_secret_path=Path(client_secret),
                spreadsheet_url=sheet_url,
            )
            svc.authenticate()
            engine = CSReportEngine(self._conn)
            rows = engine.build_rows()
            # 附加 case_id 作為 upsert 的識別欄位（第 11 欄，index=10）
            header_with_id = list(HEADER) + ["case_id"]
            data = [(r.case_id, r.as_list() + [r.case_id]) for r in rows]
            svc.upsert(header_with_id, data, id_column_index=10)
            QMessageBox.information(self, "同步完成", f"已同步 {len(rows)} 筆案件至 Google Sheets。")
            self._status.setText(f"✅ 已同步 {len(rows)} 筆")
        except Exception as exc:
            logging.getLogger(__name__).exception("Google Sheets 同步失敗")
            self._status.setText("❌ 同步失敗")
            QMessageBox.critical(self, "同步失敗", str(exc))

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

        path, _ = QFileDialog.getSaveFileName(self, "儲存報表", default_path, "Excel 檔案 (*.xlsx)")
        if not path:
            return

        try:
            engine = ReportEngine(self._conn)
            if report_type == "追蹤表":
                engine.generate_tracking_table(start, end, Path(path))
            else:
                engine.generate_monthly_report(start, end, Path(path))
            self._status.setText(f"✅ 報表已儲存：{path}")

            reply = QMessageBox.question(
                self,
                "報表下載完成",
                f"報表已儲存至：\n{path}\n\n是否立即開啟？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                open_file(path)

        except Exception as e:
            self._status.setText(f"❌ 下載失敗：{e}")
            QMessageBox.critical(self, "下載失敗", str(e))

    def _apply_theme(self, p: ColorPalette) -> None:
        """套用主題色彩。"""
        self._title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p.text_primary};")
        self._status.setStyleSheet(f"color: {p.text_muted};")
