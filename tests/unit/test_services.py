"""Tests for services layer."""

import hashlib
from pathlib import Path
from unittest.mock import patch

from hcp_cms.services.credential import CredentialManager
from hcp_cms.services.mail.base import RawEmail
from hcp_cms.services.mail.exchange import ExchangeProvider
from hcp_cms.services.mail.imap import IMAPProvider
from hcp_cms.services.mail.msg_reader import MSGReader
from hcp_cms.services.mantis.base import MantisIssue
from hcp_cms.services.mantis.rest import MantisRESTClient
from hcp_cms.services.mantis.soap import MantisSoapClient


class TestRawEmail:
    def test_create_raw_email(self):
        email = RawEmail(sender="test@example.com", subject="Test", body="Body")
        assert email.sender == "test@example.com"
        assert email.attachments == []

    def test_raw_email_defaults(self):
        email = RawEmail()
        assert email.sender == ""
        assert email.subject == ""

    def test_raw_email_has_to_recipients(self):
        email = RawEmail(to_recipients=["a@foo.com", "b@bar.com"])
        assert email.to_recipients == ["a@foo.com", "b@bar.com"]

    def test_raw_email_to_recipients_default_empty(self):
        email = RawEmail()
        assert email.to_recipients == []

    def test_raw_email_has_html_body(self):
        email = RawEmail(html_body="<p>Hello</p>")
        assert email.html_body == "<p>Hello</p>"

    def test_raw_email_html_body_default_none(self):
        email = RawEmail()
        assert email.html_body is None

    def test_raw_email_has_progress_note(self):
        email = RawEmail(progress_note="待確認需求")
        assert email.progress_note == "待確認需求"

    def test_raw_email_progress_note_default_none(self):
        email = RawEmail()
        assert email.progress_note is None

    def test_raw_email_thread_question_default_none(self):
        email = RawEmail()
        assert email.thread_question is None

    def test_raw_email_thread_answer_default_none(self):
        email = RawEmail()
        assert email.thread_answer is None

    def test_raw_email_thread_fields_settable(self):
        email = RawEmail(thread_question="客戶問題", thread_answer="我方回覆")
        assert email.thread_question == "客戶問題"
        assert email.thread_answer == "我方回覆"


