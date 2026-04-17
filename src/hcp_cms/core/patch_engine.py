"""SinglePatchEngine — 單次 Patch 整理流程。"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import TypedDict

from hcp_cms.data.repositories import PatchRepository

_ISSUE_TYPE_BUGFIX = "BugFix"
_ISSUE_TYPE_ENH = "Enhancement"


class PatchScanResult(TypedDict):
    """scan_patch_dir 回傳的資料夾掃描摘要。"""
    form_files: list[str]
    sql_files: list[str]
    muti_files: list[str]   # "muti" 是 HCP 系統內的真實子目錄名稱（多語更新）
    setup_bat: bool
    release_note: str | None
    install_guide: str | None
    missing: list[str]


class SinglePatchEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._repo = PatchRepository(conn)

    # ── 掃描資料夾 ──────────────────────────────────────────────────────────

    def scan_patch_dir(self, patch_dir: str) -> PatchScanResult:
        """掃描解壓縮資料夾，回傳結構摘要。"""
        path = Path(patch_dir)
        result: PatchScanResult = {
            "form_files": [],
            "sql_files": [],
            "muti_files": [],
            "setup_bat": False,
            "release_note": None,
            "install_guide": None,
            "missing": [],
        }

        for sub, key, required in [("form", "form_files", True),
                                    ("sql", "sql_files", True),
                                    ("muti", "muti_files", False)]:
            sub_path = path / sub
            if sub_path.exists():
                result[key] = [f.name for f in sub_path.iterdir() if f.is_file()]
            elif required:
                result["missing"].append(f"{sub}/")

        result["setup_bat"] = (path / "setup.bat").exists()

        for f in path.iterdir():
            if not f.is_file():
                continue
            name_lower = f.name.lower()
            if "releasenote" in name_lower or "release_note" in name_lower:
                result["release_note"] = str(f)
            elif "installation" in name_lower or "installguide" in name_lower or "install_guide" in name_lower:
                result["install_guide"] = str(f)

        return result

    # ── 讀取 ReleaseNote ─────────────────────────────────────────────────────

    def read_release_doc(self, doc_path: str) -> list[dict[str, str]]:
        """解析 ReleaseNote.doc/.docx，回傳 Issue 清單。"""
        path = Path(doc_path)
        if not path.exists():
            return []
        text = self._extract_doc_text(path)
        if text is None:
            return []
        return self._parse_release_note_text(text)

    def _extract_doc_text(self, path: Path) -> str | None:
        if path.suffix.lower() == ".docx":
            return self._read_docx(path)
        return self._read_doc_win32(path)

    def _read_docx(self, path: Path) -> str | None:
        try:
            import docx as python_docx
            doc = python_docx.Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception:
            return None

    def _read_doc_win32(self, path: Path) -> str | None:
        try:
            import win32com.client
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            try:
                d = word.Documents.Open(str(path.absolute()))
                text: str = d.Range().Text
                d.Close(False)
                return text
            finally:
                word.Quit()
        except Exception:
            return None

    def _parse_release_note_text(self, text: str) -> list[dict[str, str]]:
        """從文字中辨識 Issue 編號、類型、說明。"""
        issues: list[dict[str, str]] = []
        current_type = _ISSUE_TYPE_BUGFIX
        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            low = stripped.lower()
            if "bug fix" in low or "bug修正" in low or "缺陷修正" in low:
                current_type = _ISSUE_TYPE_BUGFIX
                continue
            if "enhancement" in low or "功能加強" in low or "功能增強" in low:
                current_type = _ISSUE_TYPE_ENH
                continue
            m = re.match(r"(\d{7})\s+(.*)", stripped)
            if m:
                issues.append({
                    "issue_no": m.group(1),
                    "issue_type": current_type,
                    "description": m.group(2).strip(),
                    "region": "共用",
                })
        return issues
