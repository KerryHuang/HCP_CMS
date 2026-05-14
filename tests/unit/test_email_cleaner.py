"""信件 boilerplate 清理工具測試。"""
from hcp_cms.core.email_cleaner import clean_email_body

# ============= ASE Confidentiality Notice =============


def test_clean_ase_disclaimer_block() -> None:
    """ASE disclaimer：以 ----- ASE Confidentiality Notice ----- 為起訖。"""
    body = (
        "Dear Wendy,\n"
        "測試區已更新Patch ，請再測試看看\n"
        "Jackey Lo\n"
        "\n"
        "----- ASE Confidentiality Notice -----\n"
        "The preceding message (including any attachments) contains proprietary\n"
        "information that may be confidential, privileged, or constitute non-public\n"
        "information. It is to be read and used solely by the intended recipient(s)\n"
        "----- ASE Confidentiality Notice -----\n"
    )
    cleaned = clean_email_body(body)
    assert "Dear Wendy" in cleaned
    assert "Jackey Lo" in cleaned
    assert "ASE Confidentiality Notice" not in cleaned
    assert "preceding message" not in cleaned


def test_clean_ase_disclaimer_multiple_occurrences() -> None:
    """信件中有多段 ASE disclaimer（轉寄鏈）→ 全部移除。"""
    body = (
        "客戶 A：第一段內容\n"
        "----- ASE Confidentiality Notice -----\n"
        "Disclaimer body 1\n"
        "----- ASE Confidentiality Notice -----\n"
        "\n"
        "客戶 B：第二段內容\n"
        "----- ASE Confidentiality Notice -----\n"
        "Disclaimer body 2\n"
        "----- ASE Confidentiality Notice -----\n"
    )
    cleaned = clean_email_body(body)
    assert "客戶 A" in cleaned
    assert "客戶 B" in cleaned
    assert "Disclaimer body" not in cleaned
    assert "Confidentiality Notice" not in cleaned


# ============= UNIMICRON Confidentiality Notice =============


def test_clean_unimicron_disclaimer_block() -> None:
    """UNIMICRON disclaimer：起始為 ***** UNIMICRON Confidentiality Notice ******，
    結束為一行 20+ 顆星號。"""
    body = (
        "Hi Jill,\n"
        "請協助確認\n"
        "Thanks\n"
        "\n"
        "************* UNIMICRON Confidentiality Notice ********************\n"
        "The information transmitted contains confidential and/or privileged material.\n"
        "If you are not the intended recipient of this message, you are hereby notified\n"
        "that any use is prohibited.\n"
        "***************************************************************\n"
    )
    cleaned = clean_email_body(body)
    assert "Hi Jill" in cleaned
    assert "請協助確認" in cleaned
    assert "UNIMICRON Confidentiality Notice" not in cleaned
    assert "intended recipient" not in cleaned


# ============= Email Confidentiality Notice (Kinsus / Phoenix Silicon) =============


def test_clean_kinsus_email_confidentiality_notice() -> None:
    """Kinsus 變體：Email Confidentiality Notice 至 Copyright Kinsus ... All Rights Reserved."""
    body = (
        "客戶詢問：班別津貼計算\n"
        "\n"
        "***************** Email Confidentiality Notice *****************\n"
        "This electronic message and any attachments are confidential.\n"
        "If you are not an intended recipient, please kindly reply us immediately\n"
        "and delete the Message from any computer and network.\n"
        "We greatly appreciate your cooperation.\n"
        "Copyright Kinsus Interconnect Technology Corp. 2017 - All Rights Reserved.\n"
    )
    cleaned = clean_email_body(body)
    assert "客戶詢問" in cleaned
    assert "Email Confidentiality Notice" not in cleaned
    assert "Copyright Kinsus" not in cleaned
    assert "All Rights Reserved" not in cleaned


def test_clean_phoenix_silicon_email_confidentiality() -> None:
    """同一 Email Confidentiality Notice 格式，公司名為 Phoenix Silicon。"""
    body = (
        "案件主文\n"
        "******************* Email Confidentiality Notice*********************************\n"
        "This electronic message and any attachments are confidential.\n"
        "Copyright Phoenix Silicon International Corporation - All Rights Reserved.\n"
        "***************************\n"
    )
    cleaned = clean_email_body(body)
    assert "案件主文" in cleaned
    assert "Confidentiality Notice" not in cleaned
    assert "Phoenix Silicon" not in cleaned


# ============= 附件刪除標記（Lotus Notes） =============


def test_clean_attachment_deleted_marker() -> None:
    """[附件檔 "X.docx" 已被 XXX 刪除] 標記移除。"""
    body = (
        "請參考附件\n"
        '[附件檔 "班別津貼.docx" 已被 ginny chen/Kinsus 刪除]\n'
        "謝謝"
    )
    cleaned = clean_email_body(body)
    assert "請參考附件" in cleaned
    assert "謝謝" in cleaned
    assert "[附件檔" not in cleaned
    assert "刪除]" not in cleaned


