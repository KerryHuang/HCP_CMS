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
        # ReportWriter 寫法：row 1 = 標題列（header），row 2 = 欄位標題，row 3 = 案件總數
        assert ws.cell(row=3, column=2).value == 3
        # Row 4: 已回覆 = 1
        assert ws.cell(row=4, column=2).value == 1
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
        # ReportWriter 寫法：row 3 = 案件總數
        assert ws.cell(row=3, column=2).value == 0  # total = 0
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

    def test_customer_index_has_link_text(self, seeded_db):
        """客戶索引的快速連結欄位應包含各公司連結文字。"""
        engine = ReportEngine(seeded_db.connection)
        data = engine.build_tracking_table("2026/03/01", "2026/03/31")
        index_rows = data["📋 客戶索引"]
        # 日月光 in row 1 (index 1)，連結文字在第 6 欄（index 5）
        assert "日月光" in str(index_rows[1][5])

    def test_company_sheet_has_back_link_text(self, seeded_db):
        """各公司頁籤第一列應有返回客戶索引的文字。"""
        engine = ReportEngine(seeded_db.connection)
        data = engine.build_tracking_table("2026/03/01", "2026/03/31")
        ase_key = [k for k in data if "日月光" in k][0]
        assert data[ase_key][0][0] == "↩ 返回客戶索引"

    # ── build_tracking_table 測試 ──────────────────────────────────────────

    def test_build_tracking_table_returns_dict(self, seeded_db):
        engine = ReportEngine(seeded_db.connection)
        data = engine.build_tracking_table("2026/03/01", "2026/03/31")
        assert isinstance(data, dict)
        assert "📋 客戶索引" in data
        assert "問題追蹤總表" in data
        assert "QA知識庫" in data
        assert "Mantis提單追蹤" in data

    def test_build_tracking_table_sheet_structure(self, seeded_db):
        engine = ReportEngine(seeded_db.connection)
        data = engine.build_tracking_table("2026/03/01", "2026/03/31")
        index_sheet = data["📋 客戶索引"]
        assert index_sheet[0] == ["#", "公司名稱", "Email 域名", "聯絡方式", "案件數", "快速連結"]
        tracking_sheet = data["問題追蹤總表"]
        assert len(tracking_sheet) == 4  # 1 header + 3 data rows

    def test_build_tracking_table_custom_sheet(self, seeded_db):
        engine = ReportEngine(seeded_db.connection)
        data = engine.build_tracking_table("2026/03/01", "2026/03/31")
        assert "客制需求" in data
        assert len(data["客制需求"]) == 2  # 1 header + 1 custom case

    def test_build_tracking_table_company_sheets(self, seeded_db):
        engine = ReportEngine(seeded_db.connection)
        data = engine.build_tracking_table("2026/03/01", "2026/03/31")
        ase_key = [k for k in data if "日月光" in k]
        assert len(ase_key) == 1
        ase_rows = data[ase_key[0]]
        assert ase_rows[0][0] == "↩ 返回客戶索引"
        assert ase_rows[1][0] == "案件編號"
        assert len(ase_rows) == 4  # link + header + 2 cases

    # ── build_monthly_report 測試 ──────────────────────────────────────────

    def test_build_monthly_report_returns_dict(self, seeded_db):
        engine = ReportEngine(seeded_db.connection)
        data = engine.build_monthly_report("2026/03/01", "2026/03/31")
        assert isinstance(data, dict)
        assert "📊 月報摘要" in data
        assert "📋 案件明細" in data
        assert "🏢 客戶分析" in data

    def test_build_monthly_report_kpi(self, seeded_db):
        engine = ReportEngine(seeded_db.connection)
        data = engine.build_monthly_report("2026/03/01", "2026/03/31")
        summary = data["📊 月報摘要"]
        # summary[0] = title row, summary[1] = header row, summary[2:] = KPI data rows
        total_row = summary[2]
        assert total_row[0] == "案件總數"
        assert total_row[1] == 3

    def test_build_monthly_report_case_detail(self, seeded_db):
        engine = ReportEngine(seeded_db.connection)
        data = engine.build_monthly_report("2026/03/01", "2026/03/31")
        detail = data["📋 案件明細"]
        assert detail[0][0] == "案件編號"  # header
        assert len(detail) == 4  # 1 header + 3 cases

    def test_build_monthly_report_customer_analysis(self, seeded_db):
        engine = ReportEngine(seeded_db.connection)
        data = engine.build_monthly_report("2026/03/01", "2026/03/31")
        analysis = data["🏢 客戶分析"]
        assert analysis[0] == ["客戶", "已回覆", "處理中", "合計"]
        assert len(analysis) == 3  # 1 header + 2 companies

    def test_build_monthly_report_no_data(self, db):
        engine = ReportEngine(db.connection)
        data = engine.build_monthly_report("2026/01/01", "2026/01/31")
        summary = data["📊 月報摘要"]
        total_row = summary[2]
        assert total_row[1] == 0


from hcp_cms.data.models import MantisTicket
from hcp_cms.data.repositories import MantisRepository


@pytest.fixture
def mantis_seeded_db(db: DatabaseManager) -> DatabaseManager:
    repo = MantisRepository(db.connection)
    repo.upsert(MantisTicket(
        ticket_id="MT-0001", summary="系統當機", status="assigned",
        priority="urgent", handler="王小明", last_updated="2026/03/13 10:00:00",
    ))
    repo.upsert(MantisTicket(
        ticket_id="MT-0002", summary="薪資計算錯誤", status="assigned",
        priority="normal", handler="李大華", last_updated="2026/03/24 10:00:00",
    ))
    repo.upsert(MantisTicket(
        ticket_id="MT-0003", summary="登入頁跑版", status="resolved",
        priority="low", handler="張三", last_updated="2026/03/10 10:00:00",
    ))
    return db


class TestBuildMantisSheet:
    def test_returns_list_of_dicts(self, mantis_seeded_db):
        engine = ReportEngine(mantis_seeded_db.connection)
        rows = engine.build_mantis_sheet()
        assert isinstance(rows, list)
        assert len(rows) == 3

    def test_each_row_has_category(self, mantis_seeded_db):
        engine = ReportEngine(mantis_seeded_db.connection)
        rows = engine.build_mantis_sheet()
        for row in rows:
            assert "category" in row
            assert row["category"] in ("closed", "salary", "high", "normal")

    def test_sorting_high_before_closed(self, mantis_seeded_db):
        """high 優先度排在 closed 之前。"""
        engine = ReportEngine(mantis_seeded_db.connection)
        rows = engine.build_mantis_sheet()
        categories = [r["category"] for r in rows]
        assert categories.index("high") < categories.index("closed")
