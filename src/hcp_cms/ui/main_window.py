"""Main application window with sidebar navigation."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt
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

from hcp_cms.core.kms_engine import KMSEngine
from hcp_cms.ui.case_view import CaseView
from hcp_cms.ui.dashboard_view import DashboardView
from hcp_cms.ui.email_view import EmailView
from hcp_cms.ui.kms_view import KMSView
from hcp_cms.ui.mantis_view import MantisView
from hcp_cms.ui.report_view import ReportView
from hcp_cms.ui.rules_view import RulesView
from hcp_cms.ui.settings_view import SettingsView
from hcp_cms.ui.theme import ColorPalette, ThemeManager


class MainWindow(QMainWindow):
    """HCP CMS main application window."""

    def __init__(
        self,
        db_connection: sqlite3.Connection | None = None,
        db_dir: Path | None = None,
        theme_mgr: ThemeManager | None = None,
    ) -> None:
        super().__init__()
        self._conn = db_connection
        self._db_dir = db_dir
        self._theme_mgr = theme_mgr
        self._current_palette: ColorPalette | None = None
        self.setWindowTitle("HCP CMS v2.0")
        self.setMinimumSize(1200, 800)

        self._setup_ui()
        self._setup_shortcuts()

        # 套用主題
        if self._theme_mgr:
            self._apply_theme(self._theme_mgr.current_palette())
            self._theme_mgr.theme_changed.connect(self._apply_theme)

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
            ("📊 儀表板", "dashboard", "⇧H"),
            ("📋 案件管理", "cases", "⇧C"),
            ("📚 KMS 知識庫", "kms", "⇧K"),
            ("📧 信件處理", "email", "⇧E"),
            ("🔧 Mantis 同步", "mantis", "⇧M"),
            ("📊 報表中心", "reports", "⇧R"),
            ("📏 規則設定", "rules", "⇧L"),
            ("⚙️ 系統設定", "settings", "⇧S"),
        ]

        for text, key, shortcut in nav_items:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setSizeHint(QSize(0, 40))
            self._nav_list.addItem(item)
            self._nav_list.setItemWidget(item, self._make_nav_widget(text, shortcut))

        self._nav_list.currentRowChanged.connect(self._on_nav_changed)
        sidebar_layout.addWidget(self._nav_list)

        layout.addWidget(sidebar)

        # Content area (stacked widget)
        self._stack = QStackedWidget()

        kms = KMSEngine(self._conn) if self._conn else None

        self._views: dict[str, QWidget] = {
            "dashboard": DashboardView(self._conn, theme_mgr=self._theme_mgr),
            "cases": CaseView(
                self._conn, db_path=self._db_dir / "cs_tracker.db" if self._db_dir else None, theme_mgr=self._theme_mgr
            ),
            "kms": KMSView(self._conn, kms=kms, db_dir=self._db_dir, theme_mgr=self._theme_mgr),
            "email": EmailView(self._conn, kms=kms, theme_mgr=self._theme_mgr),
            "mantis": MantisView(self._conn, theme_mgr=self._theme_mgr),
            "reports": ReportView(self._conn, theme_mgr=self._theme_mgr),
            "rules": RulesView(self._conn, theme_mgr=self._theme_mgr),
            "settings": SettingsView(self._conn, theme_mgr=self._theme_mgr),
        }

        for view in self._views.values():
            self._stack.addWidget(view)

        # 案件有異動時，儀表板自動重新整理
        self._views["cases"].cases_changed.connect(self._views["dashboard"].refresh)

        # 信件匯入完成後跳轉至案件管理（選「最近匯入」篩選）
        self._views["email"].navigate_to_cases.connect(self._on_navigate_to_recent_cases)

        layout.addWidget(self._stack)

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("就緒")

        # Select first nav item
        self._nav_list.setCurrentRow(0)

    def _make_nav_widget(self, text: str, shortcut: str | None) -> QWidget:
        """Build a nav item widget with optional right-aligned shortcut hint."""
        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(4)

        label = QLabel(text)
        label.setObjectName("navItemLabel")
        layout.addWidget(label)

        if shortcut:
            layout.addStretch()
            hint = QLabel(shortcut)
            hint.setObjectName("navShortcutHint")
            layout.addWidget(hint)

        return widget

    def _on_nav_changed(self, index: int) -> None:
        """Switch content view when navigation changes."""
        if 0 <= index < self._stack.count():
            self._stack.setCurrentIndex(index)
        # Update nav label colours to reflect selection
        p = getattr(self, "_current_palette", None)
        selected_color = p.accent if p else "#60a5fa"
        unselected_color = p.text_tertiary if p else "#94a3b8"
        for i in range(self._nav_list.count()):
            widget = self._nav_list.itemWidget(self._nav_list.item(i))
            if widget:
                label = widget.findChild(QLabel, "navItemLabel")
                if label:
                    label.setStyleSheet(f"color: {selected_color};" if i == index else f"color: {unselected_color};")
        # 切到信件處理頁時自動連線
        if index == 3:  # 信件處理 = index 3
            self._views["email"].try_auto_connect()

    def _on_navigate_to_recent_cases(self) -> None:
        """切換至案件管理頁並自動選「最近匯入」篩選。"""
        self._nav_list.setCurrentRow(1)  # 案件管理 = index 1
        case_view = self._views["cases"]
        # 設定篩選為「最近匯入」並刷新
        idx = case_view._filter_combo.findText("最近匯入")
        if idx >= 0:
            case_view._filter_combo.setCurrentIndex(idx)
        case_view.refresh()

    def _setup_shortcuts(self) -> None:
        """Set up global keyboard shortcuts for page navigation."""
        shortcuts = [
            ("Ctrl+Shift+H", 0),  # 儀表板
            ("Ctrl+Shift+C", 1),  # 案件管理
            ("Ctrl+Shift+K", 2),  # KMS 知識庫
            ("Ctrl+Shift+E", 3),  # 信件處理
            ("Ctrl+Shift+M", 4),  # Mantis 同步
            ("Ctrl+Shift+R", 5),  # 報表中心
            ("Ctrl+Shift+L", 6),  # 規則設定
            ("Ctrl+Shift+S", 7),  # 系統設定
        ]
        for key, index in shortcuts:
            action = QAction(key, self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(lambda checked=False, i=index: self._nav_list.setCurrentRow(i))
            self.addAction(action)

        # F1 — 上下文說明
        help_action = QAction("F1", self)
        help_action.setShortcut(QKeySequence("F1"))
        help_action.triggered.connect(self._on_help_requested)
        self.addAction(help_action)

    def _on_help_requested(self) -> None:
        """Open help dialog for the current page."""
        from hcp_cms.ui.help_dialog import HelpDialog

        manual_text = self._load_manual()
        if manual_text:
            page_index = self._nav_list.currentRow()
            palette = self._current_palette if hasattr(self, "_current_palette") else None
            dialog = HelpDialog(page_index, manual_text, parent=self, palette=palette)
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

    def _apply_theme(self, p: ColorPalette) -> None:
        """Apply theme stylesheet using the given palette."""
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {p.bg_primary}; }}
            #sidebar {{ background-color: {p.bg_sidebar}; border-right: 1px solid {p.border_secondary}; }}
            #logo {{ color: {p.accent}; font-size: 16px; font-weight: bold;
                    background-color: {p.bg_sidebar}; border-bottom: 1px solid {p.border_secondary}; }}
            #navList {{ background-color: {p.bg_sidebar}; border: none; color: {p.text_tertiary};
                       font-size: 13px; outline: none; }}
            #navList::item {{ padding: 10px 16px; border-radius: 6px; margin: 2px 8px; }}
            #navList::item:selected {{ background-color: {p.accent_button}; color: {p.accent}; }}
            #navList::item:hover {{ background-color: {p.bg_secondary}; }}
            QStackedWidget {{ background-color: {p.bg_primary}; }}
            QLabel {{ color: {p.text_secondary}; }}
            QLineEdit {{ background-color: {p.bg_secondary}; color: {p.text_secondary};
                        border: 1px solid {p.border_primary}; border-radius: 4px; padding: 6px; }}
            QPushButton {{ background-color: {p.accent_button}; color: white; border: none;
                          border-radius: 4px; padding: 8px 16px; font-weight: bold; }}
            QPushButton:hover {{ background-color: {p.accent_button_hover}; }}
            QTableWidget {{ background-color: {p.bg_secondary}; color: {p.text_secondary};
                          gridline-color: {p.border_primary}; border: none; }}
            QTableWidget::item {{ padding: 4px; }}
            QHeaderView::section {{ background-color: {p.accent_button}; color: white;
                                   padding: 6px; border: 1px solid {p.border_primary}; }}
            QStatusBar {{ background-color: {p.bg_sidebar}; color: {p.text_muted}; }}
            QComboBox {{ background-color: {p.bg_secondary}; color: {p.text_secondary};
                       border: 1px solid {p.border_primary}; border-radius: 4px; padding: 4px; }}
            QSpinBox {{ background-color: {p.bg_secondary}; color: {p.text_secondary};
                       border: 1px solid {p.border_primary}; }}
            QTextEdit {{ background-color: {p.bg_secondary}; color: {p.text_secondary};
                        border: 1px solid {p.border_primary}; }}
            QGroupBox {{ color: {p.text_tertiary}; border: 1px solid {p.border_primary}; border-radius: 6px;
                       margin-top: 8px; padding-top: 16px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
            #navItemLabel {{ color: {p.text_tertiary}; font-size: 13px; background: transparent; }}
            #navShortcutHint {{ color: {p.text_faint}; font-size: 10px; background: transparent; }}
        """)
        self._on_nav_changed(self._nav_list.currentRow())
        self._current_palette = p

    def changeEvent(self, event: QEvent) -> None:
        """偵測視窗啟用事件，重新檢查系統主題。"""
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow() and self._theme_mgr:
            self._theme_mgr.refresh_system_theme()
        super().changeEvent(event)