class TestMSGReader:
    def test_connect_nonexistent_dir(self):
        reader = MSGReader(Path("/nonexistent"))
        assert reader.connect() is False

    def test_connect_empty_dir(self, tmp_path):
        reader = MSGReader(tmp_path)
        assert reader.connect() is True

    def test_fetch_empty_dir(self, tmp_path):
        reader = MSGReader(tmp_path)
        reader.connect()
        messages = reader.fetch_messages()
        assert messages == []

    def test_compute_file_hash(self, tmp_path):
        f = tmp_path / "test.msg"
        f.write_bytes(b"test content")
        reader = MSGReader()
        h = reader.compute_file_hash(f)
        assert h == hashlib.sha256(b"test content").hexdigest()

    def test_fetch_sent_returns_empty(self, tmp_path):
        reader = MSGReader(tmp_path)
        assert reader.fetch_sent_messages() == []

    def test_create_draft_returns_false(self, tmp_path):
        reader = MSGReader(tmp_path)
        assert reader.create_draft(["a@b.com"], "subj", "body") is False

    def test_disconnect(self, tmp_path):
        reader = MSGReader(tmp_path)
        reader.connect()
        reader.disconnect()
        assert reader._files == []

    def test_read_msg_file_parses_to_recipients(self, tmp_path, monkeypatch):
        """_read_msg_file 應解析 msg.to 為 to_recipients list。"""
        import types

        fake_msg = types.SimpleNamespace(
            sender="hcpservice@ares.com.tw",
            subject="回覆：薪資問題",
            body="已處理",
            htmlBody=b"<p>\xe5\xb7\xb2\xe8\x99\x95\xe7\x90\x86</p>",
            date="2026/03/20 10:00",
            attachments=[],
            to="客戶 <user@customer.com>; other@customer.com",
        )

        def fake_message(path):
            fake_msg.close = lambda: None
            return fake_msg

        import extract_msg

        monkeypatch.setattr(extract_msg, "Message", fake_message)

        result = MSGReader._read_msg_file(tmp_path / "test.msg")
        assert result is not None
        assert "user@customer.com" in result.to_recipients
        assert "other@customer.com" in result.to_recipients

    def test_read_msg_file_parses_html_body(self, tmp_path, monkeypatch):
        """_read_msg_file 應將 msg.htmlBody bytes 解碼為 html_body str。"""
        import types

        fake_msg = types.SimpleNamespace(
            sender="user@customer.com",
            subject="薪資問題",
            body="純文字",
            htmlBody=b"<p>HTML\xe5\x85\xa7\xe5\xae\xb9</p>",
            date=None,
            attachments=[],
            to="",
        )

        def fake_message(path):
            fake_msg.close = lambda: None
            return fake_msg

        import extract_msg

        monkeypatch.setattr(extract_msg, "Message", fake_message)

        result = MSGReader._read_msg_file(tmp_path / "test.msg")
        assert result is not None
        assert result.html_body == "<p>HTML內容</p>"

    def test_read_msg_file_html_body_none_when_missing(self, tmp_path, monkeypatch):
        """msg.htmlBody 為 None 時，html_body 應為 None。"""
        import types

        fake_msg = types.SimpleNamespace(
            sender="user@customer.com",
            subject="Test",
            body="plain",
            htmlBody=None,
            date=None,
            attachments=[],
            to="",
        )

        def fake_message(path):
            fake_msg.close = lambda: None
            return fake_msg

        import extract_msg

        monkeypatch.setattr(extract_msg, "Message", fake_message)

        result = MSGReader._read_msg_file(tmp_path / "test.msg")
        assert result is not None
        assert result.html_body is None

    def test_read_msg_file_extracts_progress_note(self, tmp_path, monkeypatch):
        """body 含 ==進度:…== 時，progress_note 應正確擷取。"""
        import types

        fake_msg = types.SimpleNamespace(
            sender="user@customer.com",
            subject="薪資問題",
            body="說明內容\n==進度: 待與jacky確認事項==\n後續文字",
            htmlBody=None,
            date=None,
            attachments=[],
            to="",
        )

        def fake_message(path):
            fake_msg.close = lambda: None
            return fake_msg

        import extract_msg

        monkeypatch.setattr(extract_msg, "Message", fake_message)
        result = MSGReader._read_msg_file(tmp_path / "test.msg")
        assert result is not None
        assert result.progress_note == "待與jacky確認事項"

    def test_read_msg_file_extracts_multiline_progress(self, tmp_path, monkeypatch):
        """==進度== 跨多行時應完整擷取（含換行）。"""
        import types

        fake_msg = types.SimpleNamespace(
            sender="user@customer.com",
            subject="問題",
            body="前文\n==進度: 第一行\n第二行\n第三行==\n後文",
            htmlBody=None,
            date=None,
            attachments=[],
            to="",
        )

        def fake_message(path):
            fake_msg.close = lambda: None
            return fake_msg

        import extract_msg

        monkeypatch.setattr(extract_msg, "Message", fake_message)
        result = MSGReader._read_msg_file(tmp_path / "test.msg")
        assert result is not None
        assert "第一行" in result.progress_note
        assert "第三行" in result.progress_note

    def test_read_msg_file_extracts_progress_fullwidth_colon(self, tmp_path, monkeypatch):
        """全形冒號 ==進度：…== 也應正確擷取。"""
        import types

        fake_msg = types.SimpleNamespace(
            sender="user@customer.com",
            subject="問題",
            body="==進度：全形冒號測試==",
            htmlBody=None,
            date=None,
            attachments=[],
            to="",
        )

        def fake_message(path):
            fake_msg.close = lambda: None
            return fake_msg

        import extract_msg

        monkeypatch.setattr(extract_msg, "Message", fake_message)
        result = MSGReader._read_msg_file(tmp_path / "test.msg")
        assert result is not None
        assert result.progress_note == "全形冒號測試"

    def test_read_msg_file_no_progress_marker_is_none(self, tmp_path, monkeypatch):
        """body 無 ==進度== 標記時，progress_note 應為 None。"""
        import types

        fake_msg = types.SimpleNamespace(
            sender="user@customer.com",
            subject="問題",
            body="正常信件內容，無任何進度標記",
            htmlBody=None,
            date=None,
            attachments=[],
            to="",
        )

        def fake_message(path):
            fake_msg.close = lambda: None
            return fake_msg

        import extract_msg

        monkeypatch.setattr(extract_msg, "Message", fake_message)
        result = MSGReader._read_msg_file(tmp_path / "test.msg")
        assert result is not None
        assert result.progress_note is None

    def test_read_msg_file_draft_sender_from_body_angle_bracket(self, tmp_path, monkeypatch):
        """msg.sender 空白，body 含 'From: Name <email>' → sender 補回。"""
        import types

        fake_msg = types.SimpleNamespace(
            sender="",
            subject="RE: 問題",
            body="From: Nicole_Chang(GLTTCL-張淑雅) <nicole_chang@glthome.com.tw>\n\n信件內容",
            htmlBody=None,
            date=None,
            attachments=[],
            to="",
        )

        def fake_message(path):
            fake_msg.close = lambda: None
            return fake_msg

        import extract_msg

        monkeypatch.setattr(extract_msg, "Message", fake_message)
        result = MSGReader._read_msg_file(tmp_path / "draft.msg")
        assert result is not None
        assert result.sender == "nicole_chang@glthome.com.tw"

    def test_read_msg_file_draft_sender_from_body_plain_email(self, tmp_path, monkeypatch):
        """msg.sender 空白，body 含純 email 格式 'From: user@domain.com' → fallback regex 補回。"""
        import types

        fake_msg = types.SimpleNamespace(
            sender="",
            subject="RE: 問題",
            body="From: user@glthome.com.tw\n\n信件內容",
            htmlBody=None,
            date=None,
            attachments=[],
            to="",
        )

        def fake_message(path):
            fake_msg.close = lambda: None
            return fake_msg

        import extract_msg

        monkeypatch.setattr(extract_msg, "Message", fake_message)
        result = MSGReader._read_msg_file(tmp_path / "draft.msg")
        assert result is not None
        assert result.sender == "user@glthome.com.tw"

    def test_read_msg_file_existing_sender_not_overridden(self, tmp_path, monkeypatch):
        """msg.sender 已有值時，body 的 From: 行不應覆蓋 sender。"""
        import types

        fake_msg = types.SimpleNamespace(
            sender="real@customer.com",
            subject="問題",
            body="From: other@example.com\n\n內容",
            htmlBody=None,
            date=None,
            attachments=[],
            to="",
        )

        def fake_message(path):
            fake_msg.close = lambda: None
            return fake_msg

        import extract_msg

        monkeypatch.setattr(extract_msg, "Message", fake_message)
        result = MSGReader._read_msg_file(tmp_path / "test.msg")
        assert result is not None
        assert result.sender == "real@customer.com"


