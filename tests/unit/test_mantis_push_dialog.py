"""PushToMantisConfirmDialog Qt smoke test。"""
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, CaseMantisLink, MantisTicket
from hcp_cms.data.repositories import (
    CaseMantisRepository,
    CaseRepository,
    MantisRepository,
)
from hcp_cms.ui.mantis_push_dialog import PushToMantisConfirmDialog


@pytest.fixture
def setup(tmp_path: Path, qtbot):
    db = DatabaseManager(tmp_path / "t.db")
    db.initialize()

    repo = CaseRepository(db.connection)
    repo.insert(Case(case_id="C-1", subject="未連結 A", handler="jill"))
    repo.insert(Case(case_id="C-2", subject="未連結 B", handler="jill"))
    repo.insert(Case(case_id="C-3", subject="已連結", handler="jill"))

    MantisRepository(db.connection).upsert(MantisTicket(ticket_id="9999", summary=""))
    CaseMantisRepository(db.connection).insert(
        CaseMantisLink(case_id="C-3", ticket_id="9999")
    )

    yield db


def test_dialog_classifies_unlinked_vs_linked(qtbot, setup) -> None:
    db = setup
    dlg = PushToMantisConfirmDialog(db.connection, case_ids=["C-1", "C-2", "C-3"])
    qtbot.addWidget(dlg)

    assert set(dlg.unlinked_case_ids) == {"C-1", "C-2"}
    assert dlg.linked_case_ids == ["C-3"]


def test_dialog_accept_returns_unlinked_only(qtbot, setup) -> None:
    db = setup
    dlg = PushToMantisConfirmDialog(db.connection, case_ids=["C-1", "C-2", "C-3"])
    qtbot.addWidget(dlg)
    assert set(dlg.confirmed_case_ids()) == {"C-1", "C-2"}


def test_dialog_all_linked_disables_confirm(qtbot, setup) -> None:
    """若所有選取案件都已連結 → 確認按鈕應 disabled。"""
    db = setup
    dlg = PushToMantisConfirmDialog(db.connection, case_ids=["C-3"])
    qtbot.addWidget(dlg)
    assert dlg.confirm_button.isEnabled() is False
