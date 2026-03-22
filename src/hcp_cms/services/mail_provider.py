"""MailProvider 抽象介面"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class MailMessage:
    """統一信件資料結構"""

    message_id: str
    subject: str
    sender: str
    recipients: list[str]
    body: str
    html_body: str
    date: datetime
    attachments: list[str]
    in_reply_to: str | None = None
    references: list[str] | None = None


class MailProvider(ABC):
    """信件服務抽象介面 — IMAP/Exchange/MSG 實作此介面"""

    @abstractmethod
    def connect(self) -> None:
        """建立連線"""

    @abstractmethod
    def disconnect(self) -> None:
        """斷開連線"""

    @abstractmethod
    def fetch_inbox(self, since: datetime | None = None) -> list[MailMessage]:
        """取得收件匣信件"""

    @abstractmethod
    def fetch_sent(self, since: datetime | None = None) -> list[MailMessage]:
        """取得已寄送信件（回覆偵測用）"""

    @abstractmethod
    def create_draft(self, to: list[str], subject: str, body: str) -> None:
        """建立郵件草稿"""
