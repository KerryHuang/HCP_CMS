"""Classification rules management view."""

from __future__ import annotations

import sqlite3

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.data.models import ClassificationRule
from hcp_cms.data.repositories import RuleRepository

# 規則類型定義：(顯示名稱, DB key, 說明, Pattern 範例, Value 範例, 預設值)
_RULE_TYPES: list[tuple[str, str, str, str, str, str]] = [
    (
        "🖥 系統產品",
        "product",
        "根據關鍵字判斷此信件屬於哪個系統或產品。\n"
        "例如信中提到「薪資」→ 填入 HCP；提到「WebLogic」→ 填入 WebLogic。",
        "HCP|人事系統|薪資系統",
        "HCP",
        "無符合時預設填入：HCP",
    ),
    (
        "❓ 問題類型",
        "issue",
        "根據關鍵字判斷問題的大分類。\n"
        "常見值：BUG（程式錯誤）、REQ（功能需求）、OTH（其他詢問）。",
        "bug|錯誤|異常|閃退",
        "BUG",
        "無符合時預設填入：OTH",
    ),
    (
        "🔧 功能模組",
        "error",
        "根據關鍵字判斷屬於哪個功能模組（細分類）。\n"
        "例如「薪資、月薪」→ 薪資獎金計算；「請假、假單」→ 假勤管理。",
        "薪資|薪酬|月薪|工資",
        "薪資獎金計算",
        "無符合時預設填入：人事資料管理",
    ),
    (
        "⚡ 優先等級",
        "priority",
        "根據關鍵字判斷案件的處理優先順序。\n"
        "常見值：高、中、低。",
        "緊急|urgent|ASAP|立即",
        "高",
        "無符合時預設填入：中",
    ),
    (
        "📢 廣播信過濾",
        "broadcast",
        "符合此規則的信件會被視為廣播通知，不自動建立案件。\n"
        "例如系統維護公告、公司公告等群發信件。",
        "維護通知|系統公告|更新公告|停機",
        "廣播",
        "符合則跳過建案",
    ),
    (
        "👤 自動指派人員",
        "handler",
        "根據關鍵字自動填入「技術負責人」欄位。\n"
        "例如薪資相關信件自動指派給薪資模組負責工程師。",
        "薪資|薪酬",
        "王小明",
        "無符合時留空",
    ),
    (
        "📋 自動填入進度",
        "progress",
        "根據關鍵字自動填入「處理進度」欄位。\n"
        "也可在信件主旨加上 (RD_姓名) 標記來指定負責人。",
        "緊急|ASAP|urgent",
        "優先處理中",
        "無符合時留空",
    ),
]

# DB key → 索引
_TYPE_KEY_TO_IDX = {t[1]: i for i, t in enumerate(_RULE_TYPES)}


