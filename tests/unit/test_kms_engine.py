"""Tests for KMSEngine."""

from pathlib import Path
import pytest
import openpyxl

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case
from hcp_cms.data.repositories import CaseRepository
from hcp_cms.core.kms_engine import KMSEngine


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def kms(db: DatabaseManager) -> KMSEngine:
    return KMSEngine(db.connection)


class TestKMSEngine:
    def test_create_and_search(self, kms):
        kms.create_qa(question="薪資如何計算", answer="進入薪資模組")
        results = kms.search("薪資")
        assert len(results) > 0
        assert results[0].question == "薪資如何計算"

    def test_search_with_filter(self, kms):
        kms.create_qa(question="HCP 薪資", answer="A", system_product="HCP")
        kms.create_qa(question="ERP 薪資", answer="B", system_product="ERP")
        results = kms.search("薪資", system_product="HCP")
        assert all(r.system_product == "HCP" for r in results)

    def test_update_qa(self, kms):
        qa = kms.create_qa(question="舊問題", answer="舊回覆")
        updated = kms.update_qa(qa.qa_id, question="新問題", answer="新回覆")
        assert updated.question == "新問題"
        # Search should find updated content
        results = kms.search("新問題")
        assert len(results) > 0

    def test_delete_qa(self, kms):
        qa = kms.create_qa(question="待刪除", answer="test")
        kms.delete_qa(qa.qa_id)
        results = kms.search("待刪除")
        assert len(results) == 0

    def test_auto_extract_with_question(self, kms, db):
        case = Case(
            case_id="CS-2026-001",
            subject="請問薪資如何計算",
            progress="進入薪資模組設定",
            system_product="HCP",
        )
        CaseRepository(db.connection).insert(case)
        qa = kms.auto_extract_qa(case)
        assert qa is not None
        assert qa.source == "email"
        assert qa.source_case_id == "CS-2026-001"

    def test_auto_extract_no_question(self, kms):
        case = Case(case_id="CS-2026-002", subject="系統更新通知", progress="已更新")
        qa = kms.auto_extract_qa(case)
        assert qa is None

    def test_import_export_roundtrip(self, kms, tmp_path):
        # Create some QAs
        kms.create_qa(question="Q1", answer="A1", solution="S1", keywords="k1")
        kms.create_qa(question="Q2", answer="A2")

        # Export
        export_path = tmp_path / "qa_export.xlsx"
        kms.export_to_excel(export_path)
        assert export_path.exists()

        # Verify Excel content
        wb = openpyxl.load_workbook(str(export_path))
        ws = wb.active
        rows = list(ws.iter_rows(min_row=2, values_only=True))
        assert len(rows) == 2
        wb.close()

    def test_import_from_excel(self, kms, tmp_path):
        # Create Excel file
        import_path = tmp_path / "qa_import.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["問題", "回覆", "解決方案", "關鍵字"])
        ws.append(["如何設定薪資", "進入設定頁面", "步驟1...", "薪資 設定"])
        ws.append(["請假規則", "參考手冊", None, None])
        wb.save(str(import_path))

        count = kms.import_from_excel(import_path)
        assert count == 2

        # Verify searchable
        results = kms.search("薪資")
        assert len(results) > 0
