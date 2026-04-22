"""Multi-dimensional email classifier using DB-stored rules."""

import re
import sqlite3
from email.utils import parseaddr

from hcp_cms.core.customer_manager import CustomerManager
from hcp_cms.data.repositories import CompanyRepository, RuleRepository

OUR_DOMAIN = "ares.com.tw"

# 從主旨/檔名解析 Mantis ISSUE 資訊
# 支援兩種格式：
#   舊格式：ISSUE_YYYYMMDD_INNNNN_    → e.g. ISSUE_20260319_I0017445_
#   新格式：ISSUE_YYYYMM_N_INNNNNNN_  → e.g. ISSUE_202603_5_I0017475_
_ISSUE_RE = re.compile(
    r"ISSUE_(\d{6,8})_(?:\d+_)?I?(\d+)_",
    re.IGNORECASE,
)

# Mantis 通知信主旨格式：[公司名 0017095]: [摘要...]
# 擷取公司名稱（group 1）與票號（group 2）
_MANTIS_NOTIFY_RE = re.compile(
    r"^\[(.+?)\s+(\d{5,8})\]\s*:",
)


class Classifier:
    """Classifies emails by product, issue type, error type, priority, and company."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._rule_repo = RuleRepository(conn)
        self._company_repo = CompanyRepository(conn)
        self._customer_mgr = CustomerManager(conn)

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

        # 解析 Mantis ISSUE 資訊（在 subject 中搜尋）
        mantis_ticket_id: str | None = None
        mantis_issue_date: str | None = None
        m_issue = _ISSUE_RE.search(subject or "")
        if m_issue:
            raw_date = m_issue.group(1)   # "20260325"
            mantis_ticket_id = m_issue.group(2)  # "0017475"
            mantis_issue_date = f"{raw_date[:4]}/{raw_date[4:6]}/{raw_date[6:]}"

        # Mantis 通知信主旨格式 fallback：[公司名 0017095]: ...
        mantis_notify_company: str | None = None
        if not mantis_ticket_id:
            m_notify = _MANTIS_NOTIFY_RE.match(subject or "")
            if m_notify:
                mantis_notify_company = m_notify.group(1).strip()   # "Asus_華碩電腦"
                mantis_ticket_id = m_notify.group(2)                 # "0017095"
                # 若 company_id 仍未找到，嘗試以公司顯示名稱搜尋
                if not company_id:
                    for c in self._company_repo.list_all():
                        if mantis_notify_company in (c.name or "") or (c.name or "") in mantis_notify_company:
                            company_id = c.company_id
                            break

        # handler 優先序：① 主旨 (RD_XXX) ② 寄件人 domain → 公司 → 客服 ③ 分類規則
        subject_handler = tags.get("handler")
        domain_handler: str | None = None
        if not subject_handler:
            _, saddr = parseaddr(sender_email)
            if not saddr:
                saddr = sender_email
            saddr = saddr.lower()
            sender_domain = saddr.split("@")[1] if "@" in saddr else ""
            if sender_domain == OUR_DOMAIN or sender_domain.endswith(f".{OUR_DOMAIN}"):
                # 我方寄出 → 從收件人中找客戶 domain
                for r in (to_recipients or []):
                    _, raddr = parseaddr(r)
                    if not raddr:
                        raddr = r
                    raddr = raddr.lower()
                    if "@" in raddr:
                        rdomain = raddr.split("@")[1]
                        if rdomain != OUR_DOMAIN and not rdomain.endswith(f".{OUR_DOMAIN}"):
                            domain_handler = self._resolve_handler_from_domain(r)
                            if domain_handler:
                                break
            else:
                domain_handler = self._resolve_handler_from_domain(sender_email)

        result = {
            "system_product": self._match_rules("product", text, "HCP"),
            "issue_type": self._match_rules("issue", text, "OTH"),
            "error_type": self._match_rules("error", text, "人事資料管理"),
            "priority": self._match_rules("priority", text, "中"),
            "company_id": company_id,          # FK 安全值（已知公司 ID 或 None）
            "company_display": company_display,  # 顯示用（公司中文名或 domain fallback）
            "is_broadcast": self._check_broadcast(text),
            # 主旨標記優先，其次 domain 查公司客服，最後才是 DB 規則
            "handler": subject_handler
                       or domain_handler
                       or self._match_rules("handler", text, "")
                       or None,
            "progress": tags.get("progress") or self._match_rules("progress", text, "") or None,
            "issue_number": tags.get("issue_number"),
            "mantis_ticket_id": mantis_ticket_id,
            "mantis_issue_date": mantis_issue_date,
            "mantis_notify_company": mantis_notify_company,  # Mantis 通知信的公司顯示名稱
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

        # ISSUE 編號：舊格式 ISSUE_YYYYMMDD_NNNNNNN_ 或新格式 ISSUE_YYYYMM_N_INNNNNNN_
        m = re.search(r"ISSUE_\d{6,8}_(?:\d+_)?I?(\d+)_", subject, re.IGNORECASE)
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

    def _resolve_handler_from_domain(self, sender_email: str) -> str | None:
        """從寄件人 domain 查公司，再取公司的負責客服名稱。

        支援子網域 fallback：mail.abc.com.tw → abc.com.tw。
        """
        if not sender_email or "@" not in sender_email:
            return None
        _, addr = parseaddr(sender_email)
        if not addr:
            addr = sender_email
        addr = addr.lower().strip()
        if "@" not in addr:
            return None
        domain = addr.split("@")[1]
        # 直接查詢
        handler = self._customer_mgr.resolve_handler_by_domain(domain)
        if handler:
            return handler
        # 子網域 fallback：mail.abc.com.tw → abc.com.tw
        parts = domain.split(".")
        if len(parts) > 2:
            parent_domain = ".".join(parts[1:])
            handler = self._customer_mgr.resolve_handler_by_domain(parent_domain)
        return handler

    def _check_broadcast(self, text: str) -> bool:
        """Check if email is a broadcast/announcement."""
        rules = self._rule_repo.list_by_type("broadcast")
        for rule in rules:
            if re.search(rule.pattern, text, re.IGNORECASE):
                return True
        return False
