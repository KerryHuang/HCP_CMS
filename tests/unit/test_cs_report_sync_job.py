"""Tests for cs_report_sync_job — 客服問題彙整報表排程同步。"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hcp_cms.scheduler.cs_report_sync_job import (
    CSReportSyncScheduler,
    run_cs_report_sync,
    seconds_until_next,
)


class TestSecondsUntilNext:
    def test_seconds_until_next_daily(self) -> None:
        # 2026-04-24 10:00:00 → 距下一個 00:00 為 14 小時
        now = datetime(2026, 4, 24, 10, 0, 0)
        assert seconds_until_next("每日 00:00", now=now) == 14 * 3600

    def test_seconds_until_next_weekly_monday(self) -> None:
        # 2026-04-21 為週二（weekday=1），下一個週一 = 2026-04-27 00:00
        now = datetime(2026, 4, 21, 9, 30, 0)  # Tuesday
        assert now.weekday() == 1
        result = seconds_until_next("每週一 00:00", now=now)
        # 2026-04-21 09:30 → 2026-04-27 00:00 = 5 天 + 14.5 小時
        expected = 5 * 86400 + (24 - 9.5) * 3600
        assert result == expected

    def test_seconds_until_next_weekly_when_today_is_monday(self) -> None:
        # 週一非午夜 → 應排到下週一（7 天後扣已過時間）
        now = datetime(2026, 4, 20, 10, 0, 0)  # Monday
        assert now.weekday() == 0
        result = seconds_until_next("每週一 00:00", now=now)
        expected = 7 * 86400 - 10 * 3600
        assert result == expected

    def test_seconds_until_next_unknown_label_raises(self) -> None:
        with pytest.raises(ValueError):
            seconds_until_next("每月一日", now=datetime(2026, 4, 24, 10, 0, 0))


class TestRunCsReportSync:
    def test_run_cs_report_sync_calls_upsert(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            with (
                patch("hcp_cms.scheduler.cs_report_sync_job.GoogleSheetsService") as mock_svc_cls,
                patch("hcp_cms.scheduler.cs_report_sync_job.CSReportEngine") as mock_engine_cls,
            ):
                mock_svc = MagicMock()
                mock_svc_cls.return_value = mock_svc

                fake_row = MagicMock()
                fake_row.case_id = "C001"
                fake_row.as_list.return_value = ["a"] * 10
                mock_engine = MagicMock()
                mock_engine.build_rows.return_value = [fake_row]
                mock_engine_cls.return_value = mock_engine

                run_cs_report_sync(
                    conn,
                    "https://docs.google.com/spreadsheets/d/abc",
                    Path("C:/fake/secret.json"),
                )

                mock_svc.authenticate.assert_called_once()
                mock_svc.upsert.assert_called_once()
                args, kwargs = mock_svc.upsert.call_args
                header = args[0]
                data = args[1]
                assert len(header) == 11
                assert header[-1] == "case_id"
                assert kwargs.get("id_column_index") == 10 or (len(args) >= 3 and args[2] == 10)
                assert data == [("C001", ["a"] * 10 + ["C001"])]
        finally:
            conn.close()

    def test_run_cs_report_sync_swallows_exceptions(self, caplog: pytest.LogCaptureFixture) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            with patch("hcp_cms.scheduler.cs_report_sync_job.GoogleSheetsService") as mock_svc_cls:
                mock_svc = MagicMock()
                mock_svc.authenticate.side_effect = RuntimeError("auth boom")
                mock_svc_cls.return_value = mock_svc

                with caplog.at_level(logging.ERROR):
                    # 不應拋出
                    run_cs_report_sync(
                        conn,
                        "https://docs.google.com/spreadsheets/d/abc",
                        Path("C:/fake/secret.json"),
                    )

                assert any("cs_report_sync 失敗" in rec.message for rec in caplog.records)
        finally:
            conn.close()


class TestCSReportSyncSchedulerLifecycle:
    """驗證 start() / stop() 與 QSettings 讀取分支。"""

    def _make_qsettings_mock(self, values: dict[str, object]) -> MagicMock:
        mock = MagicMock()

        def _value(key: str, default: object = None, type: type | None = None) -> object:  # noqa: A002
            return values.get(key, default)

        mock.value.side_effect = _value
        return mock

    def test_start_skips_when_disabled(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            qs = self._make_qsettings_mock({"google/schedule_enabled": False})
            with (
                patch("hcp_cms.scheduler.cs_report_sync_job.QSettings", return_value=qs),
                patch("hcp_cms.scheduler.cs_report_sync_job.threading.Timer") as mock_timer,
            ):
                CSReportSyncScheduler(conn).start()
                mock_timer.assert_not_called()
        finally:
            conn.close()

    def test_start_skips_when_url_or_secret_missing(self, caplog: pytest.LogCaptureFixture) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            qs = self._make_qsettings_mock(
                {
                    "google/schedule_enabled": True,
                    "google/sheet_url": "",
                    "google/client_secret_path": "",
                    "google/schedule_interval": "每日 00:00",
                }
            )
            with (
                patch("hcp_cms.scheduler.cs_report_sync_job.QSettings", return_value=qs),
                patch("hcp_cms.scheduler.cs_report_sync_job.threading.Timer") as mock_timer,
                caplog.at_level(logging.WARNING),
            ):
                CSReportSyncScheduler(conn).start()
                mock_timer.assert_not_called()
                assert any("URL/secret 未設定" in rec.message for rec in caplog.records)
        finally:
            conn.close()

    def test_start_schedules_timer_when_enabled(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            qs = self._make_qsettings_mock(
                {
                    "google/schedule_enabled": True,
                    "google/sheet_url": "https://docs.google.com/spreadsheets/d/abc",
                    "google/client_secret_path": "C:/fake/secret.json",
                    "google/schedule_interval": "每日 00:00",
                }
            )
            fake_timer = MagicMock()
            with (
                patch("hcp_cms.scheduler.cs_report_sync_job.QSettings", return_value=qs),
                patch(
                    "hcp_cms.scheduler.cs_report_sync_job.threading.Timer",
                    return_value=fake_timer,
                ) as mock_timer_cls,
            ):
                CSReportSyncScheduler(conn).start()
                mock_timer_cls.assert_called_once()
                fake_timer.start.assert_called_once()
                assert fake_timer.daemon is True
        finally:
            conn.close()

    def test_stop_cancels_timer_and_blocks_reschedule(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            sched = CSReportSyncScheduler(conn)
            fake_timer = MagicMock()
            sched._timer = fake_timer
            sched.stop()
            fake_timer.cancel.assert_called_once()
            assert sched._timer is None
            # stop 後再呼叫 _schedule_next 不應建立新 Timer
            with patch("hcp_cms.scheduler.cs_report_sync_job.threading.Timer") as mock_timer_cls:
                sched._schedule_next("u", Path("p"), "每日 00:00")
                mock_timer_cls.assert_not_called()
        finally:
            conn.close()
