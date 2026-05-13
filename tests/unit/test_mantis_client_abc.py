"""驗證 MantisClient ABC 含 create_issue / add_note 抽象方法。"""
import inspect

from hcp_cms.services.mantis.base import MantisClient


def test_create_issue_is_abstract() -> None:
    assert "create_issue" in MantisClient.__abstractmethods__


def test_add_note_is_abstract() -> None:
    assert "add_note" in MantisClient.__abstractmethods__


def test_create_issue_signature() -> None:
    sig = inspect.signature(MantisClient.create_issue)
    params = list(sig.parameters.keys())
    assert "project_id" in params
    assert "summary" in params
    assert "description" in params
    assert sig.parameters["priority"].default == "normal"
    assert sig.parameters["severity"].default == "minor"


def test_add_note_signature() -> None:
    sig = inspect.signature(MantisClient.add_note)
    params = list(sig.parameters.keys())
    assert "issue_id" in params
    assert "text" in params
    assert sig.parameters["view_state"].default == "public"
