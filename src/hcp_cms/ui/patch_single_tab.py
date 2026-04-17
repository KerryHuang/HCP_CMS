"""SinglePatchTab — 單次 Patch 整理六步流程。"""

from __future__ import annotations

import sqlite3
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.ui.widgets.issue_table_widget import IssueTableWidget

_STEPS = ["① 選擇資料夾", "② 掃描", "③ Mantis", "④ 編輯", "⑤ 產報表", "⑥ 完成"]
_CLR_DONE    = "color: #22c55e; font-weight: bold;"
_CLR_CURRENT = "color: #3b82f6; font-weight: bold;"
_CLR_PENDING = "color: #64748b;"


class SinglePatchTab(QWidget):
    _scan_done     = Signal(object)
    _mantis_done   = Signal(object)
    _generate_done = Signal(object)

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._patch_id: int | None = None
        self._patch_dir: str | None = None
        self._mantis_service = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 步驟進度列
        self._step_labels: list[QLabel] = []
        step_bar = QHBoxLayout()
        for i, title in enumerate(_STEPS):
            lbl = QLabel(title)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._step_labels.append(lbl)
            step_bar.addWidget(lbl)
            if i < len(_STEPS) - 1:
                arrow = QLabel("→")
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                step_bar.addWidget(arrow)
        layout.addLayout(step_bar)

        # 資料夾選擇
        folder_row = QHBoxLayout()
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("選擇解壓縮後的 Patch 資料夾…")
        self._folder_edit.setReadOnly(True)
        self._browse_btn = QPushButton("瀏覽…")
        folder_row.addWidget(self._folder_edit)
        folder_row.addWidget(self._browse_btn)
        layout.addLayout(folder_row)

        # 操作按鈕列
        action_row = QHBoxLayout()
        self._start_btn          = QPushButton("▶ 開始掃描")
        self._mantis_login_btn   = QPushButton("🌐 開啟 Mantis")
        self._mantis_confirm_btn = QPushButton("✅ 已登入，繼續")
        self._skip_mantis_btn    = QPushButton("⏭ 跳過 Mantis")
        self._generate_btn       = QPushButton("📊 產生報表")
        self._regenerate_btn     = QPushButton("🔄 重新產出")
        self._mantis_confirm_btn.setVisible(False)
        self._skip_mantis_btn.setVisible(False)
        for btn in [self._start_btn, self._mantis_login_btn,
                    self._mantis_confirm_btn, self._skip_mantis_btn,
                    self._generate_btn, self._regenerate_btn]:
            action_row.addWidget(btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        # Issue 表格
        self._issue_table = IssueTableWidget(conn=self._conn)
        layout.addWidget(self._issue_table, stretch=2)

        # 執行 Log
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(150)
        layout.addWidget(self._log)

        # 產出清單
        self._output_list = QListWidget()
        self._output_list.setMaximumHeight(100)
        layout.addWidget(self._output_list)

        # Signal / Slot 連線
        self._browse_btn.clicked.connect(self._on_browse_clicked)
        self._start_btn.clicked.connect(self._on_start_clicked)
        self._mantis_login_btn.clicked.connect(self._on_mantis_login_clicked)
        self._mantis_confirm_btn.clicked.connect(self._on_mantis_login_confirmed)
        self._skip_mantis_btn.clicked.connect(self._on_skip_mantis_clicked)
        self._generate_btn.clicked.connect(self._on_generate_excel_clicked)
        self._regenerate_btn.clicked.connect(self._on_regenerate_clicked)
        self._scan_done.connect(self._on_scan_result)
        self._mantis_done.connect(self._on_mantis_result)
        self._generate_done.connect(self._on_generate_result)

        self._set_step(0)

    # ── 步驟高亮 ───────────────────────────────────────────────────────────

    def _set_step(self, step: int) -> None:
        for i, lbl in enumerate(self._step_labels):
            if i < step:
                lbl.setStyleSheet(_CLR_DONE)
            elif i == step:
                lbl.setStyleSheet(_CLR_CURRENT)
            else:
                lbl.setStyleSheet(_CLR_PENDING)

    def _append_log(self, msg: str) -> None:
        self._log.append(msg)

    # ── Slots ──────────────────────────────────────────────────────────────

    def _on_browse_clicked(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "選擇 Patch 資料夾")
        if path:
            self._folder_edit.setText(path)
            self._patch_dir = path
            self._set_step(1)

    def _on_start_clicked(self) -> None:
        if not self._patch_dir or not self._conn:
            return
        self._start_btn.setEnabled(False)
        self._append_log("🔍 開始掃描資料夾…")
        conn = self._conn
        patch_dir = self._patch_dir

        def work() -> dict:
            from hcp_cms.core.patch_engine import SinglePatchEngine
            engine = SinglePatchEngine(conn)
            patch_id = engine.setup_new_patch(patch_dir)
            scan = engine.scan_patch_dir(patch_dir)
            issue_count = 0
            if scan.get("release_note"):
                issue_count = engine.load_issues_from_release_doc(
                    patch_id, scan["release_note"]
                )
            return {"patch_id": patch_id, "scan": scan, "issue_count": issue_count}

        threading.Thread(
            target=lambda: self._scan_done.emit(work()), daemon=True
        ).start()

    def _on_scan_result(self, result: dict) -> None:
        self._patch_id = result["patch_id"]
        scan = result["scan"]
        self._append_log(
            f"✅ 掃描完成：{len(scan.get('form_files', []))} 個 FORM、"
            f"{len(scan.get('sql_files', []))} 個 SQL"
        )
        if scan.get("missing"):
            self._append_log(f"⚠️ 缺少目錄：{', '.join(scan['missing'])}")
        self._append_log(f"📋 讀取 {result['issue_count']} 筆 Issue")
        self._issue_table.load_issues(self._patch_id)
        self._start_btn.setEnabled(True)
        self._set_step(2)

    def _on_mantis_result(self, result: dict) -> None:
        self._mantis_confirm_btn.setEnabled(True)
        self._append_log(f"✅ Mantis 同步完成：{result.get('fetched', 0)} 筆")
        if self._patch_id is not None:
            self._issue_table.load_issues(self._patch_id)
        self._set_step(3)

    def _on_mantis_login_clicked(self) -> None:
        self._mantis_confirm_btn.setVisible(True)
        self._skip_mantis_btn.setVisible(True)
        self._mantis_login_btn.setEnabled(False)
        self._append_log("🌐 開啟 Mantis 瀏覽器，請登入後點「已登入，繼續」…")

        def open_browser() -> None:
            from hcp_cms.services.credential import CredentialManager
            from hcp_cms.services.mantis.playwright_service import (
                PlaywrightMantisService,
            )
            mantis_url = CredentialManager().retrieve("mantis_url") or ""
            svc = PlaywrightMantisService(mantis_url)
            self._mantis_service = svc
            svc.open_browser()

        threading.Thread(target=open_browser, daemon=True).start()

    def _on_mantis_login_confirmed(self) -> None:
        if self._mantis_service is None or self._patch_id is None:
            return
        self._mantis_confirm_btn.setEnabled(False)
        self._append_log("⏳ 讀取 Mantis Issue 資料…")
        svc = self._mantis_service
        conn = self._conn
        patch_id = self._patch_id

        def fetch() -> dict:
            from hcp_cms.core.patch_engine import SinglePatchEngine
            engine = SinglePatchEngine(conn)
            svc.confirm_login()
            issue_nos = engine.get_issue_nos_by_patch(patch_id)
            results = svc.fetch_issues_batch(issue_nos)
            svc.close()
            return {"fetched": len(results)}

        threading.Thread(
            target=lambda: self._mantis_done.emit(fetch()), daemon=True
        ).start()

    def _on_skip_mantis_clicked(self) -> None:
        if self._mantis_service:
            self._mantis_service.close()
            self._mantis_service = None
        self._mantis_confirm_btn.setVisible(False)
        self._skip_mantis_btn.setVisible(False)
        self._mantis_login_btn.setEnabled(True)
        self._append_log("⏭ 已跳過 Mantis 同步")
        self._set_step(3)

    def _on_generate_excel_clicked(self) -> None:
        if self._patch_id is None or not self._conn:
            return
        self._generate_btn.setEnabled(False)
        self._append_log("📊 產生 Excel 報表中…")
        conn = self._conn
        patch_id = self._patch_id
        patch_dir = self._patch_dir or "."

        def work() -> dict:
            from hcp_cms.core.patch_engine import SinglePatchEngine
            engine = SinglePatchEngine(conn)
            try:
                paths = engine.generate_excel_reports(patch_id, patch_dir)
                return {"paths": paths, "error": None}
            except Exception as e:
                return {"paths": [], "error": str(e)}

        threading.Thread(
            target=lambda: self._generate_done.emit(work()), daemon=True
        ).start()

    def _on_generate_result(self, result: dict) -> None:
        self._generate_btn.setEnabled(True)
        if result.get("error"):
            self._append_log(f"❌ 產出失敗：{result['error']}")
            return
        self._output_list.clear()
        for path in result.get("paths", []):
            self._output_list.addItem(QListWidgetItem(path))
            self._append_log(f"✅ {path}")
        self._set_step(5)

    def _on_regenerate_clicked(self) -> None:
        self._output_list.clear()
        self._on_generate_excel_clicked()

