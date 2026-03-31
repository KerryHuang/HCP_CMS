# src/hcp_cms/core/customer_manager.py
"""CustomerManager — 客戶公司與人員的業務邏輯層。"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from hcp_cms.data.models import Company, Staff
from hcp_cms.data.repositories import CompanyRepository, StaffRepository


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
            domain = (row.get("domain") or "").strip().lower()
            name = (row.get("name") or "").strip()
            if not domain or not name:
                continue
            existing = self._company_repo.get_by_domain(domain)
            if existing:
                existing.name = name
                existing.alias = (row.get("alias") or "").strip() or existing.alias
                existing.contact_info = (row.get("contact_info") or "").strip() or existing.contact_info
                if "cs_staff_id" in row:
                    existing.cs_staff_id = row["cs_staff_id"] or None
                if "sales_staff_id" in row:
                    existing.sales_staff_id = row["sales_staff_id"] or None
                self._company_repo.update(existing)
                updated += 1
            else:
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
