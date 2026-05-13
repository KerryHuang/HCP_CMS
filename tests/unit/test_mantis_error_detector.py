"""is_ticket_not_found 純函數單元測試。"""
from hcp_cms.services.mantis.error_detector import is_ticket_not_found


def test_detects_not_found_keyword_english() -> None:
    assert is_ticket_not_found("SOAP 錯誤：Issue #1234 not found") is True


def test_detects_does_not_exist_keyword() -> None:
    assert is_ticket_not_found("SOAP 錯誤：Issue does not exist") is True


def test_detects_chinese_not_exist() -> None:
    assert is_ticket_not_found("SOAP 錯誤：Issue 不存在") is True


def test_ignores_connection_error() -> None:
    assert is_ticket_not_found("連線失敗：HTTPSConnectionPool...") is False


def test_ignores_timeout_error() -> None:
    assert is_ticket_not_found("連線逾時（30 秒）") is False


def test_handles_none() -> None:
    assert is_ticket_not_found(None) is False


def test_handles_empty_string() -> None:
    assert is_ticket_not_found("") is False
