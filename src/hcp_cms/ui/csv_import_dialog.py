"""CSV 匯入精靈 — 3 步驟 QDialog。"""
from __future__ import annotations

import re as _re
import sqlite3
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.csv_import_engine import (
    DEFAULT_MAPPING,
    REQUIRED_DB_COLS,
    ConflictStrategy,
    CsvImportEngine,
    ImportPreview,
    ImportResult,
    Mapping,
    _detect_encoding,
)
from hcp_cms.ui.theme import DARK_PALETTE as _DARK_PALETTE
from hcp_cms.ui.theme import ColorPalette

# 用於從 combo 顯示文字（如 "主旨 (subject)"）解析出 col_key
_COMBO_KEY_RE = _re.compile(r'\(([^)]+)\)$')


class CsvImportDialog(QDialog):
    """3 步驟 CSV 匯入精靈。"""

    def __init__(self, db_path: Path, parent: QWidget | None = None, palette: ColorPalette | None = None) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._palette = palette or _DARK_PALETTE
        self._csv_path: Path | None = None
        self._headers: list[str] = []
        self._mapping: Mapping = {}
        self._preview: ImportPreview | None = None
        self._unmatched_checks: dict[str, tuple[QCheckBox, QLineEdit]] = {}
        self.setWindowTitle("📥 CSV 匯入精靈")
        self.setMinimumSize(700, 500)
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI 建構
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 步驟指示
        self._step_label = QLabel("步驟 1 / 3：選擇 CSV 檔案")
        self._step_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {self._palette.text_primary};")
        layout.addWidget(self._step_label)

        # 主體（堆疊頁）
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_step1())
        self._stack.addWidget(self._build_step2())
        self._stack.addWidget(self._build_step3())
        layout.addWidget(self._stack)

        # 底部按鈕
        btn_layout = QHBoxLayout()
        self._back_btn = QPushButton("← 上一步")
        self._back_btn.setEnabled(False)
        self._back_btn.clicked.connect(self._go_back)
        self._next_btn = QPushButton("下一步 →")
        self._next_btn.clicked.connect(self._go_next)
        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._back_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        btn_layout.addWidget(self._next_btn)
        layout.addLayout(btn_layout)

    def _build_step1(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        desc = QLabel("選擇要匯入的 CSV 檔案（支援 UTF-8、UTF-8 BOM、Big5 編碼）：")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        file_row = QHBoxLayout()
        self._file_label = QLabel("（未選擇）")
        self._file_label.setStyleSheet(f"color: {self._palette.text_tertiary};")
        browse_btn = QPushButton("瀏覽...")
        browse_btn.clicked.connect(self._on_browse)
        file_row.addWidget(self._file_label, 1)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        self._file_info = QLabel("")
        self._file_info.setWordWrap(True)
        layout.addWidget(self._file_info)

        layout.addStretch()
        return w

    def _build_step2(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        desc = QLabel("左欄為 CSV 欄位，右欄選擇對應的資料庫欄位（選「skip」略過）：")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self._mapping_layout = QFormLayout(inner)
        scroll.setWidget(inner)
        layout.addWidget(scroll)

        self._combo_map: dict[str, QComboBox] = {}  # csv_col → QComboBox

        # 未對應欄位區塊
        self._unmatched_group = QGroupBox("尚未對應的 CSV 欄位 — 勾選可自動建立新欄位：")
        self._unmatched_group.setVisible(False)
        self._unmatched_layout = QVBoxLayout(self._unmatched_group)
        layout.addWidget(self._unmatched_group)

        return w

    def _build_step3(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        self._preview_label = QLabel("正在計算...")
        layout.addWidget(self._preview_label)

        # 衝突策略
        strategy_label = QLabel("衝突處理：")
        layout.addWidget(strategy_label)
        self._skip_radio = QRadioButton("略過（保留現有資料）")
        self._overwrite_radio = QRadioButton("覆蓋（以 CSV 資料取代）")
        self._skip_radio.setChecked(True)
        self._strategy_group = QButtonGroup(w)
        self._strategy_group.addButton(self._skip_radio)
        self._strategy_group.addButton(self._overwrite_radio)
        layout.addWidget(self._skip_radio)
        layout.addWidget(self._overwrite_radio)

        # 進度條
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        # 結果
        self._result_text = QTextEdit()
        self._result_text.setReadOnly(True)
        self._result_text.setVisible(False)
        layout.addWidget(self._result_text)

        layout.addStretch()
        return w

    # ------------------------------------------------------------------
    # Step 1 邏輯
    # ------------------------------------------------------------------

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇 CSV 檔案", "", "CSV 檔案 (*.csv);;所有檔案 (*)"
        )
        if not path:
            return
        csv_path = Path(path)
        try:
            enc = _detect_encoding(csv_path)
            import csv as csv_mod

            with csv_path.open(encoding=enc, newline="") as f:
                reader = csv_mod.reader(f)
                headers = next(reader, [])
                row_count = sum(1 for _ in reader)
        except ValueError as e:
            QMessageBox.critical(self, "編碼錯誤", str(e))
            return

        self._csv_path = csv_path
        self._headers = headers
        self._file_label.setText(csv_path.name)
        self._file_label.setStyleSheet(f"color: {self._palette.text_primary};")
        self._file_info.setText(
            f"偵測編碼：{enc}　|　欄位數：{len(headers)}　|　資料筆數：{row_count}\n"
            f"欄位：{', '.join(headers[:8])}{'...' if len(headers) > 8 else ''}"
        )
        self._next_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Step 2 邏輯
    # ------------------------------------------------------------------

    def _populate_step2(self) -> None:
        # 清除舊內容
        while self._mapping_layout.rowCount():
            self._mapping_layout.removeRow(0)
        self._combo_map.clear()

        # 取得可對應欄位（含中文標籤）
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            from hcp_cms.core.custom_column_manager import CustomColumnManager
            mgr = CustomColumnManager(conn)
            mappable = mgr.get_mappable_columns()  # [(col_key, col_label), ...]
        finally:
            conn.close()

        items = ["skip"] + [f"{label} ({key})" for key, label in mappable]

        for csv_col in self._headers:
            combo = QComboBox()
            combo.addItems(items)
            # 預設值：依 DEFAULT_MAPPING 找 col_key，再比對文字
            default_db_col = DEFAULT_MAPPING.get(csv_col, "skip")
            target_text = next(
                (f"{label} ({key})" for key, label in mappable if key == default_db_col),
                "skip",
            )
            idx = combo.findText(target_text)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.currentIndexChanged.connect(self._refresh_unmatched_section)
            self._combo_map[csv_col] = combo
            self._mapping_layout.addRow(csv_col, combo)

        self._refresh_unmatched_section()

    def _refresh_unmatched_section(self) -> None:
        """重算未對應 CSV 欄位，更新 unmatched_group。"""
        # 清除舊內容
        for i in reversed(range(self._unmatched_layout.count())):
            item = self._unmatched_layout.itemAt(i)
            w = item.widget() if item else None
            if w:
                w.setParent(None)
        self._unmatched_checks.clear()

        unmatched = []
        for csv_col, combo in self._combo_map.items():
            text = combo.currentText()
            m = _COMBO_KEY_RE.search(text)
            db_col = m.group(1) if m else "skip"
            if db_col == "skip":
                unmatched.append(csv_col)

        self._unmatched_group.setVisible(bool(unmatched))
        for csv_col in unmatched:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            chk = QCheckBox(csv_col)
            chk.setChecked(True)
            label_input = QLineEdit(csv_col)
            label_input.setPlaceholderText("中文標籤")
            row_layout.addWidget(chk)
            row_layout.addWidget(QLabel("  中文標籤："))
            row_layout.addWidget(label_input)
            self._unmatched_layout.addWidget(row_widget)
            self._unmatched_checks[csv_col] = (chk, label_input)

    def _validate_step2(self) -> bool:
        """檢查必填欄位（sent_time, subject, company_id）是否已對應。"""
        mapped_db_cols = set()
        for combo in self._combo_map.values():
            text = combo.currentText()
            m = _COMBO_KEY_RE.search(text)
            if m:
                mapped_db_cols.add(m.group(1))
        missing = REQUIRED_DB_COLS - mapped_db_cols
        if missing:
            QMessageBox.warning(
                self,
                "必填欄位未對應",
                f"以下欄位必須對應（不可略過）：\n{', '.join(missing)}",
            )
            return False
        return True

    def _collect_mapping(self) -> None:
        result = {}
        for csv_col, combo in self._combo_map.items():
            text = combo.currentText()
            m = _COMBO_KEY_RE.search(text)
            result[csv_col] = m.group(1) if m else "skip"
        self._mapping = result

    # ------------------------------------------------------------------
    # Step 3 邏輯
    # ------------------------------------------------------------------

    def _populate_step3(self) -> None:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            engine = CsvImportEngine(conn)
            self._preview = engine.preview(self._csv_path, self._mapping)
        finally:
            conn.close()

        p = self._preview
        self._preview_label.setText(
            f"預覽結果：共 {p.total} 筆　"
            f"新增 {p.new_count} 筆　"
            f"衝突 {p.conflict_count} 筆"
        )
        self._result_text.setVisible(False)
        self._progress_bar.setVisible(False)
        self._next_btn.setEnabled(True)

    def _run_import(self) -> None:
        strategy = (
            ConflictStrategy.OVERWRITE
            if self._overwrite_radio.isChecked()
            else ConflictStrategy.SKIP
        )
        total = self._preview.total if self._preview else 0
        self._progress_bar.setMaximum(max(total, 1))
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        self._next_btn.setEnabled(False)
        self._back_btn.setEnabled(False)

        self._worker = CsvImportWorker(
            self._db_path, self._csv_path, self._mapping, strategy
        )
        self._worker.progress.connect(lambda c, t: self._progress_bar.setValue(c))
        self._worker.finished.connect(self._on_import_finished)
        self._worker.start()

    def _on_import_finished(self, result: ImportResult) -> None:
        self._progress_bar.setVisible(False)
        self._result_text.setVisible(True)
        lines = [
            "✅ 匯入完成",
            f"   成功：{result.success} 筆",
            f"   略過：{result.skipped} 筆",
            f"   覆蓋：{result.overwritten} 筆",
            f"   失敗：{result.failed} 筆",
        ]
        if result.errors:
            lines.append("\n錯誤清單：")
            lines.extend(f"  • {e}" for e in result.errors[:20])
            if len(result.errors) > 20:
                lines.append(f"  ... 還有 {len(result.errors) - 20} 筆錯誤")
        self._result_text.setPlainText("\n".join(lines))
        self._next_btn.setText("完成")
        self._next_btn.setEnabled(True)
        self._next_btn.clicked.disconnect()
        self._next_btn.clicked.connect(self.accept)
        self._back_btn.setEnabled(True)  # 匯入完成後允許返回上一步重新操作

    # ------------------------------------------------------------------
    # 導覽
    # ------------------------------------------------------------------

    def _go_next(self) -> None:
        idx = self._stack.currentIndex()
        if idx == 0:
            if not self._csv_path:
                QMessageBox.warning(self, "提示", "請先選擇 CSV 檔案。")
                return
            self._populate_step2()
            self._stack.setCurrentIndex(1)
            self._step_label.setText("步驟 2 / 3：確認欄位對應")
            self._back_btn.setEnabled(True)
            self._next_btn.setText("下一步 →")
        elif idx == 1:
            if not self._validate_step2():
                return
            self._collect_mapping()
            # 建立勾選的自訂欄（在 preview 前）
            requests = [
                (csv_col, line_edit.text().strip() or csv_col)
                for csv_col, (chk, line_edit) in self._unmatched_checks.items()
                if chk.isChecked()
            ]
            if requests:
                conn = sqlite3.connect(str(self._db_path))
                conn.row_factory = sqlite3.Row
                try:
                    engine = CsvImportEngine(conn)
                    new_cols = engine.create_custom_columns(requests)
                    # 更新 mapping：csv_col → cx_N
                    for (csv_col, _), col in zip(requests, new_cols):
                        if self._mapping.get(csv_col) == "skip":
                            self._mapping[csv_col] = col.col_key
                finally:
                    conn.close()
            self._populate_step3()
            self._stack.setCurrentIndex(2)
            self._step_label.setText("步驟 3 / 3：預覽與執行")
            self._next_btn.setText("執行匯入")
        elif idx == 2:
            self._run_import()

    def _go_back(self) -> None:
        idx = self._stack.currentIndex()
        if idx == 1:
            self._stack.setCurrentIndex(0)
            self._step_label.setText("步驟 1 / 3：選擇 CSV 檔案")
            self._back_btn.setEnabled(False)
            self._next_btn.setText("下一步 →")
        elif idx == 2:
            self._stack.setCurrentIndex(1)
            self._step_label.setText("步驟 2 / 3：確認欄位對應")
            self._next_btn.setText("下一步 →")
            # 若匯入完成後返回，需將 next 按鈕重新接回 _go_next
            try:
                self._next_btn.clicked.disconnect()
            except RuntimeError:
                pass
            self._next_btn.clicked.connect(self._go_next)


class CsvImportWorker(QThread):
    """在獨立執行緒執行 CsvImportEngine.execute()。"""

    progress = Signal(int, int)  # (current, total)
    finished = Signal(object)  # ImportResult

    def __init__(
        self,
        db_path: Path,
        csv_path: Path,
        mapping: Mapping,
        strategy: ConflictStrategy,
    ) -> None:
        super().__init__()
        self._db_path = db_path
        self._csv_path = csv_path
        self._mapping = mapping
        self._strategy = strategy

    def run(self) -> None:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            engine = CsvImportEngine(conn)
            result = engine.execute(
                self._csv_path,
                self._mapping,
                self._strategy,
                progress_cb=lambda c, t: self.progress.emit(c, t),
            )
            self.finished.emit(result)
        except Exception as e:
            err = ImportResult(failed=1, errors=[str(e)])
            self.finished.emit(err)
        finally:
            conn.close()
