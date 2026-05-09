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

from hcp_cms.ui.theme import ColorPalette

# 導覽鍵 → (頁面顯示名稱, 起始章節號, 結束章節號) 對應表
# 結束章節號為 exclusive（不含）。鍵與 main_window 的 nav 項 UserRole data 對應。
# ⚠ 改用 dict 而非 list：先前用 index 對應，nav 新增「客戶管理」「Patch 整理」「操作說明」後
#   會錯位（KMS 顯示信件處理章節等）。
PAGE_SECTIONS: dict[str, tuple[str, int, int]] = {
    "dashboard": ("儀表板", 3, 4),
    "cases": ("案件管理", 4, 5),
    # 客戶管理目前無獨立章節，回退到案件管理章節
    # （客戶資訊與案件相關，§4.7 案件詳情亦含公司欄位）。
    # 完整客戶管理操作請使用左側「📖 操作說明」分頁瀏覽全部文件。
    "customers": ("客戶管理（含於案件管理章節）", 4, 5),
    "kms": ("KMS 知識庫", 5, 6),
    "email": ("信件處理", 6, 7),
    "mantis": ("Mantis 同步", 7, 8),
    "reports": ("報表中心", 8, 9),
    "patch": ("Patch 整理", 13, 14),
    "rules": ("規則設定", 9, 10),
    "settings": ("系統設定", 10, 12),  # 含第 11 章備份還原
    # "help" 鍵刻意省略 — 在「📖 操作說明」分頁時 F1 不開 dialog（避免重複）
}


def _build_help_css(p: ColorPalette) -> str:
    """根據主題生成說明對話框 CSS。"""
    even_row_bg = p.bg_hover
    return f"""
<style>
body {{
    background-color: {p.bg_secondary};
    color: {p.text_secondary};
    font-family: "Microsoft JhengHei", "微軟正黑體", sans-serif;
    font-size: 14px;
    line-height: 1.6;
    padding: 16px;
}}
h2, h3, h4 {{ color: {p.accent}; margin-top: 20px; }}
table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
th {{ background-color: {p.accent_button}; color: {p.text_primary}; padding: 8px 12px;
     text-align: left; border: 1px solid {p.border_primary}; }}
td {{ padding: 8px 12px; border: 1px solid {p.border_primary}; }}
tr:nth-child(even) {{ background-color: {even_row_bg}; }}
code {{ background-color: {p.bg_code}; color: {p.accent}; padding: 2px 6px;
       border-radius: 4px; font-size: 13px; }}
pre {{ background-color: {p.bg_code}; padding: 12px; border-radius: 6px;
      overflow-x: auto; }}
pre code {{ padding: 0; }}
blockquote {{ border-left: 3px solid {p.accent}; padding-left: 12px;
             color: {p.text_tertiary}; margin: 12px 0; }}
a {{ color: {p.accent}; }}
hr {{ border: none; border-top: 1px solid {p.border_primary}; margin: 20px 0; }}
</style>
"""


def extract_section(manual_text: str, page_key: str) -> str:
    """Extract the manual section(s) corresponding to a nav-key.

    Args:
        manual_text: 操作手冊的 markdown 全文
        page_key: nav 項的鍵（如 "kms"、"cases"），與 PAGE_SECTIONS 對應
    """
    section = PAGE_SECTIONS.get(page_key)
    if section is None:
        return "找不到對應的說明內容。"

    _, start_ch, end_ch = section

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


def render_help_html(md_text: str, palette: ColorPalette | None = None) -> str:
    """Convert markdown to styled HTML with theme."""
    from hcp_cms.ui.theme import DARK_PALETTE
    p = palette or DARK_PALETTE
    css = _build_help_css(p)
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    return f"<html><head>{css}</head><body>{body}</body></html>"


class HelpDialog(QDialog):
    """Modal dialog that displays operation manual section for the current page."""

    def __init__(
        self,
        page_key: str,
        manual_text: str,
        parent: object | None = None,
        palette: ColorPalette | None = None,
    ) -> None:
        super().__init__(parent)
        from hcp_cms.ui.theme import DARK_PALETTE
        p = palette or DARK_PALETTE

        # 取得頁面名稱
        section = PAGE_SECTIONS.get(page_key)
        if section is not None:
            title = f"說明 — {section[0]}"
        else:
            title = "說明"

        self.setWindowTitle(title)
        self.resize(800, 600)
        self.setMinimumSize(600, 400)

        # 擷取章節並渲染
        section_md = extract_section(manual_text, page_key)
        html = render_help_html(section_md, palette=p)

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
            f"QPushButton {{ background-color: {p.border_primary}; color: {p.text_secondary}; "
            f"border: 1px solid {p.text_faint}; border-radius: 4px; padding: 6px 16px; }}"
            f"QPushButton:hover {{ background-color: {p.text_faint}; }}"
        )
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setStyleSheet(f"QDialog {{ background-color: {p.bg_secondary}; }}")