class TestIMAPProvider:
    def test_create(self):
        provider = IMAPProvider("imap.example.com", 993)
        assert provider._host == "imap.example.com"

    def test_connect_failure(self):
        provider = IMAPProvider("nonexistent.invalid", 993)
        provider.set_credentials("user", "pass")
        assert provider.connect() is False

    def test_fetch_without_connect(self):
        provider = IMAPProvider("imap.example.com")
        assert provider.fetch_messages() == []

    def test_disconnect_without_connect(self):
        provider = IMAPProvider("imap.example.com")
        provider.disconnect()  # Should not raise


class TestExchangeProvider:
    def test_create(self):
        provider = ExchangeProvider(server="exchange.example.com", email_address="user@example.com")
        assert provider._server == "exchange.example.com"

    def test_fetch_without_connect(self):
        provider = ExchangeProvider()
        assert provider.fetch_messages() == []

    def test_create_draft_without_connect(self):
        provider = ExchangeProvider()
        assert provider.create_draft(["a@b.com"], "subj", "body") is False


class TestMantisIssue:
    def test_create(self):
        issue = MantisIssue(id="15562", summary="Bug fix")
        assert issue.id == "15562"


class TestMantisRESTClient:
    def test_create(self):
        client = MantisRESTClient("https://mantis.example.com", "token123")
        assert client._base_url == "https://mantis.example.com"

    def test_get_issue_without_connect(self):
        client = MantisRESTClient("https://mantis.example.com")
        assert client.get_issue("123") is None

    def test_get_issues_without_connect(self):
        client = MantisRESTClient("https://mantis.example.com")
        assert client.get_issues() == []


