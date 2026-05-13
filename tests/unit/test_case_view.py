"""Tests for case_view helper functions — pure logic, no Qt widget instantiation."""

from __future__ import annotations

from hcp_cms.ui.case_view import _days_since, _overdue_color


class TestDaysSince:
    def test_none_returns_zero(self) -> None:
        assert _days_since(None) == 0

    def test_empty_returns_zero(self) -> None:
        assert _days_since("") == 0

    def test_invalid_returns_zero(self) -> None:
        assert _days_since("not-a-date") == 0

    def test_recent_returns_positive(self) -> None:
        from datetime import datetime, timedelta
        five_days_ago = (datetime.now() - timedelta(days=5)).strftime("%Y/%m/%d %H:%M:%S")
        assert _days_since(five_days_ago) == 5


class TestOverdueColor5Tiers:
    """5 級顏色梯度（使用者要求）：3+ / 5+ / 7+ / 10+ / 30+ 天。"""

    def test_under_3_days_no_color(self) -> None:
        assert _overdue_color(0) is None
        assert _overdue_color(1) is None
        assert _overdue_color(2) is None

    def test_3_to_4_days_tier1(self) -> None:
        c3 = _overdue_color(3)
        c4 = _overdue_color(4)
        assert c3 is not None
        assert c4 is not None
        assert c3 == c4  # 同一級

    def test_5_to_6_days_tier2(self) -> None:
        c5 = _overdue_color(5)
        c6 = _overdue_color(6)
        assert c5 is not None
        assert c5 == c6
        # 不同於 tier1
        assert c5 != _overdue_color(3)

    def test_7_to_9_days_tier3(self) -> None:
        c7 = _overdue_color(7)
        c9 = _overdue_color(9)
        assert c7 is not None
        assert c7 == c9
        assert c7 != _overdue_color(5)

    def test_10_to_29_days_tier4(self) -> None:
        c10 = _overdue_color(10)
        c29 = _overdue_color(29)
        assert c10 is not None
        assert c10 == c29
        assert c10 != _overdue_color(7)

    def test_30_plus_days_tier5(self) -> None:
        c30 = _overdue_color(30)
        c100 = _overdue_color(100)
        assert c30 is not None
        assert c30 == c100
        assert c30 != _overdue_color(10)

    def test_all_tiers_distinct(self) -> None:
        """5 級顏色互不相同。"""
        colors = {
            _overdue_color(3),
            _overdue_color(5),
            _overdue_color(7),
            _overdue_color(10),
            _overdue_color(30),
        }
        assert len(colors) == 5
