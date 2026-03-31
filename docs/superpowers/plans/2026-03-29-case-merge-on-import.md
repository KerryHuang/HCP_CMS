# 同主旨信件自動整合為一個案件 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 匯入同公司、同主旨的信件時自動整合為一個案件（Find-or-Create），並提供一鍵整合已存在重複案件的功能（MergeDuplicates）。

**Architecture:** 在 Data 層新增 `find_by_company_and_subject()` 與 `transfer_logs()` 方法；在 Core 層新增 `CaseMerger` 類別並修改 `CaseManager.import_email()` 加入 Find-or-Create 邏輯；在 UI 層（設定頁）新增「整合重複案件」按鈕。

**Tech Stack:** Python 3.14、SQLite、PySide6、pytest

---

## 檔案異動總覽

| 檔案 | 異動類型 | 說明 |
|------|----------|------|
| `src/hcp_cms/data/models.py` | 修改 | 第 159 行：更新方向註解加入 `'HCP 回覆'` |
| `src/hcp_cms/ui/case_detail_dialog.py` | 修改 | 第 689 行：下拉選單加入 `"HCP 回覆"` |
| `src/hcp_cms/data/repositories.py` | 修改 | 新增 `_PREFIX_RE` / `_clean_subject()`、`CaseRepository.find_by_company_and_subject()`、`CaseLogRepository.transfer_logs()` |
| `src/hcp_cms/core/case_merger.py` | 新增 | `CaseMerger` 類別 |
| `src/hcp_cms/core/case_manager.py` | 修改 | 新增 `_detect_direction()`、修改 `import_email()` |
| `src/hcp_cms/ui/settings_view.py` | 修改 | 新增「🔧 整合重複案件」按鈕與 slot |
| `tests/unit/test_repositories.py` | 修改 | 新增 `find_by_company_and_subject` 與 `transfer_logs` 測試 |
| `tests/unit/test_case_merger.py` | 新增 | `CaseMerger` 所有測試 |
| `tests/unit/test_case_manager.py` | 修改 | 新增 Find-or-Create 與方向判斷測試 |

---

## Task 1: "CS 回覆" → "HCP 回覆" 標籤變更

**Files:**
- Modify: `src/hcp_cms/data/models.py:159`
- Modify: `src/hcp_cms/ui/case_detail_dialog.py:689`

> 說明：models.py 只更新程式碼註解；UI 下拉選單同時保留 `"CS 回覆"`（相容舊資料），新增 `"HCP 回覆"`，並將其排在前面供預設選取。

- [ ] **Step 1: 更新 models.py 方向型別註解**

在 `src/hcp_cms/data/models.py` 找到第 159 行：

```python
    direction: str            # '客戶來信' | 'CS 回覆' | '內部討論'
```

改為：

```python
    direction: str            # '客戶來信' | 'HCP 回覆' | 'CS 回覆' | '內部討論'
```

- [ ] **Step 2: 更新 case_detail_dialog.py 下拉選單**

在 `src/hcp_cms/ui/case_detail_dialog.py` 找到第 689 行：

```python
        self._direction.addItems(["客戶來信", "CS 回覆", "內部討論"])
```

改為（保留 `"CS 回覆"` 供舊資料顯示，`"HCP 回覆"` 排前）：

```python
        self._direction.addItems(["客戶來信", "HCP 回覆", "CS 回覆", "內部討論"])
```