class TestMantisSoapClient:
    def test_create(self):
        client = MantisSoapClient("https://mantis.example.com", "user", "pass")
        assert client._base_url == "https://mantis.example.com"

    def test_extract_xml(self):
        xml = "<root><summary>Bug fix</summary></root>"
        result = MantisSoapClient._extract_xml(xml, "summary")
        assert result == "Bug fix"

    def test_extract_xml_with_after(self):
        xml = "<root><status><name>open</name></status><priority><name>high</name></priority></root>"
        result = MantisSoapClient._extract_xml(xml, "name", after="priority")
        assert result == "high"


class TestCredentialManager:
    def test_store_and_retrieve(self):
        cm = CredentialManager()
        # Mock keyring to avoid OS dependency in tests
        with (
            patch("keyring.set_password") as mock_set,
            patch("keyring.get_password", return_value="secret") as mock_get,
        ):
            assert cm.store("test_key", "secret") is True
            mock_set.assert_called_once_with("HCP_CMS", "test_key", "secret")

            result = cm.retrieve("test_key")
            assert result == "secret"
            mock_get.assert_called_once_with("HCP_CMS", "test_key")

    def test_retrieve_not_found(self):
        cm = CredentialManager()
        with patch("keyring.get_password", return_value=None):
            assert cm.retrieve("nonexistent") is None

    def test_delete(self):
        cm = CredentialManager()
        with patch("keyring.delete_password") as mock_del:
            assert cm.delete("test_key") is True
            mock_del.assert_called_once()


class TestMSGReaderSplitThread:
    def test_英文_from_切割(self):
        body = (
            "HCPSERVICE 的回覆內容在這裡。\n\n"
            "From: customer@client.com\n"
            "Sent: 2026-01-01\n"
            "To: hcpservice@ares.com.tw\n"
            "Subject: 詢問\n\n"
            "客戶問題內容。"
        )
        ta, tq = MSGReader._split_thread(body)
        assert ta is not None and "HCPSERVICE" in ta
        assert tq is not None and "客戶問題" in tq
        assert "From:" not in tq
        assert "Sent:" not in tq

    def test_中文_寄件者_切割(self):
        body = (
            "我方回覆。\n\n"
            "寄件者: user@client.com.tw\n"
            "傳送時間: 2026-01-01\n"
            "收件者: hcpservice@ares.com.tw\n"
            "主旨: 問題\n\n"
            "客戶的問題。"
        )
        ta, tq = MSGReader._split_thread(body)
        assert ta is not None
        assert tq is not None and "客戶的問題" in tq

    def test_無客戶_From_行回傳_None_None(self):
        ta, tq = MSGReader._split_thread("這封信沒有嵌入的原始訊息。")
        assert ta is None and tq is None

    def test_全部_From_均為_ares_回傳_None_None(self):
        body = (
            "第一封回覆\n\n"
            "From: hcpservice@ares.com.tw\n"
            "Subject: Re: 問題\n\n"
            "原始我方訊息"
        )
        ta, tq = MSGReader._split_thread(body)
        assert ta is None and tq is None

    def test_own_domain_大小寫混用仍識別為我方(self):
        body = (
            "回覆\n\n"
            "From: User@ARES.COM.TW\n"
            "Subject: test\n\n"
            "另一封我方訊息"
        )
        ta, tq = MSGReader._split_thread(body)
        assert ta is None and tq is None

    def test_客戶段清除_header_後為空_回傳_None(self):
        body = (
            "我方回覆。\n\n"
            "From: customer@client.com\n"
            "Sent: 2026-01-01\n"
        )
        ta, tq = MSGReader._split_thread(body)
        assert tq is None

    def test_多層巢狀取最後一個非我方客戶(self):
        body = (
            "最新回覆\n\n"
            "From: customer@abc.com\n"
            "Subject: 第一次詢問\n\n"
            "第一次問題\n\n"
            "From: another@xyz.com\n"
            "Subject: 更早的問題\n\n"
            "更早的問題"
        )
        ta, tq = MSGReader._split_thread(body)
        assert tq is not None and "更早的問題" in tq
