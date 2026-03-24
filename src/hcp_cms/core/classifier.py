"""Multi-dimensional email classifier using DB-stored rules."""

import re
import sqlite3
from email.utils import parseaddr

from hcp_cms.data.repositories import CompanyRepository, RuleRepository

OUR_DOMAIN = "ares.com.tw"


class Classifier:
    """Classifies emails by product, issue type, error type, priority, and company."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._rule_repo = RuleRepository(conn)
        self._company_repo = CompanyRepository(conn)

    def classify(self, subject: str, body: str, sender_email: str = "", to_recipients: list[str] | None = None) -> dict:
        """
        Classify an email based on subject, body, and sender.

        Returns dict with keys:
        - system_product: str (default "HCP")
        - issue_type: str (default "OTH")
        - error_type: str (default "人事資料管理")
        - priority: str ("高" or "中")
        - company_id: str | None
        - is_broadcast: bool
        """
        text = f"{subject} {body[:300]}"  # subject + first 300 chars of body

        tags = self.parse_tags(subject)

        company_id, company_display = self._resolve_company(sender_email, to_recipients or [])

        result = {
            "system_product": self._match_rules("product", text, "HCP"),
            "issue_type": self._match_rules("issue", text, "OTH"),
            "error_type": self._match_rules("error", text, "人事資料管理"),
            "priority": self._match_rules("priority", text, "中"),
            "company_id": company_id,          # FK 安全值（已知公司 ID 或 None）
            "company_display": company_display,  # 顯示用（公司中文名或 domain fallback）
            "is_broadcast": self._check_broadcast(text),
            # 主旨標記優先，其次才是 DB 規則
            "handler": tags.get("handler") or self._match_rules("handler", text, "") or None,
            "progress": tags.get("progress") or self._match_rules("progress", text, "") or None,
            "issue_number": tags.get("issue_number"),
        }

        return result

    def parse_tags(self, text: str) -> dict:
        """解析主旨或檔名中的標記（公開介面，供同層 Core 類別呼叫）。"""
        return self._parse_subject_tags(text)

    def _parse_subject_tags(self, subject: str) -> dict:
        """
        解析主旨中的固定標記格式，回傳可識別的欄位值。

        支援格式：
          ISSUE_YYYYMMDD_NNNNNNN_  → issue_number
          (RD_XXXX)                → handler（取第一個，去除 RD_ 前綴）
          (非 RD 開頭的括號)        → progress（取最後一個）
        """
        result: dict = {}

        # ISSUE 編號：ISSUE_20260319_0017445_
        m = re.search(r"ISSUE_\d{8}_(\d+)_", subject, re.IGNORECASE)
        if m:
            result["issue_number"] = m.group(1)

        # (RD_XXXX) → handler，取第一個符合
        rd_match = re.search(r"\(RD_([A-Za-z0-9_]+)\)", subject)
        if rd_match:
            result["handler"] = rd_match.group(1)

        # 處理進度 → 取 RD 標記之後緊接的第一個括號（全形或半形）
        # 客戶主旨中的括號（如 (** Security C**)）不視為進度
        rd_pos = re.search(r"\(RD_[A-Za-z0-9_]+\)", subject)
        if rd_pos:
            after_rd = subject[rd_pos.end():]
            prog_match = re.search(r"[（(]([^）)]+)[）)]", after_rd)
            if prog_match:
                result["progress"] = prog_match.group(1)

        return result

    def _match_rules(self, rule_type: str, text: str, default: str) -> str:
        """Match text against rules of given type. First match wins."""
        rules = self._rule_repo.list_by_type(rule_type)
        for rule in rules:
            if re.search(rule.pattern, text, re.IGNORECASE):
                return rule.value
        return default

    def _resolve_company(
        self, sender_email: str, to_recipients: list[str] | None = None
    ) -> tuple[str | None, str | None]:
        """Resolve company from sender, or recipients if sender is our side."""
        # 判斷是否為我方寄件
        if sender_email and "@" in sender_email:
            _, addr = parseaddr(sender_email)
            sender_domain = addr.split("@")[1].lower() if "@" in addr else ""
            if sender_domain == OUR_DOMAIN or sender_domain.endswith(f".{OUR_DOMAIN}"):
                # 我方寄件：委託公開方法從收件人解析公司
                return self.resolve_external_company(to_recipients or [])

        return self._lookup_by_email(sender_email)

    def resolve_external_company(self, recipients: list[str]) -> tuple[str | None, str | None]:
        """從收件人列表中找第一個非我方地址，回傳其公司 (company_id, display)。
        供 CaseManager 等同層 Core 類別呼叫。
        """
        for r in recipients:
            _, addr = parseaddr(r)
            if not addr:
                addr = r
            if "@" in addr:
                domain = addr.split("@")[1].lower()
                if domain != OUR_DOMAIN and not domain.endswith(f".{OUR_DOMAIN}"):
                    return self._lookup_by_email(addr)
        return None, None

    def _lookup_by_email(self, email_str: str) -> tuple[str | None, str | None]:
        """Look up company_id and display name from an email address string."""
        if not email_str or "@" not in email_str:
            return None, None
        _, addr = parseaddr(email_str)
        if not addr or "@" not in addr:
            addr = email_str
        domain = addr.split("@")[1].lower().rstrip(">").strip()
        company = self._company_repo.get_by_domain(domain)
        if company:
            return company.company_id, company.name
        parts = domain.split(".")
        fallback_domain = domain
        if len(parts) > 2:
            fallback_domain = ".".join(parts[1:])
            company = self._company_repo.get_by_domain(fallback_domain)
            if company:
                return company.company_id, company.name
        return None, fallback_domain

    def _check_broadcast(self, text: str) -> bool:
        """Check if email is a broadcast/announcement."""
        rules = self._rule_repo.list_by_type("broadcast")
        for rule in rules:
            if re.search(rule.pattern, text, re.IGNORECASE):
                return True
        return False
