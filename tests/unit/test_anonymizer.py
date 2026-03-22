"""Tests for Anonymizer."""

import pytest
from hcp_cms.core.anonymizer import Anonymizer


@pytest.fixture
def anon() -> Anonymizer:
    return Anonymizer()


class TestAnonymizer:
    def test_anonymize_empty(self, anon):
        assert anon.anonymize("") == ""
        assert anon.anonymize(None) is None  # or handle gracefully

    def test_anonymize_email(self, anon):
        text = "請聯絡 john@example.com 處理"
        result = anon.anonymize(text)
        assert "[email]" in result
        assert "john@example.com" not in result

    def test_anonymize_url(self, anon):
        text = "請參考 https://mantis.hcp.com/view.php?id=123"
        result = anon.anonymize(text)
        assert "[URL]" in result
        assert "https://" not in result

    def test_anonymize_ip(self, anon):
        text = "伺服器 IP: 192.168.1.100 無法連線"
        result = anon.anonymize(text)
        assert "[IP]" in result
        assert "192.168.1.100" not in result

    def test_anonymize_greeting_chinese(self, anon):
        text = "您好 王大明，感謝來信"
        result = anon.anonymize(text)
        assert "王大明" not in result
        assert "您好" in result

    def test_anonymize_greeting_english(self, anon):
        text = "Dear John,\nThank you for your email"
        result = anon.anonymize(text)
        assert "John" not in result

    def test_anonymize_company_domain(self, anon):
        text = "aseglobal.com 的系統出現問題"
        result = anon.anonymize(text, company_domain="aseglobal.com")
        assert "aseglobal.com" not in result
        assert "貴客戶" in result

    def test_anonymize_company_alias(self, anon):
        text = "日月光集團的薪資系統異常"
        result = anon.anonymize(text, company_aliases=["日月光集團"])
        assert "日月光集團" not in result
        assert "貴客戶" in result

    def test_anonymize_job_title_name(self, anon):
        text = "請聯絡工程師 陳小華處理此問題"
        result = anon.anonymize(text)
        assert "陳小華" not in result
        assert "相關人員" in result

    def test_anonymize_hi_english_name(self, anon):
        text = "Hi John\nThe issue has been resolved"
        result = anon.anonymize(text)
        assert "John" not in result
        assert "Hi" in result

    def test_anonymize_signature_block(self, anon):
        text = "問題已處理\nBest regards, John Smith"
        result = anon.anonymize(text)
        assert "John" not in result

    def test_anonymize_from_line(self, anon):
        text = "Content here\nFrom: 王大明 <wang@test.com>\nMore content"
        result = anon.anonymize(text)
        assert "王大明" not in result

    def test_anonymize_standalone_chinese_name(self, anon):
        text = "問題描述\n王大明\n以上"
        result = anon.anonymize(text)
        assert "相關人員" in result

    def test_anonymize_standalone_english_name(self, anon):
        text = "Please check\nJohn Smith\nThank you"
        result = anon.anonymize(text)
        assert "相關人員" in result

    def test_anonymize_preserves_content(self, anon):
        text = "薪資計算模組出現異常，請協助確認設定是否正確。"
        result = anon.anonymize(text)
        assert result == text  # No PII, should be unchanged

    def test_anonymize_multiple_rules_combined(self, anon):
        # Note: domain also appears standalone so Rule 7 can match it after Rule 1 handles the email
        text = "您好 王大明\n請聯絡 test@aseglobal.com\n網域 aseglobal.com 的系統\n伺服器 192.168.1.1 異常\n工程師 陳小華已處理"
        result = anon.anonymize(text, company_domain="aseglobal.com")
        assert "王大明" not in result
        assert "[email]" in result
        assert "[IP]" in result
        assert "陳小華" not in result
        assert "貴客戶" in result
