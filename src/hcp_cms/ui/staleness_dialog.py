"""警示未結清單確認對話框。"""
from __future__ import annotations

from PySide6.QtCore import Qt
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
    QVBoxLayout,
    QWidget,
)

from hcp_cms.ui.theme import DARK_PALETTE, ColorPalette


class StalenessReminderDialog(QDialog):
    """顯示警示未結清單，使用者勾選後發送警示通知 email。

    案件依 handler 排序（同 handler 相鄰），無 handler 排最後。
    handler_email 為 None 的 case 預設不勾選且不可勾（無收件人）。
    支援整批勾選 / 全不選 / 反選。
    """

    # 欄位 index 常數（方便維護）
    COL_CHECK = 0
    COL_CASE_ID = 1
    COL_COMPANY = 2
    COL_SUBJECT = 3
    COL_HANDLER = 4
    COL_HOURS = 5
    COL_EMAIL = 6

    def __init__(
        self,
        stale_cases: list[dict],
        threshold_hours: float,
        parent=None,
        palette: ColorPalette | None = None,
    ) -> None:
        super().__init__(parent)
        # 同 handler 相鄰，未指派 handler 排最後；handler 內依 case_id
        self._stale_cases = sorted(
            stale_cases,
            key=lambda c: (
                c.get("handler") is None,  # None 排最後
                c.get("handler") or "",
                c.get("case_id") or "",
            ),
        )
        self._threshold_hours = threshold_hours
        self._palette = palette or DARK_PALETTE
        self._checkboxes: list[QCheckBox] = []
        self.setWindowTitle("警示未結清單")
        self.setMinimumWidth(960)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        header = QLabel(
            f"找到 {len(self._stale_cases)} 件未結案件超過 {int(self._threshold_hours)} 工作小時無 HCP 回覆。\n"
            "勾選要發送警示通知的項目，同 handler 會合併為一封 email 寄出。"
        )
        header.setStyleSheet(f"color: {self._palette.text_primary}; font-size: 12px;")
        header.setWordWrap(True)
        layout.addWidget(header)

        # 批次勾選工具列
        bulk_row = QHBoxLayout()
        select_all_btn = QPushButton("全選")
        select_all_btn.clicked.connect(self._select_all)
        deselect_all_btn = QPushButton("全不選")
        deselect_all_btn.clicked.connect(self._deselect_all)
        invert_btn = QPushButton("反選")
        invert_btn.clicked.connect(self._invert_selection)
        bulk_row.addWidget(select_all_btn)
        bulk_row.addWidget(deselect_all_btn)
        bulk_row.addWidget(invert_btn)
        bulk_row.addStretch()
        layout.addLayout(bulk_row)

        # 表格
        self._table = QTableWidget(len(self._stale_cases), 7)
        self._table.setHorizontalHeaderLabels(
            ["發送", "案件編號", "公司", "主旨", "Handler", "超時(工時)", "收件 email"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        for i, c in enumerate(self._stale_cases):
            cb = QCheckBox()
            has_email = bool(c.get("handler_email"))
            cb.setChecked(has_email)
            cb.setEnabled(has_email)
            self._checkboxes.append(cb)
            # 用 QWidget 包 checkbox 才能置中
            wrapper = QWidget()
            wrapper_layout = QVBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wrapper_layout.addWidget(cb)
            self._table.setCellWidget(i, self.COL_CHECK, wrapper)

            self._table.setItem(i, self.COL_CASE_ID, QTableWidgetItem(c["case_id"]))
            company_label = c.get("company_name") or c.get("company_id") or "—"
            self._table.setItem(i, self.COL_COMPANY, QTableWidgetItem(company_label))
            self._table.setItem(i, self.COL_SUBJECT, QTableWidgetItem(c.get("subject") or ""))
            self._table.setItem(i, self.COL_HANDLER, QTableWidgetItem(c.get("handler") or "—"))
            self._table.setItem(i, self.COL_HOURS, QTableWidgetItem(f"{c['hours_since_last_reply']:.1f}"))
            self._table.setItem(i, self.COL_EMAIL, QTableWidgetItem(c.get("handler_email") or "（無）"))

        self._table.setMinimumHeight(320)
        layout.addWidget(self._table)

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

    def _select_all(self) -> None:
        """全選（僅勾可勾的——handler_email 存在的）。"""
        for cb in self._checkboxes:
            if cb.isEnabled():
                cb.setChecked(True)

    def _deselect_all(self) -> None:
        """全不選。"""
        for cb in self._checkboxes:
            if cb.isEnabled():
                cb.setChecked(False)

    def _invert_selection(self) -> None:
        """反選（僅可勾的反向）。"""
        for cb in self._checkboxes:
            if cb.isEnabled():
                cb.setChecked(not cb.isChecked())

    def selected_cases(self) -> list[dict]:
        """回傳使用者勾選要發送的案件。"""
        return [
            c for c, cb in zip(self._stale_cases, self._checkboxes)
            if cb.isChecked()
        ]
