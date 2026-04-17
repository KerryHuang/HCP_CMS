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
