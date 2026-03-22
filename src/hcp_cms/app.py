"""應用程式初始化"""

from hcp_cms.ui.main_window import MainWindow


def create_app() -> MainWindow:
    """建立並回傳主視窗"""
    window = MainWindow()
    return window
