"""案件 header 格式化工具 — 對齊客服專區提問格式。

範例：
    "2026/5/4 (週一) 下午 04:46 加班取小值確認"
    "2026/5/4 (週一) 下午 04:46 【景碩科技】班別津貼時薪計算評估"
        （主旨本身有【】時原樣呈現，不再重複加公司名）

使用場景：
    - MantisPushManager 推送 ticket summary
    - MantisPushManager 推送 bugnote 第一行
    - 未來桌面 App / 報表也可重用
"""
from __future__ import annotations

from datetime import datetime

from hcp_cms.core.thread_tracker import ThreadTracker
from hcp_cms.data.models import Case

_WEEKDAYS = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
_SUPPORTED_FORMATS = (
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
)


def format_case_header(case: Case) -> str:
    """格式化案件 header。

    主旨優先策略：不再前加【公司名】，主旨本身的內容（含可能的【公司】前綴）
    視為權威來源直接呈現。避免「【景碩科技股份有限公司】【景碩科技】...」
    這類重複前綴的視覺冗餘。

    Args:
        case: 含 sent_time + subject 的案件

    Returns:
        例如 "2026/5/4 (週一) 下午 04:46 加班取小值確認"

    Raises:
        ValueError: sent_time / subject 任一缺漏或無法解析
    """
    if not case.sent_time:
        raise ValueError("sent_time is empty")

    dt = _parse_sent_time(case.sent_time)
    if dt is None:
        raise ValueError(f"sent_time is not a parseable format: {case.sent_time!r}")

    if not case.subject:
        raise ValueError("subject is empty")

    clean_subject = ThreadTracker.clean_subject(case.subject)
    if not clean_subject:
        raise ValueError("subject is empty after stripping prefixes")

    date_part = f"{dt.year}/{dt.month}/{dt.day}"
    weekday = _WEEKDAYS[dt.weekday()]
    ampm = "上午" if dt.hour < 12 else "下午"
    hour_12 = dt.hour % 12 if (dt.hour % 12) else 12
    time_part = f"{hour_12:02d}:{dt.minute:02d}"

    return f"{date_part} ({weekday}) {ampm} {time_part} {clean_subject}"


def _parse_sent_time(s: str) -> datetime | None:
    """嘗試多種格式 parse sent_time，全失敗回 None。"""
    for fmt in _SUPPORTED_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None
