"""Tests for ReportEngine."""

from pathlib import Path

import openpyxl
import pytest

from hcp_cms.core.report_engine import ReportEngine
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, Company, QAKnowledge
from hcp_cms.data.repositories import CaseRepository, CompanyRepository, QARepository


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def seeded_db(db: DatabaseManager) -> DatabaseManager:
    comp_repo = CompanyRepository(db.connection)
    case_repo = CaseRepository(db.connection)
    qa_repo = QARepository(db.connection)

    comp_repo.insert(Company(company_id="C1", name="日月光", domain="ase.com"))
    comp_repo.insert(Company(company_id="C2", name="欣興", domain="uni.com"))

    case_repo.insert(Case(case_id="CS-2026-001", subject="薪資問題", company_id="C1",
                          status="處理中", priority="高", sent_time="2026/03/10 09:00",
                          system_product="HCP", issue_type="BUG", replied="否"))
    case_repo.insert(Case(case_id="CS-2026-002", subject="請假設定", company_id="C1",
                          status="已回覆", replied="是", sent_time="2026/03/15 10:00",
                          actual_reply="2026/03/15 14:00", system_product="HCP", issue_type="操作異常"))
    case_repo.insert(Case(case_id="CS-2026-003", subject="客製化需求", company_id="C2",
                          status="處理中", sent_time="2026/03/20 11:00",
                          issue_type="客制需求", system_product="HCP", replied="否"))

    qa_repo.insert(QAKnowledge(qa_id="QA-202603-001", question="如何計算", answer="進入模組"))

    return db


class TestReportEngine:
    def test_generate_tracking_table(self, seeded_db, tmp_path):
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_tracking_table(2026, 3, tmp_path / "tracking.xlsx")
        assert path.exists()
        assert path.suffix == ".xlsx"

    def test_tracking_table_sheets(self, seeded_db, tmp_path):
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_tracking_table(2026, 3, tmp_path / "tracking.xlsx")
        wb = openpyxl.load_workbook(str(path))
        sheet_names = wb.sheetnames
        assert "客戶索引" in sheet_names
        assert "問題追蹤總表" in sheet_names
        assert "QA知識庫" in sheet_names
        wb.close()

    def test_tracking_table_case_data(self, seeded_db, tmp_path):
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_tracking_table(2026, 3, tmp_path / "tracking.xlsx")
        wb = openpyxl.load_workbook(str(path))
        ws = wb["問題追蹤總表"]
        # Header + 3 data rows
        assert ws.max_row == 4  # 1 header + 3 cases
        wb.close()

    def test_tracking_table_custom_sheet(self, seeded_db, tmp_path):
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_tracking_table(2026, 3, tmp_path / "tracking.xlsx")
        wb = openpyxl.load_workbook(str(path))
        assert "客制需求" in wb.sheetnames
        ws = wb["客制需求"]
        assert ws.max_row == 2  # 1 header + 1 custom case
        wb.close()

    def test_generate_monthly_report(self, seeded_db, tmp_path):
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_monthly_report(2026, 3, tmp_path / "report.xlsx")
        assert path.exists()

    def test_monthly_report_kpi(self, seeded_db, tmp_path):
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_monthly_report(2026, 3, tmp_path / "report.xlsx")
        wb = openpyxl.load_workbook(str(path))
        ws = wb["月報摘要"]
        # Row 2: 案件總數 = 3
        assert ws.cell(row=2, column=2).value == 3
        # Row 3: 已回覆 = 1
        assert ws.cell(row=3, column=2).value == 1
        wb.close()

    def test_monthly_report_open_cases_sheet(self, seeded_db, tmp_path):
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_monthly_report(2026, 3, tmp_path / "report.xlsx")
        wb = openpyxl.load_workbook(str(path))
        assert "未結案清單" in wb.sheetnames
        ws = wb["未結案清單"]
        assert ws.max_row == 3  # 1 header + 2 open cases
        wb.close()

    def test_report_with_no_data(self, db, tmp_path):
        engine = ReportEngine(db.connection)
        path = engine.generate_monthly_report(2026, 1, tmp_path / "empty.xlsx")
        assert path.exists()
        wb = openpyxl.load_workbook(str(path))
        ws = wb["月報摘要"]
        assert ws.cell(row=2, column=2).value == 0  # total = 0
        wb.close()

    def test_report_header_style(self, seeded_db, tmp_path):
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_tracking_table(2026, 3, tmp_path / "styled.xlsx")
        wb = openpyxl.load_workbook(str(path))
        ws = wb["問題追蹤總表"]
        cell = ws.cell(row=1, column=1)
        assert cell.font.bold is True
        assert cell.font.color.rgb == "00FFFFFF"  # white text
        wb.close()
