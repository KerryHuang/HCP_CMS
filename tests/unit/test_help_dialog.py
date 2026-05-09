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
        result = extract_section(manual, "dashboard")
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
        result = extract_section(manual, "cases")
        assert "案件列表與搜尋" in result
        assert "儀表板" not in result
        assert "KMS" not in result

    def test_extract_kms_section(self):
        """KMS 知識庫應正確帶出第 5 章（先前 bug：因 nav 加入「客戶管理」index 錯位顯示信件處理）。"""
        manual = (
            "## 4. 案件管理\n\n案件內容。\n\n---\n\n"
            "## 5. KMS 知識庫\n\nKMS 內容說明。\n\n### 5.1 搜尋\n\n搜尋說明。\n\n---\n\n"
            "## 6. 信件處理\n\n信件處理內容。\n"
        )
        result = extract_section(manual, "kms")
        assert "KMS 內容說明" in result
        assert "案件內容" not in result
        assert "信件處理內容" not in result

    def test_extract_patch_section(self):
        """Patch 整理應正確帶出第 13 章（不在連續編號，先前 bug：nav index 7 取到 Patch 整理）。"""
        manual = (
            "## 12. 舊版系統遷移\n\n舊遷移內容。\n\n---\n\n"
            "## 13. Patch 整理\n\nPatch 整理流程。\n\n### 13.1 每月大 PATCH\n\n9 步流程。\n\n---\n\n"
            "## 14. 快捷鍵\n\n快捷鍵清單。\n"
        )
        result = extract_section(manual, "patch")
        assert "Patch 整理流程" in result
        assert "9 步流程" in result
        assert "快捷鍵清單" not in result

    def test_extract_customers_falls_back_to_cases(self):
        """客戶管理目前無獨立章節，應回退到案件管理章節。"""
        manual = (
            "## 4. 案件管理\n\n案件管理內容。\n\n---\n\n"
            "## 5. KMS 知識庫\n\nKMS 內容。\n"
        )
        result = extract_section(manual, "customers")
        assert "案件管理內容" in result
        assert "KMS" not in result

    def test_extract_settings_includes_backup_section(self):
        manual = (
            "## 9. 規則設定\n\n規則內容。\n\n---\n\n"
            "## 10. 系統設定\n\n系統設定內容。\n\n---\n\n"
            "## 11. 資料庫備份與還原\n\n備份內容。\n\n---\n\n"
            "## 12. 舊版系統遷移\n\n遷移說明。\n"
        )
        result = extract_section(manual, "settings")
        assert "系統設定內容" in result
        assert "備份內容" in result
        assert "規則" not in result
        assert "舊版系統遷移" not in result

    def test_extract_unknown_key_returns_fallback(self):
        """未知 nav-key（如 "help" 或無對應）應回傳 fallback 訊息。"""
        manual = "## 3. 儀表板\n\n內容。\n"
        result = extract_section(manual, "help")
        assert "找不到對應的說明內容" in result
        result2 = extract_section(manual, "unknown_key")
        assert "找不到對應的說明內容" in result2

    def test_page_sections_includes_all_nav_pages(self):
        """PAGE_SECTIONS 應涵蓋所有有對應章節的 nav 頁面（不含 help）。"""
        expected_keys = {
            "dashboard", "cases", "customers", "kms", "email",
            "mantis", "reports", "patch", "rules", "settings",
        }
        assert set(PAGE_SECTIONS.keys()) == expected_keys


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

        dialog = HelpDialog(page_key="dashboard", manual_text="## 3. 儀表板\n\n測試內容。\n")
        assert dialog.windowTitle() == "說明 — 儀表板"

    def test_dialog_contains_content(self, qapp):
        from hcp_cms.ui.help_dialog import HelpDialog

        dialog = HelpDialog(page_key="dashboard", manual_text="## 3. 儀表板\n\n測試內容。\n")
        html = dialog._browser.toHtml()
        assert "測試內容" in html

    def test_dialog_default_size(self, qapp):
        from hcp_cms.ui.help_dialog import HelpDialog

        dialog = HelpDialog(page_key="dashboard", manual_text="## 3. 儀表板\n\n內容。\n")
        assert dialog.width() >= 800
        assert dialog.height() >= 600

    def test_dialog_unknown_key_shows_fallback(self, qapp):
        from hcp_cms.ui.help_dialog import HelpDialog

        dialog = HelpDialog(page_key="bogus", manual_text="## 3. 儀表板\n\n內容。\n")
        assert dialog.windowTitle() == "說明"
        html = dialog._browser.toHtml()
        assert "找不到" in html
