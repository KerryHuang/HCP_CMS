"""Read .msg files from local filesystem using extract-msg."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from email.utils import getaddresses
from pathlib import Path

from hcp_cms.services.mail.base import MailProvider, RawEmail

_PROGRESS_RE = re.compile(r"==進度[:：]\s*(.*?)==", re.DOTALL)
_FROM_ANGLE_RE = re.compile(r"^From:\s*[^<\n]*<([^>]+)>", re.MULTILINE)
_FROM_PLAIN_RE = re.compile(r"^From:\s*(\S+@\S+)", re.MULTILINE)
_THREAD_FROM_RE = re.compile(
    r"^(?:From|寄件者)\s*:\s*.*?([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})",
    re.MULTILINE | re.IGNORECASE,
)
_HEADER_LINE_RE = re.compile(
    r"^(?:From|To|Sent|Subject|寄件者|收件者|傳送時間|主旨)\s*:.*$",
    re.MULTILINE | re.IGNORECASE,
)


def _strip_leading_headers(text: str) -> str:
    """移除 text 開頭連續符合 header pattern 的行，遇到非 header 行即停止。"""
    lines = text.split("\n")
    i = 0
    while i < len(lines) and _HEADER_LINE_RE.match(lines[i]):
        i += 1
    return "\n".join(lines[i:])


_GREETING_RE = re.compile(
    r"^(您好[\s，,、！!]*|Hi[\s,，]+|Hello[\s,，]+|Dear\s+.{1,20}[,，]\s*|親愛的.{1,10}[：:，,]\s*)\n?",
    re.IGNORECASE | re.MULTILINE,
)
_SIGNATURE_KEYWORDS = frozenset({
    "此致", "敬上", "謝謝", "感謝",
    "best regards", "regards", "thanks", "sincerely",
})
_SEPARATOR_RE = re.compile(r"^(-{3,}|_{3,})$")
_BRACKET_CO_RE = re.compile(r"^\[.{1,20}\]$")


def _clean_qa_text(text: str) -> str:
    """去除 QA 文字的招呼語、簽名檔，壓縮多餘空行。"""
    if not text:
        return ""
    # 1. 去招呼語
    text = _GREETING_RE.sub("", text, count=1).lstrip()
    # 2. 截斷簽名
    lines = text.split("\n")
    clean_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if (
            stripped.lower() in _SIGNATURE_KEYWORDS
            or _SEPARATOR_RE.match(stripped)
            or _BRACKET_CO_RE.match(stripped)
        ):
            break
        clean_lines.append(line)
    text = "\n".join(clean_lines)
    # 3. 壓縮連續空行（> 2 個空行 → 2 個）
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 4. strip
    return text.strip()


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
                results.append(self._read_msg_file(msg_path))
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
        """Read a single .msg file. Returns None on any parse error."""
        try:
            return self._read_msg_file(file_path)
        except Exception:
            return None

    def read_single_file_verbose(self, file_path: Path) -> tuple[RawEmail | None, str | None]:
        """Read a single .msg file, returning (email, error_message).

        error_message is None on success, or a string describing the failure.
        """
        try:
            return self._read_msg_file(file_path), None
        except Exception as exc:
            return None, str(exc)

    def compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def _split_thread(body: str, own_domain: str = "@ares.com.tw") -> tuple[str | None, str | None]:
        """回傳 (thread_answer, thread_question)。
        取最後一個非我方 From 行：上方為 answer，下方清除 leading header 行後為 question。
        strip 後為空字串一律轉 None。own_domain 比對大小寫不敏感。
        """
        own = own_domain.lower()
        last_match = None
        for match in _THREAD_FROM_RE.finditer(body):
            addr = match.group(1).lower()
            if own not in addr:
                last_match = match
        if last_match:
            split_pos = last_match.start()
            answer = body[:split_pos].strip() or None
            question = _strip_leading_headers(body[split_pos:]).strip() or None
            return answer, question
        return None, None

    @staticmethod
    def _safe_str(msg: object, attr: str, default: str = "") -> str:
        """安全存取 extract_msg 的字串屬性，cp950 解碼失敗時回傳 default。"""
        try:
            val = getattr(msg, attr, None)
            return (val or default) if isinstance(val, str) else default
        except (UnicodeDecodeError, UnicodeEncodeError, AttributeError):
            return default

    @staticmethod
    def _read_msg_file(file_path: Path) -> RawEmail:
        """Parse a .msg file using extract-msg. Raises on any parse error."""
        # 延遲 import：extract_msg 為選用重型套件，避免未安裝時阻擋應用啟動
        import extract_msg

        msg = extract_msg.Message(file_path)

        # ── 收件人列表：msg.to 可能以非 cp950 編碼造成 UnicodeDecodeError ──
        raw_to = MSGReader._safe_str(msg, "to")
        normalized = raw_to.replace(";", ",")
        to_recipients = [addr for _, addr in getaddresses([normalized]) if addr]

        # msg.to 解碼失敗時（cp950），嘗試從 msg.recipients 個別取 email
        if not to_recipients:
            try:
                for r in msg.recipients or []:
                    try:
                        addr = getattr(r, "email", None) or ""
                        if addr and "@" in addr:
                            to_recipients.append(addr)
                    except (UnicodeDecodeError, UnicodeEncodeError, AttributeError):
                        continue
            except (UnicodeDecodeError, UnicodeEncodeError, AttributeError):
                pass

        # ── HTML body（bytes → str，UTF-8 → cp950 fallback）───────────────
        html_body: str | None = None
        try:
            raw_html = getattr(msg, "htmlBody", None)
            if raw_html:
                if isinstance(raw_html, bytes):
                    try:
                        html_body = raw_html.decode("utf-8")
                    except UnicodeDecodeError:
                        html_body = raw_html.decode("cp950", errors="replace")
                else:
                    html_body = str(raw_html)
        except (UnicodeDecodeError, UnicodeEncodeError):
            html_body = None

        # ── 純文字 body（供後續 regex 搜尋）──────────────────────────────
        body_text = MSGReader._safe_str(msg, "body")
        if not body_text and html_body:
            # msg.body 解碼失敗時，從 HTML 移除標籤作為 fallback
            body_text = re.sub(r"<[^>]+>", " ", html_body)

        # ── 進度標記擷取（==進度:…== 或 ==進度：…==，可跨行）──────────
        _prog_match = _PROGRESS_RE.search(body_text)
        progress_note: str | None = _prog_match.group(1).strip() if _prog_match else None

        # ── 對話串切割（客戶問題段 / 我方回覆段）────────────────────
        thread_answer, thread_question = MSGReader._split_thread(body_text)
        thread_answer = _clean_qa_text(thread_answer) if thread_answer else None
        thread_question = _clean_qa_text(thread_question) if thread_question else None

        # ── 草稿寄件人補修（msg.sender 空白時從 body 搜尋 From: 行）───
        sender = MSGReader._safe_str(msg, "sender")
        if not sender:
            _from_match = _FROM_ANGLE_RE.search(body_text)
            if _from_match:
                sender = _from_match.group(1).strip()
            else:
                _plain_match = _FROM_PLAIN_RE.search(body_text)
                if _plain_match:
                    sender = _plain_match.group(1).strip()

        subject = MSGReader._safe_str(msg, "subject")
        try:
            date = msg.date or None
        except (UnicodeDecodeError, UnicodeEncodeError, AttributeError):
            date = None
        try:
            attachments = [att.longFilename or "" for att in msg.attachments] if msg.attachments else []
        except (UnicodeDecodeError, UnicodeEncodeError, AttributeError):
            attachments = []

        email = RawEmail(
            sender=sender,
            subject=subject,
            body=body_text,
            date=date,
            attachments=attachments,
            source_file=str(file_path),
            to_recipients=to_recipients,
            html_body=html_body,
            thread_question=thread_question,
            thread_answer=thread_answer,
            progress_note=progress_note,
        )
        msg.close()
        return email
