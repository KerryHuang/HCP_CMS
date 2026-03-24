"""整合測試：.MSG 對話串 → KMS 待審核 → 審核通過 → 搜尋可找到。"""

from pathlib import Path

import pytest

from hcp_cms.core.kms_engine import KMSEngine
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.repositories import QARepository
from hcp_cms.services.mail.base import RawEmail
from hcp_cms.services.mail.msg_reader import MSGReader


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def kms(db: DatabaseManager) -> KMSEngine:
    return KMSEngine(db.connection)


class TestMsgQAExtractionIntegration:
    def test_完整流程_匯入到搜尋(self, kms):
        body = (
            "感謝您的詢問，薪資計算方式請參考系統設定中的薪資模組。\n\n"
            "From: customer@clientco.com\n"
            "Sent: 2026-03-20\n"
            "To: hcpservice@ares.com.tw\n"
            "Subject: 請問薪資如何計算\n\n"
            "請問薪資如何計算？"
        )
        ta, tq = MSGReader._split_thread(body)
        raw = RawEmail(
            sender="hcpservice@ares.com.tw",
            subject="Re: 請問薪資如何計算",
            body=body,
            thread_answer=ta,
            thread_question=tq,
        )

        # 1. 抽取 → 待審核，不進 FTS
        qa = kms.extract_qa_from_email(raw, case_id=None)
        assert qa is not None and qa.status == "待審核"
        assert all(r.qa_id != qa.qa_id for r in kms.search("薪資"))

        # 2. 出現在待審核列表
        assert any(p.qa_id == qa.qa_id for p in kms.list_pending())

        # 3. 儲存草稿不進 FTS
        kms.update_qa(qa.qa_id, question="薪資如何計算")
        assert all(r.qa_id != qa.qa_id for r in kms.search("薪資"))
        assert QARepository(kms._conn).get_by_id(qa.qa_id).status == "待審核"

        # 4. 審核通過
        approved = kms.approve_qa(qa.qa_id, answer="請參考薪資模組")
        assert approved is not None and approved.status == "已完成"

        # 5. 搜尋可找到
        assert any(r.qa_id == qa.qa_id for r in kms.search("薪資"))

        # 6. 不再在待審核列表
        assert all(p.qa_id != qa.qa_id for p in kms.list_pending())

    def test_無_thread_question_不建立_QA(self, kms):
        raw = RawEmail(sender="user@ares.com.tw", subject="test", body="沒有對話串")
        assert kms.extract_qa_from_email(raw) is None
        assert len(kms.list_pending()) == 0

    def test_export_excel_排除待審核(self, kms, tmp_path):
        raw = RawEmail(thread_question="待審問題", thread_answer="待審回覆")
        kms.extract_qa_from_email(raw)
        kms.create_qa(question="已完成問題", answer="已完成回覆", status="已完成")
        path = kms.export_to_excel(tmp_path / "out.xlsx")
        import openpyxl
        wb = openpyxl.load_workbook(str(path))
        questions = [r[1] for r in wb.active.iter_rows(min_row=2, values_only=True) if r[1]]
        assert "已完成問題" in questions
        assert "待審問題" not in questions
