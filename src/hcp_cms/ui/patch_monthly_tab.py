"""MonthlyPatchTab — 每月大 PATCH 九步流程。"""

from __future__ import annotations

import sqlite3
import threading
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
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

_STEPS = ["① 選月份", "② 選來源", "③ 匯入", "④ 編輯", "⑤ S2T",
          "⑥ Excel", "⑦ 驗證", "⑧ 通知信", "⑨ 完成"]
_CLR_DONE = "color: #22c55e; font-weight: bold;"
_CLR_CURRENT = "color: #3b82f6; font-weight: bold;"
_CLR_PENDING = "color: #64748b;"
_MONTHS = [f"{m:02d}月" for m in range(1, 13)]
_SOURCE_FILE = "上傳 .txt / .json"
_SOURCE_MANTIS = "Mantis 瀏覽器"
_SOURCE_FOLDER = "掃描資料夾"


class MonthlyPatchTab(QWidget):
    _import_done = Signal(object)
    _generate_done = Signal(object)
    _s2t_done = Signal(object)
    _verify_done = Signal(object)
    _supplement_done = Signal(int)

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._patch_id: int | None = None
        self._file_path: str | None = None
        self._output_dir: str | None = None
        self._scan_dir: str | None = None
        self._scan_patch_ids: dict[str, int] | None = None
        self._banner_image_bytes: bytes | None = None
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
        self._banner_label = QLabel("底圖：無")
        self._banner_label.setStyleSheet("color: #64748b; font-size: 11px;")
        self._banner_btn = QPushButton("🖼 上傳橫幅底圖")
        self._banner_btn.setFixedWidth(120)
        month_row.addWidget(self._banner_label)
        month_row.addWidget(self._banner_btn)
        month_row.addStretch()
        layout.addLayout(month_row)

        # 來源選擇列
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Issue 來源："))
        self._source_combo = QComboBox()
        self._source_combo.addItems([_SOURCE_FILE, _SOURCE_MANTIS, _SOURCE_FOLDER])
        src_row.addWidget(self._source_combo)
        self._file_edit = QLineEdit()
        self._file_edit.setPlaceholderText("選擇 .txt 或 .json 檔案…")
        self._file_edit.setReadOnly(True)
        self._file_btn = QPushButton("瀏覽…")
        src_row.addWidget(self._file_edit)
        src_row.addWidget(self._file_btn)
        layout.addLayout(src_row)

        # 掃描資料夾路徑列
        scan_row = QHBoxLayout()
        scan_row.addWidget(QLabel("Patch 資料夾："))
        self._scan_edit = QLineEdit()
        self._scan_edit.setPlaceholderText("選擇月份 Patch 頂層資料夾（含 11G/12C 子目錄）…")
        self._scan_edit.setReadOnly(True)
        self._scan_btn = QPushButton("瀏覽…")
        scan_row.addWidget(self._scan_edit)
        scan_row.addWidget(self._scan_btn)
        layout.addLayout(scan_row)

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
        self._import_btn = QPushButton("📥 匯入 Issue")
        self._s2t_btn = QPushButton("🔤 S2T 轉換")
        self._generate_excel_btn = QPushButton("📊 產生 Excel")
        self._verify_btn = QPushButton("🔗 驗證超連結")
        self._generate_html_btn = QPushButton("✉️ 產生通知信")
        self._regenerate_btn = QPushButton("🔄 重新產出")
        for btn in [self._import_btn, self._s2t_btn, self._generate_excel_btn,
                    self._verify_btn, self._generate_html_btn, self._regenerate_btn]:
            action_row.addWidget(btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        # 排班提醒區塊
        reminder_group = QGroupBox("📅 排班提醒（選填，留空則不顯示於通知信）")
        reminder_inner = QVBoxLayout()
        self._reminder_list = QListWidget()
        self._reminder_list.setMaximumHeight(80)
        self._reminder_list.setToolTip("每條提醒可獨立刪除，切換月份自動清空")
        reminder_btn_row = QHBoxLayout()
        self._reminder_add_btn = QPushButton("＋ 新增")
        self._reminder_add_btn.setFixedWidth(70)
        self._reminder_del_btn = QPushButton("✕ 刪除選取")
        self._reminder_del_btn.setFixedWidth(90)
        reminder_btn_row.addWidget(self._reminder_add_btn)
        reminder_btn_row.addWidget(self._reminder_del_btn)
        reminder_btn_row.addStretch()
        reminder_inner.addWidget(self._reminder_list)
        reminder_inner.addLayout(reminder_btn_row)
        reminder_group.setLayout(reminder_inner)
        layout.addWidget(reminder_group)

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
        self._scan_btn.clicked.connect(self._on_scan_browse_clicked)
        self._out_btn.clicked.connect(self._on_out_browse_clicked)
        self._import_btn.clicked.connect(self._on_import_clicked)
        self._generate_excel_btn.clicked.connect(self._on_generate_excel_clicked)
        self._generate_html_btn.clicked.connect(self._on_generate_html_clicked)
        self._regenerate_btn.clicked.connect(self._on_regenerate_clicked)
        self._import_done.connect(self._on_import_result)
        self._generate_done.connect(self._on_generate_result)
        self._banner_btn.clicked.connect(self._on_banner_upload_clicked)
        self._s2t_btn.clicked.connect(self._on_s2t_clicked)
        self._verify_btn.clicked.connect(self._on_verify_clicked)
        self._reminder_add_btn.clicked.connect(self._on_reminder_add_clicked)
        self._reminder_del_btn.clicked.connect(self._on_reminder_del_clicked)
        self._month_combo.currentIndexChanged.connect(self._on_month_changed)
        self._year_spin.valueChanged.connect(self._on_month_changed)
        self._s2t_done.connect(self._on_s2t_result)
        self._verify_done.connect(self._on_verify_result)
        self._supplement_done.connect(self._on_supplement_result)

        self._on_issue_source_changed(0)
        self._set_step(0)

    # ── 輔助 ───────────────────────────────────────────────────────────────

    def _get_month_str(self) -> str:
        year = self._year_spin.value()
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
        current = self._source_combo.currentText()
        is_file = current == _SOURCE_FILE
        is_folder = current == _SOURCE_FOLDER
        self._file_edit.setVisible(is_file)
        self._file_btn.setVisible(is_file)
        self._scan_edit.setVisible(is_folder)
        self._scan_btn.setVisible(is_folder)

    def _on_scan_browse_clicked(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "選擇月份 Patch 資料夾")
        if path:
            self._scan_dir = path
            self._scan_edit.setText(path)
            self._set_step(1)

    def _on_file_browse_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "選擇 Issue 清單",
            "",
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
        if source_text == _SOURCE_FOLDER and not self._scan_dir:
            self._append_log("⚠️ 請先選擇資料夾")
            return
        month_str = self._get_month_str()
        conn = self._conn
        file_path = self._file_path
        scan_dir = self._scan_dir

        self._import_btn.setEnabled(False)
        self._append_log(f"📥 匯入 {month_str} Issue 清單…")

        if source_text == _SOURCE_FOLDER:

            def work() -> dict:
                from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine

                engine = MonthlyPatchEngine(conn)
                try:
                    patch_ids = engine.scan_monthly_dir(scan_dir, month_str)
                    counts = {v: engine.get_issue_count(pid) for v, pid in patch_ids.items()}
                    return {"patch_ids": patch_ids, "counts": counts, "error": None}
                except Exception as e:
                    return {"patch_ids": {}, "counts": {}, "error": str(e)}

            threading.Thread(target=lambda: self._import_done.emit(work()), daemon=True).start()
        else:

            def work() -> dict:  # type: ignore[no-redef]
                from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine

                engine = MonthlyPatchEngine(conn)
                try:
                    pid = engine.load_issues("manual", month_str, file_path)
                    count = engine.get_issue_count(pid)
                    return {"patch_id": pid, "count": count, "error": None}
                except Exception as e:
                    return {"patch_id": None, "count": 0, "error": str(e)}

            threading.Thread(target=lambda: self._import_done.emit(work()), daemon=True).start()

    def _on_import_result(self, result: dict) -> None:
        self._import_btn.setEnabled(True)
        if result.get("error"):
            self._append_log(f"❌ 匯入失敗：{result['error']}")
            return
        if "patch_ids" in result:
            self._scan_patch_ids = result["patch_ids"]
            counts = result.get("counts", {})
            for ver, cnt in counts.items():
                self._append_log(f"✅ {ver}：{cnt} 筆 Issue")
            first_id = next(iter(result["patch_ids"].values()), None)
            if first_id is not None:
                self._patch_id = first_id
                self._issue_table.load_issues(first_id)
        else:
            self._patch_id = result["patch_id"]
            self._append_log(f"✅ 匯入完成：{result['count']} 筆 Issue")
            self._issue_table.load_issues(self._patch_id)
        self._set_step(3)
        # 自動觸發 S2T（若有 scan_dir）
        if self._scan_dir:
            self._on_s2t_clicked()

    def _on_generate_excel_clicked(self) -> None:
        if not self._scan_patch_ids and self._patch_id is None:
            return
        if not self._conn:
            return
        self._generate_excel_btn.setEnabled(False)
        self._append_log("📊 產生 PATCH_LIST Excel…")
        conn = self._conn
        patch_id = self._patch_id
        month_str = self._get_month_str()
        output_dir = self._get_output_dir()
        scan_patch_ids = self._scan_patch_ids
        scan_dir = self._scan_dir

        def work() -> dict:
            from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine

            engine = MonthlyPatchEngine(conn)
            try:
                if scan_patch_ids:
                    paths = engine.generate_patch_list_from_dir(scan_patch_ids, scan_dir, month_str)
                else:
                    paths = engine.generate_patch_list(patch_id, output_dir, month_str)
                return {"paths": paths, "type": "excel", "error": None}
            except Exception as e:
                return {"paths": [], "type": "excel", "error": str(e)}

        threading.Thread(target=lambda: self._generate_done.emit(work()), daemon=True).start()

    def _on_generate_html_clicked(self) -> None:
        if not self._conn:
            return
        if not self._scan_patch_ids and self._patch_id is None:
            return
        self._generate_html_btn.setEnabled(False)
        self._append_log("✉️ 產生客戶通知信（呼叫 Claude API）…")
        conn = self._conn
        patch_id = self._patch_id
        month_str = self._get_month_str()
        output_dir = self._get_output_dir()
        scan_patch_ids = self._scan_patch_ids
        scan_dir = self._scan_dir
        schedule_reminders = self._get_schedule_reminders()
        banner_image_bytes = self._banner_image_bytes

        def work() -> dict:
            from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
            engine = MonthlyPatchEngine(conn)
            try:
                if scan_patch_ids:
                    paths = engine.generate_notify_html_from_dir(
                        scan_patch_ids, scan_dir, month_str,
                        schedule_reminders=schedule_reminders,
                        banner_image_bytes=banner_image_bytes,
                    )
                else:
                    from hcp_cms.services.claude_content import ClaudeContentService
                    issues = engine.get_issues(patch_id)
                    svc = ClaudeContentService()
                    notify_body = svc.generate_notify_body(
                        [{"issue_no": i.issue_no, "description": i.description} for i in issues],
                        month_str,
                    )
                    path = engine.generate_notify_html(
                        patch_id, output_dir, month_str, notify_body=notify_body,
                        schedule_reminders=schedule_reminders,
                        banner_image_bytes=banner_image_bytes,
                    )
                    paths = [path]
                return {"paths": paths, "type": "html", "error": None}
            except Exception as e:
                return {"paths": [], "type": "html", "error": str(e)}

        threading.Thread(target=lambda: self._generate_done.emit(work()), daemon=True).start()

    def _on_generate_result(self, result: dict) -> None:
        btn = self._generate_excel_btn if result.get("type") == "excel" else self._generate_html_btn
        btn.setEnabled(True)
        if result.get("error"):
            self._append_log(f"❌ 產出失敗：{result['error']}")
            return
        for path in result.get("paths", []):
            self._output_list.addItem(QListWidgetItem(path))
            self._append_log(f"✅ {path}")
        step = 6 if result.get("type") == "excel" else 8
        self._set_step(step)

    def _on_regenerate_clicked(self) -> None:
        self._output_list.clear()
        self._on_generate_excel_clicked()

    # ── 新增 Slots ────────────────────────────────────────────────────────

    def _on_banner_upload_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇橫幅底圖", "", "圖片檔 (*.png *.jpg *.jpeg);;全部檔案 (*.*)"
        )
        if path:
            try:
                self._banner_image_bytes = Path(path).read_bytes()
                self._banner_label.setText(f"底圖：{Path(path).name}")
            except OSError as e:
                self._append_log(f"❌ 無法讀取圖片：{e}")

    def _on_month_changed(self) -> None:
        self._reminder_list.clear()

    def _on_reminder_add_clicked(self) -> None:
        text, ok = QInputDialog.getText(self, "新增排班提醒", "提醒內容：")
        if ok and text.strip():
            self._reminder_list.addItem(QListWidgetItem(text.strip()))

    def _on_reminder_del_clicked(self) -> None:
        for item in self._reminder_list.selectedItems():
            self._reminder_list.takeItem(self._reminder_list.row(item))

    def _get_schedule_reminders(self) -> list[str]:
        return [self._reminder_list.item(i).text() for i in range(self._reminder_list.count())]

    def _on_s2t_clicked(self) -> None:
        if not self._scan_dir:
            return
        scan_dir = self._scan_dir
        conn = self._conn
        self._s2t_btn.setEnabled(False)
        self._append_log("🔤 S2T 簡轉繁掃描中…")

        def work() -> dict:
            from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
            eng = MonthlyPatchEngine(conn)
            try:
                return {"result": eng.run_s2t(scan_dir or ""), "error": None}
            except Exception as e:
                return {"result": {}, "error": str(e)}

        threading.Thread(target=lambda: self._s2t_done.emit(work()), daemon=True).start()

    def _on_s2t_result(self, data: dict) -> None:
        self._s2t_btn.setEnabled(True)
        if data.get("error"):
            self._append_log(f"❌ S2T 失敗：{data['error']}")
            return
        result = data.get("result", {})
        if not result:
            self._append_log("🔤 無 .docx 檔案需轉換")
            self._set_step(5)
            return
        for fname, count in result.items():
            if count > 0:
                self._append_log(f"🔤 {fname} → 已轉換 {count} 字")
            elif count == 0:
                self._append_log(f"🔤 {fname} → 無需轉換")
            else:
                self._append_log(f"❌ {fname} → 轉換失敗")
        self._set_step(5)
        self._fetch_supplements_async()

    def _fetch_supplements_async(self) -> None:
        if not self._patch_id and not self._scan_patch_ids:
            return
        conn = self._conn
        patch_ids_list = list(self._scan_patch_ids.values()) if self._scan_patch_ids else [self._patch_id]
        self._append_log("📋 從 Mantis 取得補充說明（Claude 分析中）…")

        def work() -> int:
            from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
            eng = MonthlyPatchEngine(conn)
            total = 0
            for pid in patch_ids_list:
                if pid is not None:
                    total += eng.fetch_supplements(pid)
            return total

        threading.Thread(target=lambda: self._supplement_done.emit(work()), daemon=True).start()

    def _on_supplement_result(self, count: int) -> None:
        if count > 0:
            self._append_log(f"✅ 補充說明已更新：{count} 筆")
        else:
            self._append_log("⚠️ 補充說明：無 Mantis 連線或無資料")

    def _on_verify_clicked(self) -> None:
        if not self._scan_dir:
            self._append_log("⚠️ 請先掃描資料夾再驗證超連結")
            return
        scan_dir = self._scan_dir
        conn = self._conn
        self._verify_btn.setEnabled(False)
        self._append_log("🔗 驗證超連結…")

        def work() -> dict:
            from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
            eng = MonthlyPatchEngine(conn)
            try:
                return {"result": eng.verify_patch_links(scan_dir), "error": None}
            except Exception as e:
                return {"result": {}, "error": str(e)}

        threading.Thread(target=lambda: self._verify_done.emit(work()), daemon=True).start()

    def _on_verify_result(self, data: dict) -> None:
        self._verify_btn.setEnabled(True)
        if data.get("error"):
            self._append_log(f"❌ 驗證失敗：{data['error']}")
            return
        result = data.get("result", {})
        all_ok = True
        for ver, stats in result.items():
            ok = stats["ok"]
            total = stats["total"]
            if ok == total:
                self._append_log(f"✅ {ver}：{total}/{total} 條超連結正常")
            else:
                all_ok = False
                self._append_log(f"❌ {ver}：{ok}/{total} 條正常，失敗：")
                for f in stats["failed"]:
                    self._append_log(f"   → {f}")
        if all_ok and result:
            self._set_step(7)
