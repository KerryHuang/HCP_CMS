"""F1 help dialog — shows operation manual section for the current page."""

from __future__ import annotations

import re

import markdown
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

# 頁面索引 → (頁面名稱, 起始章節號, 結束章節號) 的對應表
# 結束章節號為 exclusive（不含）
PAGE_SECTIONS: list[tuple[str, int, int]] = [
    ("儀表板", 3, 4),
    ("案件管理", 4, 5),
    ("KMS 知識庫", 5, 6),
    ("信件處理", 6, 7),
    ("Mantis 同步", 7, 8),
    ("報表中心", 8, 9),
    ("規則設定", 9, 10),
    ("系統設定", 10, 12),  # 含第 11 章備份還原
]

_DARK_CSS = """
<style>
body {
    background-color: #1e293b;
    color: #e2e8f0;
    font-family: "Microsoft JhengHei", "微軟正黑體", sans-serif;
    font-size: 14px;
    line-height: 1.6;
    padding: 16px;
}
h2, h3, h4 { color: #60a5fa; margin-top: 20px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; }
th { background-color: #1e3a5f; color: #f1f5f9; padding: 8px 12px;
     text-align: left; border: 1px solid #334155; }
td { padding: 8px 12px; border: 1px solid #334155; }
tr:nth-child(even) { background-color: #253349; }
code { background-color: #0f172a; color: #93c5fd; padding: 2px 6px;
       border-radius: 4px; font-size: 13px; }
pre { background-color: #0f172a; padding: 12px; border-radius: 6px;
      overflow-x: auto; }
pre code { padding: 0; }
blockquote { border-left: 3px solid #60a5fa; padding-left: 12px;
             color: #94a3b8; margin: 12px 0; }
a { color: #60a5fa; }
hr { border: none; border-top: 1px solid #334155; margin: 20px 0; }
</style>
"""


def extract_section(manual_text: str, page_index: int) -> str:
    """Extract the manual section(s) corresponding to a page index."""
    if page_index < 0 or page_index >= len(PAGE_SECTIONS):
        return "找不到對應的說明內容。"

    _, start_ch, end_ch = PAGE_SECTIONS[page_index]

    # 找出所有 ## N. 標題的位置
    pattern = re.compile(r"^## (\d+)\. ", re.MULTILINE)
    matches = list(pattern.finditer(manual_text))

    start_pos: int | None = None
    end_pos: int | None = None

    for i, m in enumerate(matches):
        ch_num = int(m.group(1))
        if ch_num == start_ch and start_pos is None:
            start_pos = m.start()
        if ch_num == end_ch:
            end_pos = m.start()
            break

    if start_pos is None:
        return "找不到對應的說明內容。"

    section = manual_text[start_pos:end_pos].rstrip() if end_pos else manual_text[start_pos:].rstrip()

    # 移除尾部的 --- 分隔線
    section = re.sub(r"\n---\s*$", "", section)

    return section


def render_help_html(md_text: str) -> str:
    """Convert markdown to styled HTML with dark theme."""
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    return f"<html><head>{_DARK_CSS}</head><body>{body}</body></html>"


class HelpDialog(QDialog):
    """Modal dialog that displays operation manual section for the current page."""

    def __init__(
        self,
        page_index: int,
        manual_text: str,
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)

        # 取得頁面名稱
        if 0 <= page_index < len(PAGE_SECTIONS):
            page_name = PAGE_SECTIONS[page_index][0]
            title = f"說明 — {page_name}"
        else:
            title = "說明"

        self.setWindowTitle(title)
        self.resize(800, 600)
        self.setMinimumSize(600, 400)

        # 擷取章節並渲染
        section_md = extract_section(manual_text, page_index)
        html = render_help_html(section_md)

        # UI
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setHtml(html)
        layout.addWidget(self._browser)

        close_btn = QPushButton("關閉")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.close)
        close_btn.setStyleSheet(
            "QPushButton { background-color: #334155; color: #e2e8f0; "
            "border: 1px solid #475569; border-radius: 4px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #475569; }"
        )
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Dialog 深色背景
        self.setStyleSheet("QDialog { background-color: #1e293b; }")
