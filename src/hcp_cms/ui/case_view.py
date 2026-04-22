"""Case management view — list, detail, CRUD."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
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
from hcp_cms.core.kms_engine import KMSEngine
from hcp_cms.data.fts import FTSManager
from hcp_cms.data.repositories import CaseLogRepository, CaseRepository, CompanyRepository
from hcp_cms.ui.theme import ColorPalette, ThemeManager

_FIXED_COL_COUNT = 9


def _html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _calc_elapsed(sent_time: str | None, end_time: str | None) -> str:
    """計算案件總處理時長（寄件時間 → end_time；end_time 為 None 則用現在）。"""
    if not sent_time:
        return ""
    fmt = "%Y/%m/%d %H:%M"
    try:
        start = datetime.strptime(sent_time[:16], fmt)
        end_str = (end_time or "")[:16] or datetime.now().strftime(fmt)
        end = datetime.strptime(end_str, fmt)
        total_minutes = max(0, int((end - start).total_seconds() / 60))
        hours, minutes = divmod(total_minutes, 60)
        days, hours = divmod(hours, 24)
        if days:
            return f"{days}天{hours}時" if hours else f"{days}天"
        if hours:
            return f"{hours}時{minutes}分" if minutes else f"{hours}時"
        return f"{minutes}分"
    except Exception:
        return ""


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

        relink_btn = QPushButton("🔗 串接對話串")
        relink_btn.setToolTip("重新掃描所有案件，自動補齊遺漏的回覆串關聯")
        relink_btn.clicked.connect(self._on_relink_threads)
        header.addWidget(relink_btn)

        new_btn = QPushButton("➕ 手動建案")
        new_btn.clicked.connect(self._on_new_case)
        header.addWidget(new_btn)

        import_btn = QPushButton("📥 匯入 CSV")
        import_btn.clicked.connect(self._on_import_csv)
        header.addWidget(import_btn)

        self._delete_selected_btn = QPushButton("🗑 刪除選取")
        self._delete_selected_btn.setObjectName("dangerBtn")
        self._delete_selected_btn.setToolTip("刪除目前選取的案件（需先點選一筆）")
        self._delete_selected_btn.setEnabled(False)
        self._delete_selected_btn.clicked.connect(self._on_delete_single_case)
        header.addWidget(self._delete_selected_btn)

        self._assign_company_btn = QPushButton("🏢 指定公司")
        self._assign_company_btn.setToolTip("為選取的案件批次指定公司，並自動整併同主旨案件")
        self._assign_company_btn.setEnabled(False)
        self._assign_company_btn.clicked.connect(self._on_assign_company)
        header.addWidget(self._assign_company_btn)

        self._delete_btn = QPushButton("🗑 批次刪除")
        self._delete_btn.setObjectName("dangerBtn")
        self._delete_btn.setToolTip("依日期範圍批次刪除案件")
        self._delete_btn.clicked.connect(self._on_delete_cases)
        header.addWidget(self._delete_btn)

        layout.addLayout(header)

        # Splitter: table + detail
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Case table
        self._table = QTableWidget(0, _FIXED_COL_COUNT)
        self._table.setHorizontalHeaderLabels([
            "案件編號", "狀態", "優先", "公司", "主旨", "問題類型", "處理時長", "來回次數", "時間"
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
        self._detail_progress.setReadOnly(True)
        self._detail_progress.setMinimumHeight(200)

        detail_layout.addRow("案件編號:", self._detail_id)
        detail_layout.addRow("主旨:", self._detail_subject)
        detail_layout.addRow("狀態:", self._detail_status)
        detail_layout.addRow("系統產品:", self._detail_system_product)
        detail_layout.addRow("功能模組:", self._detail_error_type)
        detail_layout.addRow("技術人員:", self._detail_handler)
        detail_layout.addRow("來回次數:", self._detail_reply_count)
        detail_layout.addRow("關聯案件:", self._detail_linked_case)
        detail_layout.addRow("對話記錄:", self._detail_progress)

        # Action buttons
        btn_layout = QHBoxLayout()
        self._btn_reply = QPushButton("✅ 標記已回覆")
        self._btn_reply.clicked.connect(self._on_mark_replied)
        btn_layout.addWidget(self._btn_reply)

        self._btn_close = QPushButton("🔒 結案")
        self._btn_close.clicked.connect(self._on_close_case)
        btn_layout.addWidget(self._btn_close)

        self._btn_add_release = QPushButton("📋 加入待發清單")
        self._btn_add_release.clicked.connect(self._on_add_to_release)
        btn_layout.addWidget(self._btn_add_release)

        self._btn_add_kms = QPushButton("📚 加入知識庫")
        self._btn_add_kms.setToolTip("將此案件的客戶問題與 HCP 回覆加入知識庫（建為待審核）")
        self._btn_add_kms.clicked.connect(self._on_add_to_kms)
        btn_layout.addWidget(self._btn_add_kms)

        detail_layout.addRow(btn_layout)

        # 相似知識庫面板
        kms_group = QGroupBox("🔍 相似知識庫")
        kms_group.setStyleSheet(
            "QGroupBox { color: #94a3b8; font-size: 11px; border: 1px solid #334155;"
            " border-radius:4px; margin-top:6px; padding-top:8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
        )
        kms_inner = QVBoxLayout(kms_group)
        kms_inner.setContentsMargins(4, 4, 4, 4)
        self._kms_panel = QTextEdit()
        self._kms_panel.setReadOnly(True)
        self._kms_panel.setMinimumHeight(80)
        self._kms_panel.setMaximumHeight(160)
        self._kms_panel.setHtml("<i style='color:#6b7280'>（選取案件後自動搜尋）</i>")
        kms_inner.addWidget(self._kms_panel)
        detail_layout.addRow(kms_group)

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
                kw_lower = keyword.lower()
                kw_parts = kw_lower.split()
                cases = [
                    c for c in all_cases
                    if c.case_id in matched_ids
                    or c.company_id in matched_company_ids
                    or all(p in (c.subject or "").lower() for p in kw_parts)
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
            headers = ["案件編號", "狀態", "優先", "公司", "主旨", "問題類型", "處理時長", "來回次數", "時間"]
            headers += [col.col_label for col in visible_cols]
            self._table.setHorizontalHeaderLabels(headers)

            self._table.setRowCount(len(cases))
            if not cases:
                self._clear_detail()
            for i, case in enumerate(cases):
                self._table.setItem(i, 0, QTableWidgetItem(case.case_id))
                self._table.setItem(i, 1, QTableWidgetItem(case.status))
                self._table.setItem(i, 2, QTableWidgetItem(case.priority))
                # 公司欄：優先顯示公司中文名稱，其次顯示 company_id
                company_display = company_map.get(case.company_id or "", case.company_id or "")
                self._table.setItem(i, 3, QTableWidgetItem(company_display))
                self._table.setItem(i, 4, QTableWidgetItem(case.subject or ""))
                self._table.setItem(i, 5, QTableWidgetItem(case.issue_type or ""))
                # 已完成案件用 updated_at（結案時間），處理中用 None（→ 現在）
                _end = case.updated_at if case.status in ("已完成", "Closed") else None
                elapsed_item = QTableWidgetItem(_calc_elapsed(case.sent_time, _end))
                elapsed_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(i, 6, elapsed_item)
                reply_item = QTableWidgetItem(str(case.reply_count) if case.reply_count else "")
                reply_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(i, 7, reply_item)
                self._table.setItem(i, 8, QTableWidgetItem(case.sent_time or ""))
                for j, col in enumerate(visible_cols):
                    val = case.extra_fields.get(col.col_key) or ""
                    self._table.setItem(i, _FIXED_COL_COUNT + j, QTableWidgetItem(val))
        except Exception:
            pass

        # refresh 後若目前選取的案件不在新清單中，清空詳情面板
        current_id = self._detail_id.text()
        if current_id and not any(c.case_id == current_id for c in self._cases):
            self._clear_detail()

    def _clear_detail(self) -> None:
        """清空下方詳細資訊面板。"""
        self._delete_selected_btn.setEnabled(False)
        self._assign_company_btn.setEnabled(False)
        self._detail_id.clear()
        self._detail_subject.clear()
        self._detail_status.clear()
        self._detail_system_product.clear()
        self._detail_error_type.clear()
        self._detail_handler.clear()
        self._detail_reply_count.clear()
        self._detail_linked_case.clear()
        self._detail_progress.clear()
        if hasattr(self, "_kms_panel"):
            self._kms_panel.setHtml("<i style='color:#6b7280'>（選取案件後自動搜尋）</i>")

    def _on_selection_changed(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        self._delete_selected_btn.setEnabled(bool(rows))
        self._assign_company_btn.setEnabled(bool(rows))
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
        self._detail_progress.setHtml(self._build_log_html(case))
        self._refresh_kms_panel(case.subject or "")

    def _build_log_html(self, case) -> str:
        """從 case_logs 建立 HTML 格式的對話時間軸。"""
        case_id: str = case.case_id
        progress: str | None = case.progress
        if not self._conn:
            return progress or ""
        logs = CaseLogRepository(self._conn).list_by_case(case_id)

        # 若完全無記錄：顯示建案基本資訊讓使用者知道脈絡
        if not logs and not progress:
            sent = case.sent_time or case.created_at or ""
            subj = _html_escape(case.subject or "")
            return (
                f"<div style='background:#1e293b;border-left:3px solid #475569;"
                f"padding:6px 8px;margin-bottom:6px;border-radius:3px;'>"
                f"<span style='color:#94a3b8;font-size:11px;'>📨 建案（尚無後續對話記錄）</span>"
                f"<span style='color:#64748b;font-size:11px;margin-left:8px;'>{_html_escape(sent)}</span><br>"
                f"<span style='color:#e2e8f0;font-size:12px;white-space:pre-wrap;'>{subj}</span></div>"
            )

        direction_color = {
            "客戶來信": "#f59e0b",
            "HCP 信件回覆": "#3b82f6",
            "HCP 線上回覆": "#10b981",
            "內部討論": "#8b5cf6",
        }
        parts: list[str] = []

        if progress:
            parts.append(
                f"<div style='background:#1e293b;border-left:3px solid #6b7280;"
                f"padding:6px 8px;margin-bottom:6px;border-radius:3px;'>"
                f"<span style='color:#94a3b8;font-size:11px;'>📋 處理進度</span><br>"
                f"<span style='color:#e2e8f0;white-space:pre-wrap;'>{_html_escape(progress)}</span></div>"
            )

        for log in logs:
            color = direction_color.get(log.direction, "#94a3b8")
            preview = (log.content or "").strip()
            parts.append(
                f"<div style='background:#1e293b;border-left:3px solid {color};"
                f"padding:6px 8px;margin-bottom:6px;border-radius:3px;'>"
                f"<span style='color:{color};font-weight:bold;font-size:11px;'>"
                f"{_html_escape(log.direction)}</span>"
                f"<span style='color:#64748b;font-size:11px;margin-left:8px;'>"
                f"{_html_escape(log.logged_at)}</span><br>"
                f"<span style='color:#e2e8f0;font-size:12px;white-space:pre-wrap;'>"
                f"{_html_escape(preview)}</span></div>"
            )

        return "".join(parts) if parts else "<i style='color:#6b7280'>（尚無對話記錄）</i>"

    def _refresh_kms_panel(self, subject: str) -> None:
        """以案件主旨搜尋相似 KMS 條目，更新面板顯示（最多 3 筆）。"""
        if not hasattr(self, "_kms_panel"):
            return
        if not self._conn or not subject.strip():
            self._kms_panel.setHtml("<i style='color:#6b7280'>（無主旨，無法搜尋）</i>")
            return
        try:
            results = KMSEngine(self._conn).search(subject.strip())[:3]
        except Exception:
            self._kms_panel.setHtml("<i style='color:#6b7280'>（搜尋失敗）</i>")
            return

        if not results:
            self._kms_panel.setHtml(
                "<i style='color:#6b7280'>（無相似知識庫條目）</i>"
            )
            return

        parts: list[str] = []
        for qa in results:
            q_raw = (qa.question or "")
            a_raw = (qa.answer or "")
            q = _html_escape(q_raw[:80])
            a = _html_escape(a_raw[:120])
            a_suffix = "…" if len(a_raw) > 120 else ""
            qid = _html_escape(qa.qa_id)
            parts.append(
                f"<div style='border-left:3px solid #3b82f6;padding:4px 6px;"
                f"margin-bottom:4px;background:#1e293b;border-radius:2px;'>"
                f"<span style='color:#60a5fa;font-size:11px;font-weight:bold;'>{qid}</span><br>"
                f"<span style='color:#e2e8f0;font-size:11px;'>Q: {q}</span><br>"
                f"<span style='color:#94a3b8;font-size:11px;'>A: {a}{a_suffix}</span>"
                f"</div>"
            )
        self._kms_panel.setHtml("".join(parts))

    def _on_relink_threads(self) -> None:
        if not self._conn:
            return
        reply = QMessageBox.question(
            self, "串接對話串",
            "將重新掃描所有案件，自動補齊遺漏的回覆串關聯（不刪除任何資料）。\n\n確定執行？",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = CaseManager(self._conn).relink_threads()
        self.refresh()
        QMessageBox.information(
            self, "完成",
            f"建立對話串關聯：{result['linked']} 筆\n"
            f"同步結案狀態：{result['status_synced']} 筆"
        )

    def _on_new_case(self) -> None:
        if not self._conn:
            return
        from hcp_cms.ui.new_case_dialog import NewCaseDialog
        dlg = NewCaseDialog(self._conn, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            QMessageBox.information(self, "建案成功", f"案件 {dlg.created_case_id} 已建立。")

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

    def _on_assign_company(self) -> None:
        """批次指定公司並整併同主旨案件。"""
        if not self._conn:
            return
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return

        if not hasattr(self, '_cases'):
            return
        case_ids = []
        for idx in rows:
            row = idx.row()
            if 0 <= row < len(self._cases):
                case_ids.append(self._cases[row].case_id)
        if not case_ids:
            return

        from hcp_cms.ui.assign_company_dialog import AssignCompanyDialog
        dlg = AssignCompanyDialog(self._conn, len(case_ids), parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        company_id = dlg.selected_company_id
        if not company_id:
            return

        result = CaseManager(self._conn).batch_assign_company_and_merge(case_ids, company_id)

        updated = result["updated"]
        merged = result["merged"]
        merge_msg = (
            f"成功整併 {merged} 筆為同主旨根案件的子案件。"
            if merged > 0
            else "無需整併同主旨案件。"
        )
        QMessageBox.information(
            self,
            "完成",
            f"已更新 {updated} 筆案件的公司。\n{merge_msg}",
        )
        self.refresh()
        self.cases_changed.emit()

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

    def _on_add_to_release(self) -> None:
        """手動將目前案件加入待發清單。"""
        if not self._conn or not self._detail_id.text():
            return
        case_id = self._detail_id.text()

        # 從已載入的案件清單找到對應案件
        case = next(
            (c for c in self._cases if c.case_id == case_id),
            None,
        ) if hasattr(self, "_cases") else None

        # 讓使用者選擇目標月份
        from datetime import datetime

        from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout

        dlg = QDialog(self)
        dlg.setWindowTitle("加入待發清單")
        layout = QFormLayout(dlg)

        month_combo = QComboBox()
        now = datetime.now()
        for i in range(-3, 13):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            while m > 12:
                m -= 12
                y += 1
            ms = f"{y}{m:02d}"
            month_combo.addItem(f"{ms[:4]}/{ms[4:]}", ms)
        layout.addRow("目標月份：", month_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        target_month = month_combo.currentData()

        # 取得 Mantis 票號（取第一筆）與公司名稱
        import re as _re

        from hcp_cms.data.repositories import CaseMantisRepository, CompanyRepository

        mantis_links = CaseMantisRepository(self._conn).list_by_case_id(case_id)
        mantis_ticket_id = mantis_links[0].ticket_id if mantis_links else None

        client_name: str | None = None
        assignee: str | None = None
        if case:
            assignee = case.rd_assignee
            if case.company_id:
                comp = CompanyRepository(self._conn).get_by_id(case.company_id)
                client_name = comp.name if comp else None

        # fallback：若仍無資料，從主旨萃取 Mantis 通知格式 [公司名 XXXXXXX]:
        if not mantis_ticket_id or not client_name:
            _m = _re.match(r"^\[(.+?)\s+(\d{5,8})\]\s*:", case.subject or "") if case else None
            if _m:
                if not mantis_ticket_id:
                    mantis_ticket_id = _m.group(2)
                if not client_name:
                    client_name = _m.group(1).strip()

        from hcp_cms.core.release_manager import ReleaseDetector, ReleaseManager
        from hcp_cms.data.repositories import CaseLogRepository

        # 從對話記錄中嘗試萃取備注與修改者（優先最新的含觸發關鍵字的記錄）
        note = ""
        modifier: str | None = None
        try:
            logs = CaseLogRepository(self._conn).list_by_case(case_id)
            detector = ReleaseDetector(self._conn)
            for log in reversed(logs):
                result = detector.detect(log.content or "")
                if result:
                    if result.get("note"):
                        note = result["note"]
                    if result.get("modifier"):
                        modifier = result["modifier"]
                    break
        except Exception:
            pass

        ReleaseManager(self._conn).add_item(
            case_id=case_id,
            mantis_ticket_id=mantis_ticket_id,
            client_name=client_name,
            assignee=assignee,
            note=note,
            modifier=modifier,
            month_str=target_month,
        )
        label = mantis_ticket_id or case_id
        QMessageBox.information(
            self, "完成", f"已將 {label} 加入 {month_combo.currentText()} 待發清單。"
        )

    def _on_add_to_kms(self) -> None:
        """從目前案件的 HCP 回覆建立 KMS 待審核條目。"""
        if not self._conn or not self._detail_id.text():
            return
        case_id = self._detail_id.text()
        case = next(
            (c for c in self._cases if c.case_id == case_id),
            None,
        ) if hasattr(self, "_cases") else None
        if not case:
            return

        # 找最後一筆 HCP 回覆作為 answer
        from hcp_cms.data.repositories import CaseLogRepository
        logs = CaseLogRepository(self._conn).list_by_case(case_id)
        hcp_logs = [
            lg for lg in logs
            if lg.direction in ("HCP 信件回覆", "HCP 線上回覆")
        ]

        if not hcp_logs:
            QMessageBox.warning(
                self, "無回覆記錄",
                "此案件尚無 HCP 回覆記錄，無法自動建立知識庫條目。\n"
                "請先回覆案件，或至 KMS 知識庫手動新增。"
            )
            return

        answer = hcp_logs[-1].content or ""
        question = case.subject or ""

        # 彈出確認視窗，讓使用者確認問題與回覆內容
        _QTE = QTextEdit  # 方法內的別名，保持與下方 layout.addRow 相容
        dlg = QDialog(self)
        dlg.setWindowTitle("加入知識庫")
        dlg.setMinimumWidth(520)
        layout = QFormLayout(dlg)

        q_edit = _QTE()
        q_edit.setPlainText(question)
        q_edit.setMinimumHeight(60)
        layout.addRow("問題（Q）：", q_edit)

        a_edit = _QTE()
        a_edit.setPlainText(answer)
        a_edit.setMinimumHeight(120)
        layout.addRow("回覆（A）：", a_edit)

        info = QLabel(f"系統產品：{case.system_product or ''}　"
                      f"問題類型：{case.issue_type or ''}　"
                      f"功能模組：{case.error_type or ''}")
        info.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addRow("", info)

        hint = QLabel("⚠ 建立後狀態為「待審核」，請至 KMS 知識庫確認完成後才會納入搜尋。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #f59e0b; font-size: 11px;")
        layout.addRow("", hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        final_q = q_edit.toPlainText().strip()
        final_a = a_edit.toPlainText().strip()
        if not final_q or not final_a:
            QMessageBox.warning(self, "欄位不完整", "問題與回覆均不可為空。")
            return

        try:
            qa = KMSEngine(self._conn).create_qa(
                question=final_q,
                answer=final_a,
                system_product=case.system_product,
                issue_type=case.issue_type,
                error_type=case.error_type,
                source="case",
                source_case_id=case_id,
                status="待審核",
            )
        except Exception as e:
            QMessageBox.critical(self, "建立失敗", f"建立知識庫條目時發生錯誤：\n{e}")
            return
        QMessageBox.information(
            self, "完成",
            f"已建立知識庫條目 {qa.qa_id}（待審核）。\n"
            "請至「KMS 知識庫 → 待審核」確認後發布。"
        )

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