class RulesView(QWidget):
    """Classification rules management page."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._editing_id: int | None = None
        self._setup_ui()

    def _current_type_key(self) -> str:
        idx = self._type_combo.currentIndex()
        return _RULE_TYPES[idx][1]

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("📏 規則設定")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f1f5f9;")
        layout.addWidget(title)

        # ── 類型選擇列 ───────────────────────────────────────────
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("規則類型："))
        self._type_combo = QComboBox()
        for display, *_ in _RULE_TYPES:
            self._type_combo.addItem(display)
        self._type_combo.setMinimumWidth(180)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        filter_layout.addWidget(self._type_combo)

        refresh_btn = QPushButton("🔄 重新整理")
        refresh_btn.clicked.connect(self.refresh)
        filter_layout.addWidget(refresh_btn)

        import_btn = QPushButton("📥 匯入 CSV")
        import_btn.clicked.connect(self._on_import_csv)
        filter_layout.addWidget(import_btn)

        export_btn = QPushButton("📤 匯出 CSV")
        export_btn.clicked.connect(self._on_export_csv)
        filter_layout.addWidget(export_btn)

        self._format_help_btn = QPushButton("📋 格式說明")
        self._format_help_btn.clicked.connect(self._on_format_help)
        filter_layout.addWidget(self._format_help_btn)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # ── 說明卡片 ─────────────────────────────────────────────
        self._desc_card = QFrame()
        self._desc_card.setStyleSheet(
            "QFrame { background-color: #1e293b; border: 1px solid #334155;"
            " border-radius: 6px; padding: 4px; }"
        )
        card_layout = QVBoxLayout(self._desc_card)
        card_layout.setContentsMargins(12, 8, 12, 8)
        card_layout.setSpacing(4)

        self._desc_title = QLabel()
        self._desc_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #93c5fd;")
        self._desc_body = QLabel()
        self._desc_body.setStyleSheet("font-size: 12px; color: #cbd5e1;")
        self._desc_body.setWordWrap(True)
        self._desc_default = QLabel()
        self._desc_default.setStyleSheet("font-size: 11px; color: #64748b; font-style: italic;")

        card_layout.addWidget(self._desc_title)
        card_layout.addWidget(self._desc_body)
        card_layout.addWidget(self._desc_default)
        layout.addWidget(self._desc_card)

        # ── 規則清單 ─────────────────────────────────────────────
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["#", "關鍵字（正則）", "符合時填入的值", "優先順序"])
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setMinimumSectionSize(60)
        self._table.setColumnWidth(0, 40)
        self._table.setColumnWidth(1, 280)
        self._table.setColumnWidth(2, 180)
        self._table.setColumnWidth(3, 80)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.clicked.connect(self._on_row_clicked)
        layout.addWidget(self._table)

        # ── 新增 / 編輯表單 ───────────────────────────────────────
        form_group = QFormLayout()
        form_group.setContentsMargins(0, 8, 0, 0)

        self._pattern_input = QLineEdit()
        self._value_input = QLineEdit()
        self._priority_spin = QSpinBox()
        self._priority_spin.setRange(0, 999)
        self._priority_spin.setToolTip("數字越小越優先。同類型有多條規則時，第一個符合的生效。")

        form_group.addRow("關鍵字（正則）：", self._pattern_input)
        form_group.addRow("符合時填入：", self._value_input)
        form_group.addRow("優先順序（越小越優先）：", self._priority_spin)

        btn_layout = QHBoxLayout()
        self._add_btn = QPushButton("➕ 新增規則")
        self._add_btn.clicked.connect(self._on_add_rule)
        btn_layout.addWidget(self._add_btn)

        self._save_btn = QPushButton("💾 儲存修改")
        self._save_btn.clicked.connect(self._on_save_edit)
        self._save_btn.setVisible(False)
        btn_layout.addWidget(self._save_btn)

        self._delete_btn = QPushButton("🗑️ 刪除")
        self._delete_btn.clicked.connect(self._on_delete_rule)
        self._delete_btn.setVisible(False)
        self._delete_btn.setStyleSheet("background-color: #7f1d1d;")
        btn_layout.addWidget(self._delete_btn)

        self._cancel_btn = QPushButton("✕ 取消")
        self._cancel_btn.clicked.connect(self._exit_edit_mode)
        self._cancel_btn.setVisible(False)
        btn_layout.addWidget(self._cancel_btn)

        form_group.addRow(btn_layout)
        layout.addLayout(form_group)

        # 初始化說明卡片
        self._update_desc_card()

    def _update_desc_card(self) -> None:
        """根據目前選擇的類型，更新說明卡片與輸入框 placeholder。"""
        idx = self._type_combo.currentIndex()
        if idx < 0 or idx >= len(_RULE_TYPES):
            return
        display, key, desc, pat_ex, val_ex, default_note = _RULE_TYPES[idx]
        self._desc_title.setText(display)
        self._desc_body.setText(desc)
        self._desc_default.setText(f"⚙ {default_note}")
        self._pattern_input.setPlaceholderText(f"關鍵字範例：{pat_ex}")
        self._value_input.setPlaceholderText(f"填入值範例：{val_ex}")

    def refresh(self) -> None:
        if not self._conn:
            return
        repo = RuleRepository(self._conn)
        rules = repo.list_by_type(self._current_type_key())
        self._table.setRowCount(len(rules))
        for i, rule in enumerate(rules):
            self._table.setItem(i, 0, QTableWidgetItem(str(rule.rule_id)))
            self._table.setItem(i, 1, QTableWidgetItem(rule.pattern))
            self._table.setItem(i, 2, QTableWidgetItem(rule.value))
            self._table.setItem(i, 3, QTableWidgetItem(str(rule.priority)))
        self._exit_edit_mode()

    def _on_type_changed(self, _: int) -> None:
        self._update_desc_card()
        self.refresh()

    def _on_row_clicked(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        self._editing_id = int(self._table.item(row, 0).text())
        self._pattern_input.setText(self._table.item(row, 1).text())
        self._value_input.setText(self._table.item(row, 2).text())
        self._priority_spin.setValue(int(self._table.item(row, 3).text()))
        self._add_btn.setVisible(False)
        self._save_btn.setVisible(True)
        self._delete_btn.setVisible(True)
        self._cancel_btn.setVisible(True)

    def _exit_edit_mode(self) -> None:
        self._editing_id = None
        self._pattern_input.clear()
        self._value_input.clear()
        self._priority_spin.setValue(0)
        self._table.clearSelection()
        self._add_btn.setVisible(True)
        self._save_btn.setVisible(False)
        self._delete_btn.setVisible(False)
        self._cancel_btn.setVisible(False)

    def _on_add_rule(self) -> None:
        if not self._conn:
            return
        pattern = self._pattern_input.text().strip()
        value = self._value_input.text().strip()
        if not pattern or not value:
            QMessageBox.warning(self, "欄位不完整", "請填寫「關鍵字」及「符合時填入的值」。")
            return
        RuleRepository(self._conn).insert(ClassificationRule(
            rule_type=self._current_type_key(),
            pattern=pattern,
            value=value,
            priority=self._priority_spin.value(),
        ))
        self.refresh()

    def _on_save_edit(self) -> None:
        if not self._conn or self._editing_id is None:
            return
        pattern = self._pattern_input.text().strip()
        value = self._value_input.text().strip()
        if not pattern or not value:
            QMessageBox.warning(self, "欄位不完整", "請填寫「關鍵字」及「符合時填入的值」。")
            return
        RuleRepository(self._conn).update(ClassificationRule(
            rule_id=self._editing_id,
            rule_type=self._current_type_key(),
            pattern=pattern,
            value=value,
            priority=self._priority_spin.value(),
        ))
        self.refresh()

    def _on_delete_rule(self) -> None:
        if not self._conn or self._editing_id is None:
            return
        RuleRepository(self._conn).delete(self._editing_id)
        self.refresh()

    def _on_import_csv(self) -> None:
        if not self._conn:
            return
        path, _ = QFileDialog.getOpenFileName(self, "匯入規則 CSV", "", "CSV 檔案 (*.csv)")
        if not path:
            return
        imported, skipped = RuleRepository(self._conn).import_csv(path)
        self.refresh()
        QMessageBox.information(
            self,
            "匯入完成",
            f"成功匯入 {imported} 筆規則，跳過 {skipped} 筆無效資料。",
        )

    def _on_export_csv(self) -> None:
        if not self._conn:
            return
        path, _ = QFileDialog.getSaveFileName(self, "匯出規則 CSV", "rules.csv", "CSV 檔案 (*.csv)")
        if not path:
            return
        RuleRepository(self._conn).export_csv(path)
        QMessageBox.information(self, "匯出完成", f"規則已匯出至：\n{path}")

    def _on_format_help(self) -> None:
        dlg = RulesFormatDialog(self)
        dlg.exec()


# ---------------------------------------------------------------------------
# CSV 格式說明對話框
# ---------------------------------------------------------------------------

_CSV_HELP_TEXT = """\
═══════════════════════════════════════════════════════════
  規則 CSV 匯入格式說明
