"""IMAP mail provider."""

from __future__ import annotations

import email
import imaplib
from datetime import datetime
from email.header import decode_header

from hcp_cms.services.mail.base import MailProvider, RawEmail


class IMAPProvider(MailProvider):
    """IMAP mail connection."""

    def __init__(self, host: str, port: int = 993, use_ssl: bool = True) -> None:
        self._host = host
        self._port = port
        self._use_ssl = use_ssl
        self._username: str = ""
        self._password: str = ""
        self._conn: imaplib.IMAP4_SSL | imaplib.IMAP4 | None = None

    def set_credentials(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

    def connect(self) -> bool:
        try:
            if self._use_ssl:
                self._conn = imaplib.IMAP4_SSL(self._host, self._port)
            else:
                self._conn = imaplib.IMAP4(self._host, self._port)
            self._conn.login(self._username, self._password)
            return True
        except Exception:
            self._conn = None
            return False

    def disconnect(self) -> None:
        if self._conn:
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

    def fetch_messages(
        self, since: datetime | None = None, until: datetime | None = None, folder: str = "INBOX"
    ) -> list[RawEmail]:
        if not self._conn:
            return []
        try:
            self._conn.select(folder)
            criteria = "ALL"
            if since:
                criteria = f'(SINCE "{since.strftime("%d-%b-%Y")}")'
            if until:
                criteria = f'(SINCE "{since.strftime("%d-%b-%Y")}" BEFORE "{until.strftime("%d-%b-%Y")}")'

            _, msg_nums = self._conn.search(None, criteria)
            results = []
            for num in msg_nums[0].split():
                _, data = self._conn.fetch(num, "(RFC822)")
                if data[0] is None:
                    continue
                msg = email.message_from_bytes(data[0][1])
                results.append(self._parse_email(msg))
            return results
        except Exception:
            return []

    def fetch_sent_messages(self, since: datetime | None = None) -> list[RawEmail]:
        # Try common sent folder names
        for folder in ('"[Gmail]/Sent Mail"', "Sent", "INBOX.Sent", '"Sent Items"'):
            try:
                return self.fetch_messages(since=since, folder=folder)
            except Exception:
                continue
        return []

    def create_draft(
        self, to: list[str], subject: str, body: str, attachments: list[str] | None = None
    ) -> bool:
        if not self._conn:
            return False
        try:
            msg = email.message.EmailMessage()
            msg["To"] = ", ".join(to)
            msg["Subject"] = subject
            msg.set_content(body)

            # Try common draft folder names
            for folder in ('"[Gmail]/Drafts"', "Drafts", "INBOX.Drafts", '"Draft"'):
                try:
                    self._conn.append(folder, "\\Draft", None, msg.as_bytes())
                    return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    @staticmethod
    def _parse_email(msg: email.message.Message) -> RawEmail:
        subject = ""
        raw_subject = msg.get("Subject", "")
        if raw_subject:
            decoded = decode_header(raw_subject)
            subject = "".join(
                part.decode(enc or "utf-8") if isinstance(part, bytes) else part
                for part, enc in decoded
            )

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")

        return RawEmail(
            sender=msg.get("From", ""),
            subject=subject,
            body=body,
            date=msg.get("Date"),
            message_id=msg.get("Message-ID"),
            in_reply_to=msg.get("In-Reply-To"),
            references=msg.get("References"),
        )
