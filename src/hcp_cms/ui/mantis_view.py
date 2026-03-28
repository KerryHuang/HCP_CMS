"""Mantis sync view."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.data.repositories import MantisRepository
from hcp_cms.services.credential import CredentialManager
from hcp_cms.services.mantis.soap import MantisSoapClient


class _SyncWorker(QThread):
    """背景執行 Mantis SOAP 同步的 Worker。"""

    log_message = Signal(str)
    ticket_synced = Signal(str, str, str, str, str)  # ticket_id, summary, status, priority, handler
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
            )
            self._mantis_repo.upsert(ticket)
            self.log_message.emit(f"  ✅ #{tid} {issue.summary[:30]} [{issue.status}]")
            self.ticket_synced.emit(tid, issue.summary, issue.status, issue.priority, issue.handler)
            success += 1
        self.finished.emit(success, failed)


class MantisView(QWidget):
    """Mantis 同步頁面 — 顯示所有已關聯的 Ticket 並可批次同步。"""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._creds = CredentialManager()
        self._worker: _SyncWorker | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("🔧 Mantis 同步")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f1f5f9;")
        layout.addWidget(title)

        # ── 連線資訊（唯讀，設定請至系統設定）──────────────────────
        conn_group = QGroupBox("連線狀態")
        conn_layout = QHBoxLayout(conn_group)

        self._url_label = QLabel("尚未設定")
        self._url_label.setStyleSheet("color: #94a3b8;")
        conn_layout.addWidget(QLabel("Mantis URL："))
        conn_layout.addWidget(self._url_label, stretch=1)

        self._status_label = QLabel("●  未連線")
        self._status_label.setStyleSheet("color: #f87171; font-weight: bold;")
        conn_layout.addWidget(self._status_label)

        self._sync_btn = QPushButton("🔄 立即同步全部")
        self._sync_btn.setMinimumWidth(130)
        self._sync_btn.clicked.connect(self._on_sync_all)
        conn_layout.addWidget(self._sync_btn)

        hint_btn = QPushButton("⚙ 設定帳密")
        hint_btn.setToolTip("請至「系統設定」→「Mantis SOAP 連線設定」填寫帳號密碼")
        hint_btn.clicked.connect(self._on_goto_settings)
        conn_layout.addWidget(hint_btn)

        layout.addWidget(conn_group)

        # ── Ticket 清單 ───────────────────────────────────────────
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["票號", "摘要", "狀態", "優先", "負責人", "最後同步"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(0, 80)
        self._table.setColumnWidth(1, 300)
        self._table.setColumnWidth(2, 90)
        self._table.setColumnWidth(3, 60)
        self._table.setColumnWidth(4, 100)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
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

    def refresh(self) -> None:
        """從本地 DB 載入已同步過的 Ticket 到清單。"""
        if not self._conn:
            return
        repo = MantisRepository(self._conn)
        tickets = repo.list_all()
        self._table.setRowCount(len(tickets))
        for i, t in enumerate(tickets):
            self._table.setItem(i, 0, QTableWidgetItem(t.ticket_id))
            self._table.setItem(i, 1, QTableWidgetItem(t.summary or ""))
            self._table.setItem(i, 2, QTableWidgetItem(t.status or ""))
            self._table.setItem(i, 3, QTableWidgetItem(t.priority or ""))
            self._table.setItem(i, 4, QTableWidgetItem(t.handler or ""))
            self._table.setItem(i, 5, QTableWidgetItem(t.synced_at or "（從未同步）"))

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
        self._sync_btn.setEnabled(True)
        self._status_label.setText("●  已連線")
        self._status_label.setStyleSheet("color: #4ade80; font-weight: bold;")
        self._log.append(f"\n✅ 完成：{success} 筆成功，{failed} 筆失敗。")
        self.refresh()

    def _on_goto_settings(self) -> None:
        QMessageBox.information(
            self, "設定位置",
            "請至左側選單「⚙ 系統設定」→ 找到「Mantis SOAP 連線設定」\n"
            "填入 Mantis 基本網址（如 https://118.163.30.33/mantis/）、帳號、密碼後儲存。"
        )
