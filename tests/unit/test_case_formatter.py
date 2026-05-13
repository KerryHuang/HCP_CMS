"""format_case_header 工具函數單元測試。"""
import pytest

from hcp_cms.core.case_formatter import format_case_header
from hcp_cms.data.models import Case


def _case(**overrides) -> Case:
    """測試用 Case factory，預設值充分滿足格式要求。"""
    defaults = dict(
        case_id="C-1",
        subject="加班取小值確認",
        sent_time="2026/05/04 16:46:00",
    )
    defaults.update(overrides)
    return Case(**defaults)


# ============= 完整格式 =============


def test_full_format_with_all_fields() -> None:
    case = _case()
    assert format_case_header(case, "欣興") == (
        "2026/5/4 (週一) 下午 04:46【欣興】加班取小值確認"
    )


# ============= 主旨清理 =============


def test_strips_re_prefix() -> None:
    case = _case(subject="RE: 加班取小值確認")
    assert "RE:" not in format_case_header(case, "欣興")


def test_strips_multiple_prefixes() -> None:
    case = _case(subject="RE: FW: 加班取小值確認")
    result = format_case_header(case, "欣興")
    assert "RE:" not in result
    assert "FW:" not in result
    assert "加班取小值確認" in result


# ============= 星期 =============


def test_weekday_each_day() -> None:
    """2026/5/4 (一) ~ 2026/5/10 (日) 都覆蓋。"""
    expected = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    for day, weekday in enumerate(expected, start=4):
        case = _case(sent_time=f"2026/05/{day:02d} 10:00:00")
        result = format_case_header(case, "欣興")
        assert f"({weekday})" in result, f"day {day} expected {weekday} in {result}"


# ============= 上午 / 下午 =============


def test_morning() -> None:
    case = _case(sent_time="2026/05/04 09:00:00")
    assert "上午 09:00" in format_case_header(case, "欣興")


def test_noon_is_pm() -> None:
    case = _case(sent_time="2026/05/04 12:00:00")
    assert "下午 12:00" in format_case_header(case, "欣興")


def test_afternoon() -> None:
    case = _case(sent_time="2026/05/04 16:46:00")
    assert "下午 04:46" in format_case_header(case, "欣興")


def test_midnight() -> None:
    """00:30 應顯示「上午 12:30」（12h 制 0 點 = 12 點）。"""
    case = _case(sent_time="2026/05/04 00:30:00")
    assert "上午 12:30" in format_case_header(case, "欣興")


# ============= 日期 / 時間格式 =============


def test_no_leading_zero_on_month_day() -> None:
    case = _case(sent_time="2026/05/04 16:46:00")
    result = format_case_header(case, "欣興")
    assert result.startswith("2026/5/4 ")  # 5/4 不是 05/04


def test_leading_zero_on_hour() -> None:
    """16:46 → 「04:46」（hour 前導 0）。"""
    case = _case(sent_time="2026/05/04 16:46:00")
    assert "04:46" in format_case_header(case, "欣興")


def test_accepts_sent_time_with_seconds() -> None:
    case = _case(sent_time="2026/05/04 16:46:30")
    result = format_case_header(case, "欣興")
    assert "下午 04:46" in result  # 秒不顯示


def test_accepts_sent_time_without_seconds() -> None:
    case = _case(sent_time="2026/05/04 16:46")
    result = format_case_header(case, "欣興")
    assert "下午 04:46" in result


# ============= 缺漏資料 =============


def test_raises_when_sent_time_missing() -> None:
    case = _case(sent_time=None)
    with pytest.raises(ValueError, match="sent_time"):
        format_case_header(case, "欣興")


def test_raises_when_sent_time_empty() -> None:
    case = _case(sent_time="")
    with pytest.raises(ValueError, match="sent_time"):
        format_case_header(case, "欣興")


def test_raises_when_sent_time_invalid_format() -> None:
    case = _case(sent_time="not a date")
    with pytest.raises(ValueError, match="sent_time"):
        format_case_header(case, "欣興")


def test_raises_when_company_name_missing() -> None:
    case = _case()
    with pytest.raises(ValueError, match="company_name"):
        format_case_header(case, None)


def test_raises_when_company_name_empty() -> None:
    case = _case()
    with pytest.raises(ValueError, match="company_name"):
        format_case_header(case, "")


def test_raises_when_subject_missing() -> None:
    case = _case(subject=None)
    with pytest.raises(ValueError, match="subject"):
        format_case_header(case, "欣興")


def test_raises_when_subject_empty() -> None:
    case = _case(subject="")
    with pytest.raises(ValueError, match="subject"):
        format_case_header(case, "欣興")


def test_raises_when_subject_only_prefixes() -> None:
    """主旨全部是 RE:/FW: 等前綴，clean 後為空 → ValueError。"""
    case = _case(subject="RE: FW: ")
    with pytest.raises(ValueError, match="subject"):
        format_case_header(case, "欣興")
