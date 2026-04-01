"""Mantis sync view."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.mantis_classifier import MantisClassifier
from hcp_cms.data.repositories import MantisRepository
from hcp_cms.services.credential import CredentialManager
from hcp_cms.services.mantis.soap import MantisSoapClient
from hcp_cms.ui.theme import ColorPalette, ThemeManager


class _SortableItem(QTableWidgetItem):
    """支援數字排序的 QTableWidgetItem（用於「未處理天數」欄）。"""

    def __init__(self, text: str, sort_key: int) -> None:
        super().__init__(text)
        self._sort_key = sort_key

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, _SortableItem):
            return self._sort_key < other._sort_key
        return super().__lt__(other)


class _SyncWorker(QThread):
    """背景執行 Mantis SOAP 同步的 Worker。"""

    log_message = Signal(str)
    ticket_synced = Signal(str, str, str, str, str, str)  # ticket_id, summary, status, priority, handler, last_updated
    finished = Signal(int, int)  # success, failed

    def __init__(
        self,
        ticket_ids: list[str],
        client: MantisSoapClient,
        mantis_repo: MantisRepository,
    ) -> None:
        super().__init__()
        self._ticket_ids = ticket_ids
        self._client = client
        self._mantis_repo = mantis_repo

    def run(self) -> None:
        from datetime import datetime

        from hcp_cms.data.models import MantisTicket

        def now_str() -> str:
            return datetime.now().strftime("%Y/%m/%d %H:%M:%S")

        success = 0
        failed = 0
        for tid in self._ticket_ids:
            self.log_message.emit(f"⏳ 同步 #{tid}...")
            issue = self._client.get_issue(tid)
            if issue is None:
                self.log_message.emit(f"  ❌ #{tid} 無法取得（API 無回應或票號不存在）")
                failed += 1
                continue
            ticket = MantisTicket(
                ticket_id=issue.id,
                summary=issue.summary,
                status=issue.status,
                priority=issue.priority,
                handler=issue.handler,
                synced_at=now_str(),
                last_updated=issue.last_updated or "",
            )
            self._mantis_repo.upsert(ticket)
            self.log_message.emit(f"  ✅ #{tid} {issue.summary[:30]} [{issue.status}]")
            self.ticket_synced.emit(
                tid, issue.summary, issue.status, issue.priority, issue.handler, issue.last_updated or ""
            )
            success += 1
        self.finished.emit(success, failed)


class MantisView(QWidget):
    """Mantis 同步頁面 — 顯示所有已關聯的 Ticket 並可批次同步。"""

    # 分類色彩：(背景色 hex, 前景色 hex)
    _CATEGORY_COLORS: dict[str, tuple[str, str]] = {
        "high":   ("#450a0a", "#ffffff"),
        "salary": ("#422006", "#fef08a"),
        "normal": ("#111827", "#e2e8f0"),
        "closed": ("#1a1a1a", "#4b5563"),
    }

    @staticmethod
    def _make_stat_frame(label: str, bg: str, fg: str) -> tuple[QFrame, QLabel]:
        """建立統計方塊 QFrame，回傳 (frame, value_label)。"""
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {fg}; border-radius: 6px; }}"
        )
        frame.setFixedHeight(56)
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(2)
        value_lbl = QLabel("0")
        value_lbl.setStyleSheet(f"color: {fg}; font-size: 18px; font-weight: bold; border: none;")
        title_lbl = QLabel(label)
        title_lbl.setStyleSheet(f"color: {fg}; font-size: 10px; border: none;")
        layout.addWidget(value_lbl)
        layout.addWidget(title_lbl)
        return frame, value_lbl

    def __init__(self, conn: sqlite3.Connection | None = None, theme_mgr: ThemeManager | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._theme_mgr = theme_mgr
        self._creds = CredentialManager()
        self._worker: _SyncWorker | None = None
        self._setup_ui()
        if theme_mgr:
            self._apply_theme(theme_mgr.current_palette())
            theme_mgr.theme_changed.connect(self._apply_theme)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        self._title = QLabel("🔧 Mantis 同步")
        layout.addWidget(self._title)

        # ── 連線資訊（唯讀，設定請至系統設定）──────────────────────
        conn_group = QGroupBox("連線狀態")
        conn_layout = QHBoxLayout(conn_group)

        self._url_label = QLabel("尚未設定")
        conn_layout.addWidget(QLabel("Mantis URL："))
        conn_layout.addWidget(self._url_label, stretch=1)

        self._status_label = QLabel("●  未連線")
        self._status_label.setStyleSheet("color: #f87171; font-weight: bold;")
        conn_layout.addWidget(self._status_label)

        self._last_sync_label = QLabel("最後同步：—")
        self._last_sync_label.setStyleSheet("color: #94a3b8;")
        conn_layout.addWidget(self._last_sync_label)

        self._sync_btn = QPushButton("🔄 立即同步全部")
        self._sync_btn.setMinimumWidth(130)
        self._sync_btn.clicked.connect(self._on_sync_all)
        conn_layout.addWidget(self._sync_btn)

        self._auto_link_btn = QPushButton("🔗 批次自動連結案件")
        self._auto_link_btn.setToolTip(
            "掃描所有備註含 ISSUE# 的案件，自動建立 Mantis 關聯（不需逐筆手動連結）"
        )
        self._auto_link_btn.clicked.connect(self._on_auto_link_cases)
        conn_layout.addWidget(self._auto_link_btn)

        hint_btn = QPushButton("⚙ 設定帳密")
        hint_btn.setToolTip("請至「系統設定」→「Mantis SOAP 連線設定」填寫帳號密碼")
        hint_btn.clicked.connect(self._on_goto_settings)
        conn_layout.addWidget(hint_btn)

        layout.addWidget(conn_group)

        # ── 統計方塊列 ───────────────────────────────────────────
        stats_widget = QWidget()
        stats_layout = QHBoxLayout(stats_widget)
        stats_layout.setContentsMargins(0, 4, 0, 4)
        stats_layout.setSpacing(8)

        high_frame, self._stat_high_lbl = self._make_stat_frame("高優先度", "#450a0a", "#fca5a5")
        salary_frame, self._stat_salary_lbl = self._make_stat_frame("薪資相關", "#422006", "#fef08a")
        open_frame, self._stat_open_lbl = self._make_stat_frame("處理中", "#1e3a5f", "#93c5fd")
        closed_frame, self._stat_closed_lbl = self._make_stat_frame("已結案", "#1a1a1a", "#6b7280")

        stats_layout.addWidget(high_frame)
        stats_layout.addWidget(salary_frame)
        stats_layout.addWidget(open_frame)
        stats_layout.addWidget(closed_frame)
        stats_layout.addStretch()
        layout.addWidget(stats_widget)

        # ── 搜尋列 ───────────────────────────────────────────────
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("🔍  搜尋票號或摘要...")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setMaximumWidth(400)
        self._search_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search_edit)

        # ── Ticket 清單 ───────────────────────────────────────────
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["票號", "摘要", "狀態", "優先", "負責人", "Mantis 最後修改", "未處理天數"]
        )
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.setColumnWidth(0, 80)
        self._table.setColumnWidth(1, 320)
        self._table.setColumnWidth(2, 90)
        self._table.setColumnWidth(3, 60)
        self._table.setColumnWidth(4, 90)
        self._table.setColumnWidth(5, 120)
        self._table.setColumnWidth(6, 80)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSortingEnabled(True)
        self._table.sortByColumn(5, Qt.SortOrder.DescendingOrder)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self._table)

        # ── 同步記錄 ─────────────────────────────────────────────
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(110)
        self._log.setPlaceholderText("同步記錄...")
        layout.addWidget(self._log)

    # ── 頁面顯示時自動載入 ────────────────────────────────────────

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._load_credentials()
        self.refresh()

    def _load_credentials(self) -> None:
        url = self._creds.retrieve("mantis_url") or ""
        if url:
            base = self._extract_base_url(url)
            self._url_label.setText(base)
            self._url_label.setStyleSheet("color: #93c5fd;")
            self._status_label.setText("●  已設定（尚未同步）")
            self._status_label.setStyleSheet("color: #fbbf24; font-weight: bold;")
        else:
            self._url_label.setText("尚未設定（請至系統設定填寫）")
            self._url_label.setStyleSheet("color: #f87171;")
            self._status_label.setText("●  未設定")
            self._status_label.setStyleSheet("color: #f87171; font-weight: bold;")

    @staticmethod
    def _extract_base_url(url: str) -> str:
        """從任意 Mantis URL 萃取 base URL（去除頁面路徑與 query string）。
        例：https://host/mantis/view.php?id=123  →  https://host/mantis
        """
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path
        # 找最後一個 .php 的上一層目錄
        if ".php" in path:
            path = path[:path.rfind("/")]
        return f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/")

    # ── 未解決狀態集合（不計算天數的狀態視為已結案）────────────────
    _RESOLVED_STATUSES = {"resolved", "closed", "已解決", "已關閉", "已結案"}

    @staticmethod
    def _fmt_last_updated(raw: str | None) -> str:
        """將 ISO 8601 或其他格式的時間字串轉為 YYYY/MM/DD HH:MM 顯示。"""
        if not raw:
            return "—"
        from datetime import datetime
        _fmts = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d",
            "%Y-%m-%d",
        ]
        for fmt in _fmts:
            try:
                dt = datetime.strptime(raw.strip(), fmt)
                if dt.tzinfo is not None:
                    dt = dt.astimezone(tz=None).replace(tzinfo=None)
                return dt.strftime("%Y/%m/%d %H:%M")
            except ValueError:
                continue
        return raw

    @staticmethod
    def _calc_unresolved_days(status: str | None, last_updated: str | None) -> str:
        """計算截至今日尚未處理完成的天數（已解決/已關閉回傳空字串）。"""
        if not status:
            return ""
        if status.lower() in MantisView._RESOLVED_STATUSES:
            return ""
        if not last_updated:
            return ""
        from datetime import datetime
        _fmts = [
            ("%Y-%m-%dT%H:%M:%S", 19),
            ("%Y/%m/%d %H:%M:%S", 19),
            ("%Y-%m-%d %H:%M:%S", 19),
            ("%Y/%m/%d", 10),
            ("%Y-%m-%d", 10),
        ]
        for fmt, length in _fmts:
            try:
                dt = datetime.strptime(last_updated[:length], fmt)
                days = (datetime.now() - dt).days
                return f"{days} 天" if days >= 0 else ""
            except ValueError:
                continue
        return ""

    def refresh(self) -> None:
        """從本地 DB 載入已同步過的 Ticket 到清單，並套用分色與更新統計。"""
        if not self._conn:
            return
        repo = MantisRepository(self._conn)
        tickets = repo.list_all()

        # 更新最後同步標籤
        sync_times = [t.synced_at for t in tickets if t.synced_at]
        if sync_times:
            self._last_sync_label.setText(f"最後同步：{max(sync_times)}")

        classifier = MantisClassifier()

        # 填入資料前暫停排序，避免插入時觸發不必要的重排
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(tickets))

        for i, t in enumerate(tickets):
            ticket_item = QTableWidgetItem(t.ticket_id)
            # 將分類存入 UserRole，供 _apply_filter 計算統計用
            category = classifier.classify(t)
            ticket_item.setData(Qt.ItemDataRole.UserRole, category)
            self._table.setItem(i, 0, ticket_item)
            self._table.setItem(i, 1, QTableWidgetItem(t.summary or ""))
            self._table.setItem(i, 2, QTableWidgetItem(t.status or ""))
            self._table.setItem(i, 3, QTableWidgetItem(t.priority or ""))
            self._table.setItem(i, 4, QTableWidgetItem(t.handler or ""))
            self._table.setItem(i, 5, QTableWidgetItem(self._fmt_last_updated(t.last_updated)))

            days_str = classifier.calc_unresolved_days(t)
            try:
                days_num = int(days_str.split()[0]) if days_str else -1
            except (ValueError, IndexError):
                days_num = -1
            self._table.setItem(i, 6, _SortableItem(days_str, days_num))

            # 套用分色
            bg = QColor(self._CATEGORY_COLORS[category][0])
            fg = QColor(self._CATEGORY_COLORS[category][1])
            for col in range(7):
                item = self._table.item(i, col)
                if item:
                    item.setBackground(bg)
                    item.setForeground(fg)

        # 重新啟用排序（Qt 會依目前 header 排序指示重新排列）
        self._table.setSortingEnabled(True)

        # 套用目前搜尋關鍵字過濾並更新統計
        self._apply_filter(self._search_edit.text())

    def _apply_filter(self, text: str = "") -> None:
        """依搜尋文字即時過濾列，並僅計算可見列的統計數字。"""
        kw = text.strip().lower()
        counts: dict[str, int] = {"high": 0, "salary": 0, "normal": 0, "closed": 0}

        for row in range(self._table.rowCount()):
            ticket_item = self._table.item(row, 0)
            summary_item = self._table.item(row, 1)

            if kw:
                ticket_text = (ticket_item.text() if ticket_item else "").lower()
                summary_text = (summary_item.text() if summary_item else "").lower()
                visible = kw in ticket_text or kw in summary_text
            else:
                visible = True

            self._table.setRowHidden(row, not visible)

            if visible and ticket_item:
                category = ticket_item.data(Qt.ItemDataRole.UserRole) or "normal"
                counts[category] += 1

        self._stat_high_lbl.setText(str(counts["high"]))
        self._stat_salary_lbl.setText(str(counts["salary"]))
        open_count = counts["high"] + counts["salary"] + counts["normal"]
        self._stat_open_lbl.setText(str(open_count))
        self._stat_closed_lbl.setText(str(counts["closed"]))

    def _on_row_double_clicked(self, row: int, _col: int) -> None:
        """雙擊列 → 在預設瀏覽器開啟對應 Mantis 票單頁面。"""
        ticket_item = self._table.item(row, 0)
        if not ticket_item:
            return
        ticket_id = ticket_item.text().strip()
        url = self._creds.retrieve("mantis_url") or ""
        if not url:
            QMessageBox.information(self, "尚未設定", "請先設定 Mantis 連線網址。")
            return
        base = self._extract_base_url(url)
        QDesktopServices.openUrl(QUrl(f"{base}/view.php?id={ticket_id}"))

    # ── 同步 ──────────────────────────────────────────────────────

    def _build_client(self) -> MantisSoapClient | None:
        url = self._creds.retrieve("mantis_url") or ""
        user = self._creds.retrieve("mantis_user") or ""
        pwd = self._creds.retrieve("mantis_password") or ""
        if not url:
            QMessageBox.warning(
                self, "尚未設定",
                "請先至「系統設定」→「Mantis SOAP 連線設定」填寫連線資訊。"
            )
            return None
        # 自動修正：無論填入哪種 Mantis 網址，都萃取 base URL
        base_url = self._extract_base_url(url)
        client = MantisSoapClient(base_url, user, pwd)
        if not client.connect():
            QMessageBox.warning(self, "連線失敗", f"無法連線至 Mantis：\n{base_url}")
            return None
        return client

    def _on_sync_all(self) -> None:
        """取得所有已關聯的 ticket ID，逐一從 SOAP API 同步。"""
        if not self._conn:
            return
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "同步中", "同步正在進行中，請稍候。")
            return

        client = self._build_client()
        if client is None:
            return

        # 取得所有 case_mantis 中的 ticket_id（去重）
        mantis_repo = MantisRepository(self._conn)
        all_links = self._conn.execute(
            "SELECT DISTINCT ticket_id FROM case_mantis"
        ).fetchall()
        ticket_ids = [r[0] for r in all_links if r[0]]

        if not ticket_ids:
            self._log.append("ℹ️ 目前沒有任何已關聯的 Mantis Ticket。")
            return

        self._log.clear()
        self._log.append(f"🔄 開始同步 {len(ticket_ids)} 筆 Ticket...")
        self._sync_btn.setEnabled(False)
        self._status_label.setText("●  同步中...")
        self._status_label.setStyleSheet("color: #fbbf24; font-weight: bold;")

        self._worker = _SyncWorker(ticket_ids, client, mantis_repo)
        self._worker.log_message.connect(self._log.append)
        self._worker.finished.connect(self._on_sync_finished)
        self._worker.start()

    def _on_sync_finished(self, success: int, failed: int) -> None:
        from datetime import datetime
        now_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        self._sync_btn.setEnabled(True)
        self._status_label.setText("●  已連線")
        self._status_label.setStyleSheet("color: #4ade80; font-weight: bold;")
        self._last_sync_label.setText(f"最後同步：{now_str}")
        self._log.append(f"\n✅ 完成：{success} 筆成功，{failed} 筆失敗。")
        self.refresh()

    def _on_auto_link_cases(self) -> None:
        """掃描所有 notes 含 ISSUE# 的案件，自動建立 Mantis 關聯。"""
        if not self._conn:
            return
        import re

        from hcp_cms.data.models import CaseMantisLink
        from hcp_cms.data.repositories import CaseMantisRepository, CaseRepository, MantisRepository

        case_repo = CaseRepository(self._conn)
        mantis_repo = MantisRepository(self._conn)
        link_repo = CaseMantisRepository(self._conn)

        issue_re = re.compile(r"ISSUE#(\d+)")
        linked = skipped = stub_created = 0

        for case in case_repo.list_all():
            if not case.notes:
                continue
            m = issue_re.search(case.notes)
            if not m:
                continue
            ticket_id = m.group(1)
            # 確認尚未連結
            existing = link_repo.list_by_case_id(case.case_id)
            if any(lk.ticket_id == ticket_id for lk in existing):
                skipped += 1
                continue
            # 若票單不在本地，先建立 stub（待同步後覆蓋）
            if mantis_repo.get_by_id(ticket_id) is None:
                from hcp_cms.data.models import MantisTicket
                mantis_repo.upsert(MantisTicket(ticket_id=ticket_id, summary=f"#{ticket_id}（待同步）"))
                stub_created += 1
            link_repo.link(CaseMantisLink(case_id=case.case_id, ticket_id=ticket_id))
            linked += 1

        msg = f"完成批次連結：\n• 新建連結：{linked} 筆\n• 已存在跳過：{skipped} 筆"
        if stub_created:
            msg += f"\n• 新建暫存票單（需同步補全）：{stub_created} 筆"
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "批次自動連結", msg)
        self.refresh()

    def _on_goto_settings(self) -> None:
        QMessageBox.information(
            self, "設定位置",
            "請至左側選單「⚙ 系統設定」→ 找到「Mantis SOAP 連線設定」\n"
            "填入 Mantis 基本網址（如 https://118.163.30.33/mantis/）、帳號、密碼後儲存。"
        )

    def _apply_theme(self, p: ColorPalette) -> None:
        """套用主題色彩。"""
        self._title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p.text_primary};")
        self._url_label.setStyleSheet(f"color: {p.text_tertiary};")
