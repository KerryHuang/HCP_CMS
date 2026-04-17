"""PatchRepository 單元測試。"""
import sqlite3
import pytest
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import PatchIssue, PatchRecord
from hcp_cms.data.repositories import PatchRepository


@pytest.fixture
def conn():
    db = DatabaseManager(":memory:")
    db.initialize()
    yield db.connection
    db.connection.close()


class TestPatchRepository:
    def test_insert_and_get_patch(self, conn):
        repo = PatchRepository(conn)
        patch = PatchRecord(type="single", patch_dir="C:/test")
        patch_id = repo.insert_patch(patch)
        result = repo.get_patch_by_id(patch_id)
        assert result is not None
        assert result.type == "single"
        assert result.patch_dir == "C:/test"
        assert result.status == "in_progress"

    def test_update_patch_status(self, conn):
        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="monthly", month_str="202604"))
        repo.update_patch_status(pid, "completed")
        assert repo.get_patch_by_id(pid).status == "completed"

    def test_insert_and_list_issues(self, conn):
        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="single"))
        issue = PatchIssue(patch_id=pid, issue_no="0015659", issue_type="BugFix", region="TW",
                           description="測試說明", sort_order=1)
        repo.insert_issue(issue)
        issues = repo.list_issues_by_patch(pid)
        assert len(issues) == 1
        assert issues[0].issue_no == "0015659"
        assert issues[0].region == "TW"

    def test_update_issue(self, conn):
        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="single"))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="0015659"))
        issue = repo.list_issues_by_patch(pid)[0]
        issue.description = "已修改說明"
        repo.update_issue(issue)
        updated = repo.list_issues_by_patch(pid)[0]
        assert updated.description == "已修改說明"

    def test_delete_issue(self, conn):
        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="single"))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="0015659"))
        issues = repo.list_issues_by_patch(pid)
        repo.delete_issue(issues[0].issue_id)
        assert repo.list_issues_by_patch(pid) == []

    def test_list_issues_sorted_by_sort_order(self, conn):
        repo = PatchRepository(conn)
        pid = repo.insert_patch(PatchRecord(type="monthly"))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="BBB", sort_order=2))
        repo.insert_issue(PatchIssue(patch_id=pid, issue_no="AAA", sort_order=1))
        issues = repo.list_issues_by_patch(pid)
        assert issues[0].issue_no == "AAA"
        assert issues[1].issue_no == "BBB"