═══════════════════════════════════════════════════════════

【必要欄位】
  rule_type  規則類型（見下方類型對照表）
  pattern    正則表達式，比對主旨 + 信件內文前 300 字
  value      符合時寫入的值

【選填欄位】
  priority   優先順序（整數，數字越小越優先，預設 0）
             同類型有多條規則時，第一個符合的規則生效

【規則類型對照表】
  rule_type    說明                      Value 範例
  ─────────    ──────────────────────    ───────────────
  product      系統產品                  HCP / WebLogic
  issue        問題類型                  BUG / REQ / OTH
  error        錯誤類型 / 功能模組       薪資獎金計算
  priority     優先等級                  高 / 中 / 低
  broadcast    廣播信（不建案）          廣播
  handler      自動指派技術人員          王小明
  progress     自動填入處理進度          優先處理

【Pattern 正則表達式說明】
  |   多個關鍵字 OR，如  bug|錯誤|異常
  \\s  空白字元
  .   任意字元（搜尋時不區分大小寫）
  範例：薪資|薪酬|月薪|工資

═══════════════════════════════════════════════════════════
  CSV 範例內容（可直接複製貼上存為 rules.csv）
═══════════════════════════════════════════════════════════

rule_type,pattern,value,priority
product,weblogic|WLS,WebLogic,10
product,HCP|人事,HCP,20
issue,bug|錯誤|異常|問題,BUG,10
issue,需求|新增功能|客制,REQ,20
error,薪資|薪酬|月薪|工資,薪資獎金計算,10
error,請假|休假|假單,假勤管理,20
error,報表|匯出|列印,報表列印,30
priority,緊急|urgent|ASAP,高,10
priority,一般,中,20
broadcast,維護通知|系統公告|更新公告,廣播,10
handler,薪資|薪酬,王小明,10
handler,報表|報告,陳小華,20
handler,請假|休假,李大明,30
progress,緊急|ASAP|urgent,優先處理,10

