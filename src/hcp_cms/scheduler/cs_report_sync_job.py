"""定時將客服問題彙整報表同步至 Google Sheets。

NEVER 直接操作 UI；失敗時僅 log，下一輪再試。
排程使用 threading.Timer 遞迴觸發；下次觸發時間由 seconds_until_next() 計算。
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QSettings

from hcp_cms.core.cs_report_engine import HEADER, CSReportEngine
from hcp_cms.services.google_sheets_service import GoogleSheetsService

log = logging.getLogger(__name__)


def seconds_until_next(interval_label: str, now: datetime | None = None) -> float:
    """計算距離下次觸發時間的秒數。

    interval_label: "每日 00:00" | "每週一 00:00"
    """
    now = now or datetime.now()
    if interval_label == "每日 00:00":
        target = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif interval_label == "每週一 00:00":
        # weekday(): Mon=0
        days_ahead = (7 - now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        target = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        raise ValueError(f"未知排程: {interval_label}")
    return (target - now).total_seconds()


def run_cs_report_sync(
    conn: sqlite3.Connection,
    spreadsheet_url: str,
    client_secret_path: Path,
) -> None:
    """執行一次同步：抓取所有 cs_cases 報表 row 並 upsert 至 Google Sheet。

    失敗時僅 log，不拋出（以免中斷遞迴排程）。
    """
    try:
        svc = GoogleSheetsService(client_secret_path, spreadsheet_url)
        svc.authenticate()
        engine = CSReportEngine(conn)
        rows = engine.build_rows()
        header_with_id = list(HEADER) + ["case_id"]
        data = [(r.case_id, r.as_list() + [r.case_id]) for r in rows]
        svc.upsert(header_with_id, data, id_column_index=len(HEADER))
        log.info("cs_report_sync 同步 %d 筆", len(rows))
    except Exception as exc:
        log.exception("cs_report_sync 失敗：%s", exc)


class CSReportSyncScheduler:
    """以 threading.Timer 遞迴排程客服問題彙整同步。

    讀取 QSettings("HCP", "CMS") 內的 google/* 設定：
      - google/schedule_enabled: 是否啟用
      - google/sheet_url: 試算表 URL
      - google/client_secret_path: OAuth client_secret.json 路徑
      - google/schedule_interval: "每日 00:00" | "每週一 00:00"
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._timer: threading.Timer | None = None
        self._stopped = False
        # 保護 _stopped / _timer 之間的 TOCTOU；stop() 與 _schedule_next() 可能交錯
        self._lock = threading.Lock()

    def start(self) -> None:
        s = QSettings("HCP", "CMS")
        if not s.value("google/schedule_enabled", False, type=bool):
            return
        url = str(s.value("google/sheet_url", "") or "")
        secret = str(s.value("google/client_secret_path", "") or "")
        interval = str(s.value("google/schedule_interval", "每日 00:00") or "每日 00:00")
        if not url or not secret:
            log.warning("cs_report_sync 排程啟用但 Sheet URL/secret 未設定，略過")
            return
        self._schedule_next(url, Path(secret), interval)

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            if self._timer:
                self._timer.cancel()
                self._timer = None

    def _schedule_next(self, url: str, secret: Path, interval: str) -> None:
        delay = seconds_until_next(interval)
        with self._lock:
            if self._stopped:
                return
            log.info("cs_report_sync 下次同步 %.0f 秒後", delay)

            def _run() -> None:
                run_cs_report_sync(self._conn, url, secret)
                self._schedule_next(url, secret, interval)

            self._timer = threading.Timer(delay, _run)
            self._timer.daemon = True
            self._timer.start()