- [ ] **Step 3: 執行測試確認未破壞現有功能**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short
```

預期：全部 PASS（無現有測試依賴特定 direction 字串值）。

- [ ] **Step 4: Commit**

```bash
git add src/hcp_cms/data/models.py src/hcp_cms/ui/case_detail_dialog.py
git commit -m "feat: 將方向標籤 CS 回覆更名為 HCP 回覆，下拉選單保留舊值相容"
```

---

## Task 2: CaseRepository.find_by_company_and_subject() + Data 層前綴清理工具

**Files:**
- Modify: `src/hcp_cms/data/repositories.py`
- Test: `tests/unit/test_repositories.py`

> 說明：在 `repositories.py` 頂層新增私有正規表達式與 `_clean_subject()` 函數，供 `find_by_company_and_subject()` 在 Python 側比對時去除主旨前綴。不可從 Core 層匯入（避免違反分層規則）。

- [ ] **Step 1: 撰寫失敗測試**

在 `tests/unit/test_repositories.py` 檔案底部，緊接在 `TestCaseRepository` 類別（或其後任意位置），新增以下測試類別：

```python
class TestCaseRepositoryFindByCompanyAndSubject:
    def test_find_by_company_and_subject_found(self, db: DatabaseManager) -> None:
        repo = CaseRepository(db.connection)
        case = Case(case_id="CS-2026-001", subject="薪資計算異常", company_id="C001")
        repo.insert(case)
        result = repo.find_by_company_and_subject("C001", "薪資計算異常")
        assert result is not None
        assert result.case_id == "CS-2026-001"

    def test_find_by_company_and_subject_not_found(self, db: DatabaseManager) -> None:
        repo = CaseRepository(db.connection)
        result = repo.find_by_company_and_subject("C001", "不存在主旨")
        assert result is None

    def test_find_by_company_and_subject_clean_subject_match(self, db: DatabaseManager) -> None:
        """DB 中的 'RE: 薪資問題' 應能被 clean_subject '薪資問題' 查到。"""
        repo = CaseRepository(db.connection)
        case = Case(case_id="CS-2026-002", subject="RE: 薪資問題", company_id="C001")
        repo.insert(case)
        result = repo.find_by_company_and_subject("C001", "薪資問題")
        assert result is not None
        assert result.case_id == "CS-2026-002"

    def test_find_by_company_and_subject_different_company(self, db: DatabaseManager) -> None:
        """相同主旨但不同公司不應回傳。"""
        repo = CaseRepository(db.connection)
        case = Case(case_id="CS-2026-003", subject="薪資問題", company_id="C002")
        repo.insert(case)
        result = repo.find_by_company_and_subject("C001", "薪資問題")
        assert result is None

    def test_find_by_company_and_subject_returns_earliest(self, db: DatabaseManager) -> None:
        """有多筆匹配時回傳 sent_time 最早的案件。"""
        repo = CaseRepository(db.connection)
        older = Case(
            case_id="CS-2026-010",
            subject="薪資問題",
            company_id="C001",
            sent_time="2026/01/01 08:00",
        )
        newer = Case(
            case_id="CS-2026-011",
            subject="RE: 薪資問題",
            company_id="C001",
            sent_time="2026/03/01 08:00",
        )
        repo.insert(older)
        repo.insert(newer)
        result = repo.find_by_company_and_subject("C001", "薪資問題")
        assert result is not None
        assert result.case_id == "CS-2026-010"
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_repositories.py::TestCaseRepositoryFindByCompanyAndSubject -v
```

預期：FAILED — `AttributeError: 'CaseRepository' object has no attribute 'find_by_company_and_subject'`

- [ ] **Step 3: 新增 `_PREFIX_RE` / `_clean_subject()` 到 repositories.py**

在 `src/hcp_cms/data/repositories.py` 第 22 行（`_COL_KEY_RE` 之後）加入：

```python
_PREFIX_RE = _re.compile(r'^(RE:|FW:|FWD:|回覆:|轉寄:|答覆:)\s*', _re.IGNORECASE)


def _clean_subject(subject: str) -> str:
    """遞迴去除主旨前綴（RE:/FW:/回覆: 等），供 Python 側比對使用。"""
    result = subject
    while True:
        stripped = _PREFIX_RE.sub('', result).strip()
        if stripped == result:
            return result
        result = stripped
```

- [ ] **Step 4: 新增 `find_by_company_and_subject()` 到 CaseRepository**

在 `src/hcp_cms/data/repositories.py` 的 `CaseRepository.list_all()` 方法之後（約第 218 行），加入：

```python
    def find_by_company_and_subject(
        self, company_id: str, clean_subject: str
    ) -> Case | None:
        """查詢 company_id 相同且主旨（去前綴後）相符的最早案件。

        先抓該公司所有案件，Python 側逐一 _clean_subject() 比對。
        回傳 sent_time 最早的匹配案件（若 sent_time 相同則取 case_id 字典序最小）。
        """
        rows = self._conn.execute(
            self._build_select() + " WHERE company_id = ? ORDER BY sent_time ASC, case_id ASC",
            (company_id,),
        ).fetchall()
        for row in rows:
            case = self._row_to_case(row)
            if _clean_subject(case.subject) == clean_subject:
                return case
        return None
```

- [ ] **Step 5: 執行測試確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_repositories.py::TestCaseRepositoryFindByCompanyAndSubject -v
```

