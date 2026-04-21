"""ReleaseItemRepository / ReleaseKeywordRepository 單元測試。"""
import sqlite3
import pytest
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.repositories import ReleaseItemRepository, ReleaseKeywordRepository
from hcp_cms.data.models import ReleaseItem, ReleaseKeyword


@pytest.fixture
def conn(tmp_path):
    db = DatabaseManager(tmp_path / "test.db")
    db.initialize()
    yield db.connection
    db.close()


class TestReleaseKeywordRepository:
    def test_list_all_returns_defaults(self, conn):
        repo = ReleaseKeywordRepository(conn)
        kws = repo.list_all()
        assert any(k.keyword == "測試ok" for k in kws)
        assert any(k.ktype == "ship" for k in kws)

    def test_insert_and_delete(self, conn):
        repo = ReleaseKeywordRepository(conn)
        kw = ReleaseKeyword(keyword="客戶確認", ktype="confirm")
        new_id = repo.insert(kw)
        assert new_id > 0
        all_kws = repo.list_all()
        assert any(k.id == new_id for k in all_kws)
        repo.delete(new_id)
        assert not any(k.id == new_id for k in repo.list_all())


class TestReleaseItemRepository:
    def test_insert_and_get(self, conn):
        repo = ReleaseItemRepository(conn)
        item = ReleaseItem(
            case_id="CS-2026-001",
            mantis_ticket_id="0017095", assignee="jill",
            client_name="華碩電腦", note="測試OK，安排出貨",
            month_str="202604",
        )
        new_id = repo.insert(item)
        assert new_id > 0

    def test_list_by_month(self, conn):
        repo = ReleaseItemRepository(conn)
        item = ReleaseItem(
            case_id="CS-2026-002",
            mantis_ticket_id=None, assignee="jill",
            client_name="測試公司", note="請出貨",
            month_str="202604",
        )
        repo.insert(item)
        results = repo.list_by_month("202604")
        assert len(results) >= 1
        assert results[0].month_str == "202604"

    def test_mark_released(self, conn):
        repo = ReleaseItemRepository(conn)
        item = ReleaseItem(
            case_id="CS-2026-003",
            month_str="202604",
        )
        new_id = repo.insert(item)
        repo.mark_released(new_id)
        results = repo.list_by_month("202604")
        target = next(r for r in results if r.id == new_id)
        assert target.status == "已發布"
