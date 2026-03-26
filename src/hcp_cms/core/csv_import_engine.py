"""CsvImportEngine — CSV 歷史客服記錄批次匯入。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# 型別定義
# ---------------------------------------------------------------------------


@dataclass
class ImportPreview:
    total: int = 0
    new_count: int = 0
    conflict_count: int = 0


@dataclass
class ImportResult:
    success: int = 0
    skipped: int = 0
    overwritten: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


class ConflictStrategy(Enum):
    SKIP = "skip"
    OVERWRITE = "overwrite"


# mapping 方向：{csv_欄名: db_欄名} 或 {csv_欄名: "skip"}
Mapping = dict[str, str]

# 下拉選單可用欄位（排除自動欄位）
MAPPABLE_DB_COLS = [
    "skip",
    "status", "progress", "sent_time", "company_id", "contact_person",
    "subject", "system_product", "issue_type", "error_type", "impact_period",
    "actual_reply", "reply_time", "notes", "rd_assignee", "handler",
    "priority", "contact_method",
]

# 預設欄位對應（CSV 欄名 → db 欄名）
DEFAULT_MAPPING: Mapping = {
    "問題狀態": "status",
    "處理進度": "progress",
    "寄件時間": "sent_time",
    "公司": "company_id",
    "聯絡人": "contact_person",
    "主旨": "subject",
    "對客服的難易度": "priority",
    "技術協助人員1": "rd_assignee",
    "技術協助人員2": "notes",  # 特殊附加處理
    "【Type】": "issue_type",
    "問題分類": "error_type",
}

# 必須對應（不可為 skip）的欄位（db 欄名）
REQUIRED_DB_COLS = {"sent_time", "subject", "company_id"}

_WEEKDAY_RE = re.compile(r'\s*\(週.\)\s*')
_AMPM_RE = re.compile(r'(上午|下午)\s*(\d{1,2}):(\d{2})')


def _parse_sent_time(value: str | None) -> str | None:
    """解析各種 sent_time 格式，回傳 YYYY/MM/DD HH:MM:SS，失敗回傳 None。"""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None

    # 嘗試中文上午/下午格式：2026/3/2 (週一) 上午 09:27
    m = _AMPM_RE.search(s)
    if m:
        ampm, h_str, mn_str = m.group(1), m.group(2), m.group(3)
        h = int(h_str)
        mn = int(mn_str)
        if ampm == "下午" and h < 12:
            h += 12
        elif ampm == "上午" and h == 12:
            h = 0
        # 取日期部分（移除星期）
        date_part = _WEEKDAY_RE.sub(" ", s).split()[0]
        try:
            parts = date_part.split("/")
            y, mo, d = int(parts[0]), int(parts[1]), int(parts[2])
            return f"{y}/{mo:02d}/{d:02d} {h:02d}:{mn:02d}:00"
        except (ValueError, IndexError):
            return None

    # 移除星期部分後嘗試其他格式
    s = _WEEKDAY_RE.sub(" ", s).strip()

    from datetime import datetime

    # YYYY/MM/DD HH:MM:SS
    try:
        dt = datetime.strptime(s, "%Y/%m/%d %H:%M:%S")
        return dt.strftime("%Y/%m/%d %H:%M:%S")
    except ValueError:
        pass

    # YYYY/MM/DD HH:MM
    try:
        dt = datetime.strptime(s, "%Y/%m/%d %H:%M")
        return dt.strftime("%Y/%m/%d %H:%M:%S")
    except ValueError:
        pass

    # YYYY/MM/DD
    try:
        dt = datetime.strptime(s, "%Y/%m/%d")
        return dt.strftime("%Y/%m/%d %H:%M:%S")
    except ValueError:
        pass

    return None


# ---------------------------------------------------------------------------
# 主引擎（後續 Task 實作）
# ---------------------------------------------------------------------------


class CsvImportEngine:
    """CSV 歷史客服記錄批次匯入引擎。"""
