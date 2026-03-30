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
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        folder: str = "INBOX",
        on_message: object = None,
    ) -> list[RawEmail]:
        if not self._conn:
            return []
        import sys
        try:
            self._conn.select(folder)
            criteria = "ALL"
            if since:
                criteria = f'(SINCE "{since.strftime("%d-%b-%Y")}")'
            if until:
                # IMAP BEFORE 不含當天，需 +1 天
                from datetime import timedelta

                before_date = until + timedelta(days=1)
                criteria = f'(SINCE "{since.strftime("%d-%b-%Y")}" BEFORE "{before_date.strftime("%d-%b-%Y")}")'

            print(f"[DEBUG fetch] folder={folder!r} criteria={criteria!r}", file=sys.stderr, flush=True)
            _, msg_nums = self._conn.search(None, criteria)
            nums = msg_nums[0].split()
            print(f"[DEBUG fetch] {len(nums)} message(s) found", file=sys.stderr, flush=True)
            results = []
            for num in nums:
                _, data = self._conn.fetch(num, "(RFC822)")
                if data[0] is None:
                    continue
                msg = email.message_from_bytes(data[0][1])
                parsed = self._parse_email(msg)
                results.append(parsed)
                if on_message:
                    on_message(parsed)
            return results
        except Exception as e:
            import sys
            print(f"[DEBUG fetch] Exception: {e}", file=sys.stderr, flush=True)
            return []

    def fetch_sent_messages(self, since: datetime | None = None) -> list[RawEmail]:
        import sys
        folder = self._find_sent_folder()
        print(f"[DEBUG sent] found folder={folder!r}", file=sys.stderr, flush=True)
        if not folder:
            print("[DEBUG sent] no sent folder found", file=sys.stderr, flush=True)
            return []
        results = self.fetch_messages(since=since, folder=folder)
        print(f"[DEBUG sent] fetched {len(results)} messages", file=sys.stderr, flush=True)
        return results

    def _find_sent_folder(self) -> str | None:
        """找出 IMAP 伺服器的寄件夾名稱。
        1. LIST 找 \\Sent 旗標
        2. LIST 解碼後名稱含「寄件」或「sent」關鍵字
        3. 逐一嘗試常見英文名稱"""
        if not self._conn:
            return None
        import re

        sent_keywords = ("寄件", "sent")

        def _extract_name(line: str) -> str | None:
            m = re.search(r'"([^"]+)"\s*$|(\S+)\s*$', line)
            return (m.group(1) or m.group(2)) if m else None

        try:
            typ, items = self._conn.list('""', "*")
            if typ == "OK" and items:
                keyword_candidates: list[str] = []
                for item in items:
                    if not item:
                        continue
                    decoded = item.decode("utf-8", errors="replace") if isinstance(item, bytes) else item
                    # 優先：有 \Sent 旗標
                    if r"\Sent" in decoded:
                        name = _extract_name(decoded)
                        if name:
                            return name
                    # 備選：解碼後名稱含寄件/sent 關鍵字
                    name_raw = _extract_name(decoded)
                    if name_raw:
                        name_decoded = self._decode_imap_utf7(name_raw)
                        folder_leaf = name_decoded.rsplit("/", 1)[-1].lower()
                        if any(kw in folder_leaf for kw in sent_keywords):
                            keyword_candidates.append(name_raw)
                # 從關鍵字候選中選頂層資料夾（不含 /），優先取解碼後名稱最短者
                top_level = [n for n in keyword_candidates if "/" not in n]
                if top_level:
                    return min(top_level, key=lambda n: len(self._decode_imap_utf7(n)))
                if keyword_candidates:
                    return keyword_candidates[0]
        except Exception:
            pass
        # 3. 逐一嘗試常見英文名稱，以 select 回傳碼判斷是否存在
        for folder in ('"[Gmail]/Sent Mail"', "Sent", "INBOX.Sent", '"Sent Items"', "Sent Messages"):
            try:
                typ, _ = self._conn.select(folder, readonly=True)
                if typ == "OK":
                    return folder
            except Exception:
                continue
        return None

    @staticmethod
    def _decode_imap_utf7(s: str) -> str:
        """解碼 IMAP Modified UTF-7 資料夾名稱（RFC 3501）。"""
        import base64

        res: list[str] = []
        i = 0
        while i < len(s):
            if s[i] == "&":
                try:
                    j = s.index("-", i + 1)
                    b64 = s[i + 1 : j].replace(",", "/")
                    if b64 == "":
                        res.append("&")
                    else:
                        pad = (4 - len(b64) % 4) % 4
                        res.append(base64.b64decode(b64 + "=" * pad).decode("utf-16-be"))
                    i = j + 1
                except Exception:
                    res.append(s[i])
                    i += 1
            else:
                res.append(s[i])
                i += 1
        return "".join(res)

    def create_draft(self, to: list[str], subject: str, body: str, attachments: list[str] | None = None) -> bool:
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
    def _decode_header_value(raw: str) -> str:
        """解碼 RFC 2047 編碼的 header 值（Subject / From 等）。"""
        if not raw:
            return ""
        decoded = decode_header(raw)
        parts = []
        for part, enc in decoded:
            if isinstance(part, bytes):
                charset = enc or "utf-8"
                try:
                    parts.append(part.decode(charset))
                except (UnicodeDecodeError, LookupError):
                    parts.append(part.decode(charset, errors="replace"))
            else:
                parts.append(part)
        return "".join(parts)

    @staticmethod
    def _parse_email(msg: email.message.Message) -> RawEmail:
        subject = IMAPProvider._decode_header_value(msg.get("Subject", ""))

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

        # 解碼寄件人（處理 RFC 2047 編碼）
        raw_from = msg.get("From", "")
        sender = IMAPProvider._decode_header_value(raw_from)

        # 解析收件人 To（寄件備份用）
        from email.utils import getaddresses

        raw_to = msg.get("To", "")
        to_recipients = [addr for _, addr in getaddresses([raw_to]) if addr]

        # 日期格式化為 yyyy/mm/dd HH:MM:SS
        raw_date = msg.get("Date", "")
        date_str = raw_date
        if raw_date:
            try:
                from email.utils import parsedate_to_datetime

                dt = parsedate_to_datetime(raw_date)
                date_str = dt.astimezone().strftime("%Y/%m/%d %H:%M:%S")
            except Exception:
                pass

        return RawEmail(
            sender=sender,
            subject=subject,
            body=body,
            date=date_str,
            message_id=msg.get("Message-ID"),
            in_reply_to=msg.get("In-Reply-To"),
            references=msg.get("References"),
            to_recipients=to_recipients,
        )
