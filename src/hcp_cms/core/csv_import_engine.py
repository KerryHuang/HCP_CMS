"""CsvImportEngine — CSV 歷史客服記錄批次匯入。"""
from __future__ import annotations

import csv
import re
import sqlite3
from collections.abc import Callable
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

    def preview(self, path: Path, mapping: Mapping) -> ImportPreview:
        """計算 CSV 中新增/衝突筆數（不寫入資料庫）。

        模擬從序號 1 開始依序產生 case_id，檢查每個 case_id 是否已存在於 DB。
        """
        enc = _detect_encoding(path)
        result = ImportPreview()
        # 以月份為 key，從 0 開始計數（不讀取 DB MAX，模擬全新匯入）
        base: dict[str, int] = {}

        with path.open(encoding=enc, newline="") as f:
            reader = csv.DictReader(f)
            sent_time_col = next(
                (c for c, d in mapping.items() if d == "sent_time"), ""
            )
            for row in reader:
                result.total += 1
                sent_time_raw = row.get(sent_time_col, "")
                normalized = _parse_sent_time(sent_time_raw)
                year_month = self._extract_year_month(normalized)

                # 直接累加，不查 DB MAX（預覽模式從 1 開始計）
                base[year_month] = base.get(year_month, 0) + 1
                case_id = f"CS-{year_month}-{base[year_month]:03d}"

                existing = self._conn.execute(
                    "SELECT 1 FROM cs_cases WHERE case_id = ?", (case_id,)
                ).fetchone()
                if existing:
                    result.conflict_count += 1
                else:
                    result.new_count += 1

        return result

    def _ensure_company(self, company_name: str) -> None:
        """若公司不存在則自動建立（INSERT OR IGNORE）。"""
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        self._conn.execute(
            """INSERT OR IGNORE INTO companies
               (company_id, name, domain, created_at)
               VALUES (?, ?, ?, ?)""",
            (company_name, company_name, company_name, now),
        )
        self._conn.commit()

    def execute(
        self,
        path: Path,
        mapping: Mapping,
        strategy: ConflictStrategy,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> ImportResult:
        """執行匯入。"""
        enc = _detect_encoding(path)
        result = ImportResult()
        base: dict[str, int] = {}

        # 計算總列數（供進度條用）
        with path.open(encoding=enc, newline="") as f:
            total = sum(1 for _ in csv.reader(f)) - 1  # 減掉標頭

        with path.open(encoding=enc, newline="") as f:
            reader = csv.DictReader(f)
            for line_no, row in enumerate(reader, start=2):  # 2 = 第一列資料
                if progress_cb:
                    progress_cb(line_no - 1, total)

                # --- 解析 sent_time ---
                sent_time_csv_col = next(
                    (c for c, d in mapping.items() if d == "sent_time"), None
                )
                sent_time_raw = (row.get(sent_time_csv_col or "", "") or "") if sent_time_csv_col else ""
                normalized_time = _parse_sent_time(sent_time_raw)
                if normalized_time is None:
                    result.failed += 1
                    result.errors.append(f"第 {line_no} 列：sent_time 格式錯誤（{sent_time_raw!r}）")
                    continue

                # --- 驗證 subject ---
                subject_csv_col = next(
                    (c for c, d in mapping.items() if d == "subject"), None
                )
                subject_val = (row.get(subject_csv_col or "", "") or "").strip() if subject_csv_col else ""
                if not subject_val:
                    result.failed += 1
                    result.errors.append(f"第 {line_no} 列：subject 為空")
                    continue

                # --- 產生 case_id（從 CSV 序號 1 開始，不查 DB MAX）---
                year_month = self._extract_year_month(normalized_time)
                base[year_month] = base.get(year_month, 0) + 1
                case_id = f"CS-{year_month}-{base[year_month]:03d}"

                # --- 公司自動建立 ---
                company_csv_col = next(
                    (c for c, d in mapping.items() if d == "company_id"), None
                )
                company_name = (row.get(company_csv_col or "", "") or "").strip() if company_csv_col else ""
                if company_name:
                    self._ensure_company(company_name)

                # --- 建構資料列 ---
                case_dict = self._build_case_dict(row, mapping, case_id)

                # --- 寫入 ---
                try:
                    existing = self._conn.execute(
                        "SELECT created_at FROM cs_cases WHERE case_id = ?", (case_id,)
                    ).fetchone()

                    if existing:
                        if strategy == ConflictStrategy.SKIP:
                            result.skipped += 1
                        else:  # OVERWRITE
                            self._overwrite_case(case_id, case_dict, existing["created_at"])
                            result.overwritten += 1
                    else:
                        self._insert_case(case_dict)
                        result.success += 1

                except Exception as e:
                    result.failed += 1
                    result.errors.append(f"第 {line_no} 列：資料庫錯誤 {e}")

        if progress_cb:
            progress_cb(total, total)
        return result

    def _insert_case(self, case_dict: dict[str, object]) -> None:
        cols = list(case_dict.keys())
        vals = [case_dict[c] for c in cols]
        placeholders = ", ".join("?" for _ in cols)
        col_list = ", ".join(cols)
        self._conn.execute(
            f"INSERT INTO cs_cases ({col_list}) VALUES ({placeholders})", vals
        )
        self._conn.commit()

    def _overwrite_case(
        self, case_id: str, case_dict: dict[str, object], original_created_at: str
    ) -> None:
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        update_dict = {k: v for k, v in case_dict.items()
                       if k not in ("case_id", "created_at", "source")}
        update_dict["updated_at"] = now
        set_clause = ", ".join(f"{k} = ?" for k in update_dict)
        vals = list(update_dict.values()) + [case_id]
        self._conn.execute(
            f"UPDATE cs_cases SET {set_clause} WHERE case_id = ?", vals
        )
        self._conn.commit()

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
