"""CaseLog.bugnote_id 欄位與 CaseLogRepository.update 測試。"""
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, CaseLog
from hcp_cms.data.repositories import CaseLogRepository, CaseRepository


@pytest.fixture
def db(tmp_path: Path):
    d = DatabaseManager(tmp_path / "t.db")
    d.initialize()
    CaseRepository(d.connection).insert(Case(case_id="C-1", subject="test"))
    yield d
    d.close()


def test_bugnote_id_column_exists(db) -> None:
    cur = db.connection.execute("PRAGMA table_info(case_logs)")
    cols = {row[1] for row in cur.fetchall()}
    assert "bugnote_id" in cols


def test_insert_with_bugnote_id(db) -> None:
    repo = CaseLogRepository(db.connection)
    log = CaseLog(
        log_id=repo.next_log_id(),
        case_id="C-1",
        direction="內部討論",
        content="test note",
        bugnote_id="N-789",
        logged_at="2026/05/13 10:00:00",
    )
    repo.insert(log)
    saved = repo.list_by_case("C-1")[0]
    assert saved.bugnote_id == "N-789"


def test_insert_without_bugnote_id_defaults_none(db) -> None:
    repo = CaseLogRepository(db.connection)
    log = CaseLog(
        log_id=repo.next_log_id(),
        case_id="C-1",
        direction="內部討論",
        content="無 bugnote",
        logged_at="2026/05/13 10:00:00",
    )
    repo.insert(log)
    saved = repo.list_by_case("C-1")[0]
    assert saved.bugnote_id is None


def test_update_writes_bugnote_id(db) -> None:
    repo = CaseLogRepository(db.connection)
    log = CaseLog(
        log_id=repo.next_log_id(),
        case_id="C-1",
        direction="內部討論",
        content="test",
        logged_at="2026/05/13 10:00:00",
    )
    repo.insert(log)
    saved = repo.list_by_case("C-1")[0]
    assert saved.bugnote_id is None

    saved.bugnote_id = "N-456"
    repo.update(saved)

    after = repo.list_by_case("C-1")[0]
    assert after.bugnote_id == "N-456"
