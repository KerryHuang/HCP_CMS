"""Multi-dimensional email classifier using DB-stored rules."""

import re
import sqlite3

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

        result = {
            "system_product": self._match_rules("product", text, "HCP"),
            "issue_type": self._match_rules("issue", text, "OTH"),
            "error_type": self._match_rules("error", text, "人事資料管理"),
            "priority": self._match_rules("priority", text, "中"),
            "company_id": self._resolve_company(sender_email),
            "is_broadcast": self._check_broadcast(text),
            "handler": self._match_rules("handler", text, "") or None,
            "progress": self._match_rules("progress", text, "") or None,
        }

        # Override: if issue_type contains 客制 keywords, set priority custom
        return result

    def _match_rules(self, rule_type: str, text: str, default: str) -> str:
        """Match text against rules of given type. First match wins."""
        rules = self._rule_repo.list_by_type(rule_type)
        for rule in rules:
            if re.search(rule.pattern, text, re.IGNORECASE):
                return rule.value
        return default

    def _resolve_company(self, sender_email: str) -> str | None:
        """Resolve company_id from sender email domain."""
        if not sender_email or "@" not in sender_email:
            return None
        domain = sender_email.split("@")[1].lower()
        # Try exact match
        company = self._company_repo.get_by_domain(domain)
        if company:
            return company.company_id
        # Try subdomain fallback: mail.abc.com → abc.com
        parts = domain.split(".")
        if len(parts) > 2:
            fallback = ".".join(parts[1:])
            company = self._company_repo.get_by_domain(fallback)
            if company:
                return company.company_id
        return None

    def _check_broadcast(self, text: str) -> bool:
        """Check if email is a broadcast/announcement."""
        rules = self._rule_repo.list_by_type("broadcast")
        for rule in rules:
            if re.search(rule.pattern, text, re.IGNORECASE):
                return True
        return False
