"""IssueTableWidget 單元測試。"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QMessageBox

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import PatchIssue, PatchRecord
from hcp_cms.data.repositories import PatchRepository


@pytest.fixture
def db(tmp_path):
    dm = DatabaseManager(str(tmp_path / "t.db"))
    dm.initialize()
    conn = dm.connection
    yield conn
    conn.close()


@pytest.fixture
def patch_id(db):
    repo = PatchRepository(db)
    return repo.insert_patch(PatchRecord(type="monthly", month_str="202604"))


def _make_issue(patch_id: int, no: str = "001") -> PatchIssue:
    return PatchIssue(patch_id=patch_id, issue_no=no, issue_type="BugFix",
                      region="TW", sort_order=0, source="manual")


# ── PatchRepository.get_issue_by_id ────────────────────────────────────────

def test_get_issue_by_id_returns_issue(db, patch_id):
    repo = PatchRepository(db)
    iid = repo.insert_issue(_make_issue(patch_id))
    result = repo.get_issue_by_id(iid)
    assert result is not None
    assert result.issue_no == "001"


def test_get_issue_by_id_returns_none_for_missing(db):
    repo = PatchRepository(db)
    assert repo.get_issue_by_id(9999) is None


# ── IssueTableWidget ────────────────────────────────────────────────────────

def test_load_issues_populates_table(qtbot, db, patch_id):
    from hcp_cms.ui.widgets.issue_table_widget import IssueTableWidget
    repo = PatchRepository(db)
    repo.insert_issue(_make_issue(patch_id))
    widget = IssueTableWidget(conn=db)
    qtbot.addWidget(widget)
    widget.load_issues(patch_id)
    assert widget._table.rowCount() == 1
    assert widget._table.item(0, 0).text() == "001"


def test_add_issue_appends_row(qtbot, db, patch_id):
    from hcp_cms.ui.widgets.issue_table_widget import IssueTableWidget
    widget = IssueTableWidget(conn=db)
    qtbot.addWidget(widget)
    widget.load_issues(patch_id)
    widget._on_add_clicked()
    assert widget._table.rowCount() == 1


def test_delete_issue_removes_row(qtbot, db, patch_id, monkeypatch):
    from hcp_cms.ui.widgets.issue_table_widget import IssueTableWidget
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **kw: QMessageBox.StandardButton.Yes,
    )
    repo = PatchRepository(db)
    repo.insert_issue(_make_issue(patch_id))
    widget = IssueTableWidget(conn=db)
    qtbot.addWidget(widget)
    widget.load_issues(patch_id)
    widget._table.selectRow(0)
    widget._on_delete_clicked()
    assert widget._table.rowCount() == 0
    assert repo.list_issues_by_patch(patch_id) == []


def test_cell_change_saves_to_db(qtbot, db, patch_id):
    from hcp_cms.ui.widgets.issue_table_widget import IssueTableWidget
    repo = PatchRepository(db)
    iid = repo.insert_issue(_make_issue(patch_id))
    widget = IssueTableWidget(conn=db)
    qtbot.addWidget(widget)
    widget.load_issues(patch_id)
    widget._table.item(0, 0).setText("999")
    saved = repo.get_issue_by_id(iid)
    assert saved is not None
    assert saved.issue_no == "999"


def test_issues_changed_signal_emitted(qtbot, db, patch_id):
    from hcp_cms.ui.widgets.issue_table_widget import IssueTableWidget
    widget = IssueTableWidget(conn=db)
    qtbot.addWidget(widget)
    widget.load_issues(patch_id)
    with qtbot.waitSignal(widget.issues_changed, timeout=1000):
        widget._on_add_clicked()
