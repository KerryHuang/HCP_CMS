"""警示未結清單確認對話框。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.ui.theme import DARK_PALETTE, ColorPalette


class StalenessReminderDialog(QDialog):
    """警示未結清單，兩分頁：

    - ⚠ 超時未回覆：曾有 HCP 回覆但已超過 threshold_hours 工時未再回
    - 🚨 從未回覆：HCP 從未回過 + 客戶來信至今超過 threshold_hours 工時

    每筆 case 依 handler 分組排序（同 handler 相鄰），handler_email 為 None 的
    case 預設不勾選且不可勾（無收件人）。
    批次勾選按鈕作用於「當前分頁」；發送時合併兩分頁的勾選結果。
    """

    case_subject_clicked = Signal(str)

    # 欄位 index 常數（順序：發送 / 公司 / 主旨 / Handler / 超時 / Email / 案件編號）
    COL_CHECK = 0
    COL_COMPANY = 1
    COL_SUBJECT = 2
    COL_HANDLER = 3
    COL_HOURS = 4
    COL_EMAIL = 5
    COL_CASE_ID = 6

    def __init__(
        self,
        stale_cases: list[dict],
        never_replied_cases: list[dict],
        threshold_hours: float,
        parent=None,
        palette: ColorPalette | None = None,
    ) -> None:
        super().__init__(parent)
        self._stale_cases = self._sort_by_handler(stale_cases)
        self._never_replied_cases = self._sort_by_handler(never_replied_cases)
        self._threshold_hours = threshold_hours
        self._palette = palette or DARK_PALETTE
        # 兩 tab 各自的 checkbox list + table，批次按鈕用 tab index 切換
        self._stale_checkboxes: list[QCheckBox] = []
        self._no_reply_checkboxes: list[QCheckBox] = []
        self._stale_table: QTableWidget | None = None
        self._no_reply_table: QTableWidget | None = None
        self.setWindowTitle("警示未結清單")
        self.setMinimumWidth(1000)
        self._setup_ui()

    @staticmethod
    def _sort_by_handler(cases: list[dict]) -> list[dict]:
        """同 handler 相鄰，未指派 handler 排最後；handler 內依 case_id。"""
        return sorted(
            cases,
            key=lambda c: (
                c.get("handler") is None,
                c.get("handler") or "",
                c.get("case_id") or "",
            ),
        )

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        header_text = (
            f"工時閾值：{int(self._threshold_hours)} 工作小時"
            f"（⚠ 超時 {len(self._stale_cases)} 件、🚨 從未回覆 {len(self._never_replied_cases)} 件）\n"
            "勾選要發送警示通知的項目，同 handler 會合併為一封 email 寄出。"
        )
        header = QLabel(header_text)
        header.setStyleSheet(f"color: {self._palette.text_primary}; font-size: 12px;")
        header.setWordWrap(True)
        layout.addWidget(header)

        # 批次勾選工具列（作用於當前 tab）
        bulk_row = QHBoxLayout()
        select_all_btn = QPushButton("全選")
        select_all_btn.clicked.connect(self._select_all_current)
        deselect_all_btn = QPushButton("全不選")
        deselect_all_btn.clicked.connect(self._deselect_all_current)
        invert_btn = QPushButton("反選")
        invert_btn.clicked.connect(self._invert_current)
        bulk_row.addWidget(select_all_btn)
        bulk_row.addWidget(deselect_all_btn)
        bulk_row.addWidget(invert_btn)
        bulk_row.addStretch()
        layout.addLayout(bulk_row)

        # 兩個 tab
        self._tabs = QTabWidget()
        # Tab 1: 超時未回覆
        self._stale_table = self._build_table(
            self._stale_cases, self._stale_checkboxes
        )
        self._tabs.addTab(
            self._wrap_in_widget(self._stale_table),
            f"⚠ 超時未回覆 ({len(self._stale_cases)})",
        )
        # Tab 2: 從未回覆
        self._no_reply_table = self._build_table(
            self._never_replied_cases, self._no_reply_checkboxes
        )
        self._tabs.addTab(
            self._wrap_in_widget(self._no_reply_table),
            f"🚨 從未回覆 ({len(self._never_replied_cases)})",
        )
        layout.addWidget(self._tabs)

        # 按鈕
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.send_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.send_button.setText("📧 發送警示通知")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _wrap_in_widget(table: QTableWidget) -> QWidget:
        """把 table 包進 QWidget 給 QTabWidget 用。"""
        w = QWidget()
        ly = QVBoxLayout(w)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.addWidget(table)
        return w

    def _build_table(
        self,
        cases: list[dict],
        checkbox_store: list[QCheckBox],
    ) -> QTableWidget:
        """建立一個 case 表格（順序：發送 / 公司 / 主旨 / Handler / 超時 / Email / 案件編號）。

        checkbox_store 接收新建的 QCheckBox 物件（呼叫端用以取勾選結果）。
        """
        table = QTableWidget(len(cases), 7)
        table.setHorizontalHeaderLabels(
            ["發送", "公司", "主旨", "Handler", "超時(工時)", "收件 email", "案件編號"]
        )
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.cellClicked.connect(
            lambda row, col, _cases=cases: self._on_cell_clicked(row, col, _cases)
        )

        for i, c in enumerate(cases):
            cb = QCheckBox()
            has_email = bool(c.get("handler_email"))
            cb.setChecked(has_email)
            cb.setEnabled(has_email)
            checkbox_store.append(cb)
            wrapper = QWidget()
            wrapper_layout = QVBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wrapper_layout.addWidget(cb)
            table.setCellWidget(i, self.COL_CHECK, wrapper)

            company_label = c.get("company_name") or c.get("company_id") or "—"
            table.setItem(i, self.COL_COMPANY, QTableWidgetItem(company_label))
            subject_item = QTableWidgetItem(c.get("subject") or "")
            subject_item.setToolTip("點此開啟案件詳情")
            table.setItem(i, self.COL_SUBJECT, subject_item)
            table.setItem(i, self.COL_HANDLER, QTableWidgetItem(c.get("handler") or "—"))
            table.setItem(
                i, self.COL_HOURS,
                QTableWidgetItem(f"{c['hours_since_last_reply']:.1f}"),
            )
            table.setItem(i, self.COL_EMAIL, QTableWidgetItem(c.get("handler_email") or "（無）"))
            table.setItem(i, self.COL_CASE_ID, QTableWidgetItem(c["case_id"]))

        table.resizeColumnsToContents()
        if table.columnWidth(self.COL_SUBJECT) < 360:
            table.setColumnWidth(self.COL_SUBJECT, 360)
        table.setMinimumHeight(320)
        return table

    def _current_checkboxes(self) -> list[QCheckBox]:
        """目前 tab 對應的 checkbox 清單。"""
        if self._tabs.currentIndex() == 0:
            return self._stale_checkboxes
        return self._no_reply_checkboxes

    def _select_all_current(self) -> None:
        for cb in self._current_checkboxes():
            if cb.isEnabled():
                cb.setChecked(True)

    def _deselect_all_current(self) -> None:
        for cb in self._current_checkboxes():
            if cb.isEnabled():
                cb.setChecked(False)

    def _invert_current(self) -> None:
        for cb in self._current_checkboxes():
            if cb.isEnabled():
                cb.setChecked(not cb.isChecked())

    def _on_cell_clicked(self, row: int, col: int, cases: list[dict]) -> None:
        """點主旨欄 → emit case_id 讓上層開案件詳情。"""
        if col != self.COL_SUBJECT:
            return
        if 0 <= row < len(cases):
            case_id = cases[row].get("case_id")
            if case_id:
                self.case_subject_clicked.emit(case_id)

    def selected_cases(self) -> list[dict]:
        """回傳兩 tab 合併後的勾選案件清單。"""
        result = [
            c for c, cb in zip(self._stale_cases, self._stale_checkboxes)
            if cb.isChecked()
        ]
        result += [
            c for c, cb in zip(self._never_replied_cases, self._no_reply_checkboxes)
            if cb.isChecked()
        ]
        return result
