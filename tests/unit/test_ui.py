"""Tests for UI layer — basic instantiation without display."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from hcp_cms.data.database import DatabaseManager


# Ensure QApplication exists for widget tests
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


class TestMainWindow:
    def test_create_without_db(self, qapp):
        from hcp_cms.ui.main_window import MainWindow

        window = MainWindow()
        assert window.windowTitle() == "HCP CMS v2.0"
        assert window.minimumWidth() == 1200

    def test_create_with_db(self, qapp, db):
        from hcp_cms.ui.main_window import MainWindow

        window = MainWindow(db.connection)
        assert window._stack.count() == 8  # 8 views

    def test_f1_shortcut_exists(self, qapp):
        from hcp_cms.ui.main_window import MainWindow

        window = MainWindow()
        shortcuts = [a.shortcut().toString() for a in window.actions()]
        assert "F1" in shortcuts


class TestDashboardView:
    def test_create(self, qapp):
        from hcp_cms.ui.dashboard_view import DashboardView

        view = DashboardView()
        assert view is not None

    def test_kpi_cards_exist(self, qapp):
        from hcp_cms.ui.dashboard_view import DashboardView

        view = DashboardView()
        assert view._kpi_total is not None
        assert view._kpi_pending is not None


class TestCaseView:
    def test_create(self, qapp):
        from hcp_cms.ui.case_view import CaseView

        view = CaseView()
        assert view is not None

    def test_detail_shows_handler(self, qapp):
        from hcp_cms.ui.case_view import CaseView

        view = CaseView()
        assert hasattr(view, "_detail_handler")

    def test_detail_shows_error_type(self, qapp):
        from hcp_cms.ui.case_view import CaseView

        view = CaseView()
        assert hasattr(view, "_detail_error_type")

    def test_detail_shows_system_product(self, qapp):
        from hcp_cms.ui.case_view import CaseView

        view = CaseView()
        assert hasattr(view, "_detail_system_product")


class TestKMSView:
    def test_create(self, qapp):
        from hcp_cms.ui.kms_view import KMSView

        view = KMSView()
        assert view is not None


class TestEmailView:
    def test_create(self, qapp):
        from hcp_cms.ui.email_view import EmailView

        view = EmailView()
        assert view is not None

    def test_email_view_has_preview_widget(self, qapp):
        from PySide6.QtWebEngineWidgets import QWebEngineView

        from hcp_cms.ui.email_view import EmailView

        view = EmailView()
        assert hasattr(view, "_preview")
        assert isinstance(view._preview, QWebEngineView)

    def test_email_view_has_emails_list(self, qapp):
        from hcp_cms.ui.email_view import EmailView

        view = EmailView()
        assert hasattr(view, "_emails")
        assert isinstance(view._emails, list)


class TestOtherViews:
    def test_mantis_view(self, qapp):
        from hcp_cms.ui.mantis_view import MantisView

        assert MantisView() is not None

    def test_report_view(self, qapp):
        from hcp_cms.ui.report_view import ReportView

        assert ReportView() is not None

    def test_rules_view(self, qapp):
        from hcp_cms.ui.rules_view import RulesView

        assert RulesView() is not None

    def test_rules_view_has_format_help_button(self, qapp):
        from hcp_cms.ui.rules_view import RulesView

        view = RulesView()
        assert view._format_help_btn is not None
        assert "格式" in view._format_help_btn.text() or "說明" in view._format_help_btn.text()

    def test_rules_format_dialog_content(self, qapp):
        from hcp_cms.ui.rules_view import RulesFormatDialog

        dlg = RulesFormatDialog()
        content = dlg._text.toPlainText()
        assert "rule_type" in content
        assert "pattern" in content
        assert "handler" in content
        assert "priority" in content

    def test_settings_view(self, qapp):
        from hcp_cms.ui.settings_view import SettingsView

        assert SettingsView() is not None


class TestStatusWidget:
    def test_create(self, qapp):
        from hcp_cms.ui.widgets.status_bar import StatusWidget

        widget = StatusWidget()
        assert widget is not None

    def test_set_db_status(self, qapp):
        from hcp_cms.ui.widgets.status_bar import StatusWidget

        widget = StatusWidget()
        widget.set_db_connected(False)
        assert "未連線" in widget._db_status.text()
        widget.set_db_connected(True)
        assert "已連線" in widget._db_status.text()
