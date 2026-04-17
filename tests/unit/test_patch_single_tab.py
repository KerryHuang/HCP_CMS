"""SinglePatchTab 單元測試。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import PatchRecord
from hcp_cms.data.repositories import PatchRepository


@pytest.fixture
def db(tmp_path):
    dm = DatabaseManager(str(tmp_path / "t.db"))
    dm.initialize()
    conn = dm.connection
    yield conn
    conn.close()


def test_single_patch_tab_instantiates(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    assert tab._folder_edit is not None
    assert tab._issue_table is not None
    assert tab._log is not None


def test_browse_sets_folder(qtbot, db, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory",
        lambda *a, **kw: str(tmp_path),
    )
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._on_browse_clicked()
    assert tab._folder_edit.text() == str(tmp_path)
    assert tab._patch_dir == str(tmp_path)


def test_start_disabled_without_folder(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._on_start_clicked()  # 無資料夾，應直接 return，不 crash


def test_start_scan_creates_patch_record(qtbot, db, tmp_path):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    with patch("hcp_cms.core.patch_engine.SinglePatchEngine.scan_patch_dir",
               return_value={"form_files": [], "sql_files": [], "muti_files": [],
                             "setup_bat": False, "release_note": None,
                             "install_guide": None, "missing": []}), \
         patch("hcp_cms.core.patch_engine.SinglePatchEngine.setup_new_patch",
               return_value=1):
        tab = SinglePatchTab(conn=db)
        qtbot.addWidget(tab)
        tab._patch_dir = str(tmp_path)
        tab._folder_edit.setText(str(tmp_path))
        with qtbot.waitSignal(tab._scan_done, timeout=3000):
            tab._on_start_clicked()


def test_generate_disabled_without_patch_id(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._on_generate_excel_clicked()  # patch_id=None，應 return，不 crash


def test_setup_new_patch_creates_record(db):
    from hcp_cms.core.patch_engine import SinglePatchEngine
    engine = SinglePatchEngine(db)
    pid = engine.setup_new_patch("/tmp/patch_test")
    repo = PatchRepository(db)
    record = repo.get_patch_by_id(pid)
    assert record is not None
    assert record.type == "single"
    assert record.patch_dir == "/tmp/patch_test"


def test_load_issues_from_release_doc_empty(db):
    from hcp_cms.core.patch_engine import SinglePatchEngine
    repo = PatchRepository(db)
    pid = repo.insert_patch(PatchRecord(type="single"))
    engine = SinglePatchEngine(db)
    with patch.object(engine, "read_release_doc", return_value=[]):
        count = engine.load_issues_from_release_doc(pid, "/fake/path.doc")
    assert count == 0


def test_load_issues_from_release_doc_inserts(db):
    from hcp_cms.core.patch_engine import SinglePatchEngine
    repo = PatchRepository(db)
    pid = repo.insert_patch(PatchRecord(type="single"))
    engine = SinglePatchEngine(db)
    fake_issues = [
        {"issue_no": "001", "description": "修正薪資", "issue_type": "BugFix",
         "region": "TW", "program_code": "PA001", "program_name": "薪資計算"},
        {"issue_no": "002", "description": "新增功能", "issue_type": "Enhancement",
         "region": "共用"},
    ]
    with patch.object(engine, "read_release_doc", return_value=fake_issues):
        count = engine.load_issues_from_release_doc(pid, "/fake/path.doc")
    assert count == 2
    assert len(repo.list_issues_by_patch(pid)) == 2
