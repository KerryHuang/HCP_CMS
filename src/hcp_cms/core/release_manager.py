"""ReleaseDetector — 偵測信件是否為待發確認，ReleaseManager — CRUD 整合。"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime

from hcp_cms.data.models import ReleaseItem, ReleaseKeyword
from hcp_cms.data.repositories import ReleaseItemRepository, ReleaseKeywordRepository

# 格式 1：分配給: JILL（HCP 內部指派格式）
_ASSIGNEE_RE = re.compile(r"分配給\s*[:：]\s*(\S+)", re.MULTILINE)
# 格式 2：(0039843) joywu (開發者)（Mantis 留言通知格式）
_MANTIS_COMMENTER_RE = re.compile(r"\(\d+\)\s+(\S+)\s+\([^)]+\)", re.MULTILINE)


class ReleaseDetector:
    """根據 cs_release_keywords 資料表中的關鍵字偵測信件是否代表待發確認。

    規則：信件內容同時包含至少一個 confirm 詞與一個 ship 詞，才視為命中。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._kw_repo = ReleaseKeywordRepository(conn)

    def detect(self, body: str) -> dict | None:
        """分析信件本文，命中時回傳 {assignee, note}，否則回傳 None。"""
        keywords = self._kw_repo.list_all()
        confirm_kws = [k.keyword for k in keywords if k.ktype == "confirm"]
        ship_kws = [k.keyword for k in keywords if k.ktype == "ship"]

        body_lower = body.lower()
        has_confirm = any(k.lower() in body_lower for k in confirm_kws)
        has_ship = any(k.lower() in body_lower for k in ship_kws)

        if not (has_confirm and has_ship):
            return None

        assignee: str | None = None
        m = _ASSIGNEE_RE.search(body)
        if m:
            # 優先採用「分配給: XXX」格式
            assignee = m.group(1).strip()
        else:
            # 次選：Mantis 留言格式「(票號) 姓名 (角色)」
            m2 = _MANTIS_COMMENTER_RE.search(body)
            if m2:
                assignee = m2.group(1).strip()

        note = self._extract_note(body, confirm_kws + ship_kws)

        return {"assignee": assignee, "note": note}

    @staticmethod
    def _extract_note(body: str, trigger_kws: list[str]) -> str:
        """擷取含觸發關鍵字的段落作為備注。

        策略：
        1. 若命中行的上方緊鄰 Mantis 留言人行（格式：(票號) 姓名 (角色) - 日期），
           則將留言人行 + 命中行合併，提供完整脈絡。
        2. 否則只回傳命中行。
        最多 400 字。
        """
        lines = body.splitlines()
        for i, line in enumerate(lines):
            if any(kw.lower() in line.lower() for kw in trigger_kws):
                # 嘗試往上找 Mantis 留言人行（跳過空行和 URL 行）
                context_lines: list[str] = []
                for j in range(i - 1, max(i - 5, -1), -1):
                    prev = lines[j].strip()
                    if not prev or prev.startswith("http"):
                        continue
                    if _MANTIS_COMMENTER_RE.match(prev):
                        context_lines.insert(0, prev)
                    break
                context_lines.append(line.strip())
                return "\n".join(context_lines)[:400]
        return ""


class ReleaseManager:
    """待發清單 CRUD 與信件偵測整合。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._detector = ReleaseDetector(conn)
        self._repo = ReleaseItemRepository(conn)
        self._kw_repo = ReleaseKeywordRepository(conn)

    def detect_and_record(
        self,
        body: str,
        case_id: str | None = None,
        mantis_ticket_id: str | None = None,
        client_name: str | None = None,
        month_str: str | None = None,
    ) -> ReleaseItem | None:
        """偵測信件是否為待發確認；命中則建立 ReleaseItem 並回傳，否則回傳 None。"""
        result = self._detector.detect(body)
        if result is None:
            return None

        if month_str is None:
            month_str = datetime.now().strftime("%Y%m")

        item = ReleaseItem(
            case_id=case_id,
            mantis_ticket_id=mantis_ticket_id,
            assignee=result["assignee"],
            client_name=client_name,
            note=result["note"],
            month_str=month_str,
        )
        new_id = self._repo.insert(item)
        item.id = new_id
        return item

    def list_by_month(self, month_str: str) -> list[ReleaseItem]:
        return self._repo.list_by_month(month_str)

    def list_all(self) -> list[ReleaseItem]:
        return self._repo.list_all()

    def mark_released(self, item_id: int) -> None:
        self._repo.mark_released(item_id)

    def update_month(self, item_id: int, month_str: str) -> None:
        self._repo.update_month(item_id, month_str)

    def mark_pending(self, item_id: int) -> None:
        self._repo.mark_pending(item_id)

    def delete_item(self, item_id: int) -> None:
        self._repo.delete(item_id)

    def add_item(
        self,
        case_id: str | None = None,
        mantis_ticket_id: str | None = None,
        client_name: str | None = None,
        assignee: str | None = None,
        note: str = "",
        month_str: str | None = None,
    ) -> ReleaseItem:
        """手動建立 ReleaseItem 並回傳。"""
        if month_str is None:
            month_str = datetime.now().strftime("%Y%m")
        item = ReleaseItem(
            case_id=case_id,
            mantis_ticket_id=mantis_ticket_id,
            client_name=client_name,
            assignee=assignee,
            note=note,
            month_str=month_str,
        )
        new_id = self._repo.insert(item)
        item.id = new_id
        return item

    def list_keywords(self) -> list[ReleaseKeyword]:
        return self._kw_repo.list_all()

    def add_keyword(self, keyword: str, ktype: str) -> int:
        return self._kw_repo.insert(ReleaseKeyword(keyword=keyword, ktype=ktype))

    def delete_keyword(self, keyword_id: int) -> None:
        self._kw_repo.delete(keyword_id)
