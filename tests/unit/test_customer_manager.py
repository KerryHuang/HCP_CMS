# tests/unit/test_customer_manager.py
"""Tests for CustomerManager."""

import pytest

from hcp_cms.core.customer_manager import CustomerManager
from hcp_cms.data.database import DatabaseManager


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(tmp_path / "test.db")
    manager.initialize()
    yield manager
    manager.close()


class TestBulkUpsertCompanies:
    def test_insert_new_companies(self, db):
        mgr = CustomerManager(db.connection)
        rows = [
            {"name": "ABC 公司", "domain": "abc.com.tw", "alias": "ABC",
             "contact_info": "", "cs_staff_id": None, "sales_staff_id": None},
            {"name": "XYZ 股份", "domain": "xyz.com.tw", "alias": "",
             "contact_info": "", "cs_staff_id": None, "sales_staff_id": None},
        ]
        inserted, updated = mgr.bulk_upsert_companies(rows)
        assert inserted == 2
        assert updated == 0

    def test_update_existing_company(self, db):
        mgr = CustomerManager(db.connection)
        rows = [{"name": "ABC 公司", "domain": "abc.com.tw", "alias": "",
                 "contact_info": "", "cs_staff_id": None, "sales_staff_id": None}]
        mgr.bulk_upsert_companies(rows)
        rows2 = [{"name": "ABC 公司 v2", "domain": "abc.com.tw", "alias": "ABC2",
                  "contact_info": "", "cs_staff_id": None, "sales_staff_id": None}]
        inserted, updated = mgr.bulk_upsert_companies(rows2)
        assert inserted == 0
        assert updated == 1

    def test_empty_domain_skipped(self, db):
        mgr = CustomerManager(db.connection)
        rows = [{"name": "無網域公司", "domain": "", "alias": "",
                 "contact_info": "", "cs_staff_id": None, "sales_staff_id": None}]
        inserted, updated = mgr.bulk_upsert_companies(rows)
        assert inserted == 0

    def test_returns_count_tuple(self, db):
        mgr = CustomerManager(db.connection)
        result = mgr.bulk_upsert_companies([])
        assert result == (0, 0)

    def test_company_stores_cs_staff_id(self, db):
        from hcp_cms.data.models import Staff
        from hcp_cms.data.repositories import CompanyRepository, StaffRepository
        StaffRepository(db.connection).insert(
            Staff(staff_id="STAFF-001", name="JILL", email="jill@ares.com.tw", role="cs")
        )
        mgr = CustomerManager(db.connection)
        rows = [{"name": "ABC 公司", "domain": "abc.com.tw", "alias": "",
                 "contact_info": "", "cs_staff_id": "STAFF-001", "sales_staff_id": None}]
        mgr.bulk_upsert_companies(rows)
        company = CompanyRepository(db.connection).get_by_domain("abc.com.tw")
        assert company.cs_staff_id == "STAFF-001"


class TestBulkUpsertStaff:
    def test_insert_new_staff(self, db):
        mgr = CustomerManager(db.connection)
        rows = [
            {"name": "JILL", "email": "jill@ares.com.tw", "role": "cs",
             "phone": "", "notes": ""},
            {"name": "MIKE", "email": "mike@ares.com.tw", "role": "sales",
             "phone": "", "notes": ""},
        ]
        inserted, updated = mgr.bulk_upsert_staff(rows)
        assert inserted == 2

    def test_update_existing_staff(self, db):
        mgr = CustomerManager(db.connection)
        rows = [{"name": "JILL", "email": "jill@ares.com.tw", "role": "cs",
                 "phone": "", "notes": ""}]
        mgr.bulk_upsert_staff(rows)
        rows2 = [{"name": "JILL-NEW", "email": "jill@ares.com.tw", "role": "cs",
                  "phone": "0912", "notes": ""}]
        inserted, updated = mgr.bulk_upsert_staff(rows2)
        assert inserted == 0
        assert updated == 1

    def test_empty_email_skipped(self, db):
        mgr = CustomerManager(db.connection)
        rows = [{"name": "無 Email", "email": "", "role": "cs",
                 "phone": "", "notes": ""}]
        inserted, updated = mgr.bulk_upsert_staff(rows)
        assert inserted == 0


class TestResolveHandlerByDomain:
    def test_resolve_handler_from_domain(self, db):
        from hcp_cms.data.models import Company, Staff
        from hcp_cms.data.repositories import CompanyRepository, StaffRepository
        StaffRepository(db.connection).insert(
            Staff(staff_id="STAFF-001", name="JILL", email="jill@ares.com.tw", role="cs")
        )
        CompanyRepository(db.connection).insert(
            Company(company_id="COMP-001", name="ABC 公司", domain="abc.com.tw",
                    cs_staff_id="STAFF-001")
        )
        mgr = CustomerManager(db.connection)
        handler = mgr.resolve_handler_by_domain("abc.com.tw")
        assert handler == "JILL"

    def test_resolve_handler_no_company(self, db):
        mgr = CustomerManager(db.connection)
        assert mgr.resolve_handler_by_domain("unknown.com") is None

    def test_resolve_handler_no_staff_assigned(self, db):
        from hcp_cms.data.models import Company
        from hcp_cms.data.repositories import CompanyRepository
        CompanyRepository(db.connection).insert(
            Company(company_id="COMP-001", name="XYZ 公司", domain="xyz.com.tw")
        )
        mgr = CustomerManager(db.connection)
        assert mgr.resolve_handler_by_domain("xyz.com.tw") is None
