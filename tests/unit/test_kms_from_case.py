# tests/unit/test_kms_from_case.py
"""測試從案件建立 KMS 條目與相似搜尋輔助函式。"""
import pytest
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, CaseLog
from hcp_cms.data.repositories import CaseRepository, CaseLogRepository
from hcp_cms.core.kms_engine import KMSEngine


@pytest.fixture
def db():
    mgr = DatabaseManager(":memory:")
    mgr.initialize()
    yield mgr.connection
    mgr.connection.close()


@pytest.fixture
def case_with_logs(db):
    """建立一個含客戶來信 + HCP 回覆的測試案件。"""
    case = Case(
        case_id="CS-TEST-001",
        subject="離職申請流程如何操作？",
        system_product="HCP",
        issue_type="OTH",
        error_type="人事資料管理",
        status="已回覆",
        sent_time="2026/04/01 09:00",
    )
    CaseRepository(db).insert(case)

    log_customer = CaseLog(
        log_id="LOG-20260401-001",
        case_id="CS-TEST-001",
        direction="客戶來信",
        content="請問離職申請的操作步驟為何？",
        logged_at="2026/04/01 09:00:00",
    )
    log_hcp = CaseLog(
        log_id="LOG-20260401-002",
        case_id="CS-TEST-001",
        direction="HCP 信件回覆",
        content="您好，離職申請請至人事管理 → 離職申請，填寫離職日期後送出即可。",
        logged_at="2026/04/01 10:00:00",
    )
    log_repo = CaseLogRepository(db)
    log_repo.insert(log_customer)
    log_repo.insert(log_hcp)
    return case


def test_build_qa_from_case_creates_pending(db, case_with_logs):
    """從案件建立 KMS 條目，預設狀態應為待審核。"""
    case = case_with_logs
    logs = CaseLogRepository(db).list_by_case(case.case_id)
    hcp_logs = [l for l in logs if l.direction in ("HCP 信件回覆", "HCP 線上回覆")]
    assert hcp_logs, "應有 HCP 回覆記錄"

    engine = KMSEngine(db)
    qa = engine.create_qa(
        question=case.subject,
        answer=hcp_logs[-1].content,
        system_product=case.system_product,
        issue_type=case.issue_type,
        error_type=case.error_type,
        source="case",
        source_case_id=case.case_id,
        status="待審核",
    )
    assert qa.qa_id.startswith("QA-")
    assert qa.status == "待審核"
    assert qa.source_case_id == "CS-TEST-001"
    assert qa.question == "離職申請流程如何操作？"
    assert "離職申請" in qa.answer


def test_search_similar_returns_empty_for_pending(db, case_with_logs):
    """待審核的 QA 不應出現在搜尋結果中。"""
    case = case_with_logs
    logs = CaseLogRepository(db).list_by_case(case.case_id)
    hcp_logs = [l for l in logs if l.direction in ("HCP 信件回覆", "HCP 線上回覆")]

    engine = KMSEngine(db)
    engine.create_qa(
        question=case.subject,
        answer=hcp_logs[-1].content,
        source="case",
        source_case_id=case.case_id,
        status="待審核",
    )
    results = engine.search("離職申請")
    assert results == [], "待審核 QA 不應出現在搜尋結果"


def test_search_similar_returns_approved(db):
    """已完成的 QA 應可被搜尋到。"""
    engine = KMSEngine(db)
    qa = engine.create_qa(
        question="離職申請流程如何操作？",
        answer="人事管理 → 離職申請，填寫離職日期後送出。",
        source="case",
        source_case_id=None,
        status="已完成",
    )
    results = engine.search("離職申請")
    assert any(r.qa_id == qa.qa_id for r in results)
