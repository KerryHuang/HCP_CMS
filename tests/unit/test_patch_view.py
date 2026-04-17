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


def test_main_window_has_patch_nav(qtbot, db):
    from hcp_cms.ui.main_window import MainWindow

    win = MainWindow(db_connection=db)
    qtbot.addWidget(win)
    from PySide6.QtCore import Qt

    keys = [
        win._nav_list.item(i).data(Qt.ItemDataRole.UserRole)
        for i in range(win._nav_list.count())
    ]
    assert "patch" in keys


def test_main_window_patch_view_in_stack(qtbot, db):
    from hcp_cms.ui.main_window import MainWindow
    from hcp_cms.ui.patch_view import PatchView

    win = MainWindow(db_connection=db)
    qtbot.addWidget(win)
    assert "patch" in win._views
    assert isinstance(win._views["patch"], PatchView)


def test_main_window_patch_nav_at_index_7(qtbot, db):
    from PySide6.QtCore import Qt

    from hcp_cms.ui.main_window import MainWindow

    win = MainWindow(db_connection=db)
    qtbot.addWidget(win)
    item = win._nav_list.item(7)
    assert item is not None
    assert item.data(Qt.ItemDataRole.UserRole) == "patch"
