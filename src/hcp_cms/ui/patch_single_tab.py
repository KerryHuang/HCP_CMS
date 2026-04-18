"""SinglePatchTab — 單次 Patch 整理五步流程。"""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

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

_STEPS = ["① 選 .7z", "② 解壓匯入", "③ 編輯", "④ 產報表", "⑤ 完成"]
_CLR_DONE    = "color: #22c55e; font-weight: bold;"
_CLR_CURRENT = "color: #3b82f6; font-weight: bold;"
_CLR_PENDING = "color: #64748b;"


class SinglePatchTab(QWidget):
    _load_done     = Signal(object)
    _generate_done = Signal(object)

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._patch_id: int | None = None
        self._version_tag: str = ""
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

        # .7z 選擇列
        archive_row = QHBoxLayout()
        archive_row.addWidget(QLabel(".7z 封存檔："))
        self._archive_edit = QLineEdit()
        self._archive_edit.setPlaceholderText("選擇 .7z 封存檔…")
        self._archive_edit.setReadOnly(True)
        self._archive_btn = QPushButton("瀏覽…")
        archive_row.addWidget(self._archive_edit)
        archive_row.addWidget(self._archive_btn)
        layout.addLayout(archive_row)

        # 輸出目錄列
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("輸出目錄："))
        self._output_dir_edit = QLineEdit()
        self._output_dir_edit.setPlaceholderText("選擇輸出目錄…")
        self._output_dir_edit.setReadOnly(True)
        self._output_dir_btn = QPushButton("瀏覽…")
        output_row.addWidget(self._output_dir_edit)
        output_row.addWidget(self._output_dir_btn)
        layout.addLayout(output_row)

        # 版本標籤列
        tag_row = QHBoxLayout()
        tag_row.addWidget(QLabel("版本標籤："))
        self._version_tag_edit = QLineEdit()
        self._version_tag_edit.setPlaceholderText("如：IP_合併_20261101")
        tag_row.addWidget(self._version_tag_edit)
        tag_row.addStretch()
        layout.addLayout(tag_row)

        # 解壓匯入按鈕
        action_row = QHBoxLayout()
        self._load_btn = QPushButton("📥 解壓匯入")
        action_row.addWidget(self._load_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        # Issue 表格
        self._issue_table = IssueTableWidget(conn=self._conn)
        layout.addWidget(self._issue_table, stretch=2)

        # 產報表按鈕群
        gen_row = QHBoxLayout()
        self._issue_list_btn     = QPushButton("📊 Issue清單整理")
        self._release_notice_btn = QPushButton("📄 發行通知")
        self._issue_split_btn    = QPushButton("📋 Issue清單(IT/HR)")
        self._test_scripts_btn   = QPushButton("📝 測試腳本")
        for btn in [self._issue_list_btn, self._release_notice_btn,
                    self._issue_split_btn, self._test_scripts_btn]:
            btn.setEnabled(False)
            gen_row.addWidget(btn)
        gen_row.addStretch()
        layout.addLayout(gen_row)

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
        self._archive_btn.clicked.connect(self._on_archive_browse_clicked)
        self._output_dir_btn.clicked.connect(self._on_output_dir_browse_clicked)
        self._version_tag_edit.textChanged.connect(self._on_version_tag_changed)
        self._load_btn.clicked.connect(self._on_load_clicked)
        self._issue_list_btn.clicked.connect(self._on_issue_list_clicked)
        self._release_notice_btn.clicked.connect(self._on_release_notice_clicked)
        self._issue_split_btn.clicked.connect(self._on_issue_split_clicked)
        self._test_scripts_btn.clicked.connect(self._on_test_scripts_clicked)
        self._load_done.connect(self._on_load_result)
        self._generate_done.connect(self._on_generate_result)

        self._set_step(0)

    # ── 步驟高亮 ──────────────────────────────────────────────────────────

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

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_archive_browse_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇 .7z 封存檔", "", "7z Archives (*.7z)"
        )
        if not path:
            return
        self._archive_edit.setText(path)
        m = re.search(r"IP_合併_\d{8}", Path(path).name)
        tag = m.group(0) if m else Path(path).stem
        self._version_tag_edit.setText(tag[:20] if len(tag) > 20 else tag)
        self._set_step(1)

    def _on_output_dir_browse_clicked(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "選擇輸出目錄")
        if path:
            self._output_dir_edit.setText(path)

    def _on_version_tag_changed(self, text: str) -> None:
        self._version_tag = text.strip()

    def _on_load_clicked(self) -> None:
        archive = self._archive_edit.text()
        output_dir = self._output_dir_edit.text()
        if not archive or not output_dir or not self._conn:
            return
        self._load_btn.setEnabled(False)
        self._append_log("📥 解壓匯入中…")
        conn = self._conn

        def work() -> dict:
            from hcp_cms.core.patch_engine import SinglePatchEngine
            engine = SinglePatchEngine(conn)
            try:
                patch_id, version_tag, issue_count = engine.load_from_archive(
                    archive, output_dir
                )
                return {"patch_id": patch_id, "version_tag": version_tag,
                        "issue_count": issue_count, "error": None}
            except Exception as e:
                return {"patch_id": None, "version_tag": "",
                        "issue_count": 0, "error": str(e)}

        threading.Thread(
            target=lambda: self._load_done.emit(work()), daemon=True
        ).start()

    def _on_load_result(self, result: dict) -> None:
        self._load_btn.setEnabled(True)
        if result.get("error"):
            self._append_log(f"❌ 匯入失敗：{result['error']}")
            return
        self._patch_id = result["patch_id"]
        if not self._version_tag and result.get("version_tag"):
            self._version_tag = result["version_tag"]
            self._version_tag_edit.setText(self._version_tag)
        self._append_log(f"✅ 匯入完成：{result['issue_count']} 筆 Issue")
        if self._patch_id is not None:
            self._issue_table.load_issues(self._patch_id)
        for btn in [self._issue_list_btn, self._release_notice_btn,
                    self._issue_split_btn, self._test_scripts_btn]:
            btn.setEnabled(True)
        self._set_step(2)

    def _on_issue_list_clicked(self) -> None:
        self._start_generate("issue_list")

    def _on_release_notice_clicked(self) -> None:
        self._start_generate("release_notice")

    def _on_issue_split_clicked(self) -> None:
        self._start_generate("issue_split")

    def _on_test_scripts_clicked(self) -> None:
        self._start_generate("test_scripts")

    def _start_generate(self, gen_type: str) -> None:
        if self._patch_id is None or not self._conn:
            return
        output_dir = self._output_dir_edit.text() or "."
        patch_id = self._patch_id
        version_tag = self._version_tag
        conn = self._conn
        self._set_step(3)
        self._append_log(f"⏳ 產出中（{gen_type}）…")

        def work() -> dict:
            from hcp_cms.core.patch_engine import SinglePatchEngine
            engine = SinglePatchEngine(conn)
            try:
                if gen_type == "issue_list":
                    paths = [engine.generate_issue_list(patch_id, output_dir,
                                                        version_tag)]
                elif gen_type == "release_notice":
                    paths = [engine.generate_release_notice(patch_id, output_dir,
                                                            version_tag)]
                elif gen_type == "issue_split":
                    paths = [engine.generate_issue_split(patch_id, output_dir,
                                                         version_tag)]
                else:
                    paths = engine.generate_test_scripts(patch_id, output_dir,
                                                         version_tag)
                return {"type": gen_type, "paths": paths, "error": None}
            except Exception as e:
                return {"type": gen_type, "paths": [], "error": str(e)}

        threading.Thread(
            target=lambda: self._generate_done.emit(work()), daemon=True
        ).start()

    def _on_generate_result(self, result: dict) -> None:
        if result.get("error"):
            self._append_log(f"❌ 產出失敗：{result['error']}")
            return
        for path in result.get("paths", []):
            self._output_list.addItem(QListWidgetItem(path))
            self._append_log(f"✅ {path}")
        self._set_step(4)
