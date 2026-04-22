"""ReleaseDetector — 偵測信件是否為待發確認，ReleaseManager — CRUD 整合。"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime

from hcp_cms.data.models import ReleaseItem, ReleaseKeyword
from hcp_cms.data.repositories import ReleaseItemRepository, ReleaseKeywordRepository

# 格式 1：分配給: JILL（HCP 內部指派格式）
_ASSIGNEE_RE = re.compile(r"分配給\s*[:：]\s*(\S+)", re.MULTILINE)

# 格式 2：(0039843) joywu (開發者) - 2026-04-21 17:07
# group(1)=姓名  group(2)=日期時間（可選）
_MANTIS_COMMENTER_RE = re.compile(
    r"\(\d+\)\s+(\S+)\s+\([^)]+\)(?:\s+-\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}))?",
    re.MULTILINE,
)

# Mantis 活動記錄行：2026-04-09 14:08 ventie 檔案已新增: ...
# group(1)=姓名
_MODIFIER_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+(\S+)\s+(?:檔案已新增|狀態已更新|指派給|已刪除|已編輯)",
    re.MULTILINE,
)


class ReleaseDetector:
    """根據 cs_release_keywords 資料表中的關鍵字偵測信件是否代表待發確認。

    規則：信件內容同時包含至少一個 confirm 詞與一個 ship 詞，才視為命中。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._kw_repo = ReleaseKeywordRepository(conn)

    def detect(self, body: str) -> dict | None:
        """分析信件本文，命中時回傳 {assignee, note, modifier}，否則回傳 None。"""
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

        # 修改者：從 Mantis 活動記錄行萃取最後一個不重複的人名
        modifier: str | None = None
        mod_matches = _MODIFIER_RE.findall(body)
        if mod_matches:
            # 取最後出現的非重複人名（排除已知客服帳號可能為 assignee 的情況）
            seen: list[str] = []
            for name in mod_matches:
                if name not in seen:
                    seen.append(name)
            modifier = seen[-1]  # 最新動作的人

        note = self._extract_note(body, confirm_kws + ship_kws)

        return {"assignee": assignee, "note": note, "modifier": modifier}

    @staticmethod
    def _extract_note(body: str, trigger_kws: list[str]) -> str:
        """擷取含觸發關鍵字的段落作為備注。

        輸出格式（優先）：
            姓名 YYYY-MM-DD HH:MM
            留言內文

        若找不到 Mantis 留言人行，則只回傳觸發行文字。
        最多 400 字。
        """
        lines = body.splitlines()
        for i, line in enumerate(lines):
            if any(kw.lower() in line.lower() for kw in trigger_kws):
                # 嘗試往上找 Mantis 留言人行（跳過空行、URL 行、虛線分隔行）
                commenter_header: str | None = None
                for j in range(i - 1, max(i - 8, -1), -1):
                    prev = lines[j].strip()
                    if not prev or prev.startswith("http") or set(prev) <= {"-", "=", " "}:
                        continue
                    m = _MANTIS_COMMENTER_RE.match(prev)
                    if m:
                        name = m.group(1)
                        date_str = m.group(2) or ""
                        # 格式化為「姓名 日期」，去除票號與角色描述
                        commenter_header = f"{name} {date_str}".strip()
                    break

                content = line.strip()
                if commenter_header:
                    return f"{commenter_header}\n{content}"[:400]
                return content[:400]
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
            modifier=result.get("modifier"),
            month_str=month_str,
        )
        new_id = self._repo.insert(item)
        item.id = new_id
        return item

    def list_by_month(self, month_str: str) -> list[ReleaseItem]:
        return self._repo.list_by_month(month_str)

    def list_all(self) -> list[ReleaseItem]:
        return self._repo.list_all()

    def mark_pending_confirm(self, item_id: int) -> None:
        self._repo.mark_pending_confirm(item_id)

    def mark_released(self, item_id: int) -> None:
        self._repo.mark_released(item_id)

    def update_month(self, item_id: int, month_str: str) -> None:
        self._repo.update_month(item_id, month_str)

    def mark_pending(self, item_id: int) -> None:
        self._repo.mark_pending(item_id)

    def update_note(self, item_id: int, note: str) -> None:
        self._repo.update_note(item_id, note)

    def move_item(self, items: list[ReleaseItem], index: int, direction: int) -> None:
        """將 items[index] 與相鄰項目交換排序（direction=-1 上移，+1 下移）。

        items 必須是同月份、已依 sort_order 排序的清單。
        """
        target_idx = index + direction
        if target_idx < 0 or target_idx >= len(items):
            return
        a = items[index]
        b = items[target_idx]
        # 確保兩者都有 sort_order
        order_a = a.sort_order if a.sort_order is not None else index + 1
        order_b = b.sort_order if b.sort_order is not None else target_idx + 1
        self._repo.swap_sort_order(a.id, order_a, b.id, order_b)

    def delete_item(self, item_id: int) -> None:
        self._repo.delete(item_id)

    def add_item(
        self,
        case_id: str | None = None,
        mantis_ticket_id: str | None = None,
        client_name: str | None = None,
        assignee: str | None = None,
        note: str = "",
        modifier: str | None = None,
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
            modifier=modifier,
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
