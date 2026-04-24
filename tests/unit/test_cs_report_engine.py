"""CSReportEngine：抓取全部案件 → 轉 10 欄 row。"""

from __future__ import annotations

import pytest

from hcp_cms.core.cs_report_engine import CSReportEngine
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, Company
from hcp_cms.data.repositories import CaseRepository, CompanyRepository


@pytest.fixture()
def conn(tmp_path):
    dbm = DatabaseManager(tmp_path / "t.db")
    dbm.initialize()
    yield dbm.connection
    dbm.close()


def _seed_case(conn, **overrides):
    # 若 company 尚未建立，才插入（多次呼叫時避免重複 insert）
    company_repo = CompanyRepository(conn)
    if not company_repo.get_by_id("acme"):
        company_repo.insert(Company(company_id="acme", name="ACME 公司", domain="acme.com"))
    defaults = dict(
        case_id="CS-001",
        subject="薪資計算錯誤",
        company_id="acme",
        sent_time="2026/04/01 09:00:00",
        issue_type="BUG",
        error_type="薪資獎金計算",
        problem="薪資少算加班",
        cause="公式錯誤",
        solution="修正公式",
        actual_reply="已補發差額",
    )
    defaults.update(overrides)
    CaseRepository(conn).insert(Case(**defaults))


def test_build_rows_contains_ten_columns(conn):
    _seed_case(conn)
    engine = CSReportEngine(conn)
    rows = engine.build_rows()
    assert len(rows) == 1
    r = rows[0]
    assert r.date == "2026/04/01"
    assert r.customer == "ACME 公司"
    assert r.problem_raw == "薪資少算加班"
    assert r.problem_level == "A"
    assert r.module == "薪資獎金計算"
    assert r.type_ == "BUG"
    assert r.summary
    assert r.suggested_reply == "修正公式"  # 優先 solution
    assert r.processed in ("Y", "N")
    assert r.notes is not None


def test_problem_level_uses_manual_override(conn):
    _seed_case(conn, problem_level="B")
    engine = CSReportEngine(conn)
    rows = engine.build_rows()
    assert rows[0].problem_level == "B"


def test_type_maps_to_four_categories(conn):
    _seed_case(conn, case_id="CS-001", issue_type="BUG")
    _seed_case(conn, case_id="CS-OP", subject="客製程式", issue_type="客制需求")
    engine = CSReportEngine(conn)
    rows = {r.case_id: r for r in engine.build_rows()}
    assert rows["CS-001"].type_ == "BUG"
    assert rows["CS-OP"].type_ == "OP"


def test_processed_flag_based_on_status(conn):
    _seed_case(conn, case_id="CS-DONE", status="已完成")
    _seed_case(conn, case_id="CS-OPEN", status="處理中")
    engine = CSReportEngine(conn)
    rows = {r.case_id: r for r in engine.build_rows()}
    assert rows["CS-DONE"].processed == "Y"
    assert rows["CS-OPEN"].processed == "N"


def test_to_sheet_values_returns_10_cells_per_row(conn):
    _seed_case(conn)
    engine = CSReportEngine(conn)
    values = engine.to_sheet_values()
    # header 列 + 1 筆資料
    assert len(values) == 2
    assert len(values[0]) == 10
    assert values[0][0] == "日期"
    assert len(values[1]) == 10
