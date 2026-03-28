"""Tests for MSGReader helper functions."""
from unittest.mock import MagicMock, patch

from hcp_cms.services.mail.msg_reader import (
    MSGReader,
    _clean_qa_text,
    _strip_leading_headers,
)


class TestStripLeadingHeaders:
    def test_removes_leading_header_lines(self):
        text = "From: foo@bar.com\nSubject: 測試主旨\n\n正文內容"
        result = _strip_leading_headers(text)
        # header 後的空行也應被跳過，直接回傳正文
        assert result == "正文內容"

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

    def test_removes_cc_line(self):
        """Cc: 行應被視為 header 並移除"""
        text = "From: foo@bar.com\nCc: cc@bar.com\n\n正文內容"
        result = _strip_leading_headers(text)
        assert "Cc:" not in result
        assert "正文內容" in result

    def test_skips_blank_lines_within_header_block(self):
        """header 之間的空行應略過，繼續移除後續 header"""
        text = "From: foo@bar.com\n\nSubject: 測試\n\n正文內容"
        result = _strip_leading_headers(text)
        assert "Subject:" not in result
        assert "正文內容" in result


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
        # 6 個以上破折號才觸發（3 個 --- 是正文常見分隔，不截斷）
        text = "正文\n------\n公司資訊"
        result = _clean_qa_text(text)
        assert "正文" in result
        assert "公司資訊" not in result

    def test_three_dashes_not_truncated(self):
        """--- (3個) 不應觸發截斷，避免誤刪正文內容"""
        text = "說明如下：\n---\n1. 補休建檔請使用 A 程式\n2. 查詢請使用 B 程式"
        result = _clean_qa_text(text)
        assert "1. 補休建檔" in result
        assert "2. 查詢" in result

    def test_double_dash_separator_truncates(self):
        """-- (兩個，email client 標準簽名分隔線) 應觸發截斷"""
        text = "回覆內容\n--\n姓名\n電話"
        result = _clean_qa_text(text)
        assert "回覆內容" in result
        assert "姓名" not in result

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

    def test_truncates_best_regards_with_comma(self):
        """'Best Regards,' 帶逗號也應觸發截斷"""
        text = "解答內容\nBest Regards,\n王小明\n公司電話"
        result = _clean_qa_text(text)
        assert "解答內容" in result
        assert "Best Regards" not in result
        assert "公司電話" not in result

    def test_truncates_感謝您_prefix(self):
        """'感謝您的耐心等候' 應觸發截斷（不需完整比對）"""
        text = "解答內容\n感謝您的耐心等候\n如有問題請聯絡我"
        result = _clean_qa_text(text)
        assert "解答內容" in result
        assert "感謝您的耐心等候" not in result

    def test_removes_confidentiality_notice_block(self):
        """UNIMICRON Confidentiality Notice 免責聲明區塊應被移除"""
        text = (
            "正文內容\n\n"
            "************* UNIMICRON Confidentiality Notice ********************\n"
            "The information transmitted contains confidential material.\n"
            "***************************************************************"
        )
        result = _clean_qa_text(text)
        assert "正文內容" in result
        assert "Confidentiality" not in result
        assert "UNIMICRON" not in result

    def test_removes_repeated_confidentiality_blocks(self):
        """重複三次的免責聲明應全部移除"""
        block = (
            "************* UNIMICRON Confidentiality Notice ********************\n"
            "The information transmitted contains confidential material.\n"
            "***************************************************************\n"
        )
        text = "正文內容\n\n" + block * 3
        result = _clean_qa_text(text)
        assert "正文內容" in result
        assert "Confidentiality" not in result

    def test_removes_ase_dash_style_confidentiality(self):
        """ASE 破折號樣式免責聲明應被移除"""
        text = (
            "解答內容\n\n"
            "#64643 Jackey_Lo@aseglobal.com ----- ASE Confidentiality Notice -----"
            " The preceding message (including any attachments) contains proprietary information."
        )
        result = _clean_qa_text(text)
        assert "解答內容" in result
        assert "Confidentiality" not in result
        assert "#64643" not in result

    def test_removes_dash_separator_confidentiality(self):
        """破折號分隔的免責聲明區塊應被移除"""
        text = (
            "正文\n\n"
            "----- Confidentiality Notice -----\n"
            "This message is confidential.\n"
        )
        result = _clean_qa_text(text)
        assert "正文" in result
        assert "Confidentiality" not in result

    def test_removes_this_email_disclaimer(self):
        """'This e-mail along...' 樣式的免責聲明應被移除"""
        text = "回覆內容\nThis e-mail along with any attachments is intended only for the addressee."
        result = _clean_qa_text(text)
        assert "回覆內容" in result
        assert "This e-mail" not in result

    def test_removes_progress_note_from_text(self):
        """==進度:...== 標記應從文字中移除"""
        text = "==進度: 待與jacky確認1.組織代號是否可以這樣異動2.所需的人天評估費用等=="
        result = _clean_qa_text(text)
        assert result == ""

    def test_progress_note_stripped_leaving_surrounding_content(self):
        """==進度:...== 前後的正文應保留"""
        text = "正式回覆內容\n==進度: 待確認==\n其他說明"
        result = _clean_qa_text(text)
        assert "正式回覆內容" in result
        assert "進度" not in result

    def test_cuts_at_tel_contact_info(self):
        """行內 Tel：電話 簽名資訊應觸發截斷"""
        text = (
            "請問如何操作薪資模組？\n"
            "Nicole Chang 桃園市中壢區 Tel：+886-3-426-2828 Fax：+886-3-425-1919 "
            "E-Mail:nicole@example.com"
        )
        result = _clean_qa_text(text)
        assert "請問如何操作薪資模組" in result
        assert "Tel：" not in result
        assert "Fax：" not in result
        assert "E-Mail:" not in result


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


