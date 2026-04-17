"""MonthlyPatchTab 單元測試。"""

from __future__ import annotations

import json

import pytest

from hcp_cms.data.database import DatabaseManager


@pytest.fixture
def db(tmp_path):
    dm = DatabaseManager(str(tmp_path / "t.db"))
    dm.initialize()
    conn = dm.connection
    yield conn
    conn.close()


def test_monthly_tab_instantiates(qtbot, db):
    from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab

    tab = MonthlyPatchTab(conn=db)
    qtbot.addWidget(tab)
    assert tab._month_combo is not None
    assert tab._year_spin is not None
    assert tab._issue_table is not None
    assert tab._log is not None


def test_month_str_format(qtbot, db):
    from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab

    tab = MonthlyPatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._year_spin.setValue(2026)
    tab._month_combo.setCurrentIndex(3)  # index 3 = 4月（0-based）
    assert tab._get_month_str() == "202604"


def test_source_changed_shows_file_browse(qtbot, db):
    from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab

    tab = MonthlyPatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._source_combo.setCurrentIndex(0)  # 第一項 = 上傳檔案
    # Widget 未 show()，isVisible() 受父層影響；改用 not isHidden() 檢查本身顯示狀態
    assert not tab._file_btn.isHidden()


def test_import_manual_loads_issues(qtbot, db, tmp_path):
    from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab

    issues_data = [{"issue_no": "001", "description": "修正", "issue_type": "BugFix"}]
    f = tmp_path / "issues.json"
    f.write_text(json.dumps(issues_data), encoding="utf-8")
    tab = MonthlyPatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._year_spin.setValue(2026)
    tab._month_combo.setCurrentIndex(3)
    tab._file_path = str(f)
    tab._file_edit.setText(str(f))
    with qtbot.waitSignal(tab._import_done, timeout=3000):
        tab._on_import_clicked()
    assert tab._patch_id is not None
    assert tab._issue_table._table.rowCount() == 1


def test_generate_excel_disabled_without_patch_id(qtbot, db):
    from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab

    tab = MonthlyPatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._on_generate_excel_clicked()  # patch_id=None，應 return 不 crash


def test_generate_html_disabled_without_patch_id(qtbot, db):
    from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab

    tab = MonthlyPatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._on_generate_html_clicked()  # patch_id=None，應 return 不 crash


def test_month_str_zero_padded(qtbot, db):
    from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab

    tab = MonthlyPatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._year_spin.setValue(2026)
    tab._month_combo.setCurrentIndex(0)  # index 0 = 1月
    assert tab._get_month_str() == "202601"


def test_source_changed_hides_file_browse(qtbot, db):
    from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab

    tab = MonthlyPatchTab(conn=db)
    qtbot.addWidget(tab)
    tab._source_combo.setCurrentIndex(1)  # Mantis 瀏覽器
    assert tab._file_btn.isHidden()


def test_output_list_widget_exists(qtbot, db):
    from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab

    tab = MonthlyPatchTab(conn=db)
    qtbot.addWidget(tab)
    assert tab._output_list is not None


class TestFolderScanSource:
    def test_source_combo_has_scan_folder_option(self, qtbot, db):
        from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab

        tab = MonthlyPatchTab(conn=db)
        qtbot.addWidget(tab)
        items = [tab._source_combo.itemText(i) for i in range(tab._source_combo.count())]
        assert "掃描資料夾" in items

    def test_scan_folder_widgets_visible_when_selected(self, qtbot, db):
        from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab

        tab = MonthlyPatchTab(conn=db)
        qtbot.addWidget(tab)
        idx = [tab._source_combo.itemText(i) for i in range(tab._source_combo.count())].index("掃描資料夾")
        tab._source_combo.setCurrentIndex(idx)
        assert not tab._scan_edit.isHidden()
        assert not tab._scan_btn.isHidden()
        assert tab._file_edit.isHidden()
        assert tab._file_btn.isHidden()

    def test_scan_dir_set_after_browse(self, qtbot, db, tmp_path, monkeypatch):
        from PySide6.QtWidgets import QFileDialog

        from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab

        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
        tab = MonthlyPatchTab(conn=db)
        qtbot.addWidget(tab)
        tab._on_scan_browse_clicked()
        assert tab._scan_dir == str(tmp_path)
        assert tab._scan_edit.text() == str(tmp_path)

    def test_import_with_scan_folder_calls_engine(self, qtbot, db, tmp_path, monkeypatch):
        from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
        from hcp_cms.ui.patch_monthly_tab import MonthlyPatchTab

        scanned = {}

        def fake_scan(self_eng, patch_dir, month_str):
            scanned["patch_dir"] = patch_dir
            scanned["month_str"] = month_str
            return {}

        monkeypatch.setattr(MonthlyPatchEngine, "scan_monthly_dir", fake_scan)
        monkeypatch.setattr(MonthlyPatchEngine, "get_issue_count", lambda s, pid: 0)

        tab = MonthlyPatchTab(conn=db)
        qtbot.addWidget(tab)
        idx = [tab._source_combo.itemText(i) for i in range(tab._source_combo.count())].index("掃描資料夾")
        tab._source_combo.setCurrentIndex(idx)
        tab._scan_dir = str(tmp_path)
        tab._year_spin.setValue(2026)
        tab._month_combo.setCurrentIndex(3)  # 4月

        with qtbot.waitSignal(tab._import_done, timeout=3000):
            tab._on_import_clicked()

        assert scanned.get("month_str") == "202604"
        assert scanned.get("patch_dir") == str(tmp_path)
