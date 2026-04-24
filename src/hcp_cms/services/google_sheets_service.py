"""GoogleSheetsService — OAuth 授權並 Upsert 資料至指定 Google Sheet。

憑證流程：
  1. 使用者於「設定」頁面提供 client_secret.json 路徑
     （由 Google Cloud Console 建立 Desktop client）。
  2. 首次授權啟動 InstalledAppFlow.run_local_server，使用者於瀏覽器核准。
  3. token 以 JSON 序列化後存入 keyring（key="google_sheets_token"）。
  4. 下次啟動直接讀回，自動 refresh（credentials.refresh）。

Upsert 邏輯：以 id_column_index（0-based）作為 key 比對既有 row：
  - 存在 → update 該 row
  - 不存在 → append_row
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from hcp_cms.services.credential import CredentialManager

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TOKEN_KEY = "google_sheets_token"


class GoogleSheetsService:
    """Google Sheets OAuth + Upsert 服務。"""

    def __init__(
        self,
        client_secret_path: Path,
        spreadsheet_url: str,
        worksheet_name: str = "Sheet1",
    ) -> None:
        self._client_secret_path = Path(client_secret_path)
        self._spreadsheet_url = spreadsheet_url
        self._worksheet_name = worksheet_name
        self._creds: Credentials | None = None
        self._ws: gspread.Worksheet | None = None
        self._cred_mgr = CredentialManager()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    def authenticate(self, force_reauth: bool = False) -> None:
        """取得有效 credentials；必要時啟動瀏覽器授權。

        失敗時拋出例外（呼叫端以 try/except 處理並顯示 UI 提示）。
        """
        creds: Credentials | None = None
        if not force_reauth:
            token_json = self._cred_mgr.retrieve(TOKEN_KEY)
            if token_json:
                try:
                    creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
                except Exception:
                    creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self._client_secret_path), SCOPES
                )
                creds = flow.run_local_server(port=0)
            self._cred_mgr.store(TOKEN_KEY, creds.to_json())

        self._creds = creds
        self._open_worksheet()

    def _open_worksheet(self) -> None:
        assert self._creds is not None
        gc = gspread.authorize(self._creds)
        sh = gc.open_by_url(self._spreadsheet_url)
        try:
            self._ws = sh.worksheet(self._worksheet_name)
        except gspread.WorksheetNotFound:
            self._ws = sh.add_worksheet(self._worksheet_name, rows=1000, cols=20)

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------
    def upsert(
        self,
        header: list[str],
        rows: Iterable[tuple[str, list[str]]],
        id_column_index: int,
    ) -> None:
        """以 id_column_index（0-based）為 key 做 upsert。

        - 既有 sheet 為空 → 先 append header，再逐筆 append_row
        - 既有 sheet 有資料 → 依 id 判斷 update 既有 row 或 append 新 row
        """
        assert self._ws is not None, "authenticate() first"
        existing = self._ws.get_all_values()

        if not existing:
            self._ws.append_row(header)
            existing = [header]

        # 建立 id → row_index 映射（row_index 1-based；跳過 header 行 → 從第 2 列開始）
        id_to_row: dict[str, int] = {}
        for idx, row in enumerate(existing[1:], start=2):
            if len(row) > id_column_index:
                id_to_row[row[id_column_index]] = idx

        for case_id, values in rows:
            if case_id in id_to_row:
                r = id_to_row[case_id]
                self._ws.update(f"A{r}", [values])
            else:
                self._ws.append_row(values)
