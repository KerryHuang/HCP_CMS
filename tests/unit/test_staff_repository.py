"""Tests for StaffRepository."""

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Staff
from hcp_cms.data.repositories import StaffRepository


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(tmp_path / "test.db")
    manager.initialize()
    yield manager
    manager.close()


def _staff(staff_id="STAFF-001", name="JILL", email="jill@ares.com.tw", role="cs") -> Staff:
    return Staff(staff_id=staff_id, name=name, email=email, role=role)


class TestStaffRepository:
    def test_insert_and_get_by_id(self, db):
        repo = StaffRepository(db.connection)
        repo.insert(_staff())
        result = repo.get_by_id("STAFF-001")
        assert result is not None
        assert result.name == "JILL"
        assert result.email == "jill@ares.com.tw"

    def test_get_by_email(self, db):
        repo = StaffRepository(db.connection)
        repo.insert(_staff())
        result = repo.get_by_email("jill@ares.com.tw")
        assert result is not None
        assert result.staff_id == "STAFF-001"

    def test_get_by_email_case_insensitive(self, db):
        repo = StaffRepository(db.connection)
        repo.insert(_staff())
        result = repo.get_by_email("JILL@ARES.COM.TW")
        assert result is not None

    def test_list_by_role_cs(self, db):
        repo = StaffRepository(db.connection)
        repo.insert(_staff("STAFF-001", "JILL", "jill@ares.com.tw", "cs"))
        repo.insert(_staff("STAFF-002", "MIKE", "mike@ares.com.tw", "sales"))
        cs_list = repo.list_by_role("cs")
        assert len(cs_list) == 1
        assert cs_list[0].name == "JILL"

    def test_list_by_role_sales(self, db):
        repo = StaffRepository(db.connection)
        repo.insert(_staff("STAFF-001", "JILL", "jill@ares.com.tw", "cs"))
        repo.insert(_staff("STAFF-002", "MIKE", "mike@ares.com.tw", "sales"))
        sales_list = repo.list_by_role("sales")
        assert len(sales_list) == 1
        assert sales_list[0].name == "MIKE"

    def test_list_all(self, db):
        repo = StaffRepository(db.connection)
        repo.insert(_staff("STAFF-001", "JILL", "jill@ares.com.tw", "cs"))
        repo.insert(_staff("STAFF-002", "MIKE", "mike@ares.com.tw", "sales"))
        assert len(repo.list_all()) == 2

    def test_update(self, db):
        repo = StaffRepository(db.connection)
        s = _staff()
        repo.insert(s)
        s.name = "JILL-UPDATED"
        s.phone = "0912345678"
        repo.update(s)
        result = repo.get_by_id("STAFF-001")
        assert result.name == "JILL-UPDATED"
        assert result.phone == "0912345678"

    def test_delete(self, db):
        repo = StaffRepository(db.connection)
        repo.insert(_staff())
        repo.delete("STAFF-001")
        assert repo.get_by_id("STAFF-001") is None

    def test_upsert_insert_new(self, db):
        repo = StaffRepository(db.connection)
        repo.upsert(_staff())
        assert repo.get_by_email("jill@ares.com.tw") is not None

    def test_upsert_update_existing(self, db):
        repo = StaffRepository(db.connection)
        repo.upsert(_staff(name="OLD"))
        repo.upsert(_staff(name="NEW"))
        result = repo.get_by_email("jill@ares.com.tw")
        assert result.name == "NEW"
