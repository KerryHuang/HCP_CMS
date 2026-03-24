"""Read .msg files from local filesystem using extract-msg."""

from __future__ import annotations

import hashlib
from datetime import datetime
from email.utils import getaddresses
from pathlib import Path

from hcp_cms.services.mail.base import MailProvider, RawEmail


class MSGReader(MailProvider):
    """Reads .msg files from a directory. Not a server connection."""

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory
        self._files: list[Path] = []

    def connect(self) -> bool:
        """Scan directory for .msg files."""
        if self._directory and self._directory.exists():
            self._files = sorted(self._directory.glob("*.msg"))
            return True
        return False

    def disconnect(self) -> None:
        self._files = []

    def fetch_messages(
        self, since: datetime | None = None, until: datetime | None = None, folder: str = "INBOX"
    ) -> list[RawEmail]:
        """Read all .msg files in directory."""
        results = []
        for msg_path in self._files:
            try:
                email = self._read_msg_file(msg_path)
                if email:
                    results.append(email)
            except Exception:
                continue  # Skip unreadable files
        return results

    def fetch_sent_messages(self, since: datetime | None = None) -> list[RawEmail]:
        """Not applicable for file-based reader."""
        return []

    def create_draft(self, to: list[str], subject: str, body: str, attachments: list[str] | None = None) -> bool:
        """Not applicable for file-based reader."""
        return False

    def read_single_file(self, file_path: Path) -> RawEmail | None:
        """Read a single .msg file."""
        return self._read_msg_file(file_path)

    def compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def _read_msg_file(file_path: Path) -> RawEmail | None:
        """Parse a .msg file using extract-msg."""
        try:
            import extract_msg

            msg = extract_msg.Message(file_path)

            # 解析收件人列表：msg.to 可能是 "Name <email>; email2" 格式
            raw_to = msg.to or ""
            # getaddresses 接受 list[str]，以 "," 或 ";" 分隔均可
            normalized = raw_to.replace(";", ",")
            to_recipients = [addr for _, addr in getaddresses([normalized]) if addr]

            # 解析 HTML body（bytes → str，嘗試 UTF-8 後 fallback cp950）
            html_body: str | None = None
            raw_html = getattr(msg, "htmlBody", None)
            if raw_html:
                if isinstance(raw_html, bytes):
                    try:
                        html_body = raw_html.decode("utf-8")
                    except UnicodeDecodeError:
                        html_body = raw_html.decode("cp950", errors="replace")
                else:
                    html_body = str(raw_html)

            email = RawEmail(
                sender=msg.sender or "",
                subject=msg.subject or "",
                body=msg.body or "",
                date=msg.date or None,
                attachments=[att.longFilename or "" for att in msg.attachments] if msg.attachments else [],
                source_file=file_path.name,
                to_recipients=to_recipients,
                html_body=html_body,
            )
            msg.close()
            return email
        except Exception:
            return None
