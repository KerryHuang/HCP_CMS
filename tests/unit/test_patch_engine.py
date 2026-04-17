"""SinglePatchEngine 單元測試。"""
from pathlib import Path

import pytest

from hcp_cms.core.patch_engine import SinglePatchEngine
from hcp_cms.data.database import DatabaseManager


@pytest.fixture
def conn():
    db = DatabaseManager(":memory:")
    db.initialize()
    yield db.connection
    db.connection.close()


@pytest.fixture
def patch_dir(tmp_path: Path) -> Path:
    (tmp_path / "form").mkdir()
    (tmp_path / "sql").mkdir()
    (tmp_path / "muti").mkdir()
    (tmp_path / "form" / "PAYROLL.fmx").write_text("form")
    (tmp_path / "sql" / "update.sql").write_text("sql")
    (tmp_path / "setup.bat").write_text("bat")
    (tmp_path / "ReleaseNote.docx").write_bytes(b"")
    return tmp_path


class TestScanPatchDir:
    def test_finds_form_sql_muti_files(self, conn, patch_dir):
        eng = SinglePatchEngine(conn)
        result = eng.scan_patch_dir(str(patch_dir))
        assert "PAYROLL.fmx" in result["form_files"]
        assert "update.sql" in result["sql_files"]
        assert result["setup_bat"] is True
        assert result["missing"] == []

    def test_missing_muti_not_error(self, conn, patch_dir):
        import shutil
        shutil.rmtree(patch_dir / "muti")
        eng = SinglePatchEngine(conn)
        result = eng.scan_patch_dir(str(patch_dir))
        assert result["muti_files"] == []
        assert "muti/" not in result["missing"]

    def test_missing_form_reported(self, conn, patch_dir):
        import shutil
        shutil.rmtree(patch_dir / "form")
        eng = SinglePatchEngine(conn)
        result = eng.scan_patch_dir(str(patch_dir))
        assert "form/" in result["missing"]

    def test_detects_release_note(self, conn, patch_dir):
        eng = SinglePatchEngine(conn)
        result = eng.scan_patch_dir(str(patch_dir))
        assert result["release_note"] is not None
        assert "ReleaseNote" in result["release_note"]


class TestReadReleaseDoc:
    def test_parse_docx_returns_issues(self, conn, tmp_path):
        docx = pytest.importorskip("docx", reason="python-docx 未安裝，跳過")
        doc = docx.Document()
        doc.add_paragraph("Bug Fix")
        doc.add_paragraph("0015659  薪資計算錯誤修正")
        doc.add_paragraph("0015660  加班費計算異常")
        doc.add_paragraph("Enhancement")
        doc.add_paragraph("0015661  新增匯出功能")
        p = tmp_path / "ReleaseNote.docx"
        doc.save(str(p))

        eng = SinglePatchEngine(conn)
        issues = eng.read_release_doc(str(p))
        assert len(issues) == 3
        assert issues[0]["issue_no"] == "0015659"
        assert issues[0]["issue_type"] == "BugFix"
        assert issues[0]["description"] == "薪資計算錯誤修正"
        assert issues[0]["region"] == "共用"
        assert issues[2]["issue_type"] == "Enhancement"

    def test_missing_file_returns_empty(self, conn, tmp_path):
        eng = SinglePatchEngine(conn)
        result = eng.read_release_doc(str(tmp_path / "nonexist.docx"))
        assert result == []
