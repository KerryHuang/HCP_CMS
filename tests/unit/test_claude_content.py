"""ClaudeContentService 單元測試（使用 mock）。"""
from unittest.mock import MagicMock, patch


class TestClaudeContentService:
    def test_returns_none_when_no_api_key(self):
        with patch("hcp_cms.services.credential.CredentialManager.retrieve", return_value=None):
            from hcp_cms.services.claude_content import ClaudeContentService
            svc = ClaudeContentService()
            assert svc.generate_description({"issue_no": "0015659"}) is None

    def test_generate_description_returns_text(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="測試生成說明文字")]
        with patch("hcp_cms.services.credential.CredentialManager.retrieve", return_value="fake-key"), \
             patch("hcp_cms.services.claude_content.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_response
            from hcp_cms.services.claude_content import ClaudeContentService
            svc = ClaudeContentService()
            result = svc.generate_description({"issue_no": "0015659", "description": "修正薪資"})
            assert result == "測試生成說明文字"

    def test_generate_description_retries_on_failure(self):
        with patch("hcp_cms.services.credential.CredentialManager.retrieve", return_value="fake-key"), \
             patch("hcp_cms.services.claude_content.Anthropic") as MockClient:
            MockClient.return_value.messages.create.side_effect = Exception("timeout")
            from hcp_cms.services.claude_content import ClaudeContentService
            svc = ClaudeContentService()
            result = svc.generate_description({"issue_no": "0015659"})
            assert result is None
            assert MockClient.return_value.messages.create.call_count == 3

    def test_generate_notify_body_returns_text(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="本月更新說明")]
        with patch("hcp_cms.services.credential.CredentialManager.retrieve", return_value="fake-key"), \
             patch("hcp_cms.services.claude_content.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_response
            from hcp_cms.services.claude_content import ClaudeContentService
            svc = ClaudeContentService()
            issues = [{"issue_no": "0015659", "description": "修正薪資"}]
            result = svc.generate_notify_body(issues, "202604")
            assert result == "本月更新說明"