def test_clean_multiple_attachment_markers() -> None:
    """多個附件刪除標記都被移除。"""
    body = (
        '[附件檔 "A.txt" 已被 user1 刪除]\n'
        "中間文字\n"
        '[附件檔 "B.rar" 已被 user2 刪除]\n'
    )
    cleaned = clean_email_body(body)
    assert "中間文字" in cleaned
    assert "[附件檔" not in cleaned


# ============= 空行正規化 =============


def test_normalize_excessive_blank_lines() -> None:
    """連續 3+ 空行 → 2 空行。"""
    body = "Line 1\n\n\n\n\n\nLine 2"
    cleaned = clean_email_body(body)
    # 2 空行 = 3 個 \n
    assert "Line 1\n\n\nLine 2" == cleaned


def test_blank_lines_after_disclaimer_removal() -> None:
    """移除 disclaimer 後留下的大量空行也要正規化。"""
    body = (
        "正文\n"
        "----- ASE Confidentiality Notice -----\n"
        "blah\n"
        "----- ASE Confidentiality Notice -----\n"
        "\n\n\n\n"
        "尾文"
    )
    cleaned = clean_email_body(body)
    assert "正文" in cleaned
    assert "尾文" in cleaned
    # 不應有連續 4+ 空行
    assert "\n\n\n\n" not in cleaned


# ============= 不誤殺正常內容 =============


def test_normal_text_unaffected() -> None:
    """純正文不含 disclaimer pattern → 原樣回傳（trim 後）。"""
    body = (
        "客戶來信內容：\n"
        "想詢問加班費計算邏輯，附上 confidential 規格說明。\n"
        "謝謝"
    )
    cleaned = clean_email_body(body)
    # confidential 出現在內文中，但無 marker pattern → 不應被清掉
    assert "confidential" in cleaned
    assert "加班費計算邏輯" in cleaned


def test_empty_or_none_input() -> None:
    """空字串或 None 輸入安全處理。"""
    assert clean_email_body("") == ""
    assert clean_email_body(None) == ""


def test_only_whitespace() -> None:
    """純空白輸入 → 空字串。"""
    assert clean_email_body("   \n\n\t  ") == ""


# ============= 綜合 =============


def test_real_world_sample_kinsus_with_attachment_marker() -> None:
    """使用者實際回報的 Kinsus 信件樣本：多重 disclaimer + 附件標記。"""
    body = (
        "Dear Jill,\n"
        "請參考附件\n"
        "\n"
        "Email Confidentiality Notice\n"
        "This electronic message and any attachments are confidential and may be\n"
        "legally privileged.\n"
        "Copyright Kinsus Interconnect Technology Corp. 2017 - All Rights Reserved.\n"
        "\n"
        '[附件檔 "班別津貼.docx" 已被 ginny chen/Kinsus 刪除]\n'
        "\n"
        "Email Confidentiality Notice\n"
        "This electronic message and any attachments are confidential.\n"
        "Copyright Kinsus Interconnect Technology Corp. 2017 - All Rights Reserved.\n"
    )
    cleaned = clean_email_body(body)
    assert "Dear Jill" in cleaned
    assert "請參考附件" in cleaned
    assert "Confidentiality" not in cleaned
    assert "Copyright" not in cleaned
    assert "[附件檔" not in cleaned


def test_email_disclaimer_stars_after_only() -> None:
    """變體：header `Email Confidentiality Notice *****`（stars 只在後面）。

    使用者實際資料的常見格式，前面沒有 stars。
    """
    body = (
        "客戶來信內文\n"
        "\n"
        "Email Confidentiality Notice *****\n"
        "This electronic message and any attachments are confidential and may be\n"
        "legally privileged or otherwise protected from disclosure.\n"
        "Copyright Kinsus Interconnect Technology Corp. 2017 - All Rights Reserved.\n"
    )
    cleaned = clean_email_body(body)
    assert "客戶來信內文" in cleaned
    assert "Confidentiality" not in cleaned
    assert "Copyright" not in cleaned


def test_email_disclaimer_three_consecutive_copies_with_stars_after() -> None:
    """使用者實測樣本：3 段連續 disclaimer（轉寄鏈累積）→ 全部移除。"""
    block = (
        "Email Confidentiality Notice *****\n"
        "This electronic message and any attachments are confidential and may be\n"
        "legally privileged or otherwise protected from disclosure.\n"
        "We greatly appreciate your cooperation.\n"
        "Copyright Kinsus Interconnect Technology Corp. 2017 - All Rights Reserved.\n"
    )
    body = "正文\n\n" + block + "\n" + block + "\n" + block
    cleaned = clean_email_body(body)
    assert "正文" in cleaned
    assert "Confidentiality" not in cleaned
    assert "Copyright" not in cleaned
    assert cleaned.count("Email") == 0  # 3 段都清掉
