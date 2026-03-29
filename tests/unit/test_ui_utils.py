"""跨平台開檔函式測試。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


class TestOpenFile:
    """測試 open_file 跨平台開檔。"""

    @patch("platform.system", return_value="Windows")
    @patch("os.startfile", create=True)
    def test_windows_使用_startfile(self, mock_startfile, _mock_sys):
        from hcp_cms.ui.utils import open_file

        open_file(Path("report.xlsx"))
        mock_startfile.assert_called_once_with(Path("report.xlsx"))

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen")
    def test_macos_使用_open(self, mock_popen, _mock_sys):
        from hcp_cms.ui.utils import open_file

        open_file(Path("report.xlsx"))
        mock_popen.assert_called_once_with(["open", "report.xlsx"])

    @patch("platform.system", return_value="Linux")
    @patch("subprocess.Popen")
    def test_linux_使用_xdg_open(self, mock_popen, _mock_sys):
        from hcp_cms.ui.utils import open_file

        open_file(Path("report.xlsx"))
        mock_popen.assert_called_once_with(["xdg-open", "report.xlsx"])
