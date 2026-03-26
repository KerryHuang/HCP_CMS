"""自訂欄位管理 — Core 層。UI 層透過此 Manager 操作自訂欄位，不直接存取 Repository。"""

import sqlite3

from hcp_cms.data.models import CustomColumn
from hcp_cms.data.repositories import CustomColumnRepository

STATIC_COL_LABELS: dict[str, str] = {
    "case_id":        "案件編號",
    "company_id":     "公司 ID",
    "subject":        "主旨",
    "status":         "狀態",
    "priority":       "優先等級",
    "replied":        "是否已回覆",
    "sent_time":      "寄件時間",
    "contact_person": "聯絡人",
    "contact_method": "聯絡方式",
    "system_product": "系統／產品",
    "issue_type":     "問題類型",
    "error_type":     "錯誤類型",
    "impact_period":  "影響期間",
    "progress":       "處理進度",
    "handler":        "負責人",
    "actual_reply":   "實際回覆時間",
    "reply_time":     "預計回覆時間",
    "rd_assignee":    "RD 負責人",
    "notes":          "備註",
}


class CustomColumnManager:
    """自訂欄位的建立與查詢，UI 層唯一入口。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._repo = CustomColumnRepository(conn)

    def list_columns(self) -> list[CustomColumn]:
        """回傳所有自訂欄，依 col_order ASC。"""
        return self._repo.list_all()

    def create_column(self, col_label: str) -> CustomColumn:
        """建立新自訂欄，ALTER TABLE + INSERT，回傳 CustomColumn。"""
        col_key = self._repo.next_col_key()
        n = int(col_key.split("_")[1])
        self._repo.add_column_to_cases(col_key)
        self._repo.insert(col_key, col_label, n)
        return CustomColumn(col_key=col_key, col_label=col_label, col_order=n)

    def get_mappable_columns(self) -> list[tuple[str, str]]:
        """回傳 (col_key, col_label) 清單；靜態欄在前，自訂欄在後。"""
        static = list(STATIC_COL_LABELS.items())
        custom = [(c.col_key, c.col_label) for c in self._repo.list_all()]
        return static + custom
