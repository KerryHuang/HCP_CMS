"""Case dataclass 對 已結案 狀態的處理。"""
from hcp_cms.data.models import Case


def test_closed_case_is_not_open() -> None:
    case = Case(case_id="C-1", subject="test", status="已結案")
    assert case.is_open is False


def test_completed_case_is_not_open() -> None:
    case = Case(case_id="C-2", subject="test", status="已完成")
    assert case.is_open is False


def test_processing_case_is_open() -> None:
    case = Case(case_id="C-3", subject="test", status="處理中")
    assert case.is_open is True
