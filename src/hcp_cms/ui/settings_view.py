"""System settings view."""

from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QFormLayout, QGroupBox, QLabel, QLineEdit, QPushButton,
    QSpinBox, QVBoxLayout, QWidget, QFileDialog, QComboBox, QHBoxLayout,
)


class SettingsView(QWidget):
    """System settings page."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("⚙️ 系統設定")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f1f5f9;")
        layout.addWidget(title)

        # User settings
        user_group = QGroupBox("使用者設定")
        user_layout = QFormLayout(user_group)
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("客服人員姓名")
        user_layout.addRow("姓名:", self._name_input)
        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["繁體中文", "English"])
        user_layout.addRow("語系:", self._lang_combo)
        layout.addWidget(user_group)

        # DB settings
        db_group = QGroupBox("資料庫設定")
        db_layout = QFormLayout(db_group)
        self._db_path = QLineEdit()
        self._db_path.setPlaceholderText("資料庫路徑")
        browse_btn = QPushButton("瀏覽...")
        browse_btn.clicked.connect(self._on_browse_db)
        db_row = QHBoxLayout()
        db_row.addWidget(self._db_path)
        db_row.addWidget(browse_btn)
        db_layout.addRow("DB 路徑:", db_row)
        layout.addWidget(db_group)

        # Backup settings
        backup_group = QGroupBox("備份設定")
        backup_layout = QFormLayout(backup_group)
        self._backup_interval = QSpinBox()
        self._backup_interval.setRange(1, 168)
        self._backup_interval.setValue(24)
        self._backup_interval.setSuffix(" 小時")
        backup_layout.addRow("備份頻率:", self._backup_interval)
        self._backup_keep = QSpinBox()
        self._backup_keep.setRange(1, 365)
        self._backup_keep.setValue(30)
        self._backup_keep.setSuffix(" 天")
        backup_layout.addRow("保留天數:", self._backup_keep)

        btn_layout = QHBoxLayout()
        self._backup_now_btn = QPushButton("💾 立即備份")
        self._restore_btn = QPushButton("📦 還原")
        self._export_btn = QPushButton("📤 匯出")
        self._import_btn = QPushButton("📥 匯入合併")
        self._migrate_btn = QPushButton("🔄 舊 DB 遷移")
        btn_layout.addWidget(self._backup_now_btn)
        btn_layout.addWidget(self._restore_btn)
        btn_layout.addWidget(self._export_btn)
        btn_layout.addWidget(self._import_btn)
        btn_layout.addWidget(self._migrate_btn)
        backup_layout.addRow(btn_layout)
        layout.addWidget(backup_group)

        # Save button
        save_btn = QPushButton("💾 儲存設定")
        layout.addWidget(save_btn)

        layout.addStretch()

    def _on_browse_db(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "選擇資料庫", "", "SQLite (*.db)")
        if path:
            self._db_path.setText(path)
