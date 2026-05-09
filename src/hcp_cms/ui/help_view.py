"""操作說明全頁視圖：顯示文件 + TOC 導覽 + 跨文件搜尋。

設計目的：
    既有的 F1 HelpDialog 是「上下文快查」（依當前頁面顯示對應章節）。
    本視圖是「完整文件瀏覽 + 搜尋」介面，使用者可：
    1. 從左側導覽列直接點選進入
    2. 切換不同文件（操作手冊 / 系統交接 / 專案藍圖）
    3. 透過 TOC 列表跳轉至特定章節
    4. 跨文件搜尋關鍵字（顯示符合的章節片段，點擊跳轉）

⚠ Anchor ID 規則：
    使用 `_slugify()` 統一產生 anchor，與 markdown 轉 HTML 後的 ID 對應。
    保留中文字以支援繁中標題，避免 markdown.toc extension 對中文 slugify
    為空字串導致無法導覽。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import markdown
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.ui.help_dialog import _build_help_css
from hcp_cms.ui.theme import ColorPalette, ThemeManager

# 文件設定：(顯示名稱, 檔案名)
# ⚠ 顯示順序與重要性對應：操作手冊（日常使用最重要）→ 交接（給維護者）→ 藍圖（最簡）
DOCS: list[tuple[str, str]] = [
    ("📘 操作手冊", "operation-manual.md"),
    ("📗 系統交接文件", "系統交接文件.md"),
    ("📙 專案藍圖", "blueprint.md"),
]


def _docs_root() -> Path:
    """取得 docs 資料夾路徑（支援開發/打包後 PyInstaller 場景）。"""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "docs"
    # src/hcp_cms/ui/help_view.py → 專案根
    return Path(__file__).resolve().parent.parent.parent.parent / "docs"


def _slugify(title: str) -> str:
    """從章節標題產生 anchor ID。

    保留：英文字母、數字、底線、連字號、中文字（U+4E00–U+9FFF）。
    其他符號（標點、emoji）移除；空白轉連字號。

    範例：
        "## 4. 案件管理"          → "4-案件管理"
        "### 6.3 信件處理流程"    → "63-信件處理流程"
        "📊 報表中心"             → "報表中心"
    """
    s = title.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^\w一-鿿\-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def parse_toc(md_text: str) -> list[tuple[int, str, str]]:
    """從 markdown 解析 TOC，回傳 [(level, title, anchor_id), ...]。

    僅取 H2~H4（# 太大、##### 太細）。level=2 表 ##、3 表 ###。
    """
    toc: list[tuple[int, str, str]] = []
    for line in md_text.splitlines():
        m = re.match(r"^(#{2,4})\s+(.+?)\s*$", line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            toc.append((level, title, _slugify(title)))
    return toc


def search_across_docs(
    query: str, docs_data: dict[str, str], max_results: int = 30
) -> list[tuple[str, str, str, str]]:
    """跨文件搜尋。

    Args:
        query: 搜尋字串（不分大小寫）
        docs_data: {filename: markdown_text}
        max_results: 最多回傳幾筆

    Returns:
        [(filename, section_title, anchor_id, snippet), ...]
        — section 內若有命中關鍵字才會列入
    """
    results: list[tuple[str, str, str, str]] = []
    if not query.strip():
        return results
    q_lower = query.lower()

    for doc_name, text in docs_data.items():
        # 用 H2/H3/H4 標題切段
        chunks = re.split(r"^(#{2,4}\s+.+?)\s*$", text, flags=re.MULTILINE)
        # chunks 結構：[前言, header1, body1, header2, body2, ...]
        for i in range(1, len(chunks), 2):
            header_line = chunks[i].strip()
            body = chunks[i + 1] if i + 1 < len(chunks) else ""

            # 解析 header
            hm = re.match(r"^(#+)\s+(.+)$", header_line)
            if not hm:
                continue
            title = hm.group(2).strip()

            # 在 title + body 中找 query
            full_text = title + "\n" + body
            if q_lower not in full_text.lower():
                continue

            anchor = _slugify(title)

            # 取出包含 query 的片段做為 snippet
            idx = full_text.lower().find(q_lower)
            start = max(0, idx - 30)
            end = min(len(full_text), idx + len(query) + 80)
            snippet = full_text[start:end].replace("\n", " ").strip()
            if start > 0:
                snippet = "…" + snippet
            if end < len(full_text):
                snippet = snippet + "…"

            results.append((doc_name, title, anchor, snippet))
            if len(results) >= max_results:
                return results

    return results


def _inject_anchors(html: str) -> str:
    """為 <h2>~<h4> 注入 id 屬性，與 _slugify() 結果一致，供 scrollToAnchor 使用。"""

    def replace(match: re.Match) -> str:
        tag = match.group(1)
        title = match.group(2).strip()
        # 移除 HTML tag（如標題含 <code>）以對齊純文字 slug
        clean_title = re.sub(r"<[^>]+>", "", title)
        anchor = _slugify(clean_title)
        return f'<{tag} id="{anchor}">{title}</{tag}>'

    return re.sub(r"<(h[2-4])>(.+?)</\1>", replace, html, flags=re.DOTALL)


def render_doc_html(md_text: str, palette: ColorPalette, highlight: str = "") -> str:
    """將 markdown 轉為帶主題的 HTML，可選擇 highlight 關鍵字。"""
    css = _build_help_css(palette)
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    body = _inject_anchors(body)
    if highlight:
        # 簡單 highlight：在 <body> 文字節點中替換（不在 tag 內）
        # ⚠ 這個簡單實作會在 tag 屬性中誤替（如 <a href="...query...">），
        #   但對一般文件影響極小，避免引入完整 HTML parser
        pattern = re.compile(re.escape(highlight), re.IGNORECASE)
        body = pattern.sub(
            lambda m: f'<mark style="background:#fbbf24;color:#000">{m.group(0)}</mark>',
            body,
        )
    return f"<html><head>{css}</head><body>{body}</body></html>"


class HelpView(QWidget):
    """操作說明全頁視圖。"""

    def __init__(self, theme_mgr: ThemeManager | None = None) -> None:
        super().__init__()
        self._theme_mgr = theme_mgr
        self._docs_data: dict[str, str] = {}
        self._current_doc: str = DOCS[0][1]
        self._setup_ui()
        self._load_docs()
        self._render_current_doc()
        if theme_mgr:
            theme_mgr.theme_changed.connect(self._on_theme_changed)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self._title = QLabel("📖 操作說明")
        layout.addWidget(self._title)

        # 控制列：文件下拉 + 搜尋
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)

        ctrl.addWidget(QLabel("文件："))
        self._doc_combo = QComboBox()
        for display, filename in DOCS:
            self._doc_combo.addItem(display, filename)
        self._doc_combo.setFixedWidth(200)
        self._doc_combo.currentIndexChanged.connect(self._on_doc_changed)
        ctrl.addWidget(self._doc_combo)

        ctrl.addSpacing(20)

        ctrl.addWidget(QLabel("搜尋："))
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(
            "輸入關鍵字（例：如何匯入信件、自動結案、報表）..."
        )
        self._search_input.textChanged.connect(self._on_search_changed)
        ctrl.addWidget(self._search_input, stretch=1)

        layout.addLayout(ctrl)

        # 主區域：左 TOC（或搜尋結果） + 右內容
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._toc_list = QListWidget()
        self._toc_list.setMinimumWidth(220)
        self._toc_list.setMaximumWidth(380)
        self._toc_list.itemClicked.connect(self._on_toc_clicked)
        splitter.addWidget(self._toc_list)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        splitter.addWidget(self._browser)

        splitter.setSizes([260, 700])
        layout.addWidget(splitter)

        # 狀態列
        self._status = QLabel("")
        layout.addWidget(self._status)

    def _load_docs(self) -> None:
        """讀取所有 docs 檔案內容到記憶體。"""
        root = _docs_root()
        for _, filename in DOCS:
            path = root / filename
            if path.exists():
                self._docs_data[filename] = path.read_text(encoding="utf-8")

    def _on_doc_changed(self) -> None:
        self._current_doc = self._doc_combo.currentData()
        # 切換文件時清掉搜尋
        self._search_input.blockSignals(True)
        self._search_input.clear()
        self._search_input.blockSignals(False)
        self._render_current_doc()

    def _render_current_doc(self) -> None:
        text = self._docs_data.get(self._current_doc, "")
        self._render_toc(text)
        self._render_html(text)
        self._status.setText(
            f"已載入：{self._current_doc}（{len(text.splitlines())} 行）"
        )

    def _render_toc(self, md_text: str) -> None:
        self._toc_list.clear()
        toc = parse_toc(md_text)
        for level, title, anchor in toc:
            indent = "    " * (level - 2)  # H2 不縮排、H3 縮一級、H4 縮兩級
            item = QListWidgetItem(f"{indent}{title}")
            # 用 str 表示 TOC 模式（單一 anchor）
            item.setData(Qt.ItemDataRole.UserRole, anchor)
            self._toc_list.addItem(item)

    def _render_html(self, md_text: str, highlight: str = "") -> None:
        from hcp_cms.ui.theme import DARK_PALETTE

        p = self._theme_mgr.current_palette() if self._theme_mgr else DARK_PALETTE
        html = render_doc_html(md_text, p, highlight=highlight)
        self._browser.setHtml(html)

    def _on_toc_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, tuple) and len(data) == 2:
            # 搜尋結果模式：(filename, anchor)
            doc_name, anchor = data
            # 切換文件下拉（會觸發重新渲染並清掉 search input）
            target_idx = next(
                (i for i, d in enumerate(DOCS) if d[1] == doc_name), -1
            )
            if target_idx >= 0:
                # 暫存 search 字串以便 highlight
                query = self._search_input.text().strip()
                # 切文件（會清空 search → 不 highlight）
                self._doc_combo.setCurrentIndex(target_idx)
                # 切完後重新加 highlight
                if query:
                    self._search_input.blockSignals(True)
                    self._search_input.setText(query)
                    self._search_input.blockSignals(False)
                    self._render_html(self._docs_data[doc_name], highlight=query)
                # 滾動到指定 anchor
                self._browser.scrollToAnchor(anchor)
        elif isinstance(data, str):
            # TOC 模式：直接 anchor
            self._browser.scrollToAnchor(data)

    def _on_search_changed(self, text: str) -> None:
        text = text.strip()
        if not text:
            # 清空搜尋 → 還原 TOC + 內容（不 highlight）
            self._render_current_doc()
            return

        # 跨文件搜尋
        results = search_across_docs(text, self._docs_data)

        # 將 TOC list 切換成搜尋結果
        self._toc_list.clear()
        if not results:
            item = QListWidgetItem(f"（無符合「{text}」的章節）")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._toc_list.addItem(item)
        else:
            for doc_name, title, anchor, snippet in results:
                doc_display = next(
                    (d[0] for d in DOCS if d[1] == doc_name), doc_name
                )
                item = QListWidgetItem(
                    f"[{doc_display}] {title}\n  {snippet[:80]}"
                )
                item.setData(Qt.ItemDataRole.UserRole, (doc_name, anchor))
                self._toc_list.addItem(item)

        # 在當前文件 highlight 關鍵字（搜尋結果跨文件，但只在當前顯示文件 highlight）
        current_text = self._docs_data.get(self._current_doc, "")
        if current_text:
            self._render_html(current_text, highlight=text)

        self._status.setText(
            f"搜尋「{text}」：找到 {len(results)} 個符合章節（跨 {len(self._docs_data)} 份文件）"
        )

    def _on_theme_changed(self, palette: ColorPalette) -> None:
        # 主題變更時重新渲染（TOC 不受影響）
        if self._search_input.text().strip():
            self._render_html(
                self._docs_data.get(self._current_doc, ""),
                highlight=self._search_input.text().strip(),
            )
        else:
            self._render_current_doc()
