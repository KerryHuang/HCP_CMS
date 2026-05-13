"""WebAuthManager 測試。"""
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Staff
from hcp_cms.data.repositories import StaffRepository
from hcp_cms.web.auth import WebAuthManager


@pytest.fixture
def auth(tmp_path: Path):
    db = DatabaseManager(tmp_path / "t.db")
    db.initialize()
    sr = StaffRepository(db.connection)
    sr.insert(Staff(staff_id="S001", name="jill", email="jill@x.com", role="cs"))
    sr.insert(Staff(staff_id="S002", name="YOGA", email="yoga@x.com", role="cs"))
    sr.insert(Staff(staff_id="S003", name="Rebecca", email="rebecca@x.com", role="cs"))
    sr.insert(Staff(staff_id="S004", name="老闆", email="boss@x.com", role="admin"))
    yield WebAuthManager(db.connection)
    db.close()


def test_list_cs_staff_returns_only_cs_role(auth: WebAuthManager) -> None:
    staff = auth.list_cs_staff()
    names = {s.name for s in staff}
    assert names == {"jill", "YOGA", "Rebecca"}


def test_get_staff_by_id_existing(auth: WebAuthManager) -> None:
    s = auth.get_staff_by_id("S001")
    assert s is not None
    assert s.name == "jill"


def test_get_staff_by_id_missing(auth: WebAuthManager) -> None:
    assert auth.get_staff_by_id("S999") is None


def test_get_staff_by_id_non_cs_returns_none(auth: WebAuthManager) -> None:
    """非 cs role 的 staff 不可透過此方法登入。"""
    assert auth.get_staff_by_id("S004") is None
