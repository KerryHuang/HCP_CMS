"""ProblemLevelClassifier — 依 error_type（模組名）自動推論 A/B/C 問題等級。

對映規則由使用者確認（2026-04-24）：
- A（6 項）：薪資/GL/調薪/福利/所得稅
- B（12 項）：行事曆、差勤、排班、刷卡、保險、組織、人事資料、HCP 錯誤等
- C（15 項 + fallback）：報表、合約、教育訓練、ESS、客製、其餘
"""

from __future__ import annotations

_LEVEL_A: set[str] = {
    "薪資獎金計算",
    "薪資報表",
    "GL拋轉作業",
    "調薪試算",
    "福利金處理",
    "所得稅處理",
}

_LEVEL_B: set[str] = {
    "行事曆與排班",
    "差勤請假管理",
    "年假管理",
    "彈休管理",
    "刷卡管理",
    "工時管理",
    "員工用餐管理",
    "社會保險管理",
    "勞健團保二代健保勞退",
    "組織部門建立",
    "人事資料管理",
    "HCP安裝&資料庫錯誤",
}

_LEVEL_C: set[str] = {
    "人事報表",
    "合約管理",
    "員工教育訓練",
    "績效考核管理",
    "員工獎懲管理",
    "簽核流程管理",
    "自助分析作業",
    "匯入匯出作業",
    "系統管理",
    "系統參數",
    "警示系統設定",
    "住宿管理",
    "客製程式",
    "ESS(.NET)",
    "ESS(PHP)",
}


class ProblemLevelClassifier:
    """將 error_type 對映為 A/B/C 風險等級；未知 → C。"""

    def classify(self, error_type: str | None) -> str:
        if not error_type:
            return "C"
        key = error_type.strip()
        if key in _LEVEL_A:
            return "A"
        if key in _LEVEL_B:
            return "B"
        return "C"
