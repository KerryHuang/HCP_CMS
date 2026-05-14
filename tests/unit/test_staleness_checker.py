"""StalenessChecker 與 business_hours_between 測試。"""
from datetime import datetime
from pathlib import Path

import pytest

from hcp_cms.core.staleness_checker import (
    StalenessChecker,
    business_hours_between,
)
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, CaseLog, Staff
from hcp_cms.data.repositories import (
    CaseLogRepository,
    CaseRepository,
    StaffRepository,
)

# ============= business_hours_between =============


def test_same_time_returns_zero() -> None:
    """同時間點 → 0 小時。"""
    t = datetime(2026, 5, 14, 10, 0)
    assert business_hours_between(t, t) == 0.0


def test_end_before_start_returns_zero() -> None:
    """end 比 start 早 → 0 小時（不計負數）。"""
    start = datetime(2026, 5, 14, 12, 0)
    end = datetime(2026, 5, 14, 10, 0)
    assert business_hours_between(start, end) == 0.0


def test_weekday_full_day() -> None:
    """週三 09:00 → 週四 09:00 = 24 小時。"""
    start = datetime(2026, 5, 13, 9, 0)  # Wed
    end = datetime(2026, 5, 14, 9, 0)    # Thu
    assert business_hours_between(start, end) == 24.0


def test_skip_weekend() -> None:
    """週五 14:00 → 週一 14:00 = 10 + 0 + 0 + 14 = 24 小時。"""
    start = datetime(2026, 5, 15, 14, 0)  # Fri
    end = datetime(2026, 5, 18, 14, 0)    # Mon
    assert business_hours_between(start, end) == 24.0


def test_weekend_only_returns_zero() -> None:
    """週六 10:00 → 週日 10:00 = 0 小時（全在週末）。"""
    start = datetime(2026, 5, 16, 10, 0)  # Sat
    end = datetime(2026, 5, 17, 10, 0)    # Sun
    assert business_hours_between(start, end) == 0.0


def test_spans_weekend_short() -> None:
    """週五 23:00 → 週一 02:00 = 1 + 0 + 0 + 2 = 3 小時。"""
    start = datetime(2026, 5, 15, 23, 0)
    end = datetime(2026, 5, 18, 2, 0)
    assert business_hours_between(start, end) == 3.0


def test_partial_day_hours() -> None:
    """週三 09:30 → 週三 17:00 = 7.5 小時。"""
    start = datetime(2026, 5, 13, 9, 30)
    end = datetime(2026, 5, 13, 17, 0)
    assert business_hours_between(start, end) == 7.5


# ============= StalenessChecker.find_stale_cases =============


@pytest.fixture
def db(tmp_path: Path):
    db = DatabaseManager(tmp_path / "t.db")
    db.initialize()
    StaffRepository(db.connection).insert(
        Staff(staff_id="S-YOGA", name="YOGA", email="yoga@test.com", role="cs")
    )
    StaffRepository(db.connection).insert(
        Staff(staff_id="S-JILL", name="JILL", email="jill@test.com", role="cs")
    )
    yield db
    db.close()


def _insert_case(conn, case_id: str, status: str, handler: str, sent_time: str) -> None:
    CaseRepository(conn).insert(Case(
        case_id=case_id, subject=f"案件 {case_id}", status=status,
        handler=handler, sent_time=sent_time,
    ))


def _insert_log(conn, case_id: str, direction: str, logged_at: str) -> None:
    log_repo = CaseLogRepository(conn)
    log_repo.insert(CaseLog(
        log_id=log_repo.next_log_id(), case_id=case_id,
        direction=direction, content="x", logged_at=logged_at,
    ))


def test_finds_processing_case_with_old_hcp_reply(db) -> None:
    """處理中 + 最後 HCP 回覆 > 48 工作小時前 → 應列出。"""
    # 100 小時前（工作時數計）的時間點 = 5 天前
    _insert_case(db.connection, "C-OLD", "處理中", "YOGA", "2026/05/01 09:00:00")
    _insert_log(db.connection, "C-OLD", "HCP 信件回覆", "2026/05/05 09:00:00")
    # now = 2026/05/14 09:00 → 距離 5/5 09:00 過了 9 天 = ~7 個工作日 ≈ 168 hr
    now = datetime(2026, 5, 14, 9, 0)
    checker = StalenessChecker(db.connection, now=now)
    results = checker.find_stale_cases(threshold_hours=48)

    assert len(results) == 1
    assert results[0]["case_id"] == "C-OLD"
    assert results[0]["handler"] == "YOGA"
    assert results[0]["handler_email"] == "yoga@test.com"
    assert results[0]["hours_since_last_reply"] > 48


