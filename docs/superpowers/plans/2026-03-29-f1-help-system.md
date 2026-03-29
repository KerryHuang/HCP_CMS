# F1 上下文說明系統 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 F1 鍵開啟 Modal Dialog，根據當前頁面自動顯示 operation-manual.md 對應章節內容（Markdown 渲染為 HTML）。

**Architecture:** 新增 `HelpDialog(QDialog)` 負責章節擷取、Markdown→HTML 轉換與深色主題渲染。`MainWindow` 新增 F1 快捷鍵綁定，取得當前頁面索引後開啟 HelpDialog。

**Tech Stack:** PySide6 QTextBrowser、Python `markdown` 套件（tables 擴展）

**Spec:** `docs/superpowers/specs/2026-03-29-f1-help-system-design.md`

---

### Task 1: 安裝 markdown 套件

**Files:**
- Modify: `pyproject.toml:14` (dependencies)

- [ ] **Step 1: 新增 markdown 依賴**

在 `pyproject.toml` 的 `dependencies` 清單中新增：

```toml
"markdown>=3.5",
```

加在 `"keyring>=25.0",` 之後。

- [ ] **Step 2: 安裝依賴**

Run: `.venv/Scripts/pip.exe install -e ".[dev]"`
Expected: Successfully installed markdown

- [ ] **Step 3: 驗證安裝**

Run: `.venv/Scripts/python.exe -c "import markdown; print(markdown.version)"`
Expected: 印出版本號（3.x）

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: 新增 markdown 套件依賴（F1 說明系統用）"
```

---

### Task 2: HelpDialog 核心邏輯 — 章節擷取與 Markdown 渲染（TDD）

**Files:**
- Create: `src/hcp_cms/ui/help_dialog.py`
- Create: `tests/unit/test_help_dialog.py`

- [ ] **Step 1: 寫失敗測試 — 章節擷取**

```python
"""Tests for HelpDialog — section extraction and markdown rendering."""

import pytest

from hcp_cms.ui.help_dialog import extract_section, PAGE_SECTIONS


class TestExtractSection:
    """Test markdown section extraction from operation manual."""

    def test_extract_dashboard_section(self):
        manual = (
            "# 操作手冊\n\n"
            "## 2. 啟動應用程式\n\n啟動說明。\n\n---\n\n"
            "## 3. 儀表板\n\n儀表板提供即時概覽。\n\n### 3.1 KPI 卡片\n\n"
            "| KPI | 說明 |\n|-----|------|\n| 本月案件 | 當月案件總數 |\n\n---\n\n"
            "## 4. 案件管理\n\n案件列表。\n"
        )
        result = extract_section(manual, 0)  # 頁面索引 0 = 儀表板 = 章節 3
        assert "儀表板提供即時概覽" in result
        assert "KPI 卡片" in result
        assert "啟動應用程式" not in result
        assert "案件管理" not in result

    def test_extract_case_section(self):
        manual = (
            "## 3. 儀表板\n\n儀表板內容。\n\n---\n\n"
            "## 4. 案件管理\n\n案件列表與搜尋。\n\n### 4.1 案件列表\n\n列表內容。\n\n---\n\n"
            "## 5. KMS 知識庫\n\nKMS 內容。\n"
        )
        result = extract_section(manual, 1)  # 頁面索引 1 = 案件管理 = 章節 4
        assert "案件列表與搜尋" in result
        assert "儀表板" not in result
        assert "KMS" not in result

    def test_extract_settings_includes_backup_section(self):
        manual = (
            "## 9. 規則設定\n\n規則內容。\n\n---\n\n"
            "## 10. 系統設定\n\n系統設定內容。\n\n---\n\n"
            "## 11. 資料庫備份與還原\n\n備份內容。\n\n---\n\n"
            "## 12. 舊版系統遷移\n\n遷移說明。\n"
        )
        result = extract_section(manual, 7)  # 頁面索引 7 = 系統設定 = 章節 10+11
        assert "系統設定內容" in result
        assert "備份內容" in result
        assert "規則" not in result
        assert "舊版系統遷移" not in result

    def test_extract_invalid_index_returns_fallback(self):
        manual = "## 3. 儀表板\n\n內容。\n"
        result = extract_section(manual, 99)
        assert "找不到對應的說明內容" in result

    def test_page_sections_mapping_count(self):
        assert len(PAGE_SECTIONS) == 8


