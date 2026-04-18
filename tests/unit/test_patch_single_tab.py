"""SinglePatchTab 單元測試（5 步 .7z 流程）。"""

from __future__ import annotations

from pathlib import Path
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
    assert tab._archive_edit is not None
    assert tab._output_dir_edit is not None
    assert tab._version_tag_edit is not None
    assert tab._issue_table is not None
    assert tab._log is not None


def test_step_labels_are_5(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    assert len(tab._step_labels) == 5


def test_generate_buttons_disabled_initially(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    assert not tab._issue_list_btn.isEnabled()
    assert not tab._release_notice_btn.isEnabled()
    assert not tab._issue_split_btn.isEnabled()
    assert not tab._test_scripts_btn.isEnabled()


def test_archive_browse_sets_path_and_version_tag(qtbot, db, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from hcp_cms.ui.patch_single_tab import SinglePatchTab

    fake_archive = str(tmp_path / "IP_合併_20261101_HCP.7z")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        lambda *a, **kw: (fake_archive, ""),
    )
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._on_archive_browse_clicked()
    assert tab._archive_edit.text() == fake_archive
    assert tab._version_tag_edit.text() == "IP_合併_20261101"


def test_output_dir_browse_sets_path(qtbot, db, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from hcp_cms.ui.patch_single_tab import SinglePatchTab

    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory",
        lambda *a, **kw: str(tmp_path),
    )
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._on_output_dir_browse_clicked()
    assert tab._output_dir_edit.text() == str(tmp_path)


def test_load_disabled_without_archive_or_output(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._on_load_clicked()  # 無 archive/output，直接 return，不 crash


def test_load_result_enables_generate_buttons(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    result = {"patch_id": 1, "version_tag": "IP_合併_20261101",
              "issue_count": 2, "error": None}
    tab._on_load_result(result)
    assert tab._patch_id == 1
    assert tab._issue_list_btn.isEnabled()
    assert tab._release_notice_btn.isEnabled()
    assert tab._issue_split_btn.isEnabled()
    assert tab._test_scripts_btn.isEnabled()


def test_load_result_error_keeps_buttons_disabled(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    result = {"patch_id": None, "version_tag": "", "issue_count": 0,
              "error": "解壓縮失敗"}
    tab._on_load_result(result)
    assert tab._patch_id is None
    assert not tab._issue_list_btn.isEnabled()


def test_load_done_signal_emitted(qtbot, db, tmp_path):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    from hcp_cms.core.patch_engine import SinglePatchEngine

    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._archive_edit.setText(str(tmp_path / "fake.7z"))
    tab._output_dir_edit.setText(str(tmp_path))

    with patch.object(SinglePatchEngine, "load_from_archive",
                      return_value=(1, "IP_合併_20261101", 0)):
        with qtbot.waitSignal(tab._load_done, timeout=3000):
            tab._on_load_clicked()


def test_generate_result_appends_to_output_list(qtbot, db):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    result = {"type": "issue_list",
              "paths": ["/tmp/IP_合併_20261101_Issue清單整理.xlsx"],
              "error": None}
    tab._on_generate_result(result)
    assert tab._output_list.count() == 1


def test_generate_done_signal_emitted(qtbot, db, tmp_path):
    from hcp_cms.ui.patch_single_tab import SinglePatchTab
    from hcp_cms.core.patch_engine import SinglePatchEngine

    tab = SinglePatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._patch_id = 1
    tab._version_tag = "IP_合併_20261101"
    tab._output_dir_edit.setText(str(tmp_path))

    fake_path = str(tmp_path / "IP_合併_20261101_Issue清單整理.xlsx")
    with patch.object(SinglePatchEngine, "generate_issue_list",
                      return_value=fake_path):
        with qtbot.waitSignal(tab._generate_done, timeout=3000):
            tab._on_issue_list_clicked()
