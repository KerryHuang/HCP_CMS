"""Tests for MSGReader helper functions."""
import pytest
from hcp_cms.services.mail.msg_reader import (
    _clean_qa_text,
    _strip_leading_headers,
    MSGReader,
)


class TestStripLeadingHeaders:
    def test_removes_leading_header_lines(self):
        text = "From: foo@bar.com\nSubject: 測試主旨\n\n正文內容"
        result = _strip_leading_headers(text)
        assert result == "\n正文內容"

    def test_stops_at_first_non_header(self):
        text = "From: foo@bar.com\n正文第一行\nSubject: 這行在正文裡"
        result = _strip_leading_headers(text)
        assert "正文第一行" in result
        assert "Subject: 這行在正文裡" in result

    def test_all_headers_returns_empty(self):
        text = "From: a@b.com\nTo: c@d.com\nSubject: 測試"
        result = _strip_leading_headers(text)
        assert result.strip() == ""

    def test_empty_string(self):
        assert _strip_leading_headers("") == ""

    def test_no_headers_unchanged(self):
        text = "這是一般文字\n第二行"
        assert _strip_leading_headers(text) == text


class TestCleanQaText:
    def test_removes_greeting_您好(self):
        text = "您好，\n\n請問如何操作？"
        result = _clean_qa_text(text)
        assert not result.startswith("您好")
        assert "請問如何操作" in result

    def test_removes_greeting_hi(self):
        text = "Hi,\n這是問題"
        result = _clean_qa_text(text)
        assert not result.lower().startswith("hi")
        assert "這是問題" in result

    def test_removes_greeting_dear(self):
        text = "Dear 客服人員,\n請協助處理"
        result = _clean_qa_text(text)
        assert not result.lower().startswith("dear")
        assert "請協助處理" in result

    def test_truncates_signature_best_regards(self):
        text = "這是正文\n\nBest regards\n王小明\n公司電話：02-1234"
        result = _clean_qa_text(text)
        assert "這是正文" in result
        assert "Best regards" not in result
        assert "公司電話" not in result

    def test_truncates_signature_此致(self):
        text = "問題描述\n此致\n敬禮"
        result = _clean_qa_text(text)
        assert "問題描述" in result
        assert "此致" not in result

    def test_signature_in_middle_of_line_not_truncated(self):
        """簽名關鍵字夾在句子中不觸發截斷"""
        text = "謝謝您的協助，後來解決了"
        result = _clean_qa_text(text)
        assert "謝謝您的協助" in result

    def test_truncates_dashes_separator(self):
        text = "正文\n---\n公司資訊"
        result = _clean_qa_text(text)
        assert "正文" in result
        assert "公司資訊" not in result

    def test_compresses_multiple_blank_lines(self):
        text = "行一\n\n\n\n\n行二"
        result = _clean_qa_text(text)
        assert "\n\n\n" not in result

    def test_empty_string(self):
        assert _clean_qa_text("") == ""

    def test_only_greeting_returns_empty(self):
        text = "您好，\n"
        result = _clean_qa_text(text)
        assert result == ""

    def test_bracket_company_triggers_cutoff(self):
        text = "正文內容\n[公司名稱]\n聯絡資訊"
        result = _clean_qa_text(text)
        assert "正文內容" in result
        assert "聯絡資訊" not in result


class TestSplitThreadFixed:
    def test_multi_layer_uses_last_customer_from(self):
        """多層引用時取最後一個非我方 From，thread_question 包含最原始問題。"""
        body = (
            "我方第二次回覆\n\n"
            "From: customer@client.com\n"
            "第一次客戶問題（被引用）\n\n"
            "From: hcpservice@ares.com.tw\n"
            "我方第一次回覆\n\n"
            "From: customer@client.com\n"
            "Subject: 原始問題\n\n"
            "最原始客戶問題內容"
        )
        answer, question = MSGReader._split_thread(body, own_domain="@ares.com.tw")
        assert question is not None
        assert "最原始客戶問題內容" in question
        assert answer is not None

    def test_leading_headers_removed_from_question(self):
        """客戶問題段開頭的 header 行被移除，正文保留。"""
        body = (
            "我方回覆\n\n"
            "From: customer@client.com\n"
            "Subject: 測試主旨\n"
            "Sent: 2026-01-01\n\n"
            "這是客戶問題正文"
        )
        _, question = MSGReader._split_thread(body)
        assert question is not None
        assert "這是客戶問題正文" in question
        assert "Subject:" not in question

    def test_no_customer_from_returns_none_none(self):
        body = "只有我方寄件人\nFrom: service@ares.com.tw\n內容"
        answer, question = MSGReader._split_thread(body, own_domain="@ares.com.tw")
        assert answer is None
        assert question is None

    def test_customer_from_at_start_answer_is_none(self):
        """客戶 From 在最開頭，answer 應為 None"""
        body = "From: customer@client.com\nSubject: 問題\n\n客戶問題內容"
        answer, question = MSGReader._split_thread(body, own_domain="@ares.com.tw")
        assert answer is None
        assert question is not None
        assert "客戶問題內容" in question
