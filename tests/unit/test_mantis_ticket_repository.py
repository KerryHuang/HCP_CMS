"""測試 MantisRepository 新欄位儲存與取回。"""
from __future__ import annotations

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import MantisTicket
from hcp_cms.data.repositories import MantisRepository


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    mgr = DatabaseManager(db_path)
    mgr.initialize()
    yield mgr.connection
    mgr.close()


def test_upsert_with_new_fields(db):
    repo = MantisRepository(db)
    ticket = MantisTicket(
        ticket_id="17186",
        summary="薪資計算錯誤",
        status="resolved",
        priority="high",
        handler="王小明",
        severity="major",
        reporter="林美麗",
        description="月底批次計算發生錯誤。",
        notes_json='[{"reporter":"王小明","text":"已修復","date_submitted":"2026-01-20"}]',
        notes_count=2,
    )
    repo.upsert(ticket)
    result = repo.get_by_id("17186")
    assert result is not None
    assert result.severity == "major"
    assert result.reporter == "林美麗"
    assert result.description == "月底批次計算發生錯誤。"
    assert result.notes_count == 2
    assert "已修復" in (result.notes_json or "")


def test_migration_is_idempotent(db):
    """重複呼叫 initialize() 不應拋出例外。"""
    mgr2 = DatabaseManager.__new__(DatabaseManager)
    mgr2._conn = db
    mgr2._apply_pending_migrations()  # 第二次執行不應報錯
