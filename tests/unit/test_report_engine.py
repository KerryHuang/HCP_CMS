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
                          system_product="HCP", issue_type="BUG"))
    case_repo.insert(Case(case_id="CS-2026-002", subject="請假設定", company_id="C1",
                          status="已回覆", sent_time="2026/03/15 10:00",
                          actual_reply="2026/03/15 14:00", system_product="HCP", issue_type="操作異常"))
    case_repo.insert(Case(case_id="CS-2026-003", subject="客製化需求", company_id="C2",
                          status="處理中", sent_time="2026/03/20 11:00",
                          issue_type="客制需求", system_product="HCP"))

    qa_repo.insert(QAKnowledge(qa_id="QA-202603-001", question="如何計算", answer="進入模組"))

    return db


class TestReportEngine:
    def test_generate_tracking_table(self, seeded_db, tmp_path):
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_tracking_table("2026/03/01", "2026/03/31", tmp_path / "tracking.xlsx")
        assert path.exists()
        assert path.suffix == ".xlsx"

    def test_tracking_table_sheets(self, seeded_db, tmp_path):
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_tracking_table("2026/03/01", "2026/03/31", tmp_path / "tracking.xlsx")
        wb = openpyxl.load_workbook(str(path))
        sheet_names = wb.sheetnames
        assert "📋 客戶索引" in sheet_names
        assert "問題追蹤總表" in sheet_names
        assert "QA知識庫" in sheet_names
        assert "Mantis提單追蹤" in sheet_names
        wb.close()

    def test_tracking_table_case_data(self, seeded_db, tmp_path):
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_tracking_table("2026/03/01", "2026/03/31", tmp_path / "tracking.xlsx")
        wb = openpyxl.load_workbook(str(path))
        ws = wb["問題追蹤總表"]
        # Header + 3 data rows
        assert ws.max_row == 4  # 1 header + 3 cases
        wb.close()

    def test_tracking_table_custom_sheet(self, seeded_db, tmp_path):
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_tracking_table("2026/03/01", "2026/03/31", tmp_path / "tracking.xlsx")
        wb = openpyxl.load_workbook(str(path))
        assert "客制需求" in wb.sheetnames
        ws = wb["客制需求"]
        assert ws.max_row == 2  # 1 header + 1 custom case
        wb.close()

    def test_generate_monthly_report(self, seeded_db, tmp_path):
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_monthly_report("2026/03/01", "2026/03/31", tmp_path / "report.xlsx")
        assert path.exists()

    def test_monthly_report_kpi(self, seeded_db, tmp_path):
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_monthly_report("2026/03/01", "2026/03/31", tmp_path / "report.xlsx")
        wb = openpyxl.load_workbook(str(path))
        ws = wb["📊 月報摘要"]
        # Row 4: 案件總數 = 3（row 1 標題、row 2 空、row 3 欄位標題）
        assert ws.cell(row=4, column=2).value == 3
        # Row 5: 已回覆 = 1
        assert ws.cell(row=5, column=2).value == 1
        wb.close()

    def test_monthly_report_customer_analysis_sheet(self, seeded_db, tmp_path):
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_monthly_report("2026/03/01", "2026/03/31", tmp_path / "report.xlsx")
        wb = openpyxl.load_workbook(str(path))
        assert "🏢 客戶分析" in wb.sheetnames
        ws = wb["🏢 客戶分析"]
        # 1 header + 2 companies (日月光, 欣興)
        assert ws.max_row == 3
        wb.close()

    def test_report_with_no_data(self, db, tmp_path):
        engine = ReportEngine(db.connection)
        path = engine.generate_monthly_report("2026/01/01", "2026/01/31", tmp_path / "empty.xlsx")
        assert path.exists()
        wb = openpyxl.load_workbook(str(path))
        ws = wb["📊 月報摘要"]
        assert ws.cell(row=4, column=2).value == 0  # total = 0
        wb.close()

    def test_report_header_style(self, seeded_db, tmp_path):
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_tracking_table("2026/03/01", "2026/03/31", tmp_path / "styled.xlsx")
        wb = openpyxl.load_workbook(str(path))
        ws = wb["問題追蹤總表"]
        cell = ws.cell(row=1, column=1)
        assert cell.font.bold is True
        assert cell.font.color.rgb == "00FFFFFF"  # white text
        wb.close()

    def test_customer_index_has_hyperlinks_to_company_sheets(self, seeded_db, tmp_path):
        """客戶索引的快速連結欄位應有超連結指向各公司頁籤。"""
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_tracking_table("2026/03/01", "2026/03/31", tmp_path / "tracking.xlsx")
        wb = openpyxl.load_workbook(str(path))
        ws = wb["📋 客戶索引"]
        # C1（日月光）在第 2 列，快速連結在第 6 欄
        link_cell = ws.cell(row=2, column=6)
        val = str(link_cell.value or "")
        assert val.startswith("=HYPERLINK"), "日月光快速連結應為 HYPERLINK 公式"
        assert "日月光" in val
        # C2（欣興）在第 3 列
        link_cell2 = ws.cell(row=3, column=6)
        val2 = str(link_cell2.value or "")
        assert val2.startswith("=HYPERLINK"), "欣興快速連結應為 HYPERLINK 公式"
        wb.close()

    def test_company_sheet_has_back_link_to_index(self, seeded_db, tmp_path):
        """各公司頁籤第一列應有返回客戶索引的 HYPERLINK 公式。"""
        engine = ReportEngine(seeded_db.connection)
        path = engine.generate_tracking_table("2026/03/01", "2026/03/31", tmp_path / "tracking.xlsx")
        wb = openpyxl.load_workbook(str(path))
        # 日月光的頁籤
        ws_ase = wb["ase.com(日月光)_問題"]
        back_cell = ws_ase.cell(row=1, column=1)
        val = str(back_cell.value or "")
        assert val.startswith("=HYPERLINK"), "公司頁籤第一列應有 HYPERLINK 公式"
        assert "客戶索引" in val
        # 表頭應在第 2 列
        header_cell = ws_ase.cell(row=2, column=1)
        assert header_cell.value == "案件編號"
        wb.close()
