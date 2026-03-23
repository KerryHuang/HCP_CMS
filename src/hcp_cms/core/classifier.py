"""Multi-dimensional email classifier using DB-stored rules."""

import re
import sqlite3
from email.utils import parseaddr

from hcp_cms.data.repositories import CompanyRepository, RuleRepository


class Classifier:
    """Classifies emails by product, issue type, error type, priority, and company."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._rule_repo = RuleRepository(conn)
        self._company_repo = CompanyRepository(conn)

    def classify(self, subject: str, body: str, sender_email: str = "") -> dict:
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

        tags = self._parse_subject_tags(subject)

        company_id, company_display = self._resolve_company(sender_email)

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

        # 非 RD 括號 → progress，取最後一個（全形或半形括號）
        all_brackets = re.findall(r"[（(]([^）)]+)[）)]", subject)
        non_rd = [b for b in all_brackets if not b.upper().startswith("RD_")]
        if non_rd:
            result["progress"] = non_rd[-1]

        return result

    def _match_rules(self, rule_type: str, text: str, default: str) -> str:
        """Match text against rules of given type. First match wins."""
        rules = self._rule_repo.list_by_type(rule_type)
        for rule in rules:
            if re.search(rule.pattern, text, re.IGNORECASE):
                return rule.value
        return default

    def _resolve_company(self, sender_email: str) -> tuple[str | None, str | None]:
        """Resolve company_id and display name from sender email domain.

        查詢順序（參考 MSG 文件 4.2 節）：
        1. 完整 domain 精確比對
        2. 逐層去子網域回落（mail.abc.com → abc.com）
        3. 查無對應公司 → company_id=None，display=domain 原文
        4. email 為空或無 @ → (None, None)

        Returns:
            (company_id, display): company_id 是 FK 安全值（或 None），
                                    display 是顯示用名稱（公司中文名或 domain）
        """
        if not sender_email or "@" not in sender_email:
            return None, None
        # 支援 "Display Name <email@domain>" 格式，先用 email.utils 解析地址
        _, addr = parseaddr(sender_email)
        if not addr or "@" not in addr:
            addr = sender_email  # fallback：直接用原始字串
        domain = addr.split("@")[1].lower().rstrip(">").strip()
        # Try exact match
        company = self._company_repo.get_by_domain(domain)
        if company:
            return company.company_id, company.name
        # Try subdomain fallback: mail.abc.com → abc.com
        parts = domain.split(".")
        fallback_domain = domain
        if len(parts) > 2:
            fallback_domain = ".".join(parts[1:])
            company = self._company_repo.get_by_domain(fallback_domain)
            if company:
                return company.company_id, company.name
        # 查無對應公司：company_id 保持 None（FK 安全），display 回傳 domain
        return None, fallback_domain

    def _check_broadcast(self, text: str) -> bool:
        """Check if email is a broadcast/announcement."""
        rules = self._rule_repo.list_by_type("broadcast")
        for rule in rules:
            if re.search(rule.pattern, text, re.IGNORECASE):
                return True
        return False