═══════════════════════════════════════════════════════════
  注意事項
═══════════════════════════════════════════════════════════
  • 檔案需儲存為 UTF-8 或 UTF-8 BOM 編碼
  • pattern 或 value 為空的列會自動跳過
  • 重複匯入不會自動去重，請勿重複匯入同一檔案
  • 可先點「📤 匯出 CSV」取得現有規則作為編輯基礎
"""


class RulesFormatDialog(QDialog):
    """CSV 格式說明對話框。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("📋 規則 CSV 格式說明")
        self.setMinimumSize(680, 580)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setPlainText(_CSV_HELP_TEXT)
        self._text.setStyleSheet(
            "QTextEdit {"
            "  font-family: 'Consolas', '微軟正黑體', monospace;"
            "  font-size: 13px;"
            "  background-color: #0f172a;"
            "  color: #e2e8f0;"
            "  border: 1px solid #334155;"
            "  border-radius: 4px;"
            "  padding: 8px;"
            "}"
        )
        layout.addWidget(self._text)

        btn_layout = QHBoxLayout()

        copy_btn = QPushButton("📋 複製範例 CSV")
        copy_btn.clicked.connect(self._on_copy_example)
        btn_layout.addWidget(copy_btn)

        btn_layout.addStretch()

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.reject)
        btn_layout.addWidget(close_box)

        layout.addLayout(btn_layout)

    def _on_copy_example(self) -> None:
        example = (
            "rule_type,pattern,value,priority\n"
            "product,weblogic|WLS,WebLogic,10\n"
            "issue,bug|錯誤|異常,BUG,10\n"
            "issue,需求|新增功能|客制,REQ,20\n"
            "error,薪資|薪酬|月薪,薪資獎金計算,10\n"
            "priority,緊急|urgent|ASAP,高,10\n"
            "broadcast,維護通知|系統公告,廣播,10\n"
            "handler,薪資|薪酬,王小明,10\n"
            "progress,緊急|ASAP,優先處理,10\n"
        )
        QGuiApplication.clipboard().setText(example)
        QMessageBox.information(self, "已複製", "範例 CSV 內容已複製到剪貼簿！\n開啟記事本貼上後存檔即可匯入。")