預期：5 個測試全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add src/hcp_cms/data/repositories.py tests/unit/test_repositories.py
git commit -m "feat: CaseRepository.find_by_company_and_subject() — Data 層查詢同公司同主旨案件"
```

---

## Task 3: CaseLogRepository.transfer_logs()

**Files:**
- Modify: `src/hcp_cms/data/repositories.py`
- Test: `tests/unit/test_repositories.py`

- [ ] **Step 1: 撰寫失敗測試**

在 `tests/unit/test_repositories.py` 底部新增（需在 `TestCaseRepositoryFindByCompanyAndSubject` 之後）：

```python
class TestCaseLogRepositoryTransferLogs:
    def test_transfer_logs_moves_all_logs(self, db: DatabaseManager) -> None:
        """transfer_logs 後，from_case 的所有 log 的 case_id 變為 to_case。"""
        from hcp_cms.data.models import CaseLog
        from hcp_cms.data.repositories import CaseLogRepository

        case_repo = CaseRepository(db.connection)
        log_repo = CaseLogRepository(db.connection)

        case_a = Case(case_id="CS-2026-020", subject="主旨A", company_id="C001")
        case_b = Case(case_id="CS-2026-021", subject="主旨B", company_id="C001")
        case_repo.insert(case_a)
        case_repo.insert(case_b)

        log1 = CaseLog(
            log_id="LOG-20260101-001",
            case_id="CS-2026-020",
            direction="客戶來信",
            content="第一封",
            logged_at="2026/01/01 09:00:00",
        )
        log2 = CaseLog(
            log_id="LOG-20260101-002",
            case_id="CS-2026-020",
            direction="HCP 回覆",
            content="第二封",
            logged_at="2026/01/02 09:00:00",
        )
        log_repo.insert(log1)
        log_repo.insert(log2)

        log_repo.transfer_logs("CS-2026-020", "CS-2026-021")

        logs_a = log_repo.list_by_case("CS-2026-020")
        logs_b = log_repo.list_by_case("CS-2026-021")
        assert len(logs_a) == 0
        assert len(logs_b) == 2
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_repositories.py::TestCaseLogRepositoryTransferLogs -v
```

預期：FAILED — `AttributeError: 'CaseLogRepository' object has no attribute 'transfer_logs'`

- [ ] **Step 3: 新增 `transfer_logs()` 到 CaseLogRepository**

在 `src/hcp_cms/data/repositories.py` 的 `CaseLogRepository.delete()` 方法（約第 894 行）之後加入：

```python
    def transfer_logs(self, from_case_id: str, to_case_id: str) -> None:
        """將 from_case_id 的所有 CaseLog 的 case_id 改為 to_case_id。"""
        self._conn.execute(
            "UPDATE case_logs SET case_id = ? WHERE case_id = ?",
            (to_case_id, from_case_id),
        )
        self._conn.commit()
```

- [ ] **Step 4: 執行測試確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_repositories.py::TestCaseLogRepositoryTransferLogs -v
```

預期：PASS。

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/data/repositories.py tests/unit/test_repositories.py
git commit -m "feat: CaseLogRepository.transfer_logs() — 整合重複案件時移轉 CaseLog"
```

---

## Task 4: CaseMerger 類別

**Files:**
- Create: `src/hcp_cms/core/case_merger.py`
- Create: `tests/unit/test_case_merger.py`

- [ ] **Step 1: 建立測試檔案**

建立 `tests/unit/test_case_merger.py`：

```python
"""Unit tests for CaseMerger."""

from __future__ import annotations

from pathlib import Path

import pytest

from hcp_cms.core.case_merger import CaseMerger
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, CaseLog
from hcp_cms.data.repositories import CaseLogRepository, CaseRepository


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


def _insert_case(
    repo: CaseRepository,
    case_id: str,
    subject: str,
    company_id: str | None = "C001",
    sent_time: str = "2026/01/01 09:00",
    reply_count: int = 0,
) -> Case:
    case = Case(
        case_id=case_id,
        subject=subject,
        company_id=company_id,
        sent_time=sent_time,
        reply_count=reply_count,
    )
    repo.insert(case)
    return case


def _insert_log(
    log_repo: CaseLogRepository,
    log_id: str,
    case_id: str,
    direction: str = "客戶來信",
) -> CaseLog:
    log = CaseLog(
        log_id=log_id,
        case_id=case_id,
        direction=direction,
        content="測試內容",
        logged_at="2026/01/01 09:00:00",
    )
    log_repo.insert(log)
    return log


