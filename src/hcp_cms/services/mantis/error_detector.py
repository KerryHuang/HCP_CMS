"""Mantis SOAP 錯誤訊息分類工具。"""
from __future__ import annotations

_NOT_FOUND_KEYWORDS = (
    "not found",        # "Issue #1234 not found"
    "does not exist",   # "Issue does not exist"
    "不存在",            # 中文 fault（少數版本）
)


def is_ticket_not_found(last_error: str | None) -> bool:
    """根據 SOAP last_error 字串判斷是否為 'ticket 不存在' 錯誤。

    用於區分「Mantis 連線失敗 / SOAP 一般錯誤」與「ticket 被刪除」兩種失敗情境。
    純字串比對，跨 Mantis 版本可能誤判 — Phase 2 可升級為 enum 返回。
    """
    if not last_error:
        return False
    lower = last_error.lower()
    return any(kw.lower() in lower for kw in _NOT_FOUND_KEYWORDS)