class TestMarkdownRendering:
    """Test that markdown-to-HTML conversion works with tables."""

    def test_table_renders_as_html(self):
        from hcp_cms.ui.help_dialog import render_help_html

        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        html = render_help_html(md)
        assert "<table" in html
        assert "<td" in html

    def test_heading_renders(self):
        from hcp_cms.ui.help_dialog import render_help_html

        md = "### 3.1 KPI 卡片\n\n說明文字。"
        html = render_help_html(md)
        assert "<h3" in html
        assert "KPI 卡片" in html

    def test_dark_theme_css_injected(self):
        from hcp_cms.ui.help_dialog import render_help_html

        md = "Hello"
        html = render_help_html(md)
        assert "#1e293b" in html  # 深色背景色
        assert "#e2e8f0" in html  # 文字色
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_help_dialog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hcp_cms.ui.help_dialog'`

- [ ] **Step 3: 實作 extract_section 和 render_help_html**

```python
"""F1 help dialog — shows operation manual section for the current page."""

from __future__ import annotations

import re
from pathlib import Path

import markdown

# 頁面索引 → (起始章節號, 結束章節號) 的對應表
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
```

- [ ] **Step 4: 執行測試確認通過**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_help_dialog.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/ui/help_dialog.py tests/unit/test_help_dialog.py
git commit -m "feat: HelpDialog 核心邏輯 — 章節擷取與 Markdown 渲染"
```

---

### Task 3: HelpDialog UI 元件

**Files:**
- Modify: `src/hcp_cms/ui/help_dialog.py`
- Modify: `tests/unit/test_help_dialog.py`

- [ ] **Step 1: 寫失敗測試 — HelpDialog UI**

在 `tests/unit/test_help_dialog.py` 末尾新增：

```python
class TestHelpDialogWidget:
    """Test HelpDialog QDialog widget."""

    def test_dialog_creation(self, qapp):
        from hcp_cms.ui.help_dialog import HelpDialog

        dialog = HelpDialog(page_index=0, manual_text="## 3. 儀表板\n\n測試內容。\n")
        assert dialog.windowTitle() == "說明 — 儀表板"

    def test_dialog_contains_content(self, qapp):
        from hcp_cms.ui.help_dialog import HelpDialog

        dialog = HelpDialog(page_index=0, manual_text="## 3. 儀表板\n\n測試內容。\n")
        html = dialog._browser.toHtml()
        assert "測試內容" in html

    def test_dialog_default_size(self, qapp):
        from hcp_cms.ui.help_dialog import HelpDialog

        dialog = HelpDialog(page_index=0, manual_text="## 3. 儀表板\n\n內容。\n")
        assert dialog.width() >= 800
        assert dialog.height() >= 600

    def test_dialog_invalid_index_shows_fallback(self, qapp):
        from hcp_cms.ui.help_dialog import HelpDialog

        dialog = HelpDialog(page_index=99, manual_text="## 3. 儀表板\n\n內容。\n")
        assert dialog.windowTitle() == "說明"
        html = dialog._browser.toHtml()
        assert "找不到" in html
```

同時在檔案頂部加入 fixture（如果尚未存在）：

```python
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_help_dialog.py::TestHelpDialogWidget -v`
Expected: FAIL — `ImportError: cannot import name 'HelpDialog'`

- [ ] **Step 3: 實作 HelpDialog 類別**

在 `src/hcp_cms/ui/help_dialog.py` 末尾新增：

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)


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
```

