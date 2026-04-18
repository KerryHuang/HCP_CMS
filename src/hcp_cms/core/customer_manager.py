# src/hcp_cms/core/customer_manager.py
"""CustomerManager — 客戶公司與人員的業務邏輯層。"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from hcp_cms.data.models import Company, Staff
from hcp_cms.data.repositories import CaseRepository, CompanyRepository, StaffRepository


def _gen_company_id() -> str:
    return f"COMP-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"


def _gen_staff_id() -> str:
    return f"STAFF-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"


class CustomerManager:
    """管理客戶公司與人員資料，提供批次 upsert 與 handler 解析。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._company_repo = CompanyRepository(conn)
        self._staff_repo = StaffRepository(conn)
        self._case_repo = CaseRepository(conn)

    # ── 公司 ──────────────────────────────────────────────────────────────

    def bulk_upsert_companies(self, rows: list[dict]) -> tuple[int, int]:
        """批次新增/更新客戶公司。

        Args:
            rows: list of dict，每筆需含 name / domain / alias / contact_info /
                  cs_staff_id / sales_staff_id。domain 為空則跳過。

        Returns:
            (inserted, updated) 計數
        """
        inserted = updated = 0
        for row in rows:
            name = (row.get("name") or "").strip()
            domain = (row.get("domain") or "").strip().lower()
            company_id = (row.get("company_id") or "").strip()
            if not name:
                continue

            # 查找現有記錄：優先用 company_id（表格編輯），其次用 domain（批次貼上）
            existing = None
            if company_id:
                existing = self._company_repo.get_by_id(company_id)
            if not existing and domain:
                existing = self._company_repo.get_by_domain(domain)

            if existing:
                existing.name = name
                if domain:
                    existing.domain = domain
                existing.alias = (row.get("alias") or "").strip() or existing.alias
                existing.contact_info = (row.get("contact_info") or "").strip() or existing.contact_info
                if "cs_staff_id" in row:
                    existing.cs_staff_id = row["cs_staff_id"] or None
                if "sales_staff_id" in row:
                    existing.sales_staff_id = row["sales_staff_id"] or None
                self._company_repo.update(existing)
                updated += 1
            elif domain:
                # 新增時仍需要 domain（作為唯一識別）
                company = Company(
                    company_id=_gen_company_id(),
                    name=name,
                    domain=domain,
                    alias=(row.get("alias") or "").strip() or None,
                    contact_info=(row.get("contact_info") or "").strip() or None,
                    cs_staff_id=row.get("cs_staff_id") or None,
                    sales_staff_id=row.get("sales_staff_id") or None,
                )
                self._company_repo.insert(company)
                inserted += 1
            # domain 與 company_id 皆無 → 跳過
        return inserted, updated

    def list_companies(self) -> list[Company]:
        return self._company_repo.list_all()

    def delete_company(self, company_id: str) -> None:
        self._company_repo.delete(company_id)

    # ── 人員 ──────────────────────────────────────────────────────────────

    def bulk_upsert_staff(self, rows: list[dict]) -> tuple[int, int]:
        """批次新增/更新人員。

        Args:
            rows: list of dict，每筆需含 name / email / role / phone / notes。
                  email 空字串視為無效，跳過。

        Returns:
            (inserted, updated) 計數
        """
        inserted = updated = 0
        for row in rows:
            email = (row.get("email") or "").strip().lower()
            name = (row.get("name") or "").strip()
            if not email or not name:
                continue
            role = (row.get("role") or "cs").strip()
            staff = Staff(
                staff_id=_gen_staff_id(),
                name=name,
                email=email,
                role=role,
                phone=(row.get("phone") or "").strip() or None,
                notes=(row.get("notes") or "").strip() or None,
            )
            existing = self._staff_repo.get_by_email(email)
            if existing:
                staff.staff_id = existing.staff_id
                self._staff_repo.update(staff)
                updated += 1
            else:
                self._staff_repo.insert(staff)
                inserted += 1
        return inserted, updated

    def list_staff(self, role: str | None = None) -> list[Staff]:
        if role:
            return self._staff_repo.list_by_role(role)
        return self._staff_repo.list_all()

    def delete_staff(self, staff_id: str) -> None:
        self._staff_repo.delete(staff_id)

    def get_company_by_domain(self, domain: str) -> Company | None:
        """依 domain 查詢公司，供 UI 層刪除時使用。"""
        return self._company_repo.get_by_domain(domain)

    def get_staff_by_email(self, email: str) -> Staff | None:
        """依 email 查詢人員，供 UI 層刪除時使用。"""
        return self._staff_repo.get_by_email(email)

    # ── 分案解析 ──────────────────────────────────────────────────────────

    def resolve_handler_by_domain(self, domain: str) -> str | None:
        """從 domain 找公司 → 取公司的 cs_staff_id → 回傳 staff.name。

        用於信件收件時自動填入 handler。
        回傳 None 表示無法判斷（公司不存在或未綁定客服）。
        """
        company = self._company_repo.get_by_domain(domain)
        if not company or not company.cs_staff_id:
            return None
        staff = self._staff_repo.get_by_id(company.cs_staff_id)
        return staff.name if staff else None

    # ── 案件重新比對 ──────────────────────────────────────────────────────

    def reassociate_case_companies(self) -> int:
        """嘗試將 company_id 遺失的案件重新比對至正確公司。

        兩種策略：
        1. contact_person 含 '@' → 擷取網域 → 查詢 companies.domain（含子網域 fallback）
        2. company_id 為公司名稱（CSV 匯入舊格式，非 COMP- 開頭）→ 比對 companies.name

        Returns:
            成功比對並更新的案件數
        """
        matched = 0

        # 策略 1：contact_person email 網域比對
        for case_id, contact_person in self._case_repo.list_null_company_with_contact():
            if not contact_person or "@" not in contact_person:
                continue
            domain = contact_person.split("@")[-1].strip().lower()
            company = self._company_repo.get_by_domain(domain)
            if not company:
                parts = domain.split(".")
                if len(parts) > 2:
                    company = self._company_repo.get_by_domain(".".join(parts[1:]))
            if company:
                self._case_repo.update_company_id(case_id, company.company_id)
                matched += 1

        # 策略 2：CSV 匯入的 company_id（= 公司名稱）比對正式 company_id
        name_to_id = {c.name: c.company_id for c in self._company_repo.list_all()}
        for case_id, stub_id in self._case_repo.list_csv_stub_company_ids():
            if stub_id in name_to_id and name_to_id[stub_id] != stub_id:
                self._case_repo.update_company_id(case_id, name_to_id[stub_id])
                matched += 1

        if matched:
            self._conn.commit()
        return matched

    # ── Mantis HcpVersion 同步 ────────────────────────────────────────────

    def sync_hcp_version_from_mantis(self, client) -> tuple[int, str]:
        """從 Mantis 使用者清單同步 HcpVersion 至 companies 表。

        比對策略：取 Mantis 使用者 email 的網域，與 companies.domain 配對。

        Args:
            client: MantisSoapClient（已呼叫 connect() 且成功連線）

        Returns:
            (updated_count, error_message)；error_message 為空字串表示成功
        """
        users = client.get_users_hcp_version()
        if not users and client.last_error:
            return 0, client.last_error

        companies = self._company_repo.list_all()
        domain_to_company: dict[str, Company] = {
            (c.domain or "").lower(): c for c in companies if c.domain
        }
        # 以公司名稱配對（Mantis 使用者的「真實姓名」即公司中文名稱）
        name_to_company: dict[str, Company] = {
            c.name.strip(): c for c in companies if c.name
        }

        # 建立 domain 關鍵字索引（僅取主網域第一段，如 alphanetworks.com.tw → alphanetworks）
        domain_keyword_to_company: dict[str, Company] = {}
        for c in companies:
            if c.domain:
                keyword = c.domain.lower().split(".")[0]
                domain_keyword_to_company[keyword] = c

        updated = 0
        for user in users:
            hcp_version = user.get("hcp_version", "")
            if not hcp_version:
                continue

            company = None

            # 策略 1：real_name（真實姓名）包含 companies.name（簡稱）
            # 例：Mantis「明泰科技股份有限公司」⊇ 系統「明泰」
            real_name = user.get("real_name", "").strip()
            if real_name:
                # 先嘗試完全比對
                company = name_to_company.get(real_name)
                # 再嘗試包含比對（系統簡稱 in Mantis 全名）
                if not company:
                    for sys_name, cand in name_to_company.items():
                        if sys_name and sys_name in real_name:
                            company = cand
                            break

            # 策略 2：email 網域比對 companies.domain
            if not company:
                email = user.get("email", "")
                if "@" in email:
                    user_domain = email.split("@")[-1].strip().lower()
                    company = domain_to_company.get(user_domain)
                    if not company:
                        parts = user_domain.split(".")
                        if len(parts) > 2:
                            company = domain_to_company.get(".".join(parts[1:]))

            # 策略 3：Mantis 使用者名稱含有公司 domain 關鍵字
            # 例：username="Alphanetworks-User" → 關鍵字 "alphanetworks" → 比對 domain 首段
            if not company:
                username = user.get("username", "").strip().lower()
                if username:
                    for keyword, cand in domain_keyword_to_company.items():
                        if keyword in username:
                            company = cand
                            break

            if company and company.hcp_version != hcp_version:
                company.hcp_version = hcp_version
                self._company_repo.update(company)
                updated += 1

        return updated, ""
