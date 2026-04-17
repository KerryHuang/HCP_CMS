"""SinglePatchEngine — 單次 Patch 整理流程。"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from hcp_cms.data.models import PatchIssue, PatchRecord
from hcp_cms.data.repositories import PatchRepository


class SinglePatchEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._repo = PatchRepository(conn)

    # ── 掃描資料夾 ──────────────────────────────────────────────────────────

    def scan_patch_dir(self, patch_dir: str) -> dict:
        """掃描解壓縮資料夾，回傳結構摘要。"""
        path = Path(patch_dir)
        result: dict = {
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
            name_lower = f.name.lower()
            if "releasenote" in name_lower or "release_note" in name_lower:
                result["release_note"] = str(f)
            elif "installation" in name_lower or "installguide" in name_lower or "install_guide" in name_lower:
                result["install_guide"] = str(f)

        return result

    # ── 讀取 ReleaseNote ─────────────────────────────────────────────────────

    def read_release_doc(self, doc_path: str) -> list[dict]:
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
            d = word.Documents.Open(str(path.absolute()))
            text: str = d.Range().Text
            d.Close(False)
            word.Quit()
            return text
        except Exception:
            return None

    def _parse_release_note_text(self, text: str) -> list[dict]:
        """從文字中辨識 Issue 編號、類型、說明。"""
        issues: list[dict] = []
        current_type = "BugFix"
        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            low = stripped.lower()
            if "bug fix" in low or "bug修正" in low or "缺陷修正" in low:
                current_type = "BugFix"
                continue
            if "enhancement" in low or "功能加強" in low or "功能增強" in low:
                current_type = "Enhancement"
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
