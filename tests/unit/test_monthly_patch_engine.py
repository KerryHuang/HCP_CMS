"""MonthlyPatchEngine 單元測試。"""
import json
from pathlib import Path

import pytest

from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
from hcp_cms.data.database import DatabaseManager


@pytest.fixture
def conn():
    db = DatabaseManager(":memory:")
    db.initialize()
    yield db.connection
    db.connection.close()


class TestLoadIssues:
    def test_load_from_json_file(self, conn, tmp_path):
        data = [
            {"issue_no": "0015659", "program_code": "PAYA001", "program_name": "薪資計算",
             "issue_type": "BugFix", "region": "TW", "description": "修正錯誤",
             "impact": "影響薪資", "test_direction": "執行薪資計算"},
        ]
        f = tmp_path / "issues.json"
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        eng = MonthlyPatchEngine(conn)
        patch_id = eng.load_issues(source="manual", month_str="202604", file_path=str(f))
        from hcp_cms.data.repositories import PatchRepository
        issues = PatchRepository(conn).list_issues_by_patch(patch_id)
        assert len(issues) == 1
        assert issues[0].issue_no == "0015659"
        assert issues[0].region == "TW"

    def test_load_from_txt_file(self, conn, tmp_path):
        txt = "0015659\tPAYA001\t薪資計算\tBugFix\tTW\t修正錯誤\t影響薪資\t執行薪資計算\n"
        txt += "0015660\tLEAA001\t請假管理\tEnhancement\t共用\t新增功能\t影響請假\t測試請假\n"
        f = tmp_path / "issues.txt"
        f.write_text(txt, encoding="utf-8")

        eng = MonthlyPatchEngine(conn)
        patch_id = eng.load_issues(source="manual", month_str="202604", file_path=str(f))
        from hcp_cms.data.repositories import PatchRepository
        issues = PatchRepository(conn).list_issues_by_patch(patch_id)
        assert len(issues) == 2
        assert issues[1].issue_no == "0015660"

    def test_creates_patch_record(self, conn, tmp_path):
        f = tmp_path / "issues.json"
        f.write_text("[]", encoding="utf-8")
        eng = MonthlyPatchEngine(conn)
        patch_id = eng.load_issues(source="manual", month_str="202604", file_path=str(f))
        from hcp_cms.data.repositories import PatchRepository
        patch = PatchRepository(conn).get_patch_by_id(patch_id)
        assert patch.type == "monthly"
        assert patch.month_str == "202604"


class TestPrepareTestReports:
    def test_detects_and_converts_simplified(self, conn, tmp_path):
        import docx as python_docx
        doc = python_docx.Document()
        doc.add_paragraph("这是简体中文测试报告")
        report_dir = tmp_path / "11G" / "测试报告"
        report_dir.mkdir(parents=True)
        f = report_dir / "01.IP_20260203_0015659_TESTREPORT_11G.docx"
        doc.save(str(f))

        eng = MonthlyPatchEngine(conn)
        result = eng.prepare_test_reports(str(tmp_path))
        assert result["converted"] >= 1

    def test_validates_naming_format(self, conn, tmp_path):
        import docx as python_docx
        doc = python_docx.Document()
        report_dir = tmp_path / "11G" / "測試報告"
        report_dir.mkdir(parents=True)
        bad_name = report_dir / "wrong_name.docx"
        doc.save(str(bad_name))

        eng = MonthlyPatchEngine(conn)
        result = eng.prepare_test_reports(str(tmp_path))
        assert len(result["invalid_names"]) >= 1


class TestGeneratePatchList:
    @pytest.fixture
    def engine_with_patch(self, conn, tmp_path):
        import json
        data = [
            {"issue_no": "0015659", "program_code": "PAYA001", "program_name": "薪資計算",
             "issue_type": "BugFix", "region": "TW", "description": "修正錯誤",
             "impact": "影響薪資", "test_direction": "執行薪資計算"},
            {"issue_no": "0015660", "program_code": "LEAA001", "program_name": "請假管理",
             "issue_type": "Enhancement", "region": "CN", "description": "新增功能",
             "impact": "影響請假", "test_direction": "測試請假"},
        ]
        f = tmp_path / "issues.json"
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        eng = MonthlyPatchEngine(conn)
        pid = eng.load_issues(source="manual", month_str="202604", file_path=str(f))
        return eng, pid

    def test_generates_two_excel_files(self, engine_with_patch, tmp_path):
        eng, pid = engine_with_patch
        paths = eng.generate_patch_list(pid, output_dir=str(tmp_path))
        assert len(paths) == 2
        names = [Path(p).name for p in paths]
        assert any("11G" in n for n in names)
        assert any("12C" in n for n in names)
        for p in paths:
            assert Path(p).exists()

    def test_excel_has_three_tabs(self, engine_with_patch, tmp_path):
        import openpyxl
        eng, pid = engine_with_patch
        paths = eng.generate_patch_list(pid, output_dir=str(tmp_path), month_str="202604")
        wb = openpyxl.load_workbook(paths[0])
        sheet_names = wb.sheetnames
        assert "IT 發行通知" in sheet_names
        assert "HR 發行通知" in sheet_names
        assert "問題修正補充說明" in sheet_names

    def test_region_color_coding(self, engine_with_patch, tmp_path):
        import openpyxl
        eng, pid = engine_with_patch
        paths = eng.generate_patch_list(pid, output_dir=str(tmp_path), month_str="202604")
        wb = openpyxl.load_workbook(paths[0])
        ws = wb["HR 發行通知"]
        tw_fill = ws.cell(2, 2).fill.fgColor.rgb  # 第一筆 TW
        cn_fill = ws.cell(3, 2).fill.fgColor.rgb  # 第二筆 CN
        assert tw_fill != cn_fill
