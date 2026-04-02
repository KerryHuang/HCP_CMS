"""Sent mail backup tab widget."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime
from typing import cast

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.excel_exporter import ExcelExporter
from hcp_cms.core.sent_mail_manager import EnrichedSentMail, SentMailManager
from hcp_cms.data.models import Company
from hcp_cms.data.repositories import CompanyRepository
from hcp_cms.services.mail.base import MailProvider
from hcp_cms.ui.theme import ColorPalette, ThemeManager


class _UnknownCompanyDialog(QDialog):
    """當收件人公司未知時，讓使用者將 email domain 指定到現有公司或新增公司。"""

    def __init__(
        self,
        conn: sqlite3.Connection,
        domain: str,
        recipient_email: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._domain = domain
        self._recipient = recipient_email
        self._companies: list[Company] = []
        self.setWindowTitle("指定未知公司")
        self.setMinimumWidth(440)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── 未識別資訊 ─────────────────────────────────────────────
        info_box = QGroupBox("未識別的收件人")
        info_layout = QFormLayout(info_box)
        info_layout.addRow("Email：", QLabel(self._recipient))
        domain_lbl = QLabel(f"<b>{self._domain}</b>")
        domain_lbl.setStyleSheet("color: #fbbf24;")
        info_layout.addRow("@後方網域：", domain_lbl)
        layout.addWidget(info_box)

        # ── 指定到現有公司 ─────────────────────────────────────────
        exist_box = QGroupBox("▸ 指定到現有公司")
        exist_layout = QVBoxLayout(exist_box)

        repo = CompanyRepository(self._conn)
        self._companies = repo.list_all()

        self._company_combo = QComboBox()
        for c in self._companies:
            label = f"{c.name}（網域：{c.domain or '尚未設定'}）"
            self._company_combo.addItem(label, c.company_id)
        exist_layout.addWidget(self._company_combo)

        assign_btn = QPushButton("✅ 將此網域指定到選取公司")
        assign_btn.clicked.connect(self._on_assign)
        exist_layout.addWidget(assign_btn)
        layout.addWidget(exist_box)

        # ── 新增為新公司 ───────────────────────────────────────────
        new_box = QGroupBox("▸ 新增為新公司")
        new_layout = QFormLayout(new_box)
        self._new_name_edit = QLineEdit()
        self._new_name_edit.setPlaceholderText("請輸入公司名稱")
        new_layout.addRow("公司名稱：", self._new_name_edit)
        new_btn = QPushButton("➕ 新增公司並套用此網域")
        new_btn.clicked.connect(self._on_new_company)
        new_layout.addRow(new_btn)
        layout.addWidget(new_box)

        # ── 取消 ───────────────────────────────────────────────────
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

    def _on_assign(self) -> None:
        idx = self._company_combo.currentIndex()
        if idx < 0 or idx >= len(self._companies):
            return
        company = self._companies[idx]
        # 若已有不同網域，詢問確認
        if company.domain and company.domain.lower() != self._domain.lower():
            ret = QMessageBox.question(
                self,
                "確認更換網域",
                f"公司「{company.name}」目前網域為「{company.domain}」，\n"
                f"確定要更換為「{self._domain}」嗎？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                return
        company.domain = self._domain
        CompanyRepository(self._conn).update(company)
        QMessageBox.information(
            self, "已儲存",
            f"已將網域「{self._domain}」指定到公司「{company.name}」。\n"
            "返回後清單將自動重新整理。"
        )
        self.accept()

    def _on_new_company(self) -> None:
        name = self._new_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "請輸入名稱", "請輸入公司名稱後再新增。")
            return
        new_company = Company(
            company_id=uuid.uuid4().hex[:8],
            name=name,
            domain=self._domain,
        )
        CompanyRepository(self._conn).insert(new_company)
        QMessageBox.information(
            self, "已新增",
            f"已新增公司「{name}」並設定網域「{self._domain}」。\n"
            "返回後清單將自動重新整理。"
        )
        self.accept()


class SentMailTab(QWidget):
    """寄件備份分頁：顯示寄件清單與公司彙總統計。"""

    _worker_done = Signal(object)
    _worker_error = Signal(str)

    def __init__(self, conn: sqlite3.Connection | None = None, theme_mgr: ThemeManager | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._theme_mgr = theme_mgr
        self._provider: MailProvider | None = None
        self._current_mails: list[EnrichedSentMail] = []
        self._setup_ui()
        if theme_mgr:
            self._apply_theme(theme_mgr.current_palette())
            theme_mgr.theme_changed.connect(self._apply_theme)

    def set_provider(self, provider: MailProvider | None) -> None:
        """由 EmailView 在連線成功後呼叫。"""
        self._provider = provider

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)

        # --- 日期導航列（同收件分頁） ---
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("日期:"))

        prev_week_btn = QPushButton("◀◀")
        prev_week_btn.setFixedWidth(42)
        prev_week_btn.setToolTip("前七天")
        prev_week_btn.clicked.connect(self._on_prev_week)
        filter_layout.addWidget(prev_week_btn)

        prev_btn = QPushButton("◀")
        prev_btn.setFixedWidth(36)
        prev_btn.setToolTip("前一天")
        prev_btn.clicked.connect(self._on_prev_day)
        filter_layout.addWidget(prev_btn)

        self._date_edit = QDateEdit(QDate.currentDate())
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy/MM/dd")
        filter_layout.addWidget(self._date_edit)

        next_btn = QPushButton("▶")
        next_btn.setFixedWidth(36)
        next_btn.setToolTip("後一天")
        next_btn.clicked.connect(self._on_next_day)
        filter_layout.addWidget(next_btn)

        next_week_btn = QPushButton("▶▶")
        next_week_btn.setFixedWidth(42)
        next_week_btn.setToolTip("後七天")
        next_week_btn.clicked.connect(self._on_next_week)
        filter_layout.addWidget(next_week_btn)

        today_btn = QPushButton("今天")
        today_btn.setFixedWidth(50)
        today_btn.clicked.connect(self._on_today)
        filter_layout.addWidget(today_btn)

        self._refresh_btn = QPushButton("🔄 重新整理")
        self._refresh_btn.clicked.connect(self._on_refresh)
        filter_layout.addWidget(self._refresh_btn)

        self._export_btn = QPushButton("📥 匯出 Excel")
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._on_export)
        filter_layout.addWidget(self._export_btn)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # 自訂區間列 — 起 [DateEdit] ~ 迄 [DateEdit] [載入]
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("區間：起"))
        self._range_start_edit = QDateEdit(QDate.currentDate().addDays(-30))
        self._range_start_edit.setCalendarPopup(True)
        self._range_start_edit.setDisplayFormat("yyyy/MM/dd")
        range_layout.addWidget(self._range_start_edit)
        range_layout.addWidget(QLabel("~  迄"))
        self._range_end_edit = QDateEdit(QDate.currentDate())
        self._range_end_edit.setCalendarPopup(True)
        self._range_end_edit.setDisplayFormat("yyyy/MM/dd")
        range_layout.addWidget(self._range_end_edit)
        range_load_btn = QPushButton("🔄 載入區間")
        range_load_btn.setToolTip("依指定起迄日期載入寄件備份")
        range_load_btn.clicked.connect(self._on_range_fetch)
        range_layout.addWidget(range_load_btn)
        range_layout.addStretch()
        layout.addLayout(range_layout)

        # --- 公司彙總表 ---
        self._summary_label = QLabel("公司彙總")
        layout.addWidget(self._summary_label)

        self._summary_table = QTableWidget(0, 2)
        self._summary_table.setHorizontalHeaderLabels(["公司名稱", "次數"])
        self._summary_table.setFixedHeight(120)
        self._summary_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._summary_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._summary_table.horizontalHeader().resizeSection(1, 60)
        layout.addWidget(self._summary_table)

        # --- 寄件清單 ---
        self._list_label = QLabel("寄件清單")
        layout.addWidget(self._list_label)

        self._list_table = QTableWidget(0, 6)
        self._list_table.setHorizontalHeaderLabels(["日期", "收件人", "主旨", "公司", "案件", "第幾封"])
        self._list_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self._list_table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for col in [0, 1, 3, 4, 5]:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        self._list_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self._list_table, stretch=1)

        # --- 日誌 ---
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(80)
        self._log.setPlaceholderText("處理日誌...")
        layout.addWidget(self._log)

        self._worker_done.connect(self._on_worker_done, Qt.ConnectionType.QueuedConnection)
        self._worker_error.connect(self._on_worker_error, Qt.ConnectionType.QueuedConnection)

    def _apply_theme(self, p: ColorPalette) -> None:
        """套用主題色彩。"""
        self._summary_label.setStyleSheet(f"font-weight: bold; color: {p.text_primary};")
        self._list_label.setStyleSheet(f"font-weight: bold; color: {p.text_primary};")

    # --- 日期導航 ---

    def _on_prev_week(self) -> None:
        d = self._date_edit.date()
        start = d.addDays(-6)
        until = datetime(d.year(), d.month(), d.day(), 23, 59, 59)
        since = datetime(start.year(), start.month(), start.day())
        self._date_edit.setDate(start)
        self._fetch(since=since, until=until)

    def _on_prev_day(self) -> None:
        self._date_edit.setDate(self._date_edit.date().addDays(-1))
        self._on_refresh()

    def _on_next_day(self) -> None:
        self._date_edit.setDate(self._date_edit.date().addDays(1))
        self._on_refresh()

    def _on_next_week(self) -> None:
        d = self._date_edit.date()
        end = d.addDays(6)
        since = datetime(d.year(), d.month(), d.day())
        until = datetime(end.year(), end.month(), end.day(), 23, 59, 59)
        self._date_edit.setDate(end)
        self._fetch(since=since, until=until)

    def _on_today(self) -> None:
        self._date_edit.setDate(QDate.currentDate())
        self._on_refresh()

    def _on_range_fetch(self) -> None:
        """依自訂起迄日期載入寄件備份。"""
        if not self._provider:
            return
        s = self._range_start_edit.date()
        e = self._range_end_edit.date()
        if s > e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self.parent(), "日期錯誤", "起始日期不可晚於迄日期。")
            return
        since = datetime(s.year(), s.month(), s.day())
        until = datetime(e.year(), e.month(), e.day(), 23, 59, 59)
        self._fetch(since=since, until=until)

    def _on_refresh(self) -> None:
        d = self._date_edit.date()
        self._fetch(
            since=datetime(d.year(), d.month(), d.day()),
            until=datetime(d.year(), d.month(), d.day(), 23, 59, 59),
        )

    # --- 背景抓取 ---

    def _fetch(self, since: datetime, until: datetime) -> None:
        if not self._conn:
            self._log.append("⚠️ 資料庫未連線。")
            return
        if not self._provider:
            self._log.append("⚠️ 請先連線信箱。")
            return
        self._refresh_btn.setEnabled(False)
        if since.date() == until.date():
            self._log.append(f"正在取得 {since.strftime('%Y/%m/%d')} 的寄件備份...")
        else:
            self._log.append(f"正在取得 {since.strftime('%Y/%m/%d')} ~ {until.strftime('%Y/%m/%d')} 的寄件備份...")

        conn = self._conn
        provider = self._provider

        def _work() -> list[EnrichedSentMail]:
            return SentMailManager(conn, provider).fetch_and_enrich(since, until)

        def _thread() -> None:
            try:
                self._worker_done.emit(_work())
            except Exception as e:
                self._worker_error.emit(str(e))

        threading.Thread(target=_thread, daemon=True).start()

    def _on_worker_done(self, results: object) -> None:
        mails = cast(list[EnrichedSentMail], results)
        self._refresh_btn.setEnabled(True)
        self._current_mails = mails
        self._export_btn.setEnabled(len(mails) > 0)
        self._log.append(f"✅ 取得 {len(mails)} 封寄件備份。")
        self._populate_tables(mails)

    def _on_worker_error(self, msg: str) -> None:
        self._refresh_btn.setEnabled(True)
        self._log.append(f"❌ 錯誤：{msg}")

    # --- 渲染 ---

    @staticmethod
    def _norm_subject(subject: str) -> str:
        """正規化主旨以進行 thread 比對：
        1. 去除 | 前綴
        2. 去除 RE:/FW: 等前綴
        3. 去除尾端括號標記（如 (回覆結案)、(RD_XXX)、(** Security C**)）
        """
        import re

        from hcp_cms.core.thread_tracker import ThreadTracker
        s = (subject or "").strip().lstrip("|").strip()
        s = ThreadTracker.clean_subject(s)
        # 去除尾端所有括號標記（全形/半形）
        s = re.sub(r'\s*[\(（][^)）]*[\)）]', '', s).strip()
        return s.lower()

    def _populate_tables(self, mails: list[EnrichedSentMail]) -> None:
        # 彙總表：以該公司總寄件封數計算次數，依次數降冪
        company_names: dict[str, str] = {}
        company_counts: dict[str, int] = {}
        for m in mails:
            if m.company_id:
                company_names.setdefault(m.company_id, m.company_name or m.company_id)
                company_counts[m.company_id] = company_counts.get(m.company_id, 0) + 1
        ranked = sorted(
            [(company_names[cid], cnt) for cid, cnt in company_counts.items()],
            key=lambda x: x[1],
            reverse=True,
        )
        self._summary_table.setRowCount(len(ranked))
        for row, (name, count) in enumerate(ranked):
            self._summary_table.setItem(row, 0, QTableWidgetItem(name))
            self._summary_table.setItem(row, 1, QTableWidgetItem(str(count)))

        # 寄件清單
        self._list_table.setRowCount(len(mails))
        # 第幾封：以 (company_id, 正規化主旨) 為 key，同一 thread 連續計數
        thread_counters: dict[tuple[str, str], int] = {}
        for row, m in enumerate(mails):
            self._list_table.setItem(row, 0, QTableWidgetItem(m.date if m.date else ""))
            self._list_table.setItem(row, 1, QTableWidgetItem(", ".join(m.recipients)))
            self._list_table.setItem(row, 2, QTableWidgetItem(m.subject))
            self._list_table.setItem(row, 3, QTableWidgetItem(m.company_name or "未知"))
            case_text = m.linked_case_id or "—"
            case_item = QTableWidgetItem(case_text)
            if m.linked_case_id:
                case_item.setToolTip("雙擊複製案件編號")
            self._list_table.setItem(row, 4, case_item)
            if m.company_id:
                key = (m.company_id, self._norm_subject(m.subject))
                thread_counters[key] = thread_counters.get(key, 0) + 1
                count_text = str(thread_counters[key])
            else:
                count_text = "—"
            self._list_table.setItem(row, 5, QTableWidgetItem(count_text))

    def _on_export(self) -> None:
        d = self._date_edit.date()
        default_name = f"寄件備份_{d.toString('yyyy-MM-dd')}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "匯出 Excel",
            default_name,
            "Excel 檔案 (*.xlsx)",
        )
        if not path:
            return
        try:
            ExcelExporter().export_sent_mail(self._current_mails, path)
            self._log.append(f"✅ 已匯出至 {path}")
        except Exception as e:
            self._log.append(f"❌ 匯出失敗：{e}")

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        if col == 4:
            # 複製案件編號
            item = self._list_table.item(row, col)
            if item and item.text() != "—":
                QApplication.clipboard().setText(item.text())
                self._log.append(f"📋 已複製案件編號：{item.text()}")
        elif col == 3:
            # 公司欄「未知」→ 開啟維護視窗
            item = self._list_table.item(row, col)
            if item and item.text() == "未知" and self._conn:
                if row < len(self._current_mails):
                    mail = self._current_mails[row]
                    recipient = mail.recipients[0] if mail.recipients else ""
                    domain = recipient.split("@", 1)[1].lower().strip() if "@" in recipient else ""
                    if not domain:
                        QMessageBox.information(
                            self, "無法識別",
                            f"收件人「{recipient}」無法解析網域。"
                        )
                        return
                    dlg = _UnknownCompanyDialog(self._conn, domain, recipient, self)
                    if dlg.exec() == QDialog.DialogCode.Accepted:
                        # 重新抓取並更新清單
                        self._on_refresh()
