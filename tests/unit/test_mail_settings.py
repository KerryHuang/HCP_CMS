"""信件連線設定 — 憑證存取單元測試。"""

from __future__ import annotations

import pytest

from hcp_cms.services.credential import CredentialManager

# ── Keyring 鍵值常數 ─────────────────────────────────────────────────────────

IMAP_KEYS = ["mail_imap_host", "mail_imap_port", "mail_imap_ssl", "mail_imap_user", "mail_imap_password"]
EXCHANGE_KEYS = ["mail_exchange_server", "mail_exchange_email", "mail_exchange_user", "mail_exchange_password"]


class TestMailCredentials:
    """CredentialManager 對信件連線設定的存取行為。"""

    @pytest.fixture(autouse=True)
    def cleanup(self, monkeypatch):
        """使用 in-memory dict 模擬 keyring，避免寫入真實 OS keychain。"""
        store: dict[str, str] = {}

        import keyring  # noqa: F401

        monkeypatch.setattr("keyring.set_password", lambda svc, key, val: store.update({key: val}))
        monkeypatch.setattr("keyring.get_password", lambda svc, key: store.get(key))
        monkeypatch.setattr("keyring.delete_password", lambda svc, key: store.pop(key, None))
        self._store = store

    def test_imap_credentials_store_and_retrieve(self):
        """IMAP 憑證可完整儲存並取回。"""
        creds = CredentialManager()
        data = {
            "mail_imap_host": "imap.example.com",
            "mail_imap_port": "993",
            "mail_imap_ssl": "true",
            "mail_imap_user": "user@example.com",
            "mail_imap_password": "secret",
        }
        for key, val in data.items():
            assert creds.store(key, val)

        for key, val in data.items():
            assert creds.retrieve(key) == val

    def test_exchange_credentials_store_and_retrieve(self):
        """Exchange 憑證可完整儲存並取回。"""
        creds = CredentialManager()
        data = {
            "mail_exchange_server": "",  # 留空 → autodiscover
            "mail_exchange_email": "hcpservice@ares.com.tw",
            "mail_exchange_user": "ARES\\hcpservice",
            "mail_exchange_password": "p@ssw0rd",
        }
        for key, val in data.items():
            assert creds.store(key, val)

        for key, val in data.items():
            assert creds.retrieve(key) == val

    def test_retrieve_missing_key_returns_none(self):
        """未設定的鍵值應返回 None，不拋異常。"""
        creds = CredentialManager()
        assert creds.retrieve("mail_imap_host") is None

    def test_store_empty_string_for_optional_field(self):
        """Exchange Server 為選填欄位，空字串也可儲存。"""
        creds = CredentialManager()
        assert creds.store("mail_exchange_server", "")
        assert creds.retrieve("mail_exchange_server") == ""

    def test_all_imap_keys_defined(self):
        """IMAP 鍵值清單完整，共 5 個。"""
        assert len(IMAP_KEYS) == 5

    def test_all_exchange_keys_defined(self):
        """Exchange 鍵值清單完整，共 4 個。"""
        assert len(EXCHANGE_KEYS) == 4
