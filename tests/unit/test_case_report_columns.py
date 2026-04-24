"""cs_cases 新增 4 欄位（problem_level/problem/cause/solution）測試。"""

from __future__ import annotations

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, Company
from hcp_cms.data.repositories import CaseRepository, CompanyRepository


@pytest.fixture()
def conn(tmp_path):
    dbm = DatabaseManager(tmp_path / "t.db")
    dbm.initialize()
    yield dbm.connection
    dbm.close()


def test_case_has_report_columns(conn):
    cursor = conn.execute("PRAGMA table_info(cs_cases)")
    cols = {row[1] for row in cursor.fetchall()}
    assert {"problem_level", "problem", "cause", "solution"} <= cols


def test_case_repository_round_trip_report_fields(conn):
    CompanyRepository(conn).insert(Company(company_id="acme", name="ACME", domain="acme.com"))
    repo = CaseRepository(conn)
    case = Case(
        case_id="CS-REP-001",
        subject="薪資計算錯誤",
        company_id="acme",
        error_type="薪資獎金計算",
        problem_level="A",
        problem="月底結算薪資少算加班費",
        cause="加班費公式漏判夜班",
        solution="修正公式 + 補發差額",
    )
    repo.insert(case)
    got = repo.get_by_id("CS-REP-001")
    assert got is not None
    assert got.problem_level == "A"
    assert got.problem == "月底結算薪資少算加班費"
    assert got.cause == "加班費公式漏判夜班"
    assert got.solution == "修正公式 + 補發差額"
