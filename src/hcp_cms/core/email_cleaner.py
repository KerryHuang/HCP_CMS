"""信件 boilerplate 清理 — 移除常見的免責聲明、附件刪除標記等噪音。

清理策略：用「起訖標記」配對而非「關鍵字截段落」，避免誤殺正常內文。
- ASE / UNIMICRON 等公司有明確的 disclaimer 起訖 marker
- 通用 Email Confidentiality Notice 以「Copyright ... All Rights Reserved」收尾
- 附件刪除標記為 Lotus Notes 固定格式

僅在收信時呼叫一次（case_manager.import_email / create_case）。
不清 HCP 自家簽名檔與郵件引文（避免破壞 traceability 與誤殺）。
"""
from __future__ import annotations

import re

# ASE 日月光：起訖均為 ----- ASE Confidentiality Notice -----
_ASE_DISCLAIMER = re.compile(
    r"-{3,}\s*ASE\s+Confidentiality\s+Notice\s*-{3,}"
    r"[\s\S]*?"
    r"-{3,}\s*ASE\s+Confidentiality\s+Notice\s*-{3,}",
    re.IGNORECASE,
)

# UNIMICRON 欣興：起始 ***** UNIMICRON Confidentiality Notice *****，結束為長星號行
_UNIMICRON_DISCLAIMER = re.compile(
    r"\*{3,}\s*UNIMICRON\s+Confidentiality\s+Notice\s*\*+"
    r"[\s\S]*?"
    r"\*{20,}",
    re.IGNORECASE,
)

# 通用 Email Confidentiality Notice（Kinsus / Phoenix Silicon 等）：
# header 允許前後各 0+ 顆星號（實際資料三種變體都見過：前後皆有、僅後有、皆無）
# 結束於 Copyright ... All Rights Reserved（再選擇性吃掉尾巴的星號）
_EMAIL_DISCLAIMER = re.compile(
    r"\**\s*Email\s+Confidentiality\s+Notice\s*\**"
    r"[\s\S]*?"
    r"Copyright[^\n]*All\s+Rights\s+Reserved\.?\s*\**",
    re.IGNORECASE,
)

# Lotus Notes 附件刪除標記：[附件檔 "X" 已被 XXX 刪除]
_ATTACHMENT_DELETED = re.compile(r"\[附件檔[^\]]*已被[^\]]*刪除\]")

# 連續 4+ 換行 → 3 個（保留最多 2 個空行）
_EXCESSIVE_BLANK_LINES = re.compile(r"\n{4,}")

_PATTERNS = (
    _ASE_DISCLAIMER,
    _UNIMICRON_DISCLAIMER,
    _EMAIL_DISCLAIMER,
    _ATTACHMENT_DELETED,
)


def clean_email_body(body: str | None) -> str:
    """移除信件中常見的免責聲明、附件刪除標記、過多空行。

    Args:
        body: 原始信件內容（可為 None / 空字串）

    Returns:
        清理後的內容；輸入為 None / 空時回傳 ""
    """
    if not body:
        return ""
    cleaned = body
    for pat in _PATTERNS:
        cleaned = pat.sub("", cleaned)
    cleaned = _EXCESSIVE_BLANK_LINES.sub("\n\n\n", cleaned)
    return cleaned.strip()
