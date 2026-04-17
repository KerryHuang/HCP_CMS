"""PatchView 單元測試。"""

from __future__ import annotations

import pytest

from hcp_cms.data.database import DatabaseManager


@pytest.fixture
def db(tmp_path):
    dm = DatabaseManager(str(tmp_path / "t.db"))
    dm.initialize()
    conn = dm.connection
    yield conn
    conn.close()


def test_patch_view_instantiates(qtbot, db):
    from hcp_cms.ui.patch_view import PatchView

    view = PatchView(conn=db)
    qtbot.addWidget(view)
    assert view._tabs is not None


def test_patch_view_has_two_tabs(qtbot, db):
    from hcp_cms.ui.patch_view import PatchView

    view = PatchView(conn=db)
    qtbot.addWidget(view)
    assert view._tabs.count() == 2


def test_patch_view_tab_titles(qtbot, db):
    from hcp_cms.ui.patch_view import PatchView

    view = PatchView(conn=db)
    qtbot.addWidget(view)
    assert view._tabs.tabText(0) == "單次 Patch"
    assert view._tabs.tabText(1) == "每月大 PATCH"


def test_patch_view_without_conn(qtbot):
    from hcp_cms.ui.patch_view import PatchView

    view = PatchView(conn=None)
    qtbot.addWidget(view)
    assert view._tabs.count() == 2
