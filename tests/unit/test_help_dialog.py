"""Tests for HelpDialog — section extraction and markdown rendering."""

import pytest
from PySide6.QtWidgets import QApplication

from hcp_cms.ui.help_dialog import PAGE_SECTIONS, extract_section


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


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
        result = extract_section(manual, 0)
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
        result = extract_section(manual, 1)
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
        result = extract_section(manual, 7)
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
        assert "#1e293b" in html
        assert "#e2e8f0" in html


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
