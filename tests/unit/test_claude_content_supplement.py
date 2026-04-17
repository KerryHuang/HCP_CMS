"""ClaudeContentService.extract_supplement 測試（mock Claude API）。"""
from unittest.mock import MagicMock
import pytest
from hcp_cms.services.claude_content import ClaudeContentService


def _make_service_with_mock(response_text: str) -> ClaudeContentService:
    svc = ClaudeContentService.__new__(ClaudeContentService)
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text=response_text)]
    )
    svc._client = mock_client
    return svc


def test_extract_supplement_parses_json():
    import json
    payload = {
        "修改原因": "原始計算邏輯有誤",
        "原問題": "加班費計算不正確",
        "範例說明": "輸入 8 小時卻計算 7 小時",
        "修正後": "修正乘數為 1.5",
        "注意事項": "需重新跑月結",
    }
    svc = _make_service_with_mock(json.dumps(payload, ensure_ascii=False))
    result = svc.extract_supplement("加班費計算有誤：輸入8小時卻計算7小時")
    assert result["修改原因"] == "原始計算邏輯有誤"
    assert result["修正後"] == "修正乘數為 1.5"
    assert set(result.keys()) == {"修改原因", "原問題", "範例說明", "修正後", "注意事項"}


def test_extract_supplement_returns_empty_on_invalid_json():
    svc = _make_service_with_mock("這不是 JSON 格式")
    result = svc.extract_supplement("任意說明文字")
    assert result == {"修改原因": "", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}


def test_extract_supplement_returns_empty_when_client_none():
    svc = ClaudeContentService.__new__(ClaudeContentService)
    svc._client = None
    result = svc.extract_supplement("任意說明文字")
    assert result == {"修改原因": "", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}


def test_extract_supplement_handles_null_values():
    import json
    payload = {
        "修改原因": "原因說明",
        "原問題": None,
        "範例說明": "",
        "修正後": "修正說明",
        "注意事項": None,
    }
    svc = _make_service_with_mock(json.dumps(payload, ensure_ascii=False))
    result = svc.extract_supplement("測試說明")
    assert result["原問題"] == ""
    assert result["注意事項"] == ""
    assert result["修改原因"] == "原因說明"
    assert result["修正後"] == "修正說明"
    assert result["範例說明"] == ""
