"""測試 CaseDetailManager.sync_mantis_ticket() 新欄位映射。"""
from __future__ import annotations
import json
import pytest
from unittest.mock import MagicMock
from hcp_cms.data.database import DatabaseManager
from hcp_cms.core.case_detail_manager import CaseDetailManager
from hcp_cms.services.mantis.base import MantisIssue, MantisNote


@pytest.fixture
def manager(tmp_path):
    db_path = tmp_path / "test.db"
    mgr = DatabaseManager(db_path)
    mgr.initialize()
    yield CaseDetailManager(mgr.connection)
    mgr.close()


def test_sync_maps_new_fields(manager):
    issue = MantisIssue(
        id="99001",
        summary="測試票",
        status="resolved",
        severity="major",
        reporter="林美麗",
        date_submitted="2026-01-15T10:00:00",
        target_version="v2.5.1",
        fixed_in_version="v2.5.2",
        description="詳細描述內容。",
        notes_list=[
            MantisNote(note_id="1", reporter="王小明", text="已修復", date_submitted="2026-01-20"),
        ],
        notes_count=1,
    )
    mock_client = MagicMock()
    mock_client.get_issue.return_value = issue

    ticket = manager.sync_mantis_ticket("99001", client=mock_client)

    assert ticket is not None
    assert ticket.severity == "major"
    assert ticket.reporter == "林美麗"
    assert ticket.planned_fix == "v2.5.1"
    assert ticket.actual_fix == "v2.5.2"
    assert ticket.description == "詳細描述內容。"
    assert ticket.notes_count == 1
    notes = json.loads(ticket.notes_json or "[]")
    assert notes[0]["text"] == "已修復"
    assert notes[0]["date_submitted"] == "2026-01-20"
