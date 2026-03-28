"""System settings view."""

from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.services.credential import CredentialManager


class SettingsView(QWidget):
    """System settings page."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._creds = CredentialManager()
        self._setup_ui()
        self._load_mantis_creds()

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

        # Mantis SOAP settings
        mantis_group = QGroupBox("🔧 Mantis SOAP 連線設定")
        mantis_layout = QFormLayout(mantis_group)

        # URL 欄位 + 清除按鈕
        url_row = QHBoxLayout()
        self._mantis_url = QLineEdit()
        self._mantis_url.setPlaceholderText("https://118.163.30.33/mantis/")
        self._mantis_url.setMinimumWidth(400)
        url_row.addWidget(self._mantis_url)
        clear_url_btn = QPushButton("✕ 清除")
        clear_url_btn.setFixedWidth(60)
        clear_url_btn.clicked.connect(lambda: self._mantis_url.clear())
        url_row.addWidget(clear_url_btn)
        mantis_layout.addRow("Mantis URL：", url_row)

        url_hint = QLabel(
            "⚠ 請只填基本網址，例如：https://118.163.30.33/mantis/\n"
            "   不要包含 login_page.php 或 view.php 等頁面路徑"
        )
        url_hint.setStyleSheet("color: #94a3b8; font-size: 11px;")
        mantis_layout.addRow("", url_hint)

        self._mantis_user = QLineEdit()
        self._mantis_user.setPlaceholderText("帳號（登入用戶名稱）")
        mantis_layout.addRow("帳號：", self._mantis_user)

        self._mantis_pwd = QLineEdit()
        self._mantis_pwd.setPlaceholderText("密碼")
        self._mantis_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        mantis_layout.addRow("密碼：", self._mantis_pwd)

        mantis_btn_row = QHBoxLayout()
        test_btn = QPushButton("🔌 測試連線")
        test_btn.clicked.connect(self._on_test_mantis)
        mantis_btn_row.addWidget(test_btn)
        save_mantis_btn = QPushButton("💾 儲存 Mantis 設定")
        save_mantis_btn.clicked.connect(self._on_save_mantis)
        mantis_btn_row.addWidget(save_mantis_btn)
        mantis_btn_row.addStretch()
        mantis_layout.addRow(mantis_btn_row)

        layout.addWidget(mantis_group)

        # Save button
        save_btn = QPushButton("💾 儲存設定")
        layout.addWidget(save_btn)

        # ── 移機提醒 ──────────────────────────────────────────
        from PySide6.QtWidgets import QFrame
        notice = QFrame()
        notice.setObjectName("migrationNotice")
        notice.setStyleSheet(
            "QFrame#migrationNotice { background-color: #fef3c7; border-radius: 6px; padding: 8px; }"
        )
        notice_layout = QVBoxLayout(notice)
        notice_layout.setContentsMargins(12, 8, 12, 8)
        notice_lbl = QLabel(
            "📦 移機注意事項\n"
            "移機時請確認以下項目一併複製至新電腦：\n"
            "  • hcp_cms.db　　  — 資料庫\n"
            "  • kms_attachments/ — 知識庫圖片（與 .db 同目錄）\n"
            "缺少 kms_attachments/ 時，知識庫圖片將無法顯示。"
        )
        notice_lbl.setStyleSheet("color: #92400e; font-size: 12px;")
        notice_lbl.setWordWrap(True)
        notice_layout.addWidget(notice_lbl)
        layout.addWidget(notice)

        layout.addStretch()

    def _on_browse_db(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "選擇資料庫", "", "SQLite (*.db)")
        if path:
            self._db_path.setText(path)

    # ── Mantis 憑證 ────────────────────────────────────────────────────

    def _load_mantis_creds(self) -> None:
        """從 keyring 載入已儲存的 Mantis 設定。"""
        self._mantis_url.setText(self._creds.retrieve("mantis_url") or "")
        self._mantis_user.setText(self._creds.retrieve("mantis_user") or "")
        self._mantis_pwd.setText(self._creds.retrieve("mantis_password") or "")

    def _on_save_mantis(self) -> None:
        """將 Mantis 設定儲存至 OS keyring。"""
        url = self._mantis_url.text().strip()
        user = self._mantis_user.text().strip()
        pwd = self._mantis_pwd.text()
        if not url:
            QMessageBox.warning(self, "欄位不完整", "請填寫 Mantis URL。")
            return
        self._creds.store("mantis_url", url)
        self._creds.store("mantis_user", user)
        self._creds.store("mantis_password", pwd)
        QMessageBox.information(self, "已儲存", "Mantis 連線設定已儲存至系統憑證庫。")

    def _on_test_mantis(self) -> None:
        """測試 SOAP 連線是否成功。"""
        from hcp_cms.services.mantis.soap import MantisSoapClient
        url = self._mantis_url.text().strip()
        user = self._mantis_user.text().strip()
        pwd = self._mantis_pwd.text()
        if not url:
            QMessageBox.warning(self, "欄位不完整", "請先填寫 Mantis URL。")
            return
        try:
            client = MantisSoapClient(url, user, pwd)
            ok = client.connect()
            if ok:
                QMessageBox.information(self, "連線成功", f"✅ 成功連線至 Mantis！\n{url}")
            else:
                QMessageBox.warning(self, "連線失敗", "❌ 無法連線至 Mantis，請確認 URL 與帳密是否正確。")
        except Exception as e:
            QMessageBox.critical(self, "連線錯誤", f"❌ 發生例外：\n{e}")
