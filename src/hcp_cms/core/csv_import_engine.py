"""CsvImportEngine — CSV 歷史客服記錄批次匯入。"""
from __future__ import annotations

import csv
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


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
_TECH2_RE = re.compile(r'\n【技術協助2】.*')


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
# 編碼偵測
# ---------------------------------------------------------------------------


def _detect_encoding(path: Path) -> str:
    """依序嘗試 UTF-8-BOM、UTF-8、Big5，回傳可用編碼，失敗拋 ValueError。"""
    for enc in ("utf-8-sig", "utf-8", "big5"):
        try:
            path.read_text(encoding=enc)
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"無法識別編碼：{path.name}")


# ---------------------------------------------------------------------------
# 主引擎
# ---------------------------------------------------------------------------


class CsvImportEngine:
    """CSV 歷史客服記錄批次匯入引擎。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        from hcp_cms.data.repositories import CaseRepository, CompanyRepository

        self._conn = conn
        self._case_repo = CaseRepository(conn)
        self._company_repo = CompanyRepository(conn)

    def parse_headers(self, path: Path) -> list[str]:
        """偵測編碼並回傳 CSV 標頭清單。"""
        enc = _detect_encoding(path)
        with path.open(encoding=enc, newline="") as f:
            reader = csv.reader(f)
            headers = next(reader, [])
        return headers

    def _next_case_id(self, year_month: str, base: dict[str, int]) -> str:
        """依月份快取產生 CS-YYYYMM-NNN 格式 case_id。"""
        if year_month not in base:
            row = self._conn.execute(
                "SELECT MAX(case_id) FROM cs_cases WHERE case_id LIKE ?",
                (f"CS-{year_month}-%",),
            ).fetchone()
            max_id: str | None = row[0] if row else None
            base[year_month] = int(max_id[-3:]) if max_id else 0
        base[year_month] += 1
        return f"CS-{year_month}-{base[year_month]:03d}"

    def _extract_year_month(self, sent_time_normalized: str | None) -> str:
        """從標準化 sent_time 取 YYYYMM，失敗時用當下年月。"""
        if sent_time_normalized:
            try:
                dt = datetime.strptime(sent_time_normalized[:7], "%Y/%m")
                return dt.strftime("%Y%m")
            except ValueError:
                pass
        return datetime.now().strftime("%Y%m")

    def _append_tech2(self, existing_notes: str | None, tech2_value: str) -> str:
        """附加技術協助人員2至 notes，移除舊值後重新附加。"""
        base = _TECH2_RE.sub("", existing_notes or "").rstrip()
        if tech2_value:
            return base + f"\n【技術協助2】{tech2_value}"
        return base

    def _build_case_dict(
        self,
        row: dict[str, str],
        mapping: Mapping,
        case_id: str,
    ) -> dict[str, object]:
        """將一列 CSV 資料依 mapping 轉換為 cs_cases 欄位字典。"""
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

        result: dict[str, object] = {
            "case_id": case_id,
            "source": "csv_import",
            "created_at": now,
            "updated_at": now,
            "contact_method": "Email",
            "replied": "否",
            "status": "處理中",
            "priority": "中",
        }

        tech2_col: str | None = None
        for csv_col, db_col in mapping.items():
            if db_col == "skip":
                continue
            val = row.get(csv_col, "") or ""
            if db_col == "notes" and csv_col == "技術協助人員2":
                # 技術協助人員2 特殊附加格式（僅限此欄名）
                tech2_col = csv_col
                continue
            if db_col == "sent_time":
                result[db_col] = _parse_sent_time(val)
            elif db_col == "company_id":
                result[db_col] = val.strip() or None
            else:
                result[db_col] = val or None

        # 技術協助人員2 附加
        if tech2_col is not None:
            tech2_val = (row.get(tech2_col, "") or "").strip()
            existing = str(result.get("notes") or "")
            result["notes"] = self._append_tech2(existing, tech2_val) or None

        return result
