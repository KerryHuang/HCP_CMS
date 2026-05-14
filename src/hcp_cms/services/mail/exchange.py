"""Exchange EWS mail provider."""

from __future__ import annotations

from datetime import datetime

from hcp_cms.services.mail.base import MailProvider, RawEmail


def _mailboxes_to_addresses(mboxes) -> list[str]:
    """將 exchangelib Mailbox 列表轉成 email 地址 list（不可用時返回空 list）。"""
    if not mboxes:
        return []
    result: list[str] = []
    for m in mboxes:
        try:
            addr = getattr(m, "email_address", None)
            if addr:
                result.append(str(addr))
        except Exception:
            continue
    return result


class ExchangeProvider(MailProvider):
    """Exchange Web Services mail connection via exchangelib."""

    def __init__(self, server: str = "", email_address: str = "") -> None:
        self._server = server
        self._email_address = email_address
        self._username: str = ""
        self._password: str = ""
        self._account = None  # exchangelib.Account

    def set_credentials(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

    def connect(self) -> bool:
        try:
            from exchangelib import DELEGATE, Account, Configuration, Credentials
            creds = Credentials(self._username, self._password)
            config = Configuration(server=self._server, credentials=creds) if self._server else None
            self._account = Account(
                self._email_address,
                credentials=creds,
                config=config,
                autodiscover=not bool(self._server),
                access_type=DELEGATE,
            )
            return True
        except Exception:
            self._account = None
            return False

    def disconnect(self) -> None:
        self._account = None

    def fetch_messages(
        self, since: datetime | None = None, until: datetime | None = None, folder: str = "INBOX"
    ) -> list[RawEmail]:
        if not self._account:
            return []
        try:
            inbox = self._account.inbox
            qs = inbox.all()
            if since:
                from exchangelib import EWSDateTime, EWSTimeZone
                tz = EWSTimeZone.localzone()
                qs = qs.filter(datetime_received__gte=EWSDateTime.from_datetime(since.replace(tzinfo=tz)))

            results = []
            for item in qs.order_by("-datetime_received")[:100]:
                results.append(RawEmail(
                    sender=str(item.sender.email_address) if item.sender else "",
                    subject=item.subject or "",
                    body=item.text_body or "",
                    date=str(item.datetime_received) if item.datetime_received else None,
                    message_id=item.message_id,
                    in_reply_to=item.in_reply_to,
                    to_recipients=_mailboxes_to_addresses(getattr(item, "to_recipients", None)),
                    cc_recipients=_mailboxes_to_addresses(getattr(item, "cc_recipients", None)),
                ))
            return results
        except Exception:
            return []

    def fetch_sent_messages(self, since: datetime | None = None) -> list[RawEmail]:
        if not self._account:
            return []
        try:
            sent = self._account.sent
            qs = sent.all()
            results = []
            for item in qs.order_by("-datetime_received")[:100]:
                results.append(RawEmail(
                    sender=str(item.sender.email_address) if item.sender else "",
                    subject=item.subject or "",
                    body=item.text_body or "",
                    date=str(item.datetime_received) if item.datetime_received else None,
                    message_id=item.message_id,
                    to_recipients=_mailboxes_to_addresses(getattr(item, "to_recipients", None)),
                    cc_recipients=_mailboxes_to_addresses(getattr(item, "cc_recipients", None)),
                ))
            return results
        except Exception:
            return []

    def create_draft(
        self, to: list[str], subject: str, body: str, attachments: list[str] | None = None
    ) -> bool:
        if not self._account:
            return False
        try:
            from exchangelib import Mailbox, Message
            draft = Message(
                account=self._account,
                subject=subject,
                body=body,
                to_recipients=[Mailbox(email_address=addr) for addr in to],
            )
            draft.save(self._account.drafts)
            return True
        except Exception:
            return False

    def send_email(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
    ) -> bool:
        """直接寄送 email（不存草稿）。寄件者為當前認證帳號。

        Returns:
            True 寄送成功；False 寄送失敗（自我提醒/通知用，不做重試）。
        """
        if not self._account:
            return False
        try:
            from exchangelib import Mailbox, Message
            msg = Message(
                account=self._account,
                subject=subject,
                body=body,
                to_recipients=[Mailbox(email_address=addr) for addr in to],
                cc_recipients=(
                    [Mailbox(email_address=addr) for addr in cc] if cc else None
                ),
            )
            # send_and_save 寄送同時保存於 Sent Items
            msg.send_and_save()
            return True
        except Exception:
            return False