class TestCaseMergerFindDuplicateGroups:
    def test_find_duplicate_groups_returns_groups(self, db: DatabaseManager) -> None:
        """相同 company_id + clean_subject 的案件歸為一組。"""
        repo = CaseRepository(db.connection)
        _insert_case(repo, "CS-2026-001", "薪資問題", "C001")
        _insert_case(repo, "CS-2026-002", "RE: 薪資問題", "C001")

        merger = CaseMerger(db.connection)
        groups = merger.find_duplicate_groups()
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_find_duplicate_groups_different_company(self, db: DatabaseManager) -> None:
        """不同公司 + 相同主旨不算重複。"""
        repo = CaseRepository(db.connection)
        _insert_case(repo, "CS-2026-001", "薪資問題", "C001")
        _insert_case(repo, "CS-2026-002", "薪資問題", "C002")

        merger = CaseMerger(db.connection)
        groups = merger.find_duplicate_groups()
        assert len(groups) == 0

    def test_find_duplicate_groups_single_case_excluded(self, db: DatabaseManager) -> None:
        """單筆不被列入重複群組。"""
        repo = CaseRepository(db.connection)
        _insert_case(repo, "CS-2026-001", "薪資問題", "C001")

        merger = CaseMerger(db.connection)
        groups = merger.find_duplicate_groups()
        assert len(groups) == 0

    def test_find_duplicate_groups_none_company_excluded(self, db: DatabaseManager) -> None:
        """company_id 為 None 的案件不納入重複偵測。"""
        repo = CaseRepository(db.connection)
        _insert_case(repo, "CS-2026-001", "薪資問題", None)
        _insert_case(repo, "CS-2026-002", "薪資問題", None)

        merger = CaseMerger(db.connection)
        groups = merger.find_duplicate_groups()
        assert len(groups) == 0


class TestCaseMergerMergeGroup:
    def test_merge_group_keeps_earliest(self, db: DatabaseManager) -> None:
        """保留 sent_time 最早的案件。"""
        repo = CaseRepository(db.connection)
        early = _insert_case(repo, "CS-2026-001", "薪資問題", sent_time="2026/01/01 08:00")
        late = _insert_case(repo, "CS-2026-002", "RE: 薪資問題", sent_time="2026/03/01 10:00")

        merger = CaseMerger(db.connection)
        primary = merger.merge_group([early, late])
        assert primary.case_id == "CS-2026-001"

    def test_merge_group_same_sent_time_uses_case_id_order(self, db: DatabaseManager) -> None:
        """sent_time 相同時，保留 case_id 字典序較小者。"""
        repo = CaseRepository(db.connection)
        a = _insert_case(repo, "CS-2026-001", "薪資問題", sent_time="2026/01/01 08:00")
        b = _insert_case(repo, "CS-2026-002", "RE: 薪資問題", sent_time="2026/01/01 08:00")

        merger = CaseMerger(db.connection)
        primary = merger.merge_group([a, b])
        assert primary.case_id == "CS-2026-001"

    def test_merge_group_transfers_logs(self, db: DatabaseManager) -> None:
        """secondary 的 CaseLog 移轉至 primary。"""
        case_repo = CaseRepository(db.connection)
        log_repo = CaseLogRepository(db.connection)

        primary_case = _insert_case(case_repo, "CS-2026-001", "薪資問題", sent_time="2026/01/01 08:00")
        secondary_case = _insert_case(case_repo, "CS-2026-002", "RE: 薪資問題", sent_time="2026/03/01 10:00")
        _insert_log(log_repo, "LOG-20260301-001", "CS-2026-002")

        merger = CaseMerger(db.connection)
        merger.merge_group([primary_case, secondary_case])

        logs_primary = log_repo.list_by_case("CS-2026-001")
        logs_secondary = log_repo.list_by_case("CS-2026-002")
        assert len(logs_primary) == 1
        assert len(logs_secondary) == 0

    def test_merge_group_sums_reply_count(self, db: DatabaseManager) -> None:
        """reply_count 累加。"""
        repo = CaseRepository(db.connection)
        a = _insert_case(repo, "CS-2026-001", "薪資問題", sent_time="2026/01/01 08:00", reply_count=2)
        b = _insert_case(repo, "CS-2026-002", "RE: 薪資問題", sent_time="2026/03/01 10:00", reply_count=3)

        merger = CaseMerger(db.connection)
        primary = merger.merge_group([a, b])
        assert primary.reply_count == 5

        # 確認 DB 已更新
        saved = CaseRepository(db.connection).get_by_id("CS-2026-001")
        assert saved.reply_count == 5

    def test_merge_group_deletes_secondary(self, db: DatabaseManager) -> None:
        """secondary 從資料庫刪除。"""
        repo = CaseRepository(db.connection)
        a = _insert_case(repo, "CS-2026-001", "薪資問題", sent_time="2026/01/01 08:00")
        b = _insert_case(repo, "CS-2026-002", "RE: 薪資問題", sent_time="2026/03/01 10:00")

        merger = CaseMerger(db.connection)
        merger.merge_group([a, b])

        assert repo.get_by_id("CS-2026-001") is not None
        assert repo.get_by_id("CS-2026-002") is None


