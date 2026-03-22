"""Cross-platform credential management using keyring."""

from __future__ import annotations

SERVICE_NAME = "HCP_CMS"


class CredentialManager:
    """Store and retrieve credentials using OS keychain."""

    def store(self, key: str, value: str) -> bool:
        """Store a credential. Returns True on success."""
        try:
            import keyring
            keyring.set_password(SERVICE_NAME, key, value)
            return True
        except Exception:
            return False

    def retrieve(self, key: str) -> str | None:
        """Retrieve a credential. Returns None if not found."""
        try:
            import keyring
            return keyring.get_password(SERVICE_NAME, key)
        except Exception:
            return None

    def delete(self, key: str) -> bool:
        """Delete a credential. Returns True on success."""
        try:
            import keyring
            keyring.delete_password(SERVICE_NAME, key)
            return True
        except Exception:
            return False
