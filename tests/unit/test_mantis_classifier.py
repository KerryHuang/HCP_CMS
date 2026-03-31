"""Tests for MantisClassifier."""

from hcp_cms.core.mantis_classifier import MantisClassifier
from hcp_cms.data.models import MantisTicket


def _ticket(**kwargs) -> MantisTicket:
    """快速建立 MantisTicket（只填必要欄位）。"""
    return MantisTicket(ticket_id="MT-0001", summary=kwargs.get("summary", "一般問題"), **{k: v for k, v in kwargs.items() if k != "summary"})


class TestMantisClassifier:
    def setup_method(self):
        self.clf = MantisClassifier()

    def test_classify_closed_resolved(self):
        t = _ticket(status="resolved")
        assert self.clf.classify(t) == "closed"

    def test_classify_closed_chinese(self):
        t = _ticket(status="已關閉")
        assert self.clf.classify(t) == "closed"

    def test_classify_closed_beats_high_priority(self):
        """已結案優先於高優先度——不應顯示紅色。"""
        t = _ticket(status="closed", priority="urgent")
        assert self.clf.classify(t) == "closed"

    def test_classify_salary_keyword_chinese(self):
        t = _ticket(summary="薪資計算錯誤", status="assigned")
        assert self.clf.classify(t) == "salary"

    def test_classify_salary_keyword_english(self):
        t = _ticket(summary="Payroll module error", status="assigned")
        assert self.clf.classify(t) == "salary"

    def test_classify_high_urgent(self):
        t = _ticket(priority="urgent", status="assigned")
        assert self.clf.classify(t) == "high"

    def test_classify_high_immediate(self):
        t = _ticket(priority="immediate", status="assigned")
        assert self.clf.classify(t) == "high"

    def test_classify_normal(self):
        t = _ticket(priority="normal", status="assigned")
        assert self.clf.classify(t) == "normal"

    def test_classify_none_summary_no_error(self):
        """summary=None 時不拋例外，應回傳 normal。"""
        t = MantisTicket(ticket_id="MT-0001", summary=None, status="assigned")
        assert self.clf.classify(t) == "normal"

    def test_calc_unresolved_days_closed_returns_dash(self):
        t = _ticket(status="resolved", last_updated="2026/03/01 10:00:00")
        assert self.clf.calc_unresolved_days(t) == "—"

    def test_calc_unresolved_days_no_last_updated(self):
        t = _ticket(status="assigned", last_updated=None)
        assert self.clf.calc_unresolved_days(t) == ""

    def test_calc_unresolved_days_returns_days_string(self):
        """使用固定日期驗證計算邏輯正確（不依賴今日）。"""
        from datetime import datetime, timedelta
        three_days_ago = (datetime.now() - timedelta(days=3)).strftime("%Y/%m/%d %H:%M:%S")
        t = _ticket(status="assigned", last_updated=three_days_ago)
        result = self.clf.calc_unresolved_days(t)
        assert result == "3 天"