class TestCaseMergerMergeAllDuplicates:
    def test_merge_all_duplicates_returns_count(self, db: DatabaseManager) -> None:
        """回傳正確刪除筆數。"""
        repo = CaseRepository(db.connection)
        # 群組 1：2 筆（刪 1）
        _insert_case(repo, "CS-2026-001", "薪資問題", "C001", sent_time="2026/01/01 08:00")
        _insert_case(repo, "CS-2026-002", "RE: 薪資問題", "C001", sent_time="2026/03/01 10:00")
        # 群組 2：3 筆（刪 2）
        _insert_case(repo, "CS-2026-003", "請假申請", "C002", sent_time="2026/01/01 08:00")
        _insert_case(repo, "CS-2026-004", "RE: 請假申請", "C002", sent_time="2026/02/01 10:00")
        _insert_case(repo, "CS-2026-005", "FW: 請假申請", "C002", sent_time="2026/03/01 10:00")

        merger = CaseMerger(db.connection)
        deleted = merger.merge_all_duplicates()
        assert deleted == 3  # 1 + 2

    def test_merge_all_duplicates_no_duplicates(self, db: DatabaseManager) -> None:
        """無重複案件時回傳 0，不報錯。"""
        repo = CaseRepository(db.connection)
        _insert_case(repo, "CS-2026-001", "薪資問題", "C001")

        merger = CaseMerger(db.connection)
        deleted = merger.merge_all_duplicates()
        assert deleted == 0
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_case_merger.py -v
```

預期：FAILED — `ModuleNotFoundError: No module named 'hcp_cms.core.case_merger'`

- [ ] **Step 3: 建立 `src/hcp_cms/core/case_merger.py`**

```python
"""CaseMerger — 整合重複案件（相同 company_id + clean_subject）。"""

from __future__ import annotations

import logging
import sqlite3

from hcp_cms.core.thread_tracker import ThreadTracker
from hcp_cms.data.models import Case
from hcp_cms.data.repositories import CaseLogRepository, CaseRepository

logger = logging.getLogger(__name__)


