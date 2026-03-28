"""測試 MantisSoapClient 新欄位解析。"""

from __future__ import annotations
from hcp_cms.services.mantis.base import MantisIssue, MantisNote


def test_mantis_issue_has_new_fields():
    issue = MantisIssue(id="1", summary="test")
    assert issue.severity == ""
    assert issue.reporter == ""
    assert issue.date_submitted == ""
    assert issue.target_version == ""
    assert issue.fixed_in_version == ""
    assert issue.description == ""
    assert issue.notes_list == []
    assert issue.notes_count == 0


def test_mantis_note_fields():
    note = MantisNote()
    assert note.note_id == ""
    assert note.reporter == ""
    assert note.text == ""
    assert note.date_submitted == ""
