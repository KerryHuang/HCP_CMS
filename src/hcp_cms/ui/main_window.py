"""Main application window with sidebar navigation."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.ui.case_view import CaseView
from hcp_cms.ui.dashboard_view import DashboardView
from hcp_cms.ui.email_view import EmailView
from hcp_cms.ui.kms_view import KMSView
from hcp_cms.ui.mantis_view import MantisView
from hcp_cms.ui.report_view import ReportView
from hcp_cms.ui.rules_view import RulesView
from hcp_cms.ui.settings_view import SettingsView


class MainWindow(QMainWindow):
    """HCP CMS main application window."""

    def __init__(self, db_connection: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = db_connection
        self.setWindowTitle("HCP CMS v2.0")
        self.setMinimumSize(1200, 800)

        self._setup_ui()
        self._setup_shortcuts()
        self._apply_dark_theme()

    def _setup_ui(self) -> None:
        """Set up the main layout: sidebar + content area."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)

        # Logo
        logo = QLabel("HCP CMS")
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedHeight(50)
        sidebar_layout.addWidget(logo)

        # Navigation list
        self._nav_list = QListWidget()
        self._nav_list.setObjectName("navList")

        nav_items = [
            ("📊 儀表板", "dashboard"),
            ("📋 案件管理", "cases"),
            ("📚 KMS 知識庫", "kms"),
            ("📧 信件處理", "email"),
            ("🔧 Mantis 同步", "mantis"),
            ("📊 報表中心", "reports"),
            ("📏 規則設定", "rules"),
            ("⚙️ 系統設定", "settings"),
        ]

        for text, key in nav_items:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self._nav_list.addItem(item)

        self._nav_list.currentRowChanged.connect(self._on_nav_changed)
        sidebar_layout.addWidget(self._nav_list)

        layout.addWidget(sidebar)

        # Content area (stacked widget)
        self._stack = QStackedWidget()

        self._views: dict[str, QWidget] = {
            "dashboard": DashboardView(self._conn),
            "cases": CaseView(self._conn),
            "kms": KMSView(self._conn),
            "email": EmailView(self._conn),
            "mantis": MantisView(self._conn),
            "reports": ReportView(self._conn),
            "rules": RulesView(self._conn),
            "settings": SettingsView(self._conn),
        }

        for view in self._views.values():
            self._stack.addWidget(view)

        layout.addWidget(self._stack)

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("就緒")

        # Select first nav item
        self._nav_list.setCurrentRow(0)

    def _on_nav_changed(self, index: int) -> None:
        """Switch content view when navigation changes."""
        if 0 <= index < self._stack.count():
            self._stack.setCurrentIndex(index)

    def _setup_shortcuts(self) -> None:
        """Set up global keyboard shortcuts."""
        search_action = QAction("Global Search", self)
        search_action.setShortcut(QKeySequence("Ctrl+K"))
        search_action.triggered.connect(self._on_global_search)
        self.addAction(search_action)

    def _on_global_search(self) -> None:
        """Focus global search (switch to KMS view)."""
        self._nav_list.setCurrentRow(2)  # KMS view

    def _apply_dark_theme(self) -> None:
        """Apply dark theme stylesheet."""
        self.setStyleSheet("""
            QMainWindow { background-color: #111827; }
            #sidebar { background-color: #0f172a; border-right: 1px solid #1e293b; }
            #logo { color: #60a5fa; font-size: 16px; font-weight: bold;
                    background-color: #0f172a; border-bottom: 1px solid #1e293b; }
            #navList { background-color: #0f172a; border: none; color: #94a3b8;
                       font-size: 13px; outline: none; }
            #navList::item { padding: 10px 16px; border-radius: 6px; margin: 2px 8px; }
            #navList::item:selected { background-color: #1e3a5f; color: #60a5fa; }
            #navList::item:hover { background-color: #1e293b; }
            QStackedWidget { background-color: #111827; }
            QLabel { color: #e2e8f0; }
            QLineEdit { background-color: #1e293b; color: #e2e8f0; border: 1px solid #334155;
                        border-radius: 4px; padding: 6px; }
            QPushButton { background-color: #1e40af; color: white; border: none;
                          border-radius: 4px; padding: 8px 16px; font-weight: bold; }
            QPushButton:hover { background-color: #2563eb; }
            QTableWidget { background-color: #1e293b; color: #e2e8f0;
                          gridline-color: #334155; border: none; }
            QTableWidget::item { padding: 4px; }
            QHeaderView::section { background-color: #1e3a5f; color: white;
                                   padding: 6px; border: 1px solid #334155; }
            QStatusBar { background-color: #0f172a; color: #64748b; }
            QComboBox { background-color: #1e293b; color: #e2e8f0; border: 1px solid #334155;
                       border-radius: 4px; padding: 4px; }
            QSpinBox { background-color: #1e293b; color: #e2e8f0; border: 1px solid #334155; }
            QTextEdit { background-color: #1e293b; color: #e2e8f0; border: 1px solid #334155; }
            QGroupBox { color: #94a3b8; border: 1px solid #334155; border-radius: 6px;
                       margin-top: 8px; padding-top: 16px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
        """)
