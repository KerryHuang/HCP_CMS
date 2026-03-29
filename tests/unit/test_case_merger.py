"""Unit tests for CaseMerger."""

from __future__ import annotations

from pathlib import Path

import pytest

from hcp_cms.core.case_merger import CaseMerger
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, CaseLog, Company
from hcp_cms.data.repositories import CaseLogRepository, CaseRepository, CompanyRepository


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


@pytest.fixture(autouse=True)
def seed_companies(db: DatabaseManager) -> None:
    """所有測試前先建立公司記錄（FK 約束需要）。"""
    co_repo = CompanyRepository(db.connection)
    co_repo.insert(Company(company_id="C001", name="公司甲", domain="c001.com"))
    co_repo.insert(Company(company_id="C002", name="公司乙", domain="c002.com"))


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

    def test_find_duplicate_groups_multi_prefix(self, db: DatabaseManager) -> None:
        """多層 RE: 前綴剝除後應歸為同一群組。"""
        repo = CaseRepository(db.connection)
        _insert_case(repo, "CS-2026-006", "薪資問題", "C001")
        _insert_case(repo, "CS-2026-007", "RE: RE: 薪資問題", "C001")

        merger = CaseMerger(db.connection)
        groups = merger.find_duplicate_groups()
        assert len(groups) == 1
        assert len(groups[0]) == 2


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