class CaseMerger:
    """整合同公司、同主旨（去 RE:/FW: 前綴後相同）的重複案件。

    職責一：find_duplicate_groups() — 找出重複群組
    職責二：merge_group() — 合併單一群組
    職責三：merge_all_duplicates() — 批次合併所有重複群組
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._case_repo = CaseRepository(conn)
        self._log_repo = CaseLogRepository(conn)

    def find_duplicate_groups(self) -> list[list[Case]]:
        """找出所有 (company_id, clean_subject) 相同的案件群組（每群組 ≥ 2 筆）。"""
        cases = self._case_repo.list_all()
        groups: dict[tuple[str, str], list[Case]] = {}
        for case in cases:
            if not case.company_id:
                continue
            key = (case.company_id, ThreadTracker.clean_subject(case.subject))
            groups.setdefault(key, []).append(case)
        return [g for g in groups.values() if len(g) >= 2]

    def merge_group(self, cases: list[Case]) -> Case:
        """保留 sent_time 最早的案件，其餘 CaseLog 移轉後刪除。回傳 primary 案件。

        排序準則：sent_time ASC，若相同則 case_id ASC（字典序）。
        """
        sorted_cases = sorted(cases, key=lambda c: (c.sent_time or "", c.case_id))
        primary = sorted_cases[0]
        secondary = sorted_cases[1:]

        for sec in secondary:
            self._log_repo.transfer_logs(sec.case_id, primary.case_id)
            primary.reply_count += sec.reply_count

        self._case_repo.update(primary)

        for sec in secondary:
            self._case_repo.delete(sec.case_id)

        return primary

    def merge_all_duplicates(self) -> int:
        """執行全部群組合併，回傳刪除的案件筆數。

        每個群組獨立執行；某群組失敗時記錄錯誤並繼續處理其餘群組。
        """
        groups = self.find_duplicate_groups()
        deleted = 0
        for group in groups:
            try:
                self.merge_group(group)
                deleted += len(group) - 1
            except Exception:
                logger.exception(
                    "合併案件群組失敗：%s",
                    [c.case_id for c in group],
                )
        return deleted
```

- [ ] **Step 4: 執行測試確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_case_merger.py -v
```

預期：所有測試 PASS。

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/core/case_merger.py tests/unit/test_case_merger.py
git commit -m "feat: CaseMerger — 整合同公司同主旨重複案件"
```

---

## Task 5: CaseManager.import_email() Find-or-Create + 方向判斷

**Files:**
- Modify: `src/hcp_cms/core/case_manager.py`
- Test: `tests/unit/test_case_manager.py`

- [ ] **Step 1: 撰寫失敗測試**

在 `tests/unit/test_case_manager.py` 的 `TestImportEmail` 類別末尾，加入以下測試方法：

```python
    def test_import_email_find_existing_adds_log(self, seeded_db):
        """相同 company + 主旨已有案件時，加入 CaseLog 而非建立新案件。"""
        from hcp_cms.data.repositories import CaseLogRepository, CaseRepository

        mgr = CaseManager(seeded_db.connection)
        # 先建立一筆案件（寄件者為外部，分類到 C-ASE）
        result1, action1 = mgr.import_email(
            subject="薪資計算異常",
            body="第一封內容",
            sender_email="user@aseglobal.com",
            sent_time="2026/03/01 09:00",
        )
        assert action1 == "created"
        original_case_id = result1.case_id

        # 匯入同主旨第二封
        result2, action2 = mgr.import_email(
            subject="RE: 薪資計算異常",
            body="第二封內容",
            sender_email="user@aseglobal.com",
            sent_time="2026/03/02 10:00",
        )
        assert action2 == "merged"
        assert result2.case_id == original_case_id

        # 確認案件總數仍為 1
        all_cases = CaseRepository(seeded_db.connection).list_all()
        assert len(all_cases) == 1

        # 確認 CaseLog 已新增
        logs = CaseLogRepository(seeded_db.connection).list_by_case(original_case_id)
        assert len(logs) == 1
        assert logs[0].content == "第二封內容"

    def test_import_email_no_match_creates_case(self, seeded_db):
        """無匹配案件時建立新案件（action='created'）。"""
        from hcp_cms.data.repositories import CaseRepository

        mgr = CaseManager(seeded_db.connection)
        _, action1 = mgr.import_email(
            subject="薪資計算異常",
            body="第一封",
            sender_email="user@aseglobal.com",
        )
        _, action2 = mgr.import_email(
            subject="請假申請流程",  # 不同主旨
            body="第二封",
            sender_email="user@aseglobal.com",
        )
        assert action1 == "created"
        assert action2 == "created"
        assert len(CaseRepository(seeded_db.connection).list_all()) == 2

    def test_import_email_direction_hcp_reply(self, seeded_db):
        """寄件者含 @ares.com.tw 時，direction 應為 'HCP 回覆'。

        HCP 回覆時 sender 為我方，Classifier 會從 to_recipients 解析公司，
        故需傳入客戶的 email 讓分類器找到 company_id。
        """
        from hcp_cms.data.repositories import CaseLogRepository

        mgr = CaseManager(seeded_db.connection)
        first, _ = mgr.import_email(
            subject="薪資計算異常",
            body="客戶來信",
            sender_email="user@aseglobal.com",
        )
        # HCP 回覆：sender 為我方，to_recipients 為客戶（讓 Classifier 找到公司）
        mgr.import_email(
            subject="RE: 薪資計算異常",
            body="我方回覆內容",
            sender_email="staff@ares.com.tw",
            to_recipients=["user@aseglobal.com"],
        )
        logs = CaseLogRepository(seeded_db.connection).list_by_case(first.case_id)
        assert len(logs) == 1
        assert logs[0].direction == "HCP 回覆"

    def test_import_email_direction_client(self, seeded_db):
        """外部寄件者且無 RE: 前綴時，direction 應為 '客戶來信'。"""
        from hcp_cms.data.repositories import CaseLogRepository

        mgr = CaseManager(seeded_db.connection)
        first, _ = mgr.import_email(
            subject="薪資計算異常",
            body="第一封",
            sender_email="user@aseglobal.com",
        )
        mgr.import_email(
            subject="薪資計算異常",  # 同主旨，外部寄件者
            body="第二封客戶來信",
            sender_email="another@aseglobal.com",
        )
        logs = CaseLogRepository(seeded_db.connection).list_by_case(first.case_id)
        assert len(logs) == 1
        assert logs[0].direction == "客戶來信"
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_case_manager.py::TestImportEmail -v
```

預期：新增的 4 個測試 FAILED（`action` 仍回傳 `"created"` 而非 `"merged"`）。

- [ ] **Step 3: 修改 `case_manager.py` — 新增 import 與 `_detect_direction()`**

在 `src/hcp_cms/core/case_manager.py` 最頂部，修改 import 區段：

```python
"""High-level case management — create, update, status transitions."""

import re
import sqlite3
from datetime import datetime
from pathlib import Path

from hcp_cms.core.classifier import Classifier
from hcp_cms.core.thread_tracker import ThreadTracker
from hcp_cms.data.fts import FTSManager
from hcp_cms.data.models import Case, CaseLog
from hcp_cms.data.repositories import CaseLogRepository, CaseRepository
```

然後在 `_normalize_sent_time()` 函數之後（`class CaseManager:` 之前），新增：

```python
def _detect_direction(sender: str, subject: str) -> str:
    """判斷信件方向：優先看寄件者網域，其次看主旨前綴。"""
    sender_lower = sender.lower()
    if "@ares.com.tw" in sender_lower or "hcpservice" in sender_lower:
        return "HCP 回覆"
    if re.match(r'^(RE|FW|FWD|回覆|轉寄|答覆)\s*:', subject, re.IGNORECASE):
        return "HCP 回覆"
    return "客戶來信"
```

- [ ] **Step 4: 修改 `CaseManager.__init__()` — 新增 `_log_repo`**

在 `src/hcp_cms/core/case_manager.py` 的 `CaseManager.__init__()` 方法中，加入 `CaseLogRepository`：

```python
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._case_repo = CaseRepository(conn)
        self._log_repo = CaseLogRepository(conn)
        self._fts = FTSManager(conn)
        self._classifier = Classifier(conn)
        self._tracker = ThreadTracker(conn)
```

- [ ] **Step 5: 修改 `import_email()` — 加入 Find-or-Create 邏輯**

將 `src/hcp_cms/core/case_manager.py` 中的 `import_email()` 方法整體替換為：

```python
    def import_email(
        self,
        subject: str,
        body: str,
        sender_email: str = "",
        to_recipients: list[str] | None = None,
        sent_time: str | None = None,
        source_filename: str | None = None,
        progress_note: str | None = None,
    ) -> tuple[Case | None, str]:
        """匯入信件並建案（Find-or-Create）。

        若同公司、同主旨（去 RE:/FW: 前綴後相同）已有案件，
        則新增 CaseLog 並更新 reply_count，不另建案件（action='merged'）。
        否則走原有建案流程（action='created'）。

        Returns:
            (case, action) — action 為 'created' 或 'merged'
        """
        recipients = to_recipients or []

        # Find-or-Create：先以分類器取得 company_id
        classification = self._classifier.classify(subject, body, sender_email, recipients)
        company_id = classification.get("company_id")

        if company_id:
            clean = ThreadTracker.clean_subject(subject)
            existing = self._case_repo.find_by_company_and_subject(company_id, clean)
            if existing:
                direction = _detect_direction(sender_email, subject)
                log_time = (
                    _normalize_sent_time(sent_time)
                    or datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                )
                log = CaseLog(
                    log_id=self._log_repo.next_log_id(),
                    case_id=existing.case_id,
                    direction=direction,
                    content=body,
                    logged_at=log_time,
                )
                self._log_repo.insert(log)
                existing.reply_count += 1
                self._case_repo.update(existing)
                return existing, "merged"

        # 沒有 existing → 原有建案流程（不變）
        case = self.create_case(
            subject=subject,
            body=body,
            sender_email=sender_email,
            to_recipients=recipients,
            sent_time=sent_time,
            source_filename=source_filename,
            progress_note=progress_note,
        )
        return case, "created"
```

- [ ] **Step 6: 執行測試確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_case_manager.py -v
```

預期：全部測試 PASS（含既有 22 個 + 新增 4 個 = 26 個）。

- [ ] **Step 7: Commit**

```bash
git add src/hcp_cms/core/case_manager.py tests/unit/test_case_manager.py
git commit -m "feat: import_email() Find-or-Create — 同主旨自動整合為一個案件，加入方向判斷"
```

---

## Task 6: 設定頁「整合重複案件」按鈕

**Files:**
- Modify: `src/hcp_cms/ui/settings_view.py`

> 說明：在現有備份操作按鈕列加入「🔧 整合重複案件」按鈕；點擊後呼叫 `CaseMerger.merge_all_duplicates()`，依結果顯示成功或錯誤訊息。此功能無需自動化測試（純 UI slot）。

- [ ] **Step 1: 新增 `CaseMerger` import**

在 `src/hcp_cms/ui/settings_view.py` 現有 import 區段末尾加入：

```python
from hcp_cms.core.case_merger import CaseMerger
```

- [ ] **Step 2: 新增按鈕到備份操作列**

在 `_setup_ui()` 的備份按鈕區段（約第 101-112 行），找到以下程式碼：

```python
        btn_layout = QHBoxLayout()
        self._backup_now_btn = QPushButton("💾 立即備份")
        self._restore_btn = QPushButton("📦 還原")
        self._export_btn = QPushButton("📤 匯出")
        self._import_btn = QPushButton("📥 匯入合併")
        self._migrate_btn = QPushButton("🔄 舊 DB 遷移")
        btn_layout.addWidget(self._backup_now_btn)
        btn_layout.addWidget(self._restore_btn)
        btn_layout.addWidget(self._export_btn)
        btn_layout.addWidget(self._import_btn)
        btn_layout.addWidget(self._migrate_btn)
        backup_layout.addRow(btn_layout)
```

改為（加入 `_merge_duplicates_btn`）：

```python
        btn_layout = QHBoxLayout()
        self._backup_now_btn = QPushButton("💾 立即備份")
        self._restore_btn = QPushButton("📦 還原")
        self._export_btn = QPushButton("📤 匯出")
        self._import_btn = QPushButton("📥 匯入合併")
        self._migrate_btn = QPushButton("🔄 舊 DB 遷移")
        self._merge_duplicates_btn = QPushButton("🔧 整合重複案件")
        self._merge_duplicates_btn.clicked.connect(self._on_merge_duplicates)
        btn_layout.addWidget(self._backup_now_btn)
        btn_layout.addWidget(self._restore_btn)
        btn_layout.addWidget(self._export_btn)
        btn_layout.addWidget(self._import_btn)
        btn_layout.addWidget(self._migrate_btn)
        btn_layout.addWidget(self._merge_duplicates_btn)
        backup_layout.addRow(btn_layout)
```

- [ ] **Step 3: 新增 `_on_merge_duplicates()` slot**

在 `settings_view.py` 現有 slot 方法的適當位置（例如 `_on_backup_now()` 附近，或在檔案末尾）新增：

```python
    def _on_merge_duplicates(self) -> None:
        """整合資料庫中所有重複案件（相同公司 + 相同主旨）。"""
        if not self._conn:
            QMessageBox.warning(self, "整合重複案件", "資料庫未連線。")
            return
        try:
            deleted = CaseMerger(self._conn).merge_all_duplicates()
            if deleted == 0:
                QMessageBox.information(self, "整合重複案件", "目前無重複案件。")
            else:
                QMessageBox.information(
                    self, "整合重複案件", f"已整合 {deleted} 個重複案件。"
                )
        except Exception as e:
            QMessageBox.critical(self, "整合重複案件", f"整合失敗：{e}")
```

- [ ] **Step 4: 執行全部測試確認無破壞**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short
```

預期：全部 PASS。

- [ ] **Step 5: Lint 檢查**

```bash
.venv/Scripts/ruff.exe check src/ tests/
```

預期：無錯誤。

- [ ] **Step 6: Commit**

```bash
git add src/hcp_cms/ui/settings_view.py
git commit -m "feat: 設定頁新增整合重複案件按鈕，呼叫 CaseMerger.merge_all_duplicates()"
```

---

## 完成驗收

- [ ] **最終測試全跑**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v
```

預期：全部 PASS，無警告。

- [ ] **Lint 全跑**

```bash
.venv/Scripts/ruff.exe check src/ tests/
```

預期：無錯誤。
