"""系統主題偵測跨平台測試。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestDetectSystemLight:
    """測試 _detect_system_light 跨平台偵測。"""

    @patch("platform.system", return_value="Windows")
    def test_windows_淺色模式(self, _mock_sys):
        mock_winreg = MagicMock()
        mock_winreg.QueryValueEx.return_value = (1, 1)
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            from hcp_cms.ui.theme import ThemeManager

            tm = ThemeManager.__new__(ThemeManager)
            assert tm._detect_system_light() is True

    @patch("platform.system", return_value="Windows")
    def test_windows_深色模式(self, _mock_sys):
        mock_winreg = MagicMock()
        mock_winreg.QueryValueEx.return_value = (0, 1)
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            from hcp_cms.ui.theme import ThemeManager

            tm = ThemeManager.__new__(ThemeManager)
            assert tm._detect_system_light() is False

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.run")
    def test_macos_淺色模式(self, mock_run, _mock_sys):
        mock_run.return_value = MagicMock(returncode=1)  # 無 Dark 設定 = 淺色
        from hcp_cms.ui.theme import ThemeManager

        tm = ThemeManager.__new__(ThemeManager)
        assert tm._detect_system_light() is True

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.run")
    def test_macos_深色模式(self, mock_run, _mock_sys):
        mock_run.return_value = MagicMock(returncode=0)  # 有 Dark 設定 = 深色
        from hcp_cms.ui.theme import ThemeManager

        tm = ThemeManager.__new__(ThemeManager)
        assert tm._detect_system_light() is False

    @patch("platform.system", return_value="Linux")
    def test_未知平台_預設深色(self, _mock_sys):
        from hcp_cms.ui.theme import ThemeManager

        tm = ThemeManager.__new__(ThemeManager)
        assert tm._detect_system_light() is False
