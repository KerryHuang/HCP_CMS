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
    r"^(?:From|To|Cc|Date|Sent|Subject|Importance|Priority|寄件者|收件者|副本|傳送時間|主旨|重要性)\s*:.*$",
    re.MULTILINE | re.IGNORECASE,
)


def _strip_leading_headers(text: str) -> str:
    """移除 text 開頭連續符合 header pattern 的行（含其間空行），遇到非空非 header 行即停止。"""
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if _HEADER_LINE_RE.match(line) or line.strip() == "":
            i += 1
        else:
            break
    return "\n".join(lines[i:])


_GREETING_RE = re.compile(
    r"^(您好[\s，,、！!]*|Hi[\s,，]+|Hello[\s,，]+|Dear\s+.{1,20}[,，]\s*|親愛的.{1,10}[：:，,]\s*)\n?",
    re.IGNORECASE | re.MULTILINE,
)
_SIGNATURE_KEYWORDS = frozenset({
    "此致", "敬上", "謝謝", "感謝",
    "best regards", "regards", "thanks", "sincerely",
})
# 以特定前綴開頭的簽名語句（不需完整比對），含常見中文客套結尾
_SIGNATURE_PREFIX_RE = re.compile(
    r"^(感謝您|感謝您的|如有問題請聯絡|如有疑問|請不吝|敬祝|祝\s*您)",
    re.IGNORECASE,
)
# 各種樣式的免責聲明起始標記（星號行 / "Confidentiality Notice" / "This e-mail" 免責聲明）
_DISCLAIMER_START_RE = re.compile(
    r"(?m)^\*{10,}|confidentiality\s+notice|this\s+e-?mail\s+(?:along|is\s+intended|contains)",
    re.IGNORECASE,
)
# ==進度:...== 格式的進度備忘標記（不屬於 QA 正文）
_PROGRESS_NOTE_RE = re.compile(r"==進度[:：].*?==\n?", re.DOTALL)
# 行內聯絡資訊簽名：TEL / Fax / E-Mail 欄位（後接電話或 email）
_SIG_CONTACT_RE = re.compile(
    r"(?:tel|fax|e-?mail|電話|傳真)\s*[：:]\s*(?:[+\d（(]|[\w.]+@)",
    re.IGNORECASE,
)
# 簽名分隔線：精確兩個破折號 "--"（email client 標準）或 6 個以上長分隔線
# 刻意排除 "---"（3個）避免與正文中的 Markdown 分隔線衝突
_SEPARATOR_RE = re.compile(r"^(--|[-]{6,}|[_]{6,})$")
_BRACKET_CO_RE = re.compile(r"^\[.{1,20}\]$")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"})


def _clean_qa_text(text: str) -> str:
    """去除 QA 文字的招呼語、簽名檔、免責聲明、進度備忘，壓縮多餘空行。"""
    if not text:
        return ""
    # 1. 移除 ==進度:...== 進度備忘標記（非 QA 正文）
    text = _PROGRESS_NOTE_RE.sub("", text).strip()
    if not text:
        return ""
    # 2. 截斷免責聲明（含 **** 星號行、----- Confidentiality Notice / This e-mail 等格式）
    #    從包含匹配的「整行行首」截斷，連帶移除該行前的追蹤 ID（如 #64643 email）
    disc_match = _DISCLAIMER_START_RE.search(text)
    if disc_match:
        line_start = text.rfind("\n", 0, disc_match.start())
        cut_pos = line_start + 1 if line_start != -1 else 0
        text = text[:cut_pos].rstrip()
    # 3. 去招呼語
    text = _GREETING_RE.sub("", text, count=1).lstrip()
    # 4. 截斷簽名（逐行判斷）
    lines = text.split("\n")
    clean_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        stripped_clean = stripped.lower().rstrip(",.，。!！:：~ ")
        if (
            stripped_clean in _SIGNATURE_KEYWORDS
            or _SIGNATURE_PREFIX_RE.match(stripped)
            or _SEPARATOR_RE.match(stripped)
            or _BRACKET_CO_RE.match(stripped)
        ):
            break
        clean_lines.append(line)
    text = "\n".join(clean_lines)
    # 5. 截斷行內聯絡資訊（Tel：/ Fax：/ E-Mail: 欄位，含同行前方的姓名部門）
    sig_match = _SIG_CONTACT_RE.search(text)
    if sig_match:
        line_start = text.rfind("\n", 0, sig_match.start())
        text = (text[:line_start].rstrip() if line_start != -1 else text[:sig_match.start()].rstrip())
    # 6. 壓縮連續空行（> 2 個空行 → 2 個）
    text = _BLANK_LINES_RE.sub("\n\n", text)
    # 7. strip
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

    @staticmethod
    def extract_images(msg_path: Path, dest_dir: Path) -> list[Path]:
        """從 .msg 提取圖片附件至 dest_dir。若 msg_path 不存在回傳 []。

        提取對象：
        1. htmlBody 中 cid: 對應的 attachment
        2. 副檔名 .png/.jpg/.jpeg/.gif/.bmp/.webp 的一般附件
        冪等：dest_dir 已有同名檔案時跳過。
        """
        if not msg_path.exists():
            return []
        try:
            import extract_msg
            msg = extract_msg.Message(msg_path)
        except Exception:
            return []

        # 收集 CID 對應的 attachment content-id 集合
        cid_names: set[str] = set()
        try:
            html = getattr(msg, "htmlBody", None)
            if html:
                if isinstance(html, bytes):
                    html = html.decode("utf-8", errors="replace")
                for cid in re.findall(r'src=["\']cid:([^"\'>\s]+)["\']', html, re.IGNORECASE):
                    cid_names.add(cid.split("@")[0].lower())
        except Exception:
            pass

        saved: list[Path] = []
        dest_dir.mkdir(parents=True, exist_ok=True)

        try:
            attachments = msg.attachments or []
        except Exception:
            attachments = []

        for att in attachments:
            try:
                filename = getattr(att, "longFilename", None) or getattr(att, "shortFilename", None) or ""
                if not filename:
                    continue
                ext = Path(filename).suffix.lower()
                content_id = (getattr(att, "contentId", None) or "").split("@")[0].lower()
                is_cid = content_id in cid_names
                is_image_ext = ext in _IMAGE_EXTS
                if not (is_cid or is_image_ext):
                    continue
                dest_file = dest_dir / filename
                if dest_file.exists():
                    saved.append(dest_file)
                    continue
                data = att.data
                if data:
                    dest_file.write_bytes(data)
                    saved.append(dest_file)
            except Exception:
                continue

        try:
            msg.close()
        except Exception:
            pass
        return saved

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
