"""Mail provider abstract interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawEmail:
    """Parsed email data from any source."""
    sender: str = ""
    subject: str = ""
    body: str = ""
    date: str | None = None
    message_id: str | None = None
    in_reply_to: str | None = None
    references: str | None = None
    attachments: list[str] = field(default_factory=list)
    source_file: str | None = None  # .msg filename if from file


class MailProvider(ABC):
    """Abstract mail provider interface."""

    @abstractmethod
    def connect(self) -> bool:
        """Connect to mail server. Returns True on success."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from mail server."""
        ...

    @abstractmethod
    def fetch_messages(
        self, since: datetime | None = None, until: datetime | None = None, folder: str = "INBOX"
    ) -> list[RawEmail]:
        """Fetch messages in date range from specified folder."""
        ...

    @abstractmethod
    def fetch_sent_messages(self, since: datetime | None = None) -> list[RawEmail]:
        """Fetch sent messages for reply detection."""
        ...

    @abstractmethod
    def create_draft(
        self, to: list[str], subject: str, body: str, attachments: list[str] | None = None
    ) -> bool:
        """Create email draft. Returns True on success."""
        ...
