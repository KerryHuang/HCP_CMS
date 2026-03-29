"""seed_rules 路徑修復測試。"""

from __future__ import annotations

from unittest.mock import patch


class TestSeedRulesPath:
    """確認 seed_rules.main() 使用跨平台路徑。"""

    @patch("platform.system", return_value="Darwin")
    @patch("pathlib.Path.home")
    def test_macos_使用_library_application_support(self, mock_home, _mock_sys):
        from pathlib import Path

        mock_home.return_value = Path("/Users/testuser")

        from hcp_cms.app import get_default_db_path

        result = get_default_db_path()
        assert "Library/Application Support/HCP_CMS" in result.as_posix()

    @patch("platform.system", return_value="Windows")
    def test_windows_使用_appdata(self, _mock_sys):
        from hcp_cms.app import get_default_db_path

        result = get_default_db_path()
        assert "HCP_CMS" in str(result)
