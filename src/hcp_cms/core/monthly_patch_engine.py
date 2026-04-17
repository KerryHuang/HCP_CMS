"""MonthlyPatchEngine — 每月大 PATCH 整理流程。"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from hcp_cms.data.models import PatchIssue, PatchRecord
from hcp_cms.data.repositories import PatchRepository

_TXT_FIELDS = ["issue_no", "program_code", "program_name", "issue_type",
               "region", "description", "impact", "test_direction"]


class MonthlyPatchEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._repo = PatchRepository(conn)

    # ── Issue 載入 ───────────────────────────────────────────────────────────

    def load_issues(self, source: str, month_str: str,
                    file_path: str | None = None) -> int:
        """載入 Issue 清單，回傳 patch_id。

        source='manual': 讀 file_path（.json 或 .txt tab 分隔）
        source='mantis': 透過 PlaywrightMantisService（需另行呼叫）
        """
        patch = PatchRecord(type="monthly", month_str=month_str)
        patch_id = self._repo.insert_patch(patch)

        if source == "manual" and file_path:
            issues = self._load_file(file_path)
            for idx, raw in enumerate(issues):
                issue = PatchIssue(
                    patch_id=patch_id,
                    issue_no=raw.get("issue_no", ""),
                    program_code=raw.get("program_code"),
                    program_name=raw.get("program_name"),
                    issue_type=raw.get("issue_type", "BugFix"),
                    region=raw.get("region", "共用"),
                    description=raw.get("description"),
                    impact=raw.get("impact"),
                    test_direction=raw.get("test_direction"),
                    source="manual",
                    sort_order=idx,
                )
                self._repo.insert_issue(issue)

        return patch_id

    def _load_file(self, file_path: str) -> list[dict]:
        path = Path(file_path)
        if path.suffix.lower() == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= len(_TXT_FIELDS):
                rows.append(dict(zip(_TXT_FIELDS, parts)))
        return rows

    # ── 測試報告整理 ─────────────────────────────────────────────────────────

    _REPORT_NAME_RE = re.compile(
        r"^\d{2}\.IP_\d{8}_\d{7}_TESTREPORT_(11G|12C)\.(doc|docx)$",
        re.IGNORECASE,
    )

    def prepare_test_reports(self, month_dir: str) -> dict:
        """掃描測試報告資料夾，轉換簡體→繁體，驗證命名格式。"""
        base = Path(month_dir)
        result: dict = {"converted": 0, "invalid_names": [], "files_checked": 0}

        for version in ("11G", "12C"):
            for sub in ("測試報告", "测试报告"):
                report_dir = base / version / sub
                if not report_dir.exists():
                    continue
                for f in report_dir.iterdir():
                    if f.suffix.lower() not in (".doc", ".docx"):
                        continue
                    result["files_checked"] += 1
                    if not self._REPORT_NAME_RE.match(f.name):
                        result["invalid_names"].append(f.name)
                    if f.suffix.lower() == ".docx":
                        converted = self._convert_simplified_to_traditional(f)
                        if converted:
                            result["converted"] += 1

        return result

    def _convert_simplified_to_traditional(self, path: Path) -> bool:
        """若 .docx 含簡體字則就地轉換為繁體，回傳是否有轉換。"""
        try:
            import docx as python_docx
            import opencc
            cc = opencc.OpenCC("s2t")
            doc = python_docx.Document(str(path))
            changed = False
            for para in doc.paragraphs:
                converted = cc.convert(para.text)
                if converted != para.text:
                    for run in para.runs:
                        run.text = cc.convert(run.text)
                    changed = True
            if changed:
                doc.save(str(path))
            return changed
        except Exception:
            return False

    # ── PATCH_LIST Excel ─────────────────────────────────────────────────────

    _CLR_TW   = "D6EAF8"   # TW 淡藍
    _CLR_CN   = "FFF3CD"   # CN 淡橘黃
    _CLR_BOTH = "E8F5E9"   # 共用 淡綠
    _CLR_BUG  = "FCE4D6"   # BugFix
    _CLR_ENH  = "E2EFDA"   # Enhancement
    _HDR_DARK = "1F3864"   # 主標題深藍
    _HDR_MID  = "2E75B6"   # 副標題中藍

    def generate_patch_list(self, patch_id: int, output_dir: str,
                            month_str: str | None = None) -> list[str]:
        """產 PATCH_LIST_{YYYYMM}_11G.xlsx 與 12C.xlsx，各含 3 頁籤。"""
        from openpyxl import Workbook
        from openpyxl.styles import PatternFill

        issues = self._repo.list_issues_by_patch(patch_id)
        if month_str is None:
            patch = self._repo.get_patch_by_id(patch_id)
            month_str = patch.month_str if patch and patch.month_str else "000000"

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths = []

        for version in ("11G", "12C"):
            wb = Workbook()

            # 頁籤①：IT 發行通知（8 欄）
            ws_it = wb.active
            ws_it.title = "IT 發行通知"
            hdrs_it = ["Issue No", "類型", "程式代號", "說明",
                       "FORM目錄", "DB物件", "多語更新", "備註"]
            self._write_patch_header(ws_it, hdrs_it)
            for i, iss in enumerate(issues, start=2):
                ws_it.cell(i, 1).value = iss.issue_no
                ws_it.cell(i, 2).value = iss.issue_type
                ws_it.cell(i, 3).value = iss.program_code
                ws_it.cell(i, 4).value = iss.description
                row_fill = self._CLR_ENH if iss.issue_type == "Enhancement" else self._CLR_BUG
                for c in range(1, 9):
                    ws_it.cell(i, c).fill = PatternFill("solid", fgColor=row_fill)

            # 頁籤②：HR 發行通知（11 欄）
            ws_hr = wb.create_sheet("HR 發行通知")
            hdrs_hr = ["Issue No", "計區域", "類型", "程式代號", "程式名稱",
                       "功能說明", "影響說明/用途", "相關程式(FORM)",
                       "上線所需動作", "測試方向及注意事項", "備註"]
            self._write_patch_header(ws_hr, hdrs_hr)
            for i, iss in enumerate(issues, start=2):
                region_fill = {"TW": self._CLR_TW, "CN": self._CLR_CN}.get(iss.region, self._CLR_BOTH)
                ws_hr.cell(i, 1).value = iss.issue_no
                ws_hr.cell(i, 2).value = iss.region
                ws_hr.cell(i, 3).value = iss.issue_type
                ws_hr.cell(i, 4).value = iss.program_code
                ws_hr.cell(i, 5).value = iss.program_name
                ws_hr.cell(i, 6).value = iss.description
                ws_hr.cell(i, 7).value = iss.impact
                ws_hr.cell(i, 9).value = "請與資訊單位確認是否已完成更新，確認更新完成再進行測試"
                ws_hr.cell(i, 10).value = iss.test_direction
                for c in range(1, 12):
                    ws_hr.cell(i, c).fill = PatternFill("solid", fgColor=region_fill)

            # 頁籤③：問題修正補充說明
            ws_supp = wb.create_sheet("問題修正補充說明")
            self._write_patch_header(ws_supp,
                ["Issue No", "修改原因", "原問題", "範例說明", "修正後", "注意事項"])
            for i, iss in enumerate(issues, start=2):
                ws_supp.cell(i, 1).value = iss.issue_no
                if iss.mantis_detail:
                    try:
                        detail = json.loads(iss.mantis_detail)
                        ws_supp.cell(i, 2).value = detail.get("reason")
                        ws_supp.cell(i, 3).value = detail.get("original")
                        ws_supp.cell(i, 4).value = detail.get("example")
                        ws_supp.cell(i, 5).value = detail.get("fixed")
                        ws_supp.cell(i, 6).value = detail.get("notes")
                    except (json.JSONDecodeError, AttributeError):
                        pass

            fname = f"PATCH_LIST_{month_str}_{version}.xlsx"
            p = str(out / fname)
            wb.save(p)
            paths.append(p)

        return paths

    def _write_patch_header(self, ws: object, headers: list[str]) -> None:
        from openpyxl.styles import Alignment, Font, PatternFill
        for c, h in enumerate(headers, start=1):
            cell = ws.cell(1, c)
            cell.value = h
            cell.font = Font(name="微軟正黑體", bold=True, size=11, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=self._HDR_DARK)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
