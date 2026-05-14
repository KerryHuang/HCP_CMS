"""PushToMantisConfirmDialog Qt smoke test（thread-aware 分類）。"""
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
    repo.insert(Case(case_id="C-1", subject="獨立案件 A", handler="jill"))
    repo.insert(Case(case_id="C-2", subject="獨立案件 B", handler="jill"))
    repo.insert(Case(case_id="C-3", subject="已連結 Mantis", handler="jill"))

    MantisRepository(db.connection).upsert(MantisTicket(ticket_id="9999", summary=""))
    CaseMantisRepository(db.connection).insert(
        CaseMantisLink(case_id="C-3", ticket_id="9999")
    )

    yield db


def _make_thread(conn, root_id: str, child_ids: list[str]) -> None:
    repo = CaseRepository(conn)
    repo.insert(Case(case_id=root_id, subject="root 主旨", handler="jill"))
    for cid in child_ids:
        repo.insert(Case(
            case_id=cid, subject=f"RE: {cid}", handler="jill",
            linked_case_id=root_id,
        ))


def test_dialog_independent_cases_all_new_ticket(qtbot, setup) -> None:
    """獨立案件（無 thread）→ 全部歸類為 new_ticket。"""
    db = setup
    dlg = PushToMantisConfirmDialog(db.connection, case_ids=["C-1", "C-2"])
    qtbot.addWidget(dlg)

    assert set(dlg.new_ticket_case_ids) == {"C-1", "C-2"}
    assert dlg.bugnote_case_ids == []
    assert dlg.skipped_case_ids == []


def test_dialog_root_plus_child_creates_one_ticket_one_bugnote(qtbot, setup) -> None:
    """root + child → root 為 new_ticket、child 為 bugnote。"""
    db = setup
    _make_thread(db.connection, "T-ROOT", ["T-A"])
    dlg = PushToMantisConfirmDialog(db.connection, case_ids=["T-ROOT", "T-A"])
    qtbot.addWidget(dlg)

    assert dlg.new_ticket_case_ids == ["T-ROOT"]
    assert dlg.bugnote_case_ids == ["T-A"]
    assert dlg.skipped_case_ids == []


def test_dialog_only_child_auto_includes_root(qtbot, setup) -> None:
    """只選 child（未選 root）→ 自動把 root 帶入 new_ticket。"""
    db = setup
    _make_thread(db.connection, "T-ROOT", ["T-A"])
    dlg = PushToMantisConfirmDialog(db.connection, case_ids=["T-A"])
    qtbot.addWidget(dlg)

    assert dlg.new_ticket_case_ids == ["T-ROOT"]
    assert dlg.bugnote_case_ids == ["T-A"]


def test_dialog_already_linked_case_skipped(qtbot, setup) -> None:
    """已連結 Mantis 的案件 → 歸 skipped。"""
    db = setup
    dlg = PushToMantisConfirmDialog(db.connection, case_ids=["C-1", "C-3"])
    qtbot.addWidget(dlg)

    assert dlg.new_ticket_case_ids == ["C-1"]
    assert dlg.bugnote_case_ids == []
    assert dlg.skipped_case_ids == ["C-3"]


def test_dialog_root_already_linked_child_becomes_bugnote_only(qtbot, setup) -> None:
    """root 已連 Mantis，child 未連 → root 不重推、child 成 bugnote。"""
    db = setup
    _make_thread(db.connection, "T-ROOT2", ["T-A2"])
    # T-ROOT2 連到既有 ticket
    CaseMantisRepository(db.connection).insert(
        CaseMantisLink(case_id="T-ROOT2", ticket_id="9999")
    )
    dlg = PushToMantisConfirmDialog(db.connection, case_ids=["T-ROOT2", "T-A2"])
    qtbot.addWidget(dlg)

    # T-ROOT2 已連結 → 不重建新 ticket，計入 skipped
    assert dlg.new_ticket_case_ids == []
    assert dlg.bugnote_case_ids == ["T-A2"]
    assert "T-ROOT2" in dlg.skipped_case_ids


def test_dialog_confirmed_case_ids_excludes_skipped(qtbot, setup) -> None:
    """confirmed_case_ids() 應回傳 new_ticket + bugnote（不含 skipped）。"""
    db = setup
    _make_thread(db.connection, "T-ROOT3", ["T-A3"])
    dlg = PushToMantisConfirmDialog(
        db.connection, case_ids=["C-1", "T-ROOT3", "T-A3", "C-3"]
    )
    qtbot.addWidget(dlg)

    confirmed = set(dlg.confirmed_case_ids())
    assert confirmed == {"C-1", "T-ROOT3", "T-A3"}
    assert "C-3" not in confirmed  # already linked → skipped


def test_dialog_all_skipped_disables_confirm(qtbot, setup) -> None:
    """全部 case 都會被 skip → 確認按鈕 disabled。"""
    db = setup
    dlg = PushToMantisConfirmDialog(db.connection, case_ids=["C-3"])
    qtbot.addWidget(dlg)
    assert dlg.confirm_button.isEnabled() is False