class TestExtractImages:
    def test_nonexistent_msg_returns_empty(self, tmp_path):
        result = MSGReader.extract_images(tmp_path / "notexist.msg", tmp_path / "out")
        assert result == []

    def test_idempotent_skip_existing(self, tmp_path):
        """若目標目錄已有同名檔案，跳過不重複寫入。"""
        dest = tmp_path / "out"
        dest.mkdir()
        existing = dest / "image.png"
        existing.write_bytes(b"original")
        # 模擬：若 msg_path 不存在，直接回傳 []（冪等驗證的前提是目的地已有檔案）
        result = MSGReader.extract_images(tmp_path / "fake.msg", dest)
        assert existing.read_bytes() == b"original"  # 未被覆蓋

    def test_corrupt_msg_returns_empty(self, tmp_path):
        """損壞的 .msg 檔案（開啟失敗）回傳 []。"""
        bad_msg = tmp_path / "bad.msg"
        bad_msg.write_bytes(b"not a real msg")
        # extract_msg.Message 會拋出例外，extract_images 應吞掉並回傳 []
        result = MSGReader.extract_images(bad_msg, tmp_path / "out")
        assert result == []

    def test_extracts_image_attachment_by_extension(self, tmp_path):
        """有圖片副檔名的附件會被提取。"""
        msg_path = tmp_path / "test.msg"
        msg_path.write_bytes(b"placeholder")
        dest = tmp_path / "out"

        mock_att = MagicMock()
        mock_att.longFilename = "photo.png"
        mock_att.shortFilename = "photo.png"
        mock_att.contentId = ""
        mock_att.data = b"\x89PNG fake image data"

        mock_msg = MagicMock()
        mock_msg.htmlBody = None
        mock_msg.attachments = [mock_att]

        with patch("extract_msg.Message", return_value=mock_msg):
            result = MSGReader.extract_images(msg_path, dest)

        assert len(result) == 1
        assert result[0].name == "photo.png"
        assert (dest / "photo.png").read_bytes() == b"\x89PNG fake image data"

    def test_skips_non_image_attachment(self, tmp_path):
        """非圖片附件不提取。"""
        msg_path = tmp_path / "test.msg"
        msg_path.write_bytes(b"placeholder")
        dest = tmp_path / "out"

        mock_att = MagicMock()
        mock_att.longFilename = "document.pdf"
        mock_att.shortFilename = "document.pdf"
        mock_att.contentId = ""
        mock_att.data = b"PDF content"

        mock_msg = MagicMock()
        mock_msg.htmlBody = None
        mock_msg.attachments = [mock_att]

        with patch("extract_msg.Message", return_value=mock_msg):
            result = MSGReader.extract_images(msg_path, dest)

        assert result == []

    def test_idempotent_existing_file_not_overwritten(self, tmp_path):
        """目標目錄已有同名檔案時跳過，原始內容不被覆蓋。"""
        msg_path = tmp_path / "test.msg"
        msg_path.write_bytes(b"placeholder")
        dest = tmp_path / "out"
        dest.mkdir()
        existing = dest / "photo.png"
        existing.write_bytes(b"original content")

        mock_att = MagicMock()
        mock_att.longFilename = "photo.png"
        mock_att.shortFilename = "photo.png"
        mock_att.contentId = ""
        mock_att.data = b"new content"

        mock_msg = MagicMock()
        mock_msg.htmlBody = None
        mock_msg.attachments = [mock_att]

        with patch("extract_msg.Message", return_value=mock_msg):
            result = MSGReader.extract_images(msg_path, dest)

        assert existing.read_bytes() == b"original content"  # 未被覆蓋
        assert len(result) == 1  # 仍加入 saved 列表
