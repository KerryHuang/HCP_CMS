"""System settings view."""

from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.services.credential import CredentialManager
from hcp_cms.ui.theme import ColorPalette, ThemeManager


class SettingsView(QWidget):
    """System settings page."""

    def __init__(self, conn: sqlite3.Connection | None = None, theme_mgr: ThemeManager | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._theme_mgr = theme_mgr
        self._creds = CredentialManager()
        self._setup_ui()
        self._load_mantis_creds()
        self._load_mail_creds()
        if theme_mgr:
            self._apply_theme(theme_mgr.current_palette())
            theme_mgr.theme_changed.connect(self._apply_theme)

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)

        self._title = QLabel("⚙️ 系統設定")
        layout.addWidget(self._title)

        # 外觀設定
        appearance_group = QGroupBox("外觀")
        appearance_layout = QHBoxLayout(appearance_group)
        appearance_layout.addWidget(QLabel("主題模式："))

        self._theme_system = QRadioButton("跟隨系統")
        self._theme_dark = QRadioButton("深色")
        self._theme_light = QRadioButton("淺色")

        self._theme_btn_group = QButtonGroup(self)
        self._theme_btn_group.addButton(self._theme_system, 0)
        self._theme_btn_group.addButton(self._theme_dark, 1)
        self._theme_btn_group.addButton(self._theme_light, 2)

        appearance_layout.addWidget(self._theme_system)
        appearance_layout.addWidget(self._theme_dark)
        appearance_layout.addWidget(self._theme_light)
        appearance_layout.addStretch()

        # 根據當前模式設定選中狀態
        if self._theme_mgr:
            mode = self._theme_mgr.current_mode()
            if mode == "system":
                self._theme_system.setChecked(True)
            elif mode == "dark":
                self._theme_dark.setChecked(True)
            else:
                self._theme_light.setChecked(True)
        else:
            self._theme_system.setChecked(True)

        self._theme_btn_group.idClicked.connect(self._on_theme_changed)
        layout.addWidget(appearance_group)

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

        self._url_hint = QLabel(
            "⚠ 請只填基本網址，例如：https://118.163.30.33/mantis/\n"
            "   不要包含 login_page.php 或 view.php 等頁面路徑"
        )
        mantis_layout.addRow("", self._url_hint)

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

        # ── 信件連線設定 ────────────────────────────────────────────────────
        mail_group = QGroupBox("📧 信件連線設定")
        mail_outer = QVBoxLayout(mail_group)

        # 協定切換列
        proto_row = QHBoxLayout()
        self._btn_imap = QPushButton("IMAP")
        self._btn_imap.setCheckable(True)
        self._btn_imap.setChecked(True)
        self._btn_imap.setObjectName("protoBtn")
        self._btn_exchange = QPushButton("Exchange")
        self._btn_exchange.setCheckable(True)
        self._btn_exchange.setObjectName("protoBtn")
        self._btn_imap.setStyleSheet(
            "QPushButton[objectName='protoBtn']:checked { background:#1d4ed8; color:white; font-weight:bold; }"
            "QPushButton[objectName='protoBtn'] { padding:4px 18px; border-radius:4px; }"
        )
        self._btn_exchange.setStyleSheet(self._btn_imap.styleSheet())
        # 初始樣式由 _apply_theme 負責，此處 inline 樣式在 _apply_theme 呼叫時會被覆蓋
        self._btn_imap.clicked.connect(lambda: self._on_toggle_protocol("imap"))
        self._btn_exchange.clicked.connect(lambda: self._on_toggle_protocol("exchange"))
        proto_row.addWidget(self._btn_imap)
        proto_row.addWidget(self._btn_exchange)
        proto_row.addStretch()
        mail_outer.addLayout(proto_row)

        # StackedWidget — 0: IMAP, 1: Exchange
        self._mail_stack = QStackedWidget()

        # ── IMAP 頁 ──
        imap_widget = QWidget()
        imap_form = QFormLayout(imap_widget)
        self._imap_host = QLineEdit()
        self._imap_host.setPlaceholderText("imap.example.com")
        imap_form.addRow("主機：", self._imap_host)

        port_row = QHBoxLayout()
        self._imap_port = QSpinBox()
        self._imap_port.setRange(1, 65535)
        self._imap_port.setValue(993)
        self._imap_port.setFixedWidth(70)
        self._imap_ssl = QCheckBox("使用 SSL")
        self._imap_ssl.setChecked(True)
        self._imap_ssl.stateChanged.connect(self._on_ssl_toggle)
        port_row.addWidget(self._imap_port)
        port_row.addWidget(self._imap_ssl)
        port_row.addStretch()
        imap_form.addRow("Port：", port_row)

        self._imap_user = QLineEdit()
        self._imap_user.setPlaceholderText("user@example.com")
        imap_form.addRow("帳號：", self._imap_user)

        self._imap_pwd = QLineEdit()
        self._imap_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self._imap_pwd.setPlaceholderText("密碼")
        imap_form.addRow("密碼：", self._imap_pwd)

        self._mail_stack.addWidget(imap_widget)   # index 0

        # ── Exchange 頁 ──
        exch_widget = QWidget()
        exch_form = QFormLayout(exch_widget)

        self._exch_server = QLineEdit()
        self._exch_server.setPlaceholderText("mail.company.com（選填）")
        exch_form.addRow("Server：", self._exch_server)

        self._exch_server_hint = QLabel("⚠ Server 留空時使用 autodiscover 自動探索")
        exch_form.addRow("", self._exch_server_hint)

        self._exch_email = QLineEdit()
        self._exch_email.setPlaceholderText("user@company.com")
        exch_form.addRow("Email：", self._exch_email)

        self._exch_user = QLineEdit()
        self._exch_user.setPlaceholderText("DOMAIN\\user")
        exch_form.addRow("帳號：", self._exch_user)

        self._exch_pwd = QLineEdit()
        self._exch_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self._exch_pwd.setPlaceholderText("密碼")
        exch_form.addRow("密碼：", self._exch_pwd)

        self._mail_stack.addWidget(exch_widget)   # index 1

        mail_outer.addWidget(self._mail_stack)

        # 操作按鈕列
        mail_btn_row = QHBoxLayout()
        mail_test_btn = QPushButton("🔌 測試連線")
        mail_test_btn.clicked.connect(self._on_test_mail)
        mail_btn_row.addWidget(mail_test_btn)
        mail_save_btn = QPushButton("💾 儲存設定")
        mail_save_btn.clicked.connect(self._on_save_mail)
        mail_btn_row.addWidget(mail_save_btn)
        mail_btn_row.addStretch()
        mail_outer.addLayout(mail_btn_row)

        layout.addWidget(mail_group)

        # Save button
        save_btn = QPushButton("💾 儲存設定")
        layout.addWidget(save_btn)

        # ── 移機提醒 ──────────────────────────────────────────
        from PySide6.QtWidgets import QFrame
        self._notice = QFrame()
        self._notice.setObjectName("migrationNotice")
        notice_layout = QVBoxLayout(self._notice)
        notice_layout.setContentsMargins(12, 8, 12, 8)
        self._notice_lbl = QLabel(
            "📦 移機注意事項\n"
            "移機時請確認以下項目一併複製至新電腦：\n"
            "  • hcp_cms.db　　  — 資料庫\n"
            "  • kms_attachments/ — 知識庫圖片（與 .db 同目錄）\n"
            "缺少 kms_attachments/ 時，知識庫圖片將無法顯示。"
        )
        self._notice_lbl.setWordWrap(True)
        notice_layout.addWidget(self._notice_lbl)
        layout.addWidget(self._notice)

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

    # ── 信件連線設定 ─────────────────────────────────────────────────────────

    def _on_toggle_protocol(self, proto: str) -> None:
        """切換 IMAP / Exchange 頁面。"""
        is_imap = proto == "imap"
        self._btn_imap.setChecked(is_imap)
        self._btn_exchange.setChecked(not is_imap)
        self._mail_stack.setCurrentIndex(0 if is_imap else 1)

    def _on_ssl_toggle(self, state: int) -> None:
        """SSL 勾選時預設 port 993，取消時預設 143。"""
        self._imap_port.setValue(993 if state else 143)

    def _load_mail_creds(self) -> None:
        """從 keyring 載入已儲存的信件連線設定。"""
        # IMAP
        self._imap_host.setText(self._creds.retrieve("mail_imap_host") or "")
        port_val = self._creds.retrieve("mail_imap_port")
        if port_val and port_val.isdigit():
            self._imap_port.setValue(int(port_val))
        ssl_val = self._creds.retrieve("mail_imap_ssl")
        if ssl_val is not None:
            self._imap_ssl.setChecked(ssl_val.lower() == "true")
        self._imap_user.setText(self._creds.retrieve("mail_imap_user") or "")
        self._imap_pwd.setText(self._creds.retrieve("mail_imap_password") or "")
        # Exchange
        self._exch_server.setText(self._creds.retrieve("mail_exchange_server") or "")
        self._exch_email.setText(self._creds.retrieve("mail_exchange_email") or "")
        self._exch_user.setText(self._creds.retrieve("mail_exchange_user") or "")
        self._exch_pwd.setText(self._creds.retrieve("mail_exchange_password") or "")
        # 若 Exchange 有 email 設定，切換至 Exchange 頁
        if self._creds.retrieve("mail_exchange_email"):
            self._on_toggle_protocol("exchange")

    def _on_save_mail(self) -> None:
        """將目前協定的連線設定儲存至 OS keyring。"""
        is_imap = self._mail_stack.currentIndex() == 0
        if is_imap:
            host = self._imap_host.text().strip()
            if not host:
                QMessageBox.warning(self, "欄位不完整", "請填寫 IMAP 主機位址。")
                return
            self._creds.store("mail_imap_host", host)
            self._creds.store("mail_imap_port", str(self._imap_port.value()))
            self._creds.store("mail_imap_ssl", "true" if self._imap_ssl.isChecked() else "false")
            self._creds.store("mail_imap_user", self._imap_user.text().strip())
            self._creds.store("mail_imap_password", self._imap_pwd.text())
        else:
            email_addr = self._exch_email.text().strip()
            if not email_addr:
                QMessageBox.warning(self, "欄位不完整", "請填寫 Exchange Email 帳號。")
                return
            self._creds.store("mail_exchange_server", self._exch_server.text().strip())
            self._creds.store("mail_exchange_email", email_addr)
            self._creds.store("mail_exchange_user", self._exch_user.text().strip())
            self._creds.store("mail_exchange_password", self._exch_pwd.text())
        proto = "IMAP" if is_imap else "Exchange"
        QMessageBox.information(self, "已儲存", f"📧 {proto} 連線設定已儲存至系統憑證庫。")

    def _on_test_mail(self) -> None:
        """測試信件連線是否成功。"""
        is_imap = self._mail_stack.currentIndex() == 0
        try:
            if is_imap:
                from hcp_cms.services.mail.imap import IMAPProvider
                host = self._imap_host.text().strip()
                if not host:
                    QMessageBox.warning(self, "欄位不完整", "請先填寫 IMAP 主機位址。")
                    return
                provider = IMAPProvider(
                    host=host,
                    port=self._imap_port.value(),
                    use_ssl=self._imap_ssl.isChecked(),
                )
                provider.set_credentials(
                    self._imap_user.text().strip(),
                    self._imap_pwd.text(),
                )
            else:
                from hcp_cms.services.mail.exchange import ExchangeProvider
                email_addr = self._exch_email.text().strip()
                if not email_addr:
                    QMessageBox.warning(self, "欄位不完整", "請先填寫 Exchange Email 帳號。")
                    return
                provider = ExchangeProvider(
                    server=self._exch_server.text().strip(),
                    email_address=email_addr,
                )
                provider.set_credentials(
                    self._exch_user.text().strip(),
                    self._exch_pwd.text(),
                )
            ok = provider.connect()
            proto = "IMAP" if is_imap else "Exchange"
            if ok:
                provider.disconnect()
                QMessageBox.information(self, "連線成功", f"✅ 成功連線至 {proto} 信箱！")
            else:
                QMessageBox.warning(self, "連線失敗", f"❌ 無法連線至 {proto}，請確認主機與帳密是否正確。")
        except Exception as e:
            QMessageBox.critical(self, "連線錯誤", f"❌ 發生例外：\n{e}")

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

    def _on_theme_changed(self, button_id: int) -> None:
        """使用者切換主題模式。"""
        if not self._theme_mgr:
            return
        mode_map = {0: "system", 1: "dark", 2: "light"}
        mode = mode_map.get(button_id, "system")
        self._theme_mgr.set_theme(mode)

    def _apply_theme(self, p: ColorPalette) -> None:
        """套用主題色彩。"""
        self._title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p.text_primary};")
        self._url_hint.setStyleSheet(f"color: {p.text_tertiary}; font-size: 11px;")
        self._exch_server_hint.setStyleSheet(f"color: {p.text_tertiary}; font-size: 11px;")
        self._notice.setStyleSheet(
            f"QFrame#migrationNotice {{ background-color: {p.warning}22; border-radius: 6px; padding: 8px; }}"
        )
        self._notice_lbl.setStyleSheet(f"color: {p.warning}; font-size: 12px;")
        proto_style = (
            f"QPushButton[objectName='protoBtn']:checked {{ background:{p.accent_button_hover}; color:white; font-weight:bold; }}"
            f"QPushButton[objectName='protoBtn'] {{ padding:4px 18px; border-radius:4px; }}"
        )
        self._btn_imap.setStyleSheet(proto_style)
        self._btn_exchange.setStyleSheet(proto_style)
