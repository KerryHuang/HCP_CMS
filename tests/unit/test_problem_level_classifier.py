"""ProblemLevelClassifier：error_type → A/B/C 自動推論。"""

from __future__ import annotations

from hcp_cms.core.problem_level_classifier import ProblemLevelClassifier


def test_classify_a_level():
    c = ProblemLevelClassifier()
    assert c.classify("薪資獎金計算") == "A"
    assert c.classify("GL拋轉作業") == "A"
    assert c.classify("所得稅處理") == "A"


def test_classify_b_level():
    c = ProblemLevelClassifier()
    assert c.classify("差勤請假管理") == "B"
    assert c.classify("人事資料管理") == "B"
    assert c.classify("HCP安裝&資料庫錯誤") == "B"


def test_classify_c_level():
    c = ProblemLevelClassifier()
    assert c.classify("合約管理") == "C"
    assert c.classify("人事報表") == "C"
    assert c.classify("ESS(PHP)") == "C"


def test_classify_unknown_falls_back_to_c():
    c = ProblemLevelClassifier()
    assert c.classify("未知模組") == "C"
    assert c.classify(None) == "C"
    assert c.classify("") == "C"
