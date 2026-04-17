"""MonthlyPatchEngine — 每月大 PATCH 整理流程。"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path

from hcp_cms.data.models import PatchIssue, PatchRecord
from hcp_cms.data.repositories import PatchRepository

_TXT_FIELDS = [
    "issue_no",
    "program_code",
    "program_name",
    "issue_type",
    "region",
    "description",
    "impact",
    "test_direction",
]


class MonthlyPatchEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._repo = PatchRepository(conn)

    # ── Issue 載入 ───────────────────────────────────────────────────────────

    def load_issues(self, source: str, month_str: str, file_path: str | None = None) -> int:
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

    def get_issue_count(self, patch_id: int) -> int:
        """回傳 Patch 的 Issue 筆數。"""
        return len(self._repo.list_issues_by_patch(patch_id))

    def get_issues(self, patch_id: int) -> list[PatchIssue]:
        """回傳 Patch 的 Issue 清單。"""
        return self._repo.list_issues_by_patch(patch_id)

    # ── 資料夾掃描 ────────────────────────────────────────────────────────────

    _ARCHIVE_RE = re.compile(r"\d{2}\.IP_\d{8}_(\d{7})_", re.IGNORECASE)

    def _detect_structure(self, base: Path) -> str:
        """回傳 'A'（有 11G/12C 子目錄）或 'B'（平坦）。"""
        if (base / "11G").exists() or (base / "12C").exists():
            return "A"
        return "B"

    def _reorganize_to_mode_a(self, base: Path) -> None:
        """將模式 B 平坦結構整理至 11G/12C 子目錄。"""
        import shutil
        for version in ("11G", "12C"):
            ver_dir = base / version
            report_dir = ver_dir / "測試報告"
            ver_dir.mkdir(exist_ok=True)
            report_dir.mkdir(exist_ok=True)
            v_upper = version.upper()
            for f in list(base.iterdir()):
                if not f.is_file():
                    continue
                name_upper = f.name.upper()
                if f"_{v_upper}" not in name_upper:
                    continue
                if "TESTREPORT" in name_upper:
                    shutil.move(str(f), str(report_dir / f.name))
                elif f.suffix.lower() in (".7z", ".zip", ".rar"):
                    shutil.move(str(f), str(ver_dir / f.name))

    def _extract_archive(self, archive: Path, extract_dir: Path) -> None:
        """解壓 .7z 或 .zip 至 extract_dir。"""
        extract_dir.mkdir(parents=True, exist_ok=True)
        suffix = archive.suffix.lower()
        if suffix == ".7z":
            import py7zr
            with py7zr.SevenZipFile(str(archive), mode="r") as z:
                z.extractall(path=str(extract_dir))
        elif suffix == ".zip":
            import zipfile
            with zipfile.ZipFile(str(archive), "r") as z:
                z.extractall(path=str(extract_dir))
        else:
            logging.warning("不支援的封存格式，略過 [%s]", archive.name)

    def _list_files(self, directory: Path, extensions: list[str], keep_ext: bool = False) -> list[str]:
        """列出目錄內符合副檔名的檔案，keep_ext=False 則去副檔名。"""
        if not directory.exists():
            return []
        return [
            f.name if keep_ext else f.stem
            for f in sorted(directory.iterdir())
            if f.is_file() and f.suffix.lower() in extensions
        ]

    def _extract_issue_no(self, filename: str) -> str | None:
        """從封存檔名解析 7 位數 Issue No，如 '01.IP_20241128_0016552_11G.7z' → '0016552'。"""
        m = self._ARCHIVE_RE.search(filename)
        return m.group(1) if m else None

    def _read_release_note(self, extract_dir: Path) -> list[dict[str, str]]:
        """在解壓資料夾尋找 ReleaseNote，委託 SinglePatchEngine 解析。"""
        if not extract_dir.exists():
            return []
        from hcp_cms.core.patch_engine import SinglePatchEngine
        for f in extract_dir.iterdir():
            if not f.is_file():
                continue
            low = f.name.lower()
            if "releasenote" in low or "release_note" in low:
                return SinglePatchEngine(self._conn).read_release_doc(str(f))
        return []

    def scan_monthly_dir(self, patch_dir: str, month_str: str) -> dict[str, int]:
        """掃描月份資料夾，建立各版本 PatchRecord 並匯入 Issues。

        自動偵測模式 A（11G/12C 子目錄）或模式 B（平坦），模式 B 時自動整理。
        回傳 {"11G": patch_id, "12C": patch_id}（版本不存在則無對應 key）。
        """
        base = Path(patch_dir)
        patch_ids: dict[str, int] = {}

        if self._detect_structure(base) == "B":
            self._reorganize_to_mode_a(base)

        for version in ("11G", "12C"):
            version_dir = base / version
            if not version_dir.exists():
                continue
            archives = sorted(version_dir.glob("*.7z")) + sorted(version_dir.glob("*.zip"))
            if not archives:
                continue

            patch = PatchRecord(type="monthly", month_str=month_str, patch_dir=patch_dir)
            patch_id = self._repo.insert_patch(patch)
            patch_ids[version] = patch_id

            for idx, archive in enumerate(archives):
                issue_no = self._extract_issue_no(archive.name)
                extract_dir = version_dir / f"_extracted_{archive.stem}"
                try:
                    self._extract_archive(archive, extract_dir)
                except Exception as e:
                    logging.warning("解壓縮失敗 [%s]: %s", archive.name, e)
                    continue

                raw_issues = self._read_release_note(extract_dir)
                form_files = self._list_files(extract_dir / "form", [".fmb", ".rdf", ".fmx"])
                sql_files = self._list_files(extract_dir / "sql", [".sql"])
                muti_files = self._list_files(extract_dir / "muti", [".sql"], keep_ext=True)
                scan_meta = json.dumps({
                    "form_files": form_files,
                    "sql_files": sql_files,
                    "muti_files": muti_files,
                    "archive_name": archive.name,
                })

                if raw_issues:
                    for raw_idx, raw in enumerate(raw_issues):
                        self._repo.insert_issue(PatchIssue(
                            patch_id=patch_id,
                            issue_no=raw.get("issue_no", issue_no or ""),
                            issue_type=raw.get("issue_type", "BugFix"),
                            region=raw.get("region", "共用"),
                            description=raw.get("description"),
                            source="scan",
                            sort_order=idx * 100 + raw_idx,
                            mantis_detail=scan_meta,
                        ))
                elif issue_no:
                    self._repo.insert_issue(PatchIssue(
                        patch_id=patch_id,
                        issue_no=issue_no,
                        source="scan",
                        sort_order=idx,
                        mantis_detail=scan_meta,
                    ))

        return patch_ids

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
        except Exception as e:
            logging.warning("opencc 轉換失敗 [%s]: %s", path.name, e)
            return False

    # ── PATCH_LIST Excel ─────────────────────────────────────────────────────

    _CLR_TW = "D6EAF8"  # TW 淡藍
    _CLR_CN = "FFF3CD"  # CN 淡橘黃
    _CLR_BOTH = "E8F5E9"  # 共用 淡綠
    _CLR_BUG = "FCE4D6"  # BugFix
    _CLR_ENH = "E2EFDA"  # Enhancement
    _HDR_DARK = "1F3864"  # 主標題深藍
    _HDR_MID = "2E75B6"  # 副標題中藍

    def generate_patch_list(self, patch_id: int, output_dir: str, month_str: str | None = None) -> list[str]:
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
            hdrs_it = ["Issue No", "類型", "程式代號", "說明", "FORM目錄", "DB物件", "多語更新", "備註"]
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
            hdrs_hr = [
                "Issue No",
                "計區域",
                "類型",
                "程式代號",
                "程式名稱",
                "功能說明",
                "影響說明/用途",
                "相關程式(FORM)",
                "上線所需動作",
                "測試方向及注意事項",
                "備註",
            ]
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
            self._write_patch_header(ws_supp, ["Issue No", "修改原因", "原問題", "範例說明", "修正後", "注意事項"])
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

    def _find_test_report(self, base: Path, version: str, issue_no: str) -> str | None:
        """在 {base}/{version}/測試報告/ 搜尋含 issue_no 的 .doc/.docx，回傳絕對路徑。"""
        report_dir = base / version / "測試報告"
        if not report_dir.exists():
            return None
        for f in sorted(report_dir.iterdir()):
            if issue_no in f.name and f.suffix.lower() in (".doc", ".docx"):
                return str(f.absolute())
        return None

    def _write_patch_header_row(self, ws: object, headers: list[str], row: int = 1) -> None:
        """將標題列寫入指定行（可指定 row 參數，預設第 1 列）。"""
        from openpyxl.styles import Alignment, Font, PatternFill
        for c, h in enumerate(headers, start=1):
            cell = ws.cell(row, c)
            cell.value = h
            cell.font = Font(name="微軟正黑體", bold=True, size=11, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=self._HDR_DARK)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def generate_patch_list_from_dir(
        self, patch_ids: dict[str, int], patch_dir: str, month_str: str
    ) -> list[str]:
        """依 patch_ids 各版本產 PATCH_LIST_{month_str}_{VER}.xlsx，存至版本子目錄。"""
        from openpyxl import Workbook
        from openpyxl.styles import Font

        base = Path(patch_dir)
        all_issues: dict[str, list[PatchIssue]] = {
            ver: self._repo.list_issues_by_patch(pid)
            for ver, pid in patch_ids.items()
        }

        # 建立聯集 issue_no 清單（以出現順序去重）
        union_nos: list[str] = []
        seen: set[str] = set()
        for ver_issues in all_issues.values():
            for iss in ver_issues:
                if iss.issue_no not in seen:
                    union_nos.append(iss.issue_no)
                    seen.add(iss.issue_no)

        paths: list[str] = []

        for version, version_issues in all_issues.items():
            wb = Workbook()

            # ① 清單整理
            ws1 = wb.active
            ws1.title = "清單整理"
            self._write_patch_header_row(ws1, ["Issue No", "6I", "11G", "12C", "", "Mantis說明"])
            nos_11g = {i.issue_no for i in all_issues.get("11G", [])}
            nos_12c = {i.issue_no for i in all_issues.get("12C", [])}
            for r, no in enumerate(union_nos, start=2):
                ws1.cell(r, 1).value = no
                ws1.cell(r, 3).value = "V" if no in nos_11g else ""
                ws1.cell(r, 4).value = "V" if no in nos_12c else ""
                desc_iss = next(
                    (i for ver_list in all_issues.values() for i in ver_list if i.issue_no == no),
                    None,
                )
                if desc_iss:
                    ws1.cell(r, 6).value = f"{no}: {desc_iss.description or ''}"

            # ② {VER}新項目說明
            ws2 = wb.create_sheet(f"{version}新項目說明")
            ws2.cell(1, 1).value = f"{month_str[:4]}/{month_str[4:]}大PATCH更新項目說明"
            self._write_patch_header_row(
                ws2, ["區域", "類別", "程式代碼", "程式名稱", "說明", "測試報告"], row=2
            )
            for r, iss in enumerate(version_issues, start=3):
                ws2.cell(r, 1).value = iss.region
                ws2.cell(r, 2).value = "修正" if iss.issue_type == "BugFix" else "改善"
                ws2.cell(r, 3).value = iss.program_code
                ws2.cell(r, 4).value = iss.program_name
                ws2.cell(r, 5).value = iss.description
                report_path = self._find_test_report(base, version, iss.issue_no)
                cell6 = ws2.cell(r, 6)
                cell6.value = iss.issue_no
                if report_path:
                    cell6.hyperlink = "file:///" + report_path.replace("\\", "/")
                    cell6.font = Font(color="0563C1", underline="single")

            # ③ 更新物件
            ws3 = wb.create_sheet("更新物件")
            ws3.cell(1, 1).value = f"{month_str[:4]}/{month_str[4:]}大PATCH更新項目說明"
            self._write_patch_header_row(ws3, ["測試報告", "資料庫物件", "程式代碼", "多語"], row=2)
            for r, iss in enumerate(version_issues, start=3):
                ws3.cell(r, 1).value = iss.issue_no
                if iss.mantis_detail:
                    try:
                        meta = json.loads(iss.mantis_detail)
                        ws3.cell(r, 2).value = "、".join(meta.get("sql_files", []))
                        ws3.cell(r, 3).value = "、".join(meta.get("form_files", []))
                        ws3.cell(r, 4).value = "\n".join(meta.get("muti_files", []))
                    except (json.JSONDecodeError, AttributeError):
                        pass

            fname = f"PATCH_LIST_{month_str}_{version}.xlsx"
            out_path = base / version / fname
            wb.save(str(out_path))
            paths.append(str(out_path))

        return paths

    def _write_patch_header(self, ws: object, headers: list[str]) -> None:
        from openpyxl.styles import Alignment, Font, PatternFill

        for c, h in enumerate(headers, start=1):
            cell = ws.cell(1, c)
            cell.value = h
            cell.font = Font(name="微軟正黑體", bold=True, size=11, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=self._HDR_DARK)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # ── 客戶通知 HTML ────────────────────────────────────────────────────────

    def generate_notify_html(
        self,
        patch_id: int,
        output_dir: str,
        month_str: str | None = None,
        reminders: list[str] | None = None,
        notify_body: str | None = None,
    ) -> str:
        """使用 Jinja2 範本產客戶通知信 HTML。"""
        from pathlib import Path as _Path

        from jinja2 import Environment, FileSystemLoader

        issues = self._repo.list_issues_by_patch(patch_id)
        if month_str is None:
            patch = self._repo.get_patch_by_id(patch_id)
            month_str = patch.month_str if patch and patch.month_str else "000000"

        year = month_str[:4]
        month = month_str[4:]

        templates_dir = _Path(__file__).parent.parent.parent.parent / "templates"
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
        tmpl = env.get_template("patch_notify.html.j2")

        html = tmpl.render(
            year=year,
            month=month,
            issues=issues,
            notify_body=notify_body or "",
            reminders=reminders or [],
        )

        out = _Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        fname = f"【HCP11G維護客戶】{month_str}月份大PATCH更新通知.html"
        path = str(out / fname)
        _Path(path).write_text(html, encoding="utf-8")
        return path
