# 信件連線設定 UI 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `SettingsView` 新增「📧 信件連線設定」區塊，支援 IMAP / Exchange 協定切換，並將憑證儲存至 OS keyring。

**Architecture:** 在現有 `SettingsView` 單一檔案中新增 `_build_mail_group()` 方法與四個 slot 方法。UI 層只接觸 `CredentialManager`（儲存/讀取）和 `IMAPProvider` / `ExchangeProvider`（測試連線）。兩組設定各自儲存，切換時不清空。

**Tech Stack:** PySide6 6.10.2、keyring（透過 CredentialManager）、hcp_cms.services.mail.imap、hcp_cms.services.mail.exchange

---

## 檔案異動

| 動作 | 路徑 |
|------|------|
| 修改 | `src/hcp_cms/ui/settings_view.py` |
| 修改 | `tests/unit/test_ui.py` |

---

## Task 1：UI 結構 — 建立信件設定 GroupBox

### Files:
- Modify: `src/hcp_cms/ui/settings_view.py`
- Test: `tests/unit/test_ui.py`

- [ ] **Step 1：撰寫失敗測試（widget 屬性存在性）**

在 `tests/unit/test_ui.py` 的 `TestOtherViews` class 末尾加入：

```python
class TestSettingsViewMail:
    def test_mail_group_widgets_exist(self, qapp):
        from hcp_cms.ui.settings_view import SettingsView

        view = SettingsView()
        assert hasattr(view, "_mail_imap_btn")
        assert hasattr(view, "_mail_exchange_btn")
        assert hasattr(view, "_mail_imap_widget")
        assert hasattr(view, "_mail_exchange_widget")

    def test_imap_fields_exist(self, qapp):
        from hcp_cms.ui.settings_view import SettingsView

        view = SettingsView()
        assert hasattr(view, "_mail_imap_host")
        assert hasattr(view, "_mail_imap_port")
        assert hasattr(view, "_mail_imap_ssl")
        assert hasattr(view, "_mail_imap_user")
        assert hasattr(view, "_mail_imap_pwd")

    def test_exchange_fields_exist(self, qapp):
        from hcp_cms.ui.settings_view import SettingsView

        view = SettingsView()
        assert hasattr(view, "_mail_exchange_server")
        assert hasattr(view, "_mail_exchange_email")
        assert hasattr(view, "_mail_exchange_user")
        assert hasattr(view, "_mail_exchange_pwd")

    def test_imap_visible_by_default(self, qapp):
        from hcp_cms.ui.settings_view import SettingsView

        view = SettingsView()
        assert view._mail_imap_widget.isVisible()
        assert not view._mail_exchange_widget.isVisible()
```

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_ui.py::TestSettingsViewMail -v
```

預期：`FAILED — AttributeError: 'SettingsView' object has no attribute '_mail_imap_btn'`

- [ ] **Step 3：在 settings_view.py 新增 QCheckBox import**

在現有 import 區塊，將 `QComboBox` 前加入 `QCheckBox`：

```python
from PySide6.QtWidgets import (
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
```

- [ ] **Step 4：新增 `_build_mail_group()` 方法**

在 `SettingsView` class 中 `_on_browse_db` 方法之前加入：

```python
def _build_mail_group(self) -> QGroupBox:
    """Build the mail connection settings group."""
    mail_group = QGroupBox("📧 信件連線設定")
    mail_layout = QVBoxLayout(mail_group)

    # Protocol toggle buttons
    toggle_row = QHBoxLayout()
    self._mail_imap_btn = QPushButton("IMAP")
    self._mail_imap_btn.setCheckable(True)
    self._mail_imap_btn.setChecked(True)
    self._mail_exchange_btn = QPushButton("Exchange")
    self._mail_exchange_btn.setCheckable(True)
    toggle_row.addWidget(self._mail_imap_btn)
    toggle_row.addWidget(self._mail_exchange_btn)
    toggle_row.addStretch()
    mail_layout.addLayout(toggle_row)

    # IMAP fields
    self._mail_imap_widget = QWidget()
    imap_form = QFormLayout(self._mail_imap_widget)
    self._mail_imap_host = QLineEdit()
    self._mail_imap_host.setPlaceholderText("imap.example.com")
    imap_form.addRow("主機：", self._mail_imap_host)
    port_row = QHBoxLayout()
    self._mail_imap_port = QSpinBox()
    self._mail_imap_port.setRange(1, 65535)
    self._mail_imap_port.setValue(993)
    port_row.addWidget(self._mail_imap_port)
    self._mail_imap_ssl = QCheckBox("使用 SSL")
    self._mail_imap_ssl.setChecked(True)
    port_row.addWidget(self._mail_imap_ssl)
    port_row.addStretch()
    imap_form.addRow("Port：", port_row)
    self._mail_imap_user = QLineEdit()
    self._mail_imap_user.setPlaceholderText("user@example.com")
    imap_form.addRow("帳號：", self._mail_imap_user)
    self._mail_imap_pwd = QLineEdit()
    self._mail_imap_pwd.setPlaceholderText("密碼")
    self._mail_imap_pwd.setEchoMode(QLineEdit.EchoMode.Password)
    imap_form.addRow("密碼：", self._mail_imap_pwd)
    mail_layout.addWidget(self._mail_imap_widget)

    # Exchange fields
    self._mail_exchange_widget = QWidget()
    exchange_form = QFormLayout(self._mail_exchange_widget)
    self._mail_exchange_server = QLineEdit()
    self._mail_exchange_server.setPlaceholderText("mail.company.com（選填，留空用 autodiscover）")
    exchange_form.addRow("Server：", self._mail_exchange_server)
    self._mail_exchange_email = QLineEdit()
    self._mail_exchange_email.setPlaceholderText("user@company.com")
    exchange_form.addRow("Email：", self._mail_exchange_email)
    self._mail_exchange_user = QLineEdit()
    self._mail_exchange_user.setPlaceholderText("DOMAIN\\user")
    exchange_form.addRow("帳號：", self._mail_exchange_user)
    self._mail_exchange_pwd = QLineEdit()
    self._mail_exchange_pwd.setPlaceholderText("密碼")
    self._mail_exchange_pwd.setEchoMode(QLineEdit.EchoMode.Password)
    exchange_form.addRow("密碼：", self._mail_exchange_pwd)
    self._mail_exchange_widget.setVisible(False)
    mail_layout.addWidget(self._mail_exchange_widget)

    # Action buttons
    btn_row = QHBoxLayout()
    test_btn = QPushButton("🔌 測試連線")
    test_btn.clicked.connect(self._on_test_mail)
    save_btn = QPushButton("💾 儲存設定")
    save_btn.clicked.connect(self._on_save_mail)
    btn_row.addWidget(test_btn)
    btn_row.addWidget(save_btn)
    btn_row.addStretch()
    mail_layout.addLayout(btn_row)

    # Connect toggle buttons
    self._mail_imap_btn.clicked.connect(lambda: self._on_mail_protocol_switch("imap"))
    self._mail_exchange_btn.clicked.connect(lambda: self._on_mail_protocol_switch("exchange"))

    return mail_group
```

- [ ] **Step 5：在 `_setup_ui()` 中插入 mail group（Mantis group 之後、Save button 之前）**

找到 `_setup_ui()` 中 `layout.addWidget(mantis_group)` 這行，在其後插入：

```python
        layout.addWidget(mantis_group)

        # Mail connection settings
        layout.addWidget(self._build_mail_group())
```

- [ ] **Step 6：新增暫時佔位 slot（讓 `_build_mail_group` 內的 connect 不報錯）**

在 `_on_browse_db` 之前加入以下三個空 slot，後續 Task 會填充：

```python
    def _on_mail_protocol_switch(self, protocol: str) -> None:
        pass

    def _on_save_mail(self) -> None:
        pass

    def _on_test_mail(self) -> None:
        pass
```

- [ ] **Step 7：執行測試確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_ui.py::TestSettingsViewMail -v
```

預期：4 個測試全部 `PASSED`

- [ ] **Step 8：Commit**

```bash
git add src/hcp_cms/ui/settings_view.py tests/unit/test_ui.py
git commit -m "feat(ui): 新增信件連線設定 GroupBox 結構（IMAP/Exchange 切換）"
```

---

## Task 2：協定切換邏輯

### Files:
- Modify: `src/hcp_cms/ui/settings_view.py`
- Test: `tests/unit/test_ui.py`

- [ ] **Step 1：撰寫失敗測試**

在 `TestSettingsViewMail` class 末尾加入：

```python
    def test_switch_to_exchange_hides_imap(self, qapp):
        from hcp_cms.ui.settings_view import SettingsView

        view = SettingsView()
        view._on_mail_protocol_switch("exchange")
        assert not view._mail_imap_widget.isVisible()
        assert view._mail_exchange_widget.isVisible()
        assert view._mail_exchange_btn.isChecked()
        assert not view._mail_imap_btn.isChecked()

    def test_switch_back_to_imap(self, qapp):
        from hcp_cms.ui.settings_view import SettingsView

        view = SettingsView()
        view._on_mail_protocol_switch("exchange")
        view._on_mail_protocol_switch("imap")
        assert view._mail_imap_widget.isVisible()
        assert not view._mail_exchange_widget.isVisible()
        assert view._mail_imap_btn.isChecked()
        assert not view._mail_exchange_btn.isChecked()
```

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_ui.py::TestSettingsViewMail::test_switch_to_exchange_hides_imap tests/unit/test_ui.py::TestSettingsViewMail::test_switch_back_to_imap -v
```

預期：`FAILED` — 因為目前 `_on_mail_protocol_switch` 是空 slot

- [ ] **Step 3：實作 `_on_mail_protocol_switch`**

將 `settings_view.py` 中的空 `_on_mail_protocol_switch` 替換為：

```python
    def _on_mail_protocol_switch(self, protocol: str) -> None:
        """Switch between IMAP and Exchange fields."""
        is_imap = protocol == "imap"
        self._mail_imap_widget.setVisible(is_imap)
        self._mail_exchange_widget.setVisible(not is_imap)
        self._mail_imap_btn.setChecked(is_imap)
        self._mail_exchange_btn.setChecked(not is_imap)
        self._load_mail_creds(protocol)
        self._creds.store("mail_active_protocol", protocol)
```

注意：`_load_mail_creds` 在 Task 3 實作；目前先新增空方法在 `_on_mail_protocol_switch` 下方：

```python
    def _load_mail_creds(self, protocol: str) -> None:
        pass
```

- [ ] **Step 4：執行測試確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_ui.py::TestSettingsViewMail -v
```

預期：所有測試 `PASSED`

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/ui/settings_view.py tests/unit/test_ui.py
git commit -m "feat(ui): 實作信件協定切換邏輯（IMAP/Exchange toggle）"
```

---

## Task 3：憑證讀取（啟動時還原設定）

### Files:
- Modify: `src/hcp_cms/ui/settings_view.py`
- Test: `tests/unit/test_ui.py`

- [ ] **Step 1：撰寫失敗測試**

在 `TestSettingsViewMail` class 末尾加入：

```python
    def test_load_imap_creds_fills_fields(self, qapp, monkeypatch):
        from hcp_cms.ui.settings_view import SettingsView

        stored = {
            "mail_imap_host": "imap.test.com",
            "mail_imap_port": "465",
            "mail_imap_ssl": "0",
            "mail_imap_user": "testuser",
            "mail_imap_password": "secret",
        }
        view = SettingsView()
        monkeypatch.setattr(view._creds, "retrieve", lambda key: stored.get(key))
        view._load_mail_creds("imap")
        assert view._mail_imap_host.text() == "imap.test.com"
        assert view._mail_imap_port.value() == 465
        assert not view._mail_imap_ssl.isChecked()
        assert view._mail_imap_user.text() == "testuser"
        assert view._mail_imap_pwd.text() == "secret"

    def test_load_exchange_creds_fills_fields(self, qapp, monkeypatch):
        from hcp_cms.ui.settings_view import SettingsView

        stored = {
            "mail_exchange_server": "mail.corp.com",
            "mail_exchange_email": "a@corp.com",
            "mail_exchange_user": "CORP\\a",
            "mail_exchange_password": "pass123",
        }
        view = SettingsView()
        monkeypatch.setattr(view._creds, "retrieve", lambda key: stored.get(key))
        view._load_mail_creds("exchange")
        assert view._mail_exchange_server.text() == "mail.corp.com"
        assert view._mail_exchange_email.text() == "a@corp.com"
        assert view._mail_exchange_user.text() == "CORP\\a"
        assert view._mail_exchange_pwd.text() == "pass123"

    def test_startup_restores_active_protocol_exchange(self, qapp, monkeypatch):
        from hcp_cms.ui.settings_view import SettingsView

        stored = {"mail_active_protocol": "exchange"}
        view = SettingsView()
        monkeypatch.setattr(view._creds, "retrieve", lambda key: stored.get(key))
        view._load_mail_settings()
        assert view._mail_exchange_widget.isVisible()
        assert not view._mail_imap_widget.isVisible()
```

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_ui.py::TestSettingsViewMail::test_load_imap_creds_fills_fields tests/unit/test_ui.py::TestSettingsViewMail::test_load_exchange_creds_fills_fields tests/unit/test_ui.py::TestSettingsViewMail::test_startup_restores_active_protocol_exchange -v
```

預期：`FAILED` — `_load_mail_creds` 是空方法，`_load_mail_settings` 不存在

- [ ] **Step 3：實作 `_load_mail_creds`**

將空的 `_load_mail_creds` 替換為：

```python
    def _load_mail_creds(self, protocol: str) -> None:
        """Load credentials for the specified protocol from keyring."""
        if protocol == "imap":
            self._mail_imap_host.setText(self._creds.retrieve("mail_imap_host") or "")
            port_val = self._creds.retrieve("mail_imap_port") or "993"
            self._mail_imap_port.setValue(int(port_val) if port_val.isdigit() else 993)
            ssl_val = self._creds.retrieve("mail_imap_ssl") or "1"
            self._mail_imap_ssl.setChecked(ssl_val == "1")
            self._mail_imap_user.setText(self._creds.retrieve("mail_imap_user") or "")
            self._mail_imap_pwd.setText(self._creds.retrieve("mail_imap_password") or "")
        else:
            self._mail_exchange_server.setText(self._creds.retrieve("mail_exchange_server") or "")
            self._mail_exchange_email.setText(self._creds.retrieve("mail_exchange_email") or "")
            self._mail_exchange_user.setText(self._creds.retrieve("mail_exchange_user") or "")
            self._mail_exchange_pwd.setText(self._creds.retrieve("mail_exchange_password") or "")
```

- [ ] **Step 4：新增 `_load_mail_settings` 方法**

在 `_load_mail_creds` 下方加入：

```python
    def _load_mail_settings(self) -> None:
        """Restore active protocol and load its credentials on startup."""
        protocol = self._creds.retrieve("mail_active_protocol") or "imap"
        self._on_mail_protocol_switch(protocol)
```

- [ ] **Step 5：在 `__init__` 中呼叫 `_load_mail_settings`**

找到 `__init__` 中 `self._load_mantis_creds()` 這行，在其後加入：

```python
        self._load_mantis_creds()
        self._load_mail_settings()
```

- [ ] **Step 6：執行測試確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_ui.py::TestSettingsViewMail -v
```

預期：所有測試 `PASSED`

- [ ] **Step 7：Commit**

```bash
git add src/hcp_cms/ui/settings_view.py tests/unit/test_ui.py
git commit -m "feat(ui): 實作信件憑證讀取與啟動還原協定狀態"
```

---

## Task 4：儲存憑證

### Files:
- Modify: `src/hcp_cms/ui/settings_view.py`
- Test: `tests/unit/test_ui.py`

- [ ] **Step 1：撰寫失敗測試**

在 `TestSettingsViewMail` class 末尾加入：

```python
    def test_save_imap_stores_correct_keys(self, qapp, monkeypatch):
        from hcp_cms.ui.settings_view import SettingsView

        view = SettingsView()
        view._mail_imap_host.setText("imap.mymail.com")
        view._mail_imap_port.setValue(993)
        view._mail_imap_ssl.setChecked(True)
        view._mail_imap_user.setText("myuser")
        view._mail_imap_pwd.setText("mypass")

        stored = {}
        monkeypatch.setattr(view._creds, "store", lambda k, v: stored.update({k: v}))
        monkeypatch.setattr(
            "hcp_cms.ui.settings_view.QMessageBox.information",
            lambda *a: None,
        )
        view._on_save_mail()

        assert stored["mail_imap_host"] == "imap.mymail.com"
        assert stored["mail_imap_port"] == "993"
        assert stored["mail_imap_ssl"] == "1"
        assert stored["mail_imap_user"] == "myuser"
        assert stored["mail_imap_password"] == "mypass"

    def test_save_exchange_stores_correct_keys(self, qapp, monkeypatch):
        from hcp_cms.ui.settings_view import SettingsView

        view = SettingsView()
        view._on_mail_protocol_switch("exchange")
        view._mail_exchange_server.setText("mail.corp.com")
        view._mail_exchange_email.setText("u@corp.com")
        view._mail_exchange_user.setText("CORP\\u")
        view._mail_exchange_pwd.setText("p@ss")

        stored = {}
        monkeypatch.setattr(view._creds, "store", lambda k, v: stored.update({k: v}))
        monkeypatch.setattr(
            "hcp_cms.ui.settings_view.QMessageBox.information",
            lambda *a: None,
        )
        view._on_save_mail()

        assert stored["mail_exchange_server"] == "mail.corp.com"
        assert stored["mail_exchange_email"] == "u@corp.com"
        assert stored["mail_exchange_user"] == "CORP\\u"
        assert stored["mail_exchange_password"] == "p@ss"

    def test_save_imap_warns_if_host_empty(self, qapp, monkeypatch):
        from hcp_cms.ui.settings_view import SettingsView

        view = SettingsView()
        view._mail_imap_host.setText("")
        warned = []
        monkeypatch.setattr(
            "hcp_cms.ui.settings_view.QMessageBox.warning",
            lambda *a: warned.append(True),
        )
        view._on_save_mail()
        assert warned
```

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_ui.py::TestSettingsViewMail::test_save_imap_stores_correct_keys tests/unit/test_ui.py::TestSettingsViewMail::test_save_exchange_stores_correct_keys tests/unit/test_ui.py::TestSettingsViewMail::test_save_imap_warns_if_host_empty -v
```

預期：`FAILED` — `_on_save_mail` 是空方法

- [ ] **Step 3：實作 `_on_save_mail`**

將空的 `_on_save_mail` 替換為：

```python
    def _on_save_mail(self) -> None:
        """Save current protocol's credentials to keyring."""
        if self._mail_imap_btn.isChecked():
            host = self._mail_imap_host.text().strip()
            if not host:
                QMessageBox.warning(self, "欄位不完整", "請填寫主機位址。")
                return
            self._creds.store("mail_imap_host", host)
            self._creds.store("mail_imap_port", str(self._mail_imap_port.value()))
            self._creds.store("mail_imap_ssl", "1" if self._mail_imap_ssl.isChecked() else "0")
            self._creds.store("mail_imap_user", self._mail_imap_user.text().strip())
            self._creds.store("mail_imap_password", self._mail_imap_pwd.text())
        else:
            email = self._mail_exchange_email.text().strip()
            if not email:
                QMessageBox.warning(self, "欄位不完整", "請填寫 Email 位址。")
                return
            self._creds.store("mail_exchange_server", self._mail_exchange_server.text().strip())
            self._creds.store("mail_exchange_email", email)
            self._creds.store("mail_exchange_user", self._mail_exchange_user.text().strip())
            self._creds.store("mail_exchange_password", self._mail_exchange_pwd.text())
        QMessageBox.information(self, "已儲存", "信件連線設定已儲存至系統憑證庫。")
```

- [ ] **Step 4：執行測試確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_ui.py::TestSettingsViewMail -v
```

預期：所有測試 `PASSED`

- [ ] **Step 5：Commit**

```bash
git add src/hcp_cms/ui/settings_view.py tests/unit/test_ui.py
git commit -m "feat(ui): 實作信件憑證儲存至 OS keyring"
```

---

## Task 5：測試連線

### Files:
- Modify: `src/hcp_cms/ui/settings_view.py`
- Test: `tests/unit/test_ui.py`

- [ ] **Step 1：撰寫失敗測試**

在 `TestSettingsViewMail` class 末尾加入：

```python
    def test_test_mail_imap_success(self, qapp, monkeypatch):
        from hcp_cms.ui.settings_view import SettingsView

        view = SettingsView()
        view._mail_imap_host.setText("imap.test.com")
        view._mail_imap_user.setText("u")
        view._mail_imap_pwd.setText("p")

        import hcp_cms.services.mail.imap as imap_mod
        class FakeProvider:
            def set_credentials(self, u, p): pass
            def connect(self): return True
            def disconnect(self): pass
        monkeypatch.setattr(imap_mod, "IMAPProvider", lambda **kw: FakeProvider())
        shown = []
        monkeypatch.setattr(
            "hcp_cms.ui.settings_view.QMessageBox.information",
            lambda *a: shown.append(a[2]),
        )
        view._on_test_mail()
        assert any("成功" in s for s in shown)

    def test_test_mail_imap_failure(self, qapp, monkeypatch):
        from hcp_cms.ui.settings_view import SettingsView

        view = SettingsView()
        view._mail_imap_host.setText("imap.test.com")

        import hcp_cms.services.mail.imap as imap_mod
        class FakeProvider:
            def set_credentials(self, u, p): pass
            def connect(self): return False
        monkeypatch.setattr(imap_mod, "IMAPProvider", lambda **kw: FakeProvider())
        warned = []
        monkeypatch.setattr(
            "hcp_cms.ui.settings_view.QMessageBox.warning",
            lambda *a: warned.append(a[2]),
        )
        view._on_test_mail()
        assert any("失敗" in w for w in warned)

    def test_test_mail_imap_warns_if_host_empty(self, qapp, monkeypatch):
        from hcp_cms.ui.settings_view import SettingsView

        view = SettingsView()
        view._mail_imap_host.setText("")
        warned = []
        monkeypatch.setattr(
            "hcp_cms.ui.settings_view.QMessageBox.warning",
            lambda *a: warned.append(True),
        )
        view._on_test_mail()
        assert warned
```

- [ ] **Step 2：確認測試失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_ui.py::TestSettingsViewMail::test_test_mail_imap_success tests/unit/test_ui.py::TestSettingsViewMail::test_test_mail_imap_failure tests/unit/test_ui.py::TestSettingsViewMail::test_test_mail_imap_warns_if_host_empty -v
```

預期：`FAILED` — `_on_test_mail` 是空方法

- [ ] **Step 3：實作 `_on_test_mail`**

將空的 `_on_test_mail` 替換為：

```python
    def _on_test_mail(self) -> None:
        """Test mail connection with current fields."""
        if self._mail_imap_btn.isChecked():
            host = self._mail_imap_host.text().strip()
            if not host:
                QMessageBox.warning(self, "欄位不完整", "請填寫主機位址。")
                return
            from hcp_cms.services.mail.imap import IMAPProvider
            provider = IMAPProvider(
                host=host,
                port=self._mail_imap_port.value(),
                use_ssl=self._mail_imap_ssl.isChecked(),
            )
            provider.set_credentials(
                self._mail_imap_user.text().strip(),
                self._mail_imap_pwd.text(),
            )
        else:
            email = self._mail_exchange_email.text().strip()
            if not email:
                QMessageBox.warning(self, "欄位不完整", "請填寫 Email 位址。")
                return
            from hcp_cms.services.mail.exchange import ExchangeProvider
            provider = ExchangeProvider(
                server=self._mail_exchange_server.text().strip(),
                email_address=email,
            )
            provider.set_credentials(
                self._mail_exchange_user.text().strip(),
                self._mail_exchange_pwd.text(),
            )
        ok = provider.connect()
        if ok:
            provider.disconnect()
            QMessageBox.information(self, "連線成功", "✅ 信件伺服器連線成功！")
        else:
            QMessageBox.warning(self, "連線失敗", "❌ 無法連線至信件伺服器，請確認設定是否正確。")
```

- [ ] **Step 4：執行全部信件設定測試確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_ui.py::TestSettingsViewMail -v
```

預期：所有測試 `PASSED`

- [ ] **Step 5：執行完整測試套件確認無回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v
```

預期：所有測試 `PASSED`

- [ ] **Step 6：Lint 檢查**

```bash
.venv/Scripts/ruff.exe check src/hcp_cms/ui/settings_view.py tests/unit/test_ui.py
```

預期：無錯誤

- [ ] **Step 7：Commit**

```bash
git add src/hcp_cms/ui/settings_view.py tests/unit/test_ui.py
git commit -m "feat(ui): 實作信件連線測試功能（IMAP/Exchange）"
```
