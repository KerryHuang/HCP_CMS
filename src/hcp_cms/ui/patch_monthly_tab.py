"""MonthlyPatchTab — 每月大 PATCH 七步流程。"""

from __future__ import annotations

import sqlite3
import threading
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.ui.widgets.issue_table_widget import IssueTableWidget

_STEPS = ["① 選月份", "② 選來源", "③ 匯入", "④ 編輯", "⑤ Excel", "⑥ 通知信", "⑦ 完成"]
_CLR_DONE    = "color: #22c55e; font-weight: bold;"
_CLR_CURRENT = "color: #3b82f6; font-weight: bold;"
_CLR_PENDING = "color: #64748b;"
_MONTHS = [f"{m:02d}月" for m in range(1, 13)]
_SOURCE_FILE   = "上傳 .txt / .json"
_SOURCE_MANTIS = "Mantis 瀏覽器"


class MonthlyPatchTab(QWidget):
    _import_done   = Signal(object)
    _generate_done = Signal(object)

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._patch_id: int | None = None
        self._file_path: str | None = None
        self._output_dir: str | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        today = date.today()
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

        # 月份選擇列
        month_row = QHBoxLayout()
        month_row.addWidget(QLabel("月份："))
        self._year_spin = QSpinBox()
        self._year_spin.setRange(2000, 2100)
        self._year_spin.setValue(today.year)
        self._year_spin.setFixedWidth(80)
        month_row.addWidget(self._year_spin)
        self._month_combo = QComboBox()
        self._month_combo.addItems(_MONTHS)
        self._month_combo.setCurrentIndex(today.month - 1)
        self._month_combo.setFixedWidth(80)
        month_row.addWidget(self._month_combo)
        month_row.addStretch()
        layout.addLayout(month_row)

        # 來源選擇列
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Issue 來源："))
        self._source_combo = QComboBox()
        self._source_combo.addItems([_SOURCE_FILE, _SOURCE_MANTIS])
        src_row.addWidget(self._source_combo)
        self._file_edit = QLineEdit()
        self._file_edit.setPlaceholderText("選擇 .txt 或 .json 檔案…")
        self._file_edit.setReadOnly(True)
        self._file_btn = QPushButton("瀏覽…")
        src_row.addWidget(self._file_edit)
        src_row.addWidget(self._file_btn)
        layout.addLayout(src_row)

        # 輸出目錄列
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("輸出目錄："))
        self._out_edit = QLineEdit()
        self._out_edit.setPlaceholderText("預設：_temp/monthly_{月份}/")
        self._out_edit.setReadOnly(True)
        self._out_btn = QPushButton("瀏覽…")
        out_row.addWidget(self._out_edit)
        out_row.addWidget(self._out_btn)
        layout.addLayout(out_row)

        # 操作按鈕列
        action_row = QHBoxLayout()
        self._import_btn         = QPushButton("📥 匯入 Issue")
        self._generate_excel_btn = QPushButton("📊 產生 Excel")
        self._generate_html_btn  = QPushButton("✉️ 產生通知信")
        self._regenerate_btn     = QPushButton("🔄 重新產出")
        for btn in [self._import_btn, self._generate_excel_btn,
                    self._generate_html_btn, self._regenerate_btn]:
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
        self._source_combo.currentIndexChanged.connect(self._on_issue_source_changed)
        self._file_btn.clicked.connect(self._on_file_browse_clicked)
        self._out_btn.clicked.connect(self._on_out_browse_clicked)
        self._import_btn.clicked.connect(self._on_import_clicked)
        self._generate_excel_btn.clicked.connect(self._on_generate_excel_clicked)
        self._generate_html_btn.clicked.connect(self._on_generate_html_clicked)
        self._regenerate_btn.clicked.connect(self._on_regenerate_clicked)
        self._import_done.connect(self._on_import_result)
        self._generate_done.connect(self._on_generate_result)

        self._on_issue_source_changed(0)
        self._set_step(0)

    # ── 輔助 ───────────────────────────────────────────────────────────────

    def _get_month_str(self) -> str:
        year  = self._year_spin.value()
        month = self._month_combo.currentIndex() + 1
        return f"{year}{month:02d}"

    def _get_output_dir(self) -> str:
        if self._output_dir:
            return self._output_dir
        return f"_temp/monthly_{self._get_month_str()}"

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

    def _on_issue_source_changed(self, index: int) -> None:
        is_file = self._source_combo.currentText() == _SOURCE_FILE
        self._file_edit.setVisible(is_file)
        self._file_btn.setVisible(is_file)

    def _on_file_browse_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇 Issue 清單", "",
            "資料檔 (*.txt *.json);;全部檔案 (*.*)",
        )
        if path:
            self._file_path = path
            self._file_edit.setText(path)
            self._set_step(1)

    def _on_out_browse_clicked(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "選擇輸出目錄")
        if path:
            self._output_dir = path
            self._out_edit.setText(path)

    def _on_import_clicked(self) -> None:
        if not self._conn:
            return
        source_text = self._source_combo.currentText()
        if source_text == _SOURCE_FILE and not self._file_path:
            self._append_log("⚠️ 請先選擇檔案")
            return
        month_str = self._get_month_str()
        conn      = self._conn
        file_path = self._file_path

        self._import_btn.setEnabled(False)
        self._append_log(f"📥 匯入 {month_str} Issue 清單…")

        def work() -> dict:
            from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
            engine = MonthlyPatchEngine(conn)
            pid = engine.load_issues("manual", month_str, file_path)
            count = engine.get_issue_count(pid)
            return {"patch_id": pid, "count": count}

        threading.Thread(
            target=lambda: self._import_done.emit(work()), daemon=True
        ).start()

    def _on_import_result(self, result: dict) -> None:
        self._import_btn.setEnabled(True)
        self._patch_id = result["patch_id"]
        self._append_log(f"✅ 匯入完成：{result['count']} 筆 Issue")
        self._issue_table.load_issues(self._patch_id)
        self._set_step(3)

    def _on_generate_excel_clicked(self) -> None:
        if self._patch_id is None or not self._conn:
            return
        self._generate_excel_btn.setEnabled(False)
        self._append_log("📊 產生 PATCH_LIST Excel…")
        conn       = self._conn
        patch_id   = self._patch_id
        month_str  = self._get_month_str()
        output_dir = self._get_output_dir()

        def work() -> dict:
            from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
            engine = MonthlyPatchEngine(conn)
            try:
                paths = engine.generate_patch_list(patch_id, output_dir, month_str)
                return {"paths": paths, "type": "excel", "error": None}
            except Exception as e:
                return {"paths": [], "type": "excel", "error": str(e)}

        threading.Thread(
            target=lambda: self._generate_done.emit(work()), daemon=True
        ).start()

    def _on_generate_html_clicked(self) -> None:
        if self._patch_id is None or not self._conn:
            return
        self._generate_html_btn.setEnabled(False)
        self._append_log("✉️ 產生客戶通知信（呼叫 Claude API）…")
        conn       = self._conn
        patch_id   = self._patch_id
        month_str  = self._get_month_str()
        output_dir = self._get_output_dir()

        def work() -> dict:
            from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
            from hcp_cms.services.claude_content import ClaudeContentService
            engine = MonthlyPatchEngine(conn)
            issues = engine.get_issues(patch_id)
            svc    = ClaudeContentService()
            notify_body = svc.generate_notify_body(
                [{"issue_no": i.issue_no, "description": i.description}
                 for i in issues],
                month_str,
            )
            try:
                path = engine.generate_notify_html(
                    patch_id, output_dir, month_str, notify_body=notify_body
                )
                return {"paths": [path], "type": "html", "error": None}
            except Exception as e:
                return {"paths": [], "type": "html", "error": str(e)}

        threading.Thread(
            target=lambda: self._generate_done.emit(work()), daemon=True
        ).start()

    def _on_generate_result(self, result: dict) -> None:
        btn = (self._generate_excel_btn
               if result.get("type") == "excel"
               else self._generate_html_btn)
        btn.setEnabled(True)
        if result.get("error"):
            self._append_log(f"❌ 產出失敗：{result['error']}")
            return
        for path in result.get("paths", []):
            self._output_list.addItem(QListWidgetItem(path))
            self._append_log(f"✅ {path}")
        step = 5 if result.get("type") == "excel" else 6
        self._set_step(step)

    def _on_regenerate_clicked(self) -> None:
        self._output_list.clear()
        self._on_generate_excel_clicked()
