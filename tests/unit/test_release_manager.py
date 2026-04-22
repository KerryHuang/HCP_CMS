"""ReleaseDetector / ReleaseManager 單元測試。"""
import pytest
from hcp_cms.data.database import DatabaseManager
from hcp_cms.core.release_manager import ReleaseDetector, ReleaseManager


@pytest.fixture
def conn(tmp_path):
    db = DatabaseManager(tmp_path / "test.db")
    db.initialize()
    yield db.connection
    db.close()


class TestReleaseDetector:
    def test_detects_confirm_and_ship(self, conn):
        det = ReleaseDetector(conn)
        body = "分配給: jill\n客戶回覆測試ok，請安排出貨，謝謝。"
        result = det.detect(body)
        assert result is not None
        assert result["assignee"] == "jill"
        assert "安排出貨" in result["note"]

    def test_returns_none_when_missing_ship_keyword(self, conn):
        det = ReleaseDetector(conn)
        body = "分配給: jill\n測試OK，功能正常。"
        assert det.detect(body) is None

    def test_returns_none_when_missing_confirm_keyword(self, conn):
        det = ReleaseDetector(conn)
        body = "分配給: jill\n請安排出貨。"
        assert det.detect(body) is None

    def test_assignee_optional(self, conn):
        det = ReleaseDetector(conn)
        body = "測試OK，安排出貨。"
        result = det.detect(body)
        assert result is not None
        assert result["assignee"] is None

    def test_multiline_assignee(self, conn):
        det = ReleaseDetector(conn)
        body = "分配給:        jill\n測試ok 安排出貨"
        result = det.detect(body)
        assert result["assignee"] == "jill"

    def test_mantis_commenter_as_assignee(self, conn):
        det = ReleaseDetector(conn)
        body = "(0039843) joywu (開發者) - 2026-04-21 17:07\n客戶回覆測試ok，請安排出貨，謝謝。"
        result = det.detect(body)
        assert result is not None
        assert result["assignee"] == "joywu"

    def test_assignee_format_priority(self, conn):
        """分配給格式優先於 Mantis 留言格式。"""
        det = ReleaseDetector(conn)
        body = "(0039843) joywu (開發者) - 2026-04-21 17:07\n分配給: jill\n測試ok，安排出貨。"
        result = det.detect(body)
        assert result["assignee"] == "jill"

    def test_note_includes_mantis_commenter_context(self, conn):
        """Mantis 留言格式時，note 應包含留言人行以提供完整脈絡。"""
        det = ReleaseDetector(conn)
        body = (
            "----------------------------------------------------------------------\n"
            "(0039843) joywu (開發者) - 2026-04-21 17:07\n"
            "https://172.18.2.1/mantis/view.php?id=17095#c39843\n"
            "客戶回覆測試ok，請安排出貨，謝謝。\n"
        )
        result = det.detect(body)
        assert result is not None
        assert "(0039843) joywu (開發者)" in result["note"]
        assert "客戶回覆測試ok" in result["note"]


class TestReleaseManager:
    def test_detect_and_record_creates_item(self, conn):
        mgr = ReleaseManager(conn)
        mgr.detect_and_record(
            body="分配給: jill\n客戶測試OK，安排出貨",
            case_id="CS-2026-001",
            mantis_ticket_id="0017095",
            client_name="華碩電腦",
            month_str="202604",
        )
        from hcp_cms.data.repositories import ReleaseItemRepository
        items = ReleaseItemRepository(conn).list_by_month("202604")
        assert len(items) == 1
        assert items[0].assignee == "jill"
        assert items[0].mantis_ticket_id == "0017095"

    def test_detect_and_record_no_match_does_nothing(self, conn):
        mgr = ReleaseManager(conn)
        mgr.detect_and_record(
            body="一般諮詢信件",
            case_id="CS-2026-002",
            mantis_ticket_id=None,
            client_name="測試公司",
            month_str="202604",
        )
        from hcp_cms.data.repositories import ReleaseItemRepository
        items = ReleaseItemRepository(conn).list_by_month("202604")
        assert len(items) == 0
