"""主視窗 — 左側導覽 + 右側內容區"""

from typing import ClassVar

from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QWidget,
)


class MainWindow(QMainWindow):
    """主視窗"""

    PAGE_LABELS: ClassVar[list[str]] = [
        "儀表板",
        "案件管理",
        "KMS 知識庫",
        "信件處理",
        "Mantis 同步",
        "報表中心",
        "設定",
    ]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("HCP 客服自動化系統")
        self.setMinimumSize(1200, 800)
        self._setup_ui()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        # 左側導覽
        self._nav = QListWidget()
        self._nav.setFixedWidth(180)
        self._nav.addItems(self.PAGE_LABELS)
        self._nav.setCurrentRow(0)

        # 右側內容區
        self._stack = QStackedWidget()
        for _label in self.PAGE_LABELS:
            page = QWidget()
            self._stack.addWidget(page)

        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)

        layout.addWidget(self._nav)
        layout.addWidget(self._stack, stretch=1)