- [ ] **Step 4: 執行測試確認通過**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_help_dialog.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/ui/help_dialog.py tests/unit/test_help_dialog.py
git commit -m "feat: HelpDialog UI 元件 — QTextBrowser + 深色主題"
```

---

### Task 4: MainWindow F1 快捷鍵綁定

**Files:**
- Modify: `src/hcp_cms/ui/main_window.py`
- Modify: `tests/unit/test_ui.py`

- [ ] **Step 1: 寫失敗測試**

在 `tests/unit/test_ui.py` 的 `TestMainWindow` 類別中新增：

```python
    def test_f1_shortcut_exists(self, qapp):
        from PySide6.QtGui import QKeySequence
        from hcp_cms.ui.main_window import MainWindow

        window = MainWindow()
        shortcuts = [
            a.shortcut().toString()
            for a in window.actions()
        ]
        assert "F1" in shortcuts
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_ui.py::TestMainWindow::test_f1_shortcut_exists -v`
Expected: FAIL — `assert "F1" in shortcuts`

- [ ] **Step 3: 在 MainWindow 中新增 F1 綁定**

在 `main_window.py` 頂部新增 import：

```python
from pathlib import Path
import sys
```

在 `_setup_shortcuts` 方法末尾新增：

```python
        # F1 — 上下文說明
        help_action = QAction("F1", self)
        help_action.setShortcut(QKeySequence("F1"))
        help_action.triggered.connect(self._on_help_requested)
        self.addAction(help_action)
```

在 `MainWindow` 類別中新增方法：

```python
    def _on_help_requested(self) -> None:
        """Open help dialog for the current page."""
        from hcp_cms.ui.help_dialog import HelpDialog

        manual_text = self._load_manual()
        if manual_text:
            page_index = self._nav_list.currentRow()
            dialog = HelpDialog(page_index, manual_text, parent=self)
            dialog.exec()

    def _load_manual(self) -> str:
        """Load operation-manual.md content."""
        # 打包後從 _MEIPASS 讀取，開發時從專案根目錄讀取
        if hasattr(sys, "_MEIPASS"):
            base = Path(sys._MEIPASS)
        else:
            base = Path(__file__).resolve().parent.parent.parent.parent  # src/hcp_cms/ui → 專案根

        manual_path = base / "docs" / "operation-manual.md"
        if manual_path.exists():
            return manual_path.read_text(encoding="utf-8")
        return ""
```

- [ ] **Step 4: 執行測試確認通過**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_ui.py::TestMainWindow::test_f1_shortcut_exists -v`
Expected: PASS

- [ ] **Step 5: 執行全部測試確認無破壞**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_ui.py tests/unit/test_help_dialog.py -v`
Expected: All passed

- [ ] **Step 6: Commit**

```bash
git add src/hcp_cms/ui/main_window.py tests/unit/test_ui.py
git commit -m "feat: MainWindow 新增 F1 快捷鍵開啟上下文說明"
```

---

### Task 5: PyInstaller 打包設定 — 包含 operation-manual.md

**Files:**
- Modify: `hcp_cms.spec`（若存在）或 PyInstaller 相關設定

- [ ] **Step 1: 確認打包設定檔案位置**

Run: `ls D:/CMS/*.spec D:/CMS/build.py 2>/dev/null || echo "NO SPEC FILE"`

根據結果決定修改方式。

- [ ] **Step 2: 新增 data file 設定**

在 PyInstaller spec 的 `datas` 清單中新增：

```python
('docs/operation-manual.md', 'docs'),
```

或若使用 `build.py` 中的 `--add-data` 參數，新增：

```python
"--add-data", "docs/operation-manual.md:docs",
```

Windows 分隔符使用 `;` 而非 `:`：

```python
"--add-data", "docs/operation-manual.md;docs",
```

- [ ] **Step 3: Commit**

```bash
git add <打包設定檔>
git commit -m "chore: 打包設定新增 operation-manual.md"
```

---

### Task 6: 更新操作手冊 — 新增 F1 說明快捷鍵

**Files:**
- Modify: `docs/operation-manual.md`

- [ ] **Step 1: 在快捷鍵章節新增 F1**

在 `docs/operation-manual.md` 的 `## 13. 快捷鍵` 表格中新增一行：

```markdown
| `F1` | 開啟當前頁面的操作說明 |
```

- [ ] **Step 2: Commit**

```bash
git add docs/operation-manual.md
git commit -m "docs: 快捷鍵章節新增 F1 說明"
```
