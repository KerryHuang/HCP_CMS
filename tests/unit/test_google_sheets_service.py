"""GoogleSheetsService：upsert 行為（mock gspread）。"""

from __future__ import annotations

from unittest.mock import MagicMock

from hcp_cms.services.google_sheets_service import GoogleSheetsService


def test_upsert_appends_new_rows_by_case_id():
    fake_ws = MagicMock()
    # 既有 sheet：header + 1 筆
    fake_ws.get_all_values.return_value = [
        ["日期", "客戶名稱", "case_id"],
        ["2026/04/01", "ACME", "CS-001"],
    ]
    svc = GoogleSheetsService.__new__(GoogleSheetsService)
    svc._ws = fake_ws

    header = ["日期", "客戶名稱", "case_id"]
    rows = [
        ("CS-001", ["2026/04/02", "ACME-UPD", "CS-001"]),  # 更新
        ("CS-002", ["2026/04/03", "BETA", "CS-002"]),      # 新增
    ]
    svc.upsert(header, rows, id_column_index=2)

    # 更新 row 2 呼叫 update；新增 CS-002 呼叫 append_row
    fake_ws.update.assert_called()
    fake_ws.append_row.assert_called_with(["2026/04/03", "BETA", "CS-002"])

    # 驗證 gspread 6.x 具名引數呼叫
    call_args = fake_ws.update.call_args
    assert call_args.kwargs.get("range_name") == "A2"  # CS-001 在第 2 列
    assert call_args.args[0] == [["2026/04/02", "ACME-UPD", "CS-001"]]


def test_upsert_writes_header_when_sheet_empty():
    fake_ws = MagicMock()
    fake_ws.get_all_values.return_value = []
    svc = GoogleSheetsService.__new__(GoogleSheetsService)
    svc._ws = fake_ws

    svc.upsert(["日期", "case_id"], [("CS-001", ["2026/04/01", "CS-001"])], id_column_index=1)

    # header + 資料皆 append
    assert fake_ws.append_row.call_count == 2