def test_excludes_case_replied_within_threshold(db) -> None:
    """最後 HCP 回覆在 48 小時內 → 不列出。"""
    _insert_case(db.connection, "C-FRESH", "處理中", "YOGA", "2026/05/13 09:00:00")
    _insert_log(db.connection, "C-FRESH", "HCP 信件回覆", "2026/05/13 09:00:00")
    now = datetime(2026, 5, 14, 9, 0)  # 24 小時後
    checker = StalenessChecker(db.connection, now=now)

    assert checker.find_stale_cases(threshold_hours=48) == []


def test_excludes_non_processing_status(db) -> None:
    """status != 處理中 不列出（已回覆 / 已完成 / 已結案 都排除）。"""
    for status in ("已回覆", "已完成", "已結案"):
        cid = f"C-{status}"
        _insert_case(db.connection, cid, status, "YOGA", "2026/05/01 09:00:00")
        _insert_log(db.connection, cid, "HCP 信件回覆", "2026/05/01 09:00:00")

    now = datetime(2026, 5, 14, 9, 0)
    checker = StalenessChecker(db.connection, now=now)
    assert checker.find_stale_cases(threshold_hours=48) == []


def test_excludes_case_with_no_hcp_reply(db) -> None:
    """處理中但完全沒 HCP 回覆 → 不列出（屬另一個 SLA 範疇）。"""
    _insert_case(db.connection, "C-NEW", "處理中", "YOGA", "2026/05/01 09:00:00")
    _insert_log(db.connection, "C-NEW", "客戶來信", "2026/05/01 09:00:00")
    now = datetime(2026, 5, 14, 9, 0)
    checker = StalenessChecker(db.connection, now=now)

    assert checker.find_stale_cases(threshold_hours=48) == []


def test_hcp_online_reply_also_counts(db) -> None:
    """direction=HCP 線上回覆 也算 HCP 活動，會 reset 計時。"""
    _insert_case(db.connection, "C-ONLINE", "處理中", "YOGA", "2026/05/01 09:00:00")
    _insert_log(db.connection, "C-ONLINE", "HCP 信件回覆", "2026/05/01 09:00:00")
    _insert_log(db.connection, "C-ONLINE", "HCP 線上回覆", "2026/05/13 09:00:00")  # 後一筆
    now = datetime(2026, 5, 14, 9, 0)
    checker = StalenessChecker(db.connection, now=now)

    # 最後一筆 HCP 活動是 5/13 09:00 → 距離 now 24h → 不超時
    assert checker.find_stale_cases(threshold_hours=48) == []


def test_uses_latest_hcp_reply_not_earliest(db) -> None:
    """有多筆 HCP 回覆 → 以最新一筆計時。"""
    _insert_case(db.connection, "C-MULTI", "處理中", "YOGA", "2026/05/01 09:00:00")
    _insert_log(db.connection, "C-MULTI", "HCP 信件回覆", "2026/05/01 09:00:00")  # 舊
    _insert_log(db.connection, "C-MULTI", "客戶來信", "2026/05/05 09:00:00")
    _insert_log(db.connection, "C-MULTI", "HCP 信件回覆", "2026/05/06 09:00:00")  # 新
    now = datetime(2026, 5, 14, 9, 0)  # 距 5/6 09:00 過了 8 天 ≈ 6 個工作日 ≈ 144 hr
    checker = StalenessChecker(db.connection, now=now)
    results = checker.find_stale_cases(threshold_hours=48)

    assert len(results) == 1
    # 應以 5/6 09:00 為起算，而非 5/1
    assert results[0]["last_hcp_reply"] == "2026/05/06 09:00:00"


def test_handler_email_resolved_via_staff_table(db) -> None:
    """handler 字串對應 staff.email；查不到 → handler_email 為 None。"""
    _insert_case(db.connection, "C-NOSTAFF", "處理中", "UNKNOWN", "2026/05/01 09:00:00")
    _insert_log(db.connection, "C-NOSTAFF", "HCP 信件回覆", "2026/05/01 09:00:00")
    now = datetime(2026, 5, 14, 9, 0)
    checker = StalenessChecker(db.connection, now=now)
    results = checker.find_stale_cases(threshold_hours=48)

    assert len(results) == 1
    assert results[0]["handler"] == "UNKNOWN"
    assert results[0]["handler_email"] is None


def test_case_without_handler_excluded_from_email_target(db) -> None:
    """case.handler 為 None → 仍列出但 handler_email 為 None（UI 可選擇是否發信）。"""
    _insert_case(db.connection, "C-NOHANDLER", "處理中", None, "2026/05/01 09:00:00")
    _insert_log(db.connection, "C-NOHANDLER", "HCP 信件回覆", "2026/05/01 09:00:00")
    now = datetime(2026, 5, 14, 9, 0)
    checker = StalenessChecker(db.connection, now=now)
    results = checker.find_stale_cases(threshold_hours=48)

    assert len(results) == 1
    assert results[0]["handler"] is None
    assert results[0]["handler_email"] is None
