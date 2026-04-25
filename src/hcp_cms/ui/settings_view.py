"""System settings view."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import QSettings
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

from hcp_cms.core.case_merger import CaseMerger
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
        self._merge_duplicates_btn = QPushButton("🔧 整合重複案件")
        self._merge_duplicates_btn.clicked.connect(self._on_merge_duplicates)
        self._clear_all_cases_btn = QPushButton("🗑️ 清除所有案件")
        self._clear_all_cases_btn.clicked.connect(self._on_clear_all_cases)
        btn_layout.addWidget(self._backup_now_btn)
        btn_layout.addWidget(self._restore_btn)
        btn_layout.addWidget(self._export_btn)
        btn_layout.addWidget(self._import_btn)
        btn_layout.addWidget(self._migrate_btn)
        btn_layout.addWidget(self._merge_duplicates_btn)
        btn_layout.addWidget(self._clear_all_cases_btn)
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
            "⚠ 請只填基本網址，例如：https://118.163.30.33/mantis/\n   不要包含 login_page.php 或 view.php 等頁面路徑"
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

        self._mail_stack.addWidget(imap_widget)  # index 0

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

        self._mail_stack.addWidget(exch_widget)  # index 1

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

        # ── AI 設定 ────────────────────────────────────────────
        ai_group = QGroupBox("🤖 AI 設定（Claude）")
        ai_form = QFormLayout(ai_group)
        ai_form.setContentsMargins(12, 12, 12, 12)
        ai_form.setSpacing(8)

        self._claude_key = QLineEdit()
        self._claude_key.setPlaceholderText("sk-ant-api03-…")
        self._claude_key.setEchoMode(QLineEdit.EchoMode.Password)
        ai_form.addRow("Anthropic API Key：", self._claude_key)

        ai_hint = QLabel("用於 Patch 補充說明自動分析。可至 console.anthropic.com 申請 API Key。")
        ai_hint.setWordWrap(True)
        ai_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        ai_form.addRow("", ai_hint)

        ai_btn_row = QHBoxLayout()
        ai_save_btn = QPushButton("💾 儲存 API Key")
        ai_save_btn.clicked.connect(self._on_save_claude)
        ai_btn_row.addWidget(ai_save_btn)
        ai_btn_row.addStretch()
        ai_form.addRow("", ai_btn_row)

        layout.addWidget(ai_group)
        self._load_claude_creds()

        # ── Google Sheets 同步設定 ─────────────────────────────────────────
        google_group = QGroupBox("Google Sheets 同步")
        google_form = QFormLayout(google_group)
        google_form.setContentsMargins(12, 12, 12, 12)
        google_form.setSpacing(8)

        self._google_url_edit = QLineEdit()
        self._google_url_edit.setObjectName("googleSheetUrlEdit")
        self._google_url_edit.setPlaceholderText("https://docs.google.com/spreadsheets/d/.../edit")
        google_form.addRow("Sheet URL：", self._google_url_edit)

        self._client_secret_edit = QLineEdit()
        self._client_secret_edit.setObjectName("googleClientSecretEdit")
        self._client_secret_edit.setPlaceholderText("client_secret.json 路徑")

        self._browse_btn = QPushButton("瀏覽…")
        self._browse_btn.setObjectName("googleBrowseClientSecretBtn")
        self._browse_btn.clicked.connect(self._on_browse_client_secret)

        client_row = QHBoxLayout()
        client_row.addWidget(self._client_secret_edit)
        client_row.addWidget(self._browse_btn)
        google_form.addRow("client_secret.json：", client_row)

        self._reauth_btn = QPushButton("重新授權 Google")
        self._reauth_btn.setObjectName("googleReauthBtn")
        self._reauth_btn.clicked.connect(self._on_reauth_google)
        google_form.addRow(self._reauth_btn)

        self._schedule_checkbox = QCheckBox("啟用排程同步")
        self._schedule_checkbox.setObjectName("googleScheduleEnabledCheckbox")
        google_form.addRow(self._schedule_checkbox)

        self._schedule_interval = QComboBox()
        self._schedule_interval.setObjectName("googleScheduleIntervalCombo")
        self._schedule_interval.addItems(["每日 00:00", "每週一 00:00"])
        google_form.addRow("排程頻率：", self._schedule_interval)

        google_save_row = QHBoxLayout()
        google_save_btn = QPushButton("💾 儲存 Google 設定")
        google_save_btn.clicked.connect(self._on_save_google)
        google_save_row.addWidget(google_save_btn)
        google_save_row.addStretch()
        google_form.addRow(google_save_row)

        layout.addWidget(google_group)
        self._load_google_settings()

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

    def _on_merge_duplicates(self) -> None:
        """整合資料庫中所有重複案件（相同公司 + 相同主旨）。"""
        if not self._conn:
            QMessageBox.warning(self, "整合重複案件", "資料庫未連線。")
            return
        try:
            deleted = CaseMerger(self._conn).merge_all_duplicates()
            if deleted == 0:
                QMessageBox.information(self, "整合重複案件", "目前無重複案件。")
            else:
                QMessageBox.information(self, "整合重複案件", f"已整合 {deleted} 個重複案件。")
        except Exception as e:
            QMessageBox.critical(self, "整合重複案件", f"整合失敗：{e}")

    def _on_clear_all_cases(self) -> None:
        """清除資料庫中所有案件、對話記錄及已處理信件紀錄，以便重新收信建案。"""
        if not self._conn:
            QMessageBox.warning(self, "清除所有案件", "資料庫未連線。")
            return
        reply = QMessageBox.warning(
            self,
            "清除所有案件",
            "此操作將刪除所有案件、對話記錄，並重置已處理信件紀錄（使重新收信生效）。\n\n"
            "⚠️ 刪除後無法復原，請先確認已備份。\n確定繼續？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            from hcp_cms.core.case_manager import CaseManager
            deleted = CaseManager(self._conn).delete_all_cases()
            QMessageBox.information(self, "清除完成", f"已刪除 {deleted} 筆案件，可重新收信建案。")
        except Exception as e:
            QMessageBox.critical(self, "清除失敗", f"發生錯誤：{e}")

    # ── Claude AI 憑證 ─────────────────────────────────────────────────

    def _load_claude_creds(self) -> None:
        key = self._creds.retrieve("claude_api_key") or ""
        if key:
            self._claude_key.setText(key)

    def _on_save_claude(self) -> None:
        key = self._claude_key.text().strip()
        if not key:
            QMessageBox.warning(self, "AI 設定", "API Key 不可為空。")
            return
        self._creds.store("claude_api_key", key)
        QMessageBox.information(self, "AI 設定", "Anthropic API Key 已儲存。")

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

    # ── Google Sheets 同步設定 ────────────────────────────────────────────

    def _load_google_settings(self) -> None:
        """從 QSettings 載入 Google Sheets 同步設定。"""
        s = QSettings("HCP", "CMS")
        self._google_url_edit.setText(s.value("google/sheet_url", "", type=str))
        self._client_secret_edit.setText(s.value("google/client_secret_path", "", type=str))
        self._schedule_checkbox.setChecked(s.value("google/schedule_enabled", False, type=bool))
        interval = s.value("google/schedule_interval", "每日 00:00", type=str)
        idx = self._schedule_interval.findText(interval)
        if idx >= 0:
            self._schedule_interval.setCurrentIndex(idx)

    def _on_save_google(self) -> None:
        """將 Google Sheets 同步設定儲存至 QSettings。"""
        s = QSettings("HCP", "CMS")
        s.setValue("google/sheet_url", self._google_url_edit.text().strip())
        s.setValue("google/client_secret_path", self._client_secret_edit.text().strip())
        s.setValue("google/schedule_enabled", self._schedule_checkbox.isChecked())
        s.setValue("google/schedule_interval", self._schedule_interval.currentText())
        QMessageBox.information(self, "已儲存", "Google Sheets 同步設定已儲存。")

    def _on_browse_client_secret(self) -> None:
        """開啟檔案選擇器，讓使用者選擇 client_secret.json。"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "選擇 client_secret.json",
            "",
            "JSON 檔 (*.json);;所有檔案 (*)",
        )
        if path:
            self._client_secret_edit.setText(path)

    def _on_reauth_google(self) -> None:
        """強制重新進行 Google OAuth 授權流程。"""
        from pathlib import Path

        from hcp_cms.services.google_sheets_service import GoogleSheetsService

        url = self._google_url_edit.text().strip()
        secret = self._client_secret_edit.text().strip()
        if not url or not secret:
            QMessageBox.warning(self, "資料不完整", "請先填寫 Sheet URL 與 client_secret.json 路徑。")
            return
        try:
            svc = GoogleSheetsService(client_secret_path=Path(secret), spreadsheet_url=url)
            svc.authenticate(force_reauth=True)
            QMessageBox.information(self, "授權成功", "Google 授權已更新。")
        except Exception as exc:
            import logging

            logging.getLogger(__name__).exception("Google 授權失敗")
            QMessageBox.critical(self, "授權失敗", str(exc))

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
            f"QPushButton[objectName='protoBtn']:checked"
            f" {{ background:{p.accent_button_hover}; color:white; font-weight:bold; }}"
            f"QPushButton[objectName='protoBtn']"
            f" {{ padding:4px 18px; border-radius:4px; }}"
        )
        self._btn_imap.setStyleSheet(proto_style)
        self._btn_exchange.setStyleSheet(proto_style)
