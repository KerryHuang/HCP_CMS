"""CaseVisibilityFilter B+A 聯集 + G-3 排除未指派。"""
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, Company, Staff
from hcp_cms.data.repositories import (
    CaseRepository,
    CompanyRepository,
    StaffRepository,
)
from hcp_cms.web.visibility import CaseVisibilityFilter


@pytest.fixture
def setup(tmp_path: Path):
    db = DatabaseManager(tmp_path / "t.db")
    db.initialize()

    sr = StaffRepository(db.connection)
    sr.insert(Staff(staff_id="S-YOGA", name="YOGA", email="y@x.com", role="cs"))
    sr.insert(Staff(staff_id="S-REBECCA", name="Rebecca", email="r@x.com", role="cs"))

    co_repo = CompanyRepository(db.connection)
    co_repo.insert(Company(company_id="CO-A", name="A 公司", domain="a.com", cs_staff_id="S-YOGA"))
    co_repo.insert(Company(company_id="CO-B", name="B 公司", domain="b.com", cs_staff_id="S-REBECCA"))
    co_repo.insert(Company(company_id="CO-X", name="X 公司", domain="x.com"))

    case_repo = CaseRepository(db.connection)
    case_repo.insert(Case(case_id="C-1", subject="A1", handler="YOGA", company_id="CO-A"))
    case_repo.insert(Case(case_id="C-2", subject="A2", handler="Rebecca", company_id="CO-A"))
    case_repo.insert(Case(case_id="C-3", subject="B1", handler="Rebecca", company_id="CO-B"))
    case_repo.insert(Case(case_id="C-4", subject="A3", handler=None, company_id="CO-A"))
    case_repo.insert(Case(case_id="C-5", subject="A4", handler="", company_id="CO-A"))
    case_repo.insert(Case(case_id="C-6", subject="X1", handler=None, company_id="CO-X"))

    yield db, CaseVisibilityFilter(db.connection)
    db.close()


def test_yoga_sees_handler_and_company_cases(setup) -> None:
    _, vf = setup
    yoga = Staff(staff_id="S-YOGA", name="YOGA", email="y@x.com", role="cs")
    ids = {c.case_id for c in vf.visible_cases(yoga)}
    # C-1 (handler=YOGA) + C-2 (CO-A → YOGA)
    assert ids == {"C-1", "C-2"}


def test_rebecca_sees_only_her_cases(setup) -> None:
    _, vf = setup
    rebecca = Staff(staff_id="S-REBECCA", name="Rebecca", email="r@x.com", role="cs")
    ids = {c.case_id for c in vf.visible_cases(rebecca)}
    # C-2 (handler=Rebecca) + C-3 (handler=Rebecca + CO-B)
    assert ids == {"C-2", "C-3"}


def test_unassigned_cases_excluded(setup) -> None:
    _, vf = setup
    yoga = Staff(staff_id="S-YOGA", name="YOGA", email="y@x.com", role="cs")
    ids = {c.case_id for c in vf.visible_cases(yoga)}
    assert "C-4" not in ids  # handler=None
    assert "C-5" not in ids  # handler=''


def test_handler_case_insensitive(setup) -> None:
    """既有資料有 ~7 筆 JILL 大寫，比對需大小寫不敏感。"""
    db, vf = setup
    case_repo = CaseRepository(db.connection)
    case_repo.insert(Case(case_id="C-7", subject="legacy", handler="YOGA", company_id="CO-A"))
    case_repo.insert(Case(case_id="C-8", subject="legacy", handler="yoga", company_id="CO-A"))
    yoga = Staff(staff_id="S-YOGA", name="YOGA", email="y@x.com", role="cs")
    ids = {c.case_id for c in vf.visible_cases(yoga)}
    assert "C-7" in ids
    assert "C-8" in ids
