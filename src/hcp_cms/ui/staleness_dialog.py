"""超時案件提醒確認對話框。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.ui.theme import DARK_PALETTE, ColorPalette


class StalenessReminderDialog(QDialog):
    """顯示超時案件清單，使用者勾選後發送提醒 email。

    案件依 handler_email 自動分組，每位 handler 收到一封 email。
    handler_email 為 None 的 case 預設不勾選（無收件人）。
    """

    def __init__(
        self,
        stale_cases: list[dict],
        threshold_hours: float,
        parent=None,
        palette: ColorPalette | None = None,
    ) -> None:
        super().__init__(parent)
        self._stale_cases = stale_cases
        self._threshold_hours = threshold_hours
        self._palette = palette or DARK_PALETTE
        self._checkboxes: list[QCheckBox] = []
        self.setWindowTitle("超時案件提醒")
        self.setMinimumWidth(820)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        header = QLabel(
            f"找到 {len(self._stale_cases)} 筆案件超過 {int(self._threshold_hours)} 工作小時無 HCP 回覆。\n"
            "勾選要寄送提醒的項目，同 handler 會合併為一封 email 寄出。"
        )
        header.setStyleSheet(f"color: {self._palette.text_primary}; font-size: 12px;")
        header.setWordWrap(True)
        layout.addWidget(header)

        # 表格：勾選 | 案件 | 主旨 | Handler | 已超時 | 收件 email
        self._table = QTableWidget(len(self._stale_cases), 6)
        self._table.setHorizontalHeaderLabels(
            ["發送", "案件編號", "主旨", "Handler", "超時(工時)", "收件 email"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        for i, c in enumerate(self._stale_cases):
            cb = QCheckBox()
            cb.setChecked(bool(c.get("handler_email")))
            cb.setEnabled(bool(c.get("handler_email")))  # 無 email 不可勾
            self._checkboxes.append(cb)
            # 用 QWidget 包 checkbox 才能置中
            wrapper = QWidget()
            wrapper_layout = QVBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wrapper_layout.addWidget(cb)
            self._table.setCellWidget(i, 0, wrapper)

            self._table.setItem(i, 1, QTableWidgetItem(c["case_id"]))
            self._table.setItem(i, 2, QTableWidgetItem(c.get("subject") or ""))
            self._table.setItem(i, 3, QTableWidgetItem(c.get("handler") or "—"))
            self._table.setItem(i, 4, QTableWidgetItem(f"{c['hours_since_last_reply']:.1f}"))
            self._table.setItem(i, 5, QTableWidgetItem(c.get("handler_email") or "（無）"))

        self._table.setMinimumHeight(280)
        layout.addWidget(self._table)

        # 按鈕
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.send_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.send_button.setText("📧 發送提醒")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_cases(self) -> list[dict]:
        """回傳使用者勾選要發送的案件。"""
        return [
            c for c, cb in zip(self._stale_cases, self._checkboxes)
            if cb.isChecked()
        ]
