from pathlib import Path

import pytest

from hcp_cms.core.case_manager import CaseManager
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, ClassificationRule, Company
from hcp_cms.data.repositories import CaseRepository, CompanyRepository, RuleRepository


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def seeded_db(db: DatabaseManager) -> DatabaseManager:
    """DB with rules and companies for classification."""
    RuleRepository(db.connection).insert(
        ClassificationRule(rule_type="issue", pattern=r"bug|異常", value="BUG", priority=1)
    )
    RuleRepository(db.connection).insert(
        ClassificationRule(rule_type="error", pattern=r"薪資", value="薪資獎金計算", priority=1)
    )
    CompanyRepository(db.connection).insert(
        Company(company_id="C-ASE", name="日月光", domain="aseglobal.com")
    )
    return db


class TestCaseManager:
    def test_create_case(self, seeded_db):
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(
            subject="薪資計算異常",
            body="員工薪資有 bug",
            sender_email="user@aseglobal.com",
            sent_time="2026/03/20 09:00",
        )
        assert case.case_id.startswith("CS-")
        assert case.issue_type == "BUG"
        assert case.error_type == "薪資獎金計算"
        assert case.company_id == "C-ASE"

    def test_mark_replied(self, seeded_db):
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(subject="Test", body="body")
        mgr.mark_replied(case.case_id, "2026/03/20 12:00")

        updated = CaseRepository(seeded_db.connection).get_by_id(case.case_id)
        assert updated.status == "已回覆"
        assert updated.actual_reply == "2026/03/20 12:00"

    def test_mark_replied_increments_reply_count(self, seeded_db):
        """CS 標記已回覆時，reply_count 應 +1（參考舊版 _link_and_update_case）。"""
        mgr = CaseManager(seeded_db.connection)
        # create_case 初始 reply_count=1（第一封信已計入）
        case = mgr.create_case(subject="Test", body="body")
        assert case.reply_count == 1
        mgr.mark_replied(case.case_id)

        updated = CaseRepository(seeded_db.connection).get_by_id(case.case_id)
        assert updated.reply_count == 2

    def test_reopen_case(self, seeded_db):
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(subject="Test", body="body")
        mgr.mark_replied(case.case_id)   # reply_count: 1 → 2
        mgr.reopen_case(case.case_id, "客戶再次來信")

        updated = CaseRepository(seeded_db.connection).get_by_id(case.case_id)
        assert updated.status == "處理中"
        # reopen 本身不應再 +1（舊版 _reopen_existing_case 不修改 reply_count）
        assert updated.reply_count == 2
        assert "重開" in updated.notes

    def test_reply_count_no_double_count_on_reopen(self, seeded_db):
        """客戶回覆已回覆案件時：link_to_parent +1 即可，reopen 不應再 +1。"""
        mgr = CaseManager(seeded_db.connection)
        repo = CaseRepository(seeded_db.connection)

        # 建立根案件並回覆（create_case → reply_count=1，mark_replied → 2）
        root = mgr.create_case(
            subject="薪資問題", body="原始來信",
            sender_email="user@aseglobal.com",
        )
        mgr.mark_replied(root.case_id)  # reply_count: 1 → 2

        # 客戶再次來信（觸發 thread detection → link + reopen → root reply_count +1）
        child = mgr.create_case(
            subject="RE: 薪資問題", body="再次詢問",
            sender_email="user@aseglobal.com",
        )
        root_updated = repo.get_by_id(root.case_id)
        # mark_replied(+1) + link_to_parent(+1) = 3；不應因 reopen 又變 4
        assert root_updated.reply_count == 3
        assert child.linked_case_id == root.case_id

    def test_close_case(self, seeded_db):
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(subject="Test", body="body")
        mgr.close_case(case.case_id)

        updated = CaseRepository(seeded_db.connection).get_by_id(case.case_id)
        assert updated.status == "已完成"

    def test_create_case_strips_disclaimer_before_logging(self, seeded_db):
        """create_case 應在存入 case_log 前清除常見 disclaimer boilerplate。"""
        from hcp_cms.data.repositories import CaseLogRepository
        mgr = CaseManager(seeded_db.connection)
        body_with_disclaimer = (
            "客戶詢問加班費計算\n"
            "----- ASE Confidentiality Notice -----\n"
            "Disclaimer body\n"
            "----- ASE Confidentiality Notice -----\n"
        )
        case = mgr.create_case(subject="加班費問題", body=body_with_disclaimer)

        logs = CaseLogRepository(seeded_db.connection).list_by_case(case.case_id)
        assert len(logs) == 1
        assert "客戶詢問加班費計算" in logs[0].content
        assert "ASE Confidentiality Notice" not in logs[0].content

    def test_import_email_strips_disclaimer(self, seeded_db):
        """import_email 應在存入 case_log 前清除常見 disclaimer boilerplate（新建路徑）。"""
        from hcp_cms.data.repositories import CaseLogRepository
        mgr = CaseManager(seeded_db.connection)
        body = (
            "Dear Jill,\n"
            "請協助處理\n"
            '[附件檔 "X.docx" 已被 user/Kinsus 刪除]\n'
        )
        case, action = mgr.import_email(
            subject="新案", body=body, sender_email="user@aseglobal.com",
        )
        assert action == "created"

        logs = CaseLogRepository(seeded_db.connection).list_by_case(case.case_id)
        assert "Dear Jill" in logs[0].content
        assert "[附件檔" not in logs[0].content

    def test_dashboard_stats(self, seeded_db):
        mgr = CaseManager(seeded_db.connection)
        # Create cases
        c1 = mgr.create_case(subject="A", body="", sent_time="2026/03/10 09:00")
        c2 = mgr.create_case(subject="B", body="", sent_time="2026/03/15 10:00")
        mgr.create_case(subject="C", body="", sent_time="2026/03/20 14:00")

        mgr.mark_replied(c1.case_id, "2026/03/10 11:00")
        mgr.mark_replied(c2.case_id, "2026/03/16 10:00")

        stats = mgr.get_dashboard_stats(2026, 3)
        assert stats["total"] == 3
        assert stats["replied"] == 2
        assert stats["pending"] == 1  # c3 is still open
        assert stats["reply_rate"] == 66.7

    def test_frt_calculation(self, seeded_db):
        mgr = CaseManager(seeded_db.connection)
        c = mgr.create_case(subject="X", body="", sent_time="2026/03/20 09:00")
        mgr.mark_replied(c.case_id, "2026/03/20 12:00")

        stats = mgr.get_dashboard_stats(2026, 3)
        assert stats["avg_frt"] == 3.0  # 3 hours

    def test_frt_excludes_outliers(self, seeded_db):
        mgr = CaseManager(seeded_db.connection)
        c1 = mgr.create_case(subject="Normal", body="", sent_time="2026/03/10 09:00")
        mgr.mark_replied(c1.case_id, "2026/03/10 12:00")  # 3h

        c2 = mgr.create_case(subject="Outlier", body="", sent_time="2026/03/01 09:00")
        mgr.mark_replied(c2.case_id, "2026/03/31 09:00")  # 720h, excluded

        stats = mgr.get_dashboard_stats(2026, 3)
        assert stats["avg_frt"] == 3.0  # Only c1 counted

    def test_create_case_parses_filename_tags(self, seeded_db):
        """匯入 .msg 時，ISSUE#/handler/progress 應從檔名中解析。"""
        mgr = CaseManager(seeded_db.connection)
        filename = (
            "ISSUE_20260319_0017445_ 【欣興】表單開假問題"
            "(RD_JACKY)(待請JACKY安排修正).msg"
        )
        case = mgr.create_case(
            subject="RE: RE: 【欣興】表單開假問題",
            body="問題說明",
            sender_email="user@aseglobal.com",
            source_filename=filename,
        )
        assert case.notes and "ISSUE#0017445" in case.notes
        assert case.handler == "JACKY"
        assert case.progress == "待請JACKY安排修正"

    def test_create_case_email_subject_tags_when_no_filename(self, seeded_db):
        """無檔名時，仍能從 email 主旨本身解析 RD/進度標記。"""
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(
            subject="【問題】(RD_JACKY)(待確認)",
            body="",
        )
        assert case.handler == "JACKY"
        assert case.progress == "待確認"

    def test_thread_detection_links_cases(self, seeded_db):
        mgr = CaseManager(seeded_db.connection)
        c1 = mgr.create_case(
            subject="薪資問題", body="original",
            sender_email="user@aseglobal.com", sent_time="2026/03/20 09:00"
        )
        # Reply from same company, same subject
        c2 = mgr.create_case(
            subject="RE: 薪資問題", body="follow up",
            sender_email="user@aseglobal.com", sent_time="2026/03/21 10:00"
        )

        repo = CaseRepository(seeded_db.connection)
        child = repo.get_by_id(c2.case_id)
        assert child.linked_case_id == c1.case_id

    def test_create_case_with_progress_note(self, seeded_db):
        """create_case(progress_note=…) → case.progress 應寫入 progress_note。"""
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(
            subject="薪資問題",
            body="員工薪資異常",
            sender_email="user@aseglobal.com",
            progress_note="待與jacky確認組織代號",
        )
        assert case.progress == "待與jacky確認組織代號"

    def test_create_case_progress_note_overrides_subject_tag(self, seeded_db):
        """傳入 progress_note 時，應優先於主旨解析出的進度標記。"""
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(
            subject="問題(RD_JACKY)(待確認主旨進度)",
            body="內容",
            sender_email="user@aseglobal.com",
            progress_note="body進度優先",
        )
        assert case.progress == "body進度優先"

    def test_create_case_no_progress_note_uses_subject_tag(self, seeded_db):
        """progress_note 為 None 時，仍使用主旨/檔名解析的進度。"""
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(
            subject="問題(RD_JACKY)(待確認)",
            body="內容",
            sender_email="user@aseglobal.com",
            progress_note=None,
        )
        assert case.progress == "待確認"


    def test_create_case_fills_contact_person_from_sender(self, seeded_db):
        """create_case 未顯式傳 contact_person 時，應以 sender_email 作為預設值。

        目的：未知公司案件在報表中心可辨識來源（寄件者）。
        """
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(
            subject="未知公司來信",
            body="內容",
            sender_email="user@aseglobal.com",
        )
        assert case.contact_person == "user@aseglobal.com"

    def test_create_case_explicit_contact_person_overrides_sender(self, seeded_db):
        """顯式傳入 contact_person 時，應優先採用，不被 sender_email 覆蓋。"""
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(
            subject="手動建案",
            body="內容",
            sender_email="user@aseglobal.com",
            contact_person="張小姐",
        )
        assert case.contact_person == "張小姐"

    def test_create_case_no_sender_no_contact(self, seeded_db):
        """無 sender_email、無 contact_person 時，contact_person 為 None。"""
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(
            subject="無寄件者來源",
            body="",
        )
        assert case.contact_person is None

    def test_create_case_normalizes_iso_sent_time(self, seeded_db):
        """傳入 ISO 8601 格式 sent_time（含時區）應自動轉為 YYYY/MM/DD HH:MM。"""
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(
            subject="日期格式測試",
            body="測試",
            sender_email="user@aseglobal.com",
            sent_time="2026-03-17 09:34:03+08:00",
        )
        stored = CaseRepository(seeded_db.connection).get_by_id(case.case_id)
        assert stored.sent_time == "2026/03/17 09:34"

    def test_create_case_normalizes_iso_with_T(self, seeded_db):
        """ISO 8601 T 格式也應正規化。"""
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(
            subject="日期格式測試T",
            body="測試",
            sent_time="2026-03-17T14:22:05+00:00",
        )
        stored = CaseRepository(seeded_db.connection).get_by_id(case.case_id)
        assert stored.sent_time == "2026/03/17 14:22"

    def test_batch_assign_company_and_merge_links_cases(self, seeded_db):
        """5 筆孤兒案件（無公司），批次指定公司後 company_id 全更新。

        注意：subject-only fallback 修正後，create_case 建立 RE: 案件時已透過
        主旨比對自動串接至根案件（linked_case_id 在 create_case 時即設定），
        因此 batch_assign 時案件已串接，merged == 0。
        最終串接狀態（linked_case_id）在建案時即正確。
        """
        CompanyRepository(seeded_db.connection).insert(
            Company(company_id="C-CHI", name="群光", domain="chicony.com")
        )
        mgr = CaseManager(seeded_db.connection)
        repo = CaseRepository(seeded_db.connection)

        # 建立 5 筆孤兒案件，主旨去前綴後相同
        case_ids = []
        subjects = [
            "HCP 緊急聯絡人資訊 如何匯出",
            "RE: HCP 緊急聯絡人資訊 如何匯出",
            "RE: HCP 緊急聯絡人資訊 如何匯出",
            "RE: HCP 緊急聯絡人資訊 如何匯出",
            "RE: HCP 緊急聯絡人資訊 如何匯出",
        ]
        for i, subj in enumerate(subjects):
            case = mgr.create_case(
                subject=subj,
                body="測試內容",
                sent_time=f"2026/04/0{i+1} 10:00:00",
            )
            case_ids.append(case.case_id)

        result = mgr.batch_assign_company_and_merge(case_ids, "C-CHI")

        # 公司 ID 全部更新
        assert result["updated"] == 5
        cases = [repo.get_by_id(cid) for cid in case_ids]
        assert all(c.company_id == "C-CHI" for c in cases)

        # 案件已在 create_case 時串接，batch_assign 不重複計入 merged
        root = cases[0]  # 第一個建立的是根案件
        linked = [c for c in cases if c.case_id != root.case_id]
        assert all(c.linked_case_id == root.case_id for c in linked)
        # merged == 0：案件已於 create_case 時自動串接，batch 跳過已串接案件
        assert result["merged"] == 0

    def test_batch_assign_company_and_merge_skips_already_linked(self, seeded_db):
        """已有 linked_case_id 的案件不重複連結。"""
        CompanyRepository(seeded_db.connection).insert(
            Company(company_id="C-CHI", name="群光", domain="chicony.com")
        )
        mgr = CaseManager(seeded_db.connection)
        repo = CaseRepository(seeded_db.connection)

        c1 = mgr.create_case(subject="問題 X", body="", sent_time="2026/04/01 10:00:00")
        c2 = mgr.create_case(subject="問題 X", body="", sent_time="2026/04/02 10:00:00")
        c3 = mgr.create_case(subject="問題 X", body="", sent_time="2026/04/03 10:00:00")

        # c3 已手動連結至 c2（非正常狀況，但要能容忍）
        c3_obj = repo.get_by_id(c3.case_id)
        c3_obj.linked_case_id = c2.case_id
        repo.update(c3_obj)

        result = mgr.batch_assign_company_and_merge([c1.case_id, c2.case_id, c3.case_id], "C-CHI")

        assert result["updated"] == 3
        c3_after = repo.get_by_id(c3.case_id)
        # c3 已有 linked_case_id，不應被覆蓋
        assert c3_after.linked_case_id == c2.case_id

    def test_update_problem_fields_updates_case(self, db):
        """update_problem_fields 應正確更新問題整理 4 欄位。"""
        CompanyRepository(db.connection).insert(
            Company(company_id="acme", name="ACME", domain="acme.com")
        )
        repo = CaseRepository(db.connection)
        repo.insert(Case(case_id="CS-PF-001", subject="x", company_id="acme"))

        mgr = CaseManager(db.connection)
        mgr.update_problem_fields(
            case_id="CS-PF-001",
            problem_level="A",
            problem="加班費少算",
            cause="公式錯",
            solution="改公式",
        )

        case = repo.get_by_id("CS-PF-001")
        assert case is not None
        assert case.problem_level == "A"
        assert case.problem == "加班費少算"
        assert case.cause == "公式錯"
        assert case.solution == "改公式"

    def test_update_problem_fields_no_op_for_missing_case(self, db):
        """case_id 不存在時不應拋出例外，靜默回傳。"""
        mgr = CaseManager(db.connection)
        # 不應拋出例外，靜默處理
        mgr.update_problem_fields(
            case_id="CS-NOT-EXIST",
            problem_level="A",
            problem=None,
            cause=None,
            solution=None,
        )


class TestImportEmail:
    """測試 import_email() 智慧派送邏輯。"""

    @pytest.fixture
    def mgr(self, seeded_db):
        return CaseManager(seeded_db.connection)

    def test_customer_email_creates_case(self, mgr):
        """客戶發信 → 建立新案件，action 為 'created'。"""
        case, action = mgr.import_email(
            subject="薪資問題",
            body="員工薪資異常",
            sender_email="user@aseglobal.com",
            to_recipients=["hcpservice@ares.com.tw"],
            sent_time="2026/03/20 09:00",
        )
        assert action == "created"
        assert case is not None
        assert case.case_id.startswith("CS-")

    def test_our_reply_merges_into_existing_case(self, mgr, seeded_db):
        """我方回覆同主旨 → merged（action='merged'），不另建新案件，加入 CaseLog。"""
        parent, _ = mgr.import_email(
            subject="薪資計算問題",
            body="有異常",
            sender_email="user@aseglobal.com",
            to_recipients=["hcpservice@ares.com.tw"],
            sent_time="2026/03/20 09:00",
        )
        assert parent is not None

        # 我方回覆 → 合併入既有案件，action='merged'
        reply_case, action = mgr.import_email(
            subject="RE: 薪資計算問題",
            body="已處理",
            sender_email="hcpservice@ares.com.tw",
            to_recipients=["user@aseglobal.com"],
            sent_time="2026/03/20 10:00",
        )
        assert action == "merged"
        assert reply_case is not None
        assert reply_case.case_id == parent.case_id

        from hcp_cms.data.repositories import CaseLogRepository, CaseRepository
        # 案件總數仍為 1（不另建案）
        assert len(CaseRepository(seeded_db.connection).list_all()) == 1
        # CaseLog 應已新增（初始1筆 + 合併1筆 = 2筆），最後一筆 direction 為 HCP 信件回覆
        logs = CaseLogRepository(seeded_db.connection).list_by_case(parent.case_id)
        assert len(logs) == 2
        assert logs[-1].direction == "HCP 信件回覆"

    def test_our_reply_increments_reply_count(self, mgr, seeded_db):
        """我方每次回覆建案都應讓父案件 reply_count +1（由 link_to_parent 計算）。"""
        parent, _ = mgr.import_email(
            subject="問題追蹤",
            body="內容",
            sender_email="user@aseglobal.com",
            to_recipients=["hcpservice@ares.com.tw"],
            sent_time="2026/03/20 09:00",
        )

        mgr.import_email(
            subject="RE: 問題追蹤",
            body="第一次回覆",
            sender_email="hcpservice@ares.com.tw",
            to_recipients=["user@aseglobal.com"],
            sent_time="2026/03/20 10:00",
        )
        mgr.import_email(
            subject="RE: 問題追蹤",
            body="第二次回覆",
            sender_email="hcpservice@ares.com.tw",
            to_recipients=["user@aseglobal.com"],
            sent_time="2026/03/21 10:00",
        )

        from hcp_cms.data.repositories import CaseRepository
        updated = CaseRepository(seeded_db.connection).get_by_id(parent.case_id)
        # 初始1 + 第一次回覆+1 + 第二次回覆+1 = 3
        assert updated.reply_count == 3

    def test_our_reply_no_parent_still_creates_case(self, mgr):
        """我方回覆找不到父案件 → 仍建案（action='created'），不略過。"""
        case, action = mgr.import_email(
            subject="RE: 完全不存在的案件",
            body="回覆",
            sender_email="hcpservice@ares.com.tw",
            to_recipients=["user@aseglobal.com"],
            sent_time="2026/03/20 10:00",
        )
        assert action == "created"
        assert case is not None

    def test_import_email_passes_progress_note_to_case(self, mgr, seeded_db):
        """import_email(progress_note=…) → 建案後 case.progress 正確。"""
        case, action = mgr.import_email(
            subject="組織異動問題",
            body="說明",
            sender_email="user@aseglobal.com",
            to_recipients=["hcpservice@ares.com.tw"],
            progress_note="待確認人天費用",
        )
        assert action == "created"
        assert case is not None
        assert case.progress == "待確認人天費用"

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

        # 確認 CaseLog 已新增（初始1筆 + 合併1筆 = 2筆）
        logs = CaseLogRepository(seeded_db.connection).list_by_case(original_case_id)
        assert len(logs) == 2
        assert logs[-1].content == "第二封內容"

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
        # 初始1筆（客戶來信）+ 合併1筆（HCP 信件回覆）= 2筆
        logs = CaseLogRepository(seeded_db.connection).list_by_case(first.case_id)
        assert len(logs) == 2
        assert logs[-1].direction == "HCP 信件回覆"

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
        # 初始1筆（客戶來信）+ 合併1筆（客戶來信）= 2筆
        logs = CaseLogRepository(seeded_db.connection).list_by_case(first.case_id)
        assert len(logs) == 2
        assert logs[-1].direction == "客戶來信"

    def test_hcp_reply_with_close_keyword_closes_thread(self, seeded_db):
        """HCP 回覆主旨含 (回覆結案) → 整串 thread 案件 status 改為「已完成」。

        情境：客戶來信建立案件 A，後續 HCP 回覆主旨末端追加 (回覆結案)。
        應將同 thread 的所有案件（A 與其他 linked 案件）一併設為「已完成」。
        """
        from hcp_cms.data.repositories import CaseRepository

        mgr = CaseManager(seeded_db.connection)
        repo = CaseRepository(seeded_db.connection)

        # 客戶來信建案 A
        case_a, _ = mgr.import_email(
            subject="留停轉離職作業詢問",
            body="請問流程",
            sender_email="user@aseglobal.com",
            to_recipients=["hcpservice@ares.com.tw"],
            sent_time="2026/05/01 09:00",
        )
        # 客戶後續再來信，被串成同 thread（不同 case 但 linked_case_id=A）
        case_b, _ = mgr.import_email(
            subject="RE: 留停轉離職作業詢問 補充",
            body="補充資料",
            sender_email="user@aseglobal.com",
            to_recipients=["hcpservice@ares.com.tw"],
            sent_time="2026/05/02 09:00",
        )

        # HCP 回覆並標記結案
        mgr.import_email(
            subject="RE: 留停轉離職作業詢問(回覆結案)",
            body="已處理",
            sender_email="hcpservice@ares.com.tw",
            to_recipients=["user@aseglobal.com"],
            sent_time="2026/05/03 10:00",
        )

        # A 與 B 應全部變「已完成」
        a_after = repo.get_by_id(case_a.case_id)
        b_after = repo.get_by_id(case_b.case_id)
        assert a_after.status == "已完成"
        assert b_after.status == "已完成"

    def test_hcp_reply_without_close_keyword_does_not_close(self, seeded_db):
        """HCP 一般回覆（無 (回覆結案)）不應觸發自動結案。"""
        from hcp_cms.data.repositories import CaseRepository

        mgr = CaseManager(seeded_db.connection)
        repo = CaseRepository(seeded_db.connection)
        case_a, _ = mgr.import_email(
            subject="薪資問題",
            body="請問薪資",
            sender_email="user@aseglobal.com",
            to_recipients=["hcpservice@ares.com.tw"],
        )
        mgr.import_email(
            subject="RE: 薪資問題",
            body="處理中",
            sender_email="hcpservice@ares.com.tw",
            to_recipients=["user@aseglobal.com"],
        )
        after = repo.get_by_id(case_a.case_id)
        assert after.status != "已完成"

    def test_customer_email_with_close_keyword_does_not_close(self, seeded_db):
        """關鍵字僅由 HCP 端觸發，客戶來信含 (回覆結案) 不應結案。"""
        from hcp_cms.data.repositories import CaseRepository

        mgr = CaseManager(seeded_db.connection)
        repo = CaseRepository(seeded_db.connection)
        # 客戶誤打 (回覆結案) — 例如手動轉貼了標題
        case_a, _ = mgr.import_email(
            subject="薪資問題(回覆結案)",
            body="客戶誤打",
            sender_email="user@aseglobal.com",
            to_recipients=["hcpservice@ares.com.tw"],
        )
        after = repo.get_by_id(case_a.case_id)
        assert after.status != "已完成"

    def test_close_keyword_must_be_in_subject_not_body(self, seeded_db):
        """關鍵字僅看主旨，body 含 (回覆結案) 不應觸發。"""
        from hcp_cms.data.repositories import CaseRepository

        mgr = CaseManager(seeded_db.connection)
        repo = CaseRepository(seeded_db.connection)
        case_a, _ = mgr.import_email(
            subject="薪資問題",
            body="客戶提到的關鍵字 (回覆結案) 在內文",
            sender_email="user@aseglobal.com",
            to_recipients=["hcpservice@ares.com.tw"],
        )
        # HCP 回覆，body 含 (回覆結案) 但主旨不含
        mgr.import_email(
            subject="RE: 薪資問題",
            body="(回覆結案) — 但這是寫在 body",
            sender_email="hcpservice@ares.com.tw",
            to_recipients=["user@aseglobal.com"],
        )
        after = repo.get_by_id(case_a.case_id)
        assert after.status != "已完成"

    def test_close_keyword_strict_match_with_parens(self, seeded_db):
        """嚴格匹配 (回覆結案) — 不含括號的「回覆結案」不觸發。"""
        from hcp_cms.data.repositories import CaseRepository

        mgr = CaseManager(seeded_db.connection)
        repo = CaseRepository(seeded_db.connection)
        case_a, _ = mgr.import_email(
            subject="薪資問題",
            body="",
            sender_email="user@aseglobal.com",
            to_recipients=["hcpservice@ares.com.tw"],
        )
        # HCP 回覆，主旨僅含「回覆結案」（無括號），不應結案
        mgr.import_email(
            subject="RE: 薪資問題 回覆結案",
            body="",
            sender_email="hcpservice@ares.com.tw",
            to_recipients=["user@aseglobal.com"],
        )
        after = repo.get_by_id(case_a.case_id)
        assert after.status != "已完成"

    def test_import_email_merged_log_time_format_with_seconds(self, seeded_db):
        """sent_time 已有秒數時，logged_at 不應再拼接 :00。"""
        from hcp_cms.data.repositories import CaseLogRepository

        mgr = CaseManager(seeded_db.connection)
        first, _ = mgr.import_email(
            subject="薪資計算異常",
            body="第一封",
            sender_email="user@aseglobal.com",
            sent_time="2026/03/01 09:00:00",
        )
        _, action = mgr.import_email(
            subject="RE: 薪資計算異常",
            body="第二封",
            sender_email="user@aseglobal.com",
            sent_time="2026/03/02 10:30:45",  # has seconds
        )
        assert action == "merged"
        # 初始1筆 + 合併1筆 = 2筆；最後一筆時間格式應有秒數
        logs = CaseLogRepository(seeded_db.connection).list_by_case(first.case_id)
        assert len(logs) == 2
        # Should be "2026/03/02 10:30:45" NOT "2026/03/02 10:30:45:00"
        assert logs[-1].logged_at == "2026/03/02 10:30:45"


class TestManualLinkCases:
    """手動串接案件（任選兩筆以上，最早當 root）。

    手動串接 = 使用者明確選擇 → 強制覆蓋既有 linked_case_id。
    主要用於 subjects_match 因主旨中段差異無法自動匹配的情境。
    """

    def test_link_two_cases_by_sent_time(self, seeded_db):
        """兩筆案件：後建立者（sent_time 較晚）串接到先建立者。"""
        mgr = CaseManager(seeded_db.connection)
        repo = CaseRepository(seeded_db.connection)
        early = mgr.create_case(subject="A", body="x", sent_time="2026/03/10 09:00")
        late = mgr.create_case(subject="B", body="y", sent_time="2026/03/15 09:00")

        result = mgr.manual_link_cases([late.case_id, early.case_id])

        assert result == {"linked": 1, "already": 0}
        assert repo.get_by_id(late.case_id).linked_case_id == early.case_id
        assert repo.get_by_id(early.case_id).linked_case_id is None

    def test_link_three_cases_all_point_to_earliest(self, seeded_db):
        """三筆案件：全部串到最早，linked_case_id 都指向 root。"""
        mgr = CaseManager(seeded_db.connection)
        repo = CaseRepository(seeded_db.connection)
        c1 = mgr.create_case(subject="A", body="x", sent_time="2026/03/10 09:00")
        c2 = mgr.create_case(subject="B", body="y", sent_time="2026/03/12 09:00")
        c3 = mgr.create_case(subject="C", body="z", sent_time="2026/03/15 09:00")

        # 傳入順序刻意打亂，驗證內部會排序
        result = mgr.manual_link_cases([c3.case_id, c1.case_id, c2.case_id])

        assert result == {"linked": 2, "already": 0}
        assert repo.get_by_id(c2.case_id).linked_case_id == c1.case_id
        assert repo.get_by_id(c3.case_id).linked_case_id == c1.case_id

    def test_already_linked_to_same_root_counts_as_already(self, seeded_db):
        """已串到目標 root 的案件不重複串接，計入 already。"""
        mgr = CaseManager(seeded_db.connection)
        repo = CaseRepository(seeded_db.connection)
        root = mgr.create_case(subject="Root", body="x", sent_time="2026/03/10 09:00")
        child1 = mgr.create_case(subject="C1", body="y", sent_time="2026/03/12 09:00")
        child2 = mgr.create_case(subject="C2", body="z", sent_time="2026/03/15 09:00")
        # 預先把 child1 串到 root
        mgr.manual_link_cases([child1.case_id, root.case_id])

        # 重複呼叫：child1 已串到 root → already；child2 新串 → linked
        result = mgr.manual_link_cases([root.case_id, child1.case_id, child2.case_id])

        assert result == {"linked": 1, "already": 1}
        assert repo.get_by_id(child1.case_id).linked_case_id == root.case_id
        assert repo.get_by_id(child2.case_id).linked_case_id == root.case_id

    def test_overrides_existing_link_to_different_root(self, seeded_db):
        """已串到別 root 的案件 → 強制覆蓋到新 root（不再 skip）。"""
        mgr = CaseManager(seeded_db.connection)
        repo = CaseRepository(seeded_db.connection)
        old_root = mgr.create_case(subject="X", body="x", sent_time="2026/03/01 09:00")
        new_root = mgr.create_case(subject="Y", body="y", sent_time="2026/03/05 09:00")
        child = mgr.create_case(subject="Z", body="z", sent_time="2026/03/10 09:00")
        # 先把 child 串到 old_root
        mgr.manual_link_cases([child.case_id, old_root.case_id])
        assert repo.get_by_id(child.case_id).linked_case_id == old_root.case_id

        # 把 child 改串到 new_root
        result = mgr.manual_link_cases([child.case_id, new_root.case_id])

        assert result == {"linked": 1, "already": 0}
        assert repo.get_by_id(child.case_id).linked_case_id == new_root.case_id

    def test_increments_root_reply_count(self, seeded_db):
        """串接後，root 的 reply_count 應依新串接的筆數累加。"""
        mgr = CaseManager(seeded_db.connection)
        repo = CaseRepository(seeded_db.connection)
        root = mgr.create_case(subject="A", body="x", sent_time="2026/03/10 09:00")
        c2 = mgr.create_case(subject="B", body="y", sent_time="2026/03/12 09:00")
        c3 = mgr.create_case(subject="C", body="z", sent_time="2026/03/15 09:00")
        # create_case 初始 reply_count=1
        assert repo.get_by_id(root.case_id).reply_count == 1

        mgr.manual_link_cases([root.case_id, c2.case_id, c3.case_id])

        # root: 1 (初始) + 2 (兩筆串接) = 3
        assert repo.get_by_id(root.case_id).reply_count == 3

    def test_empty_or_single_case_is_noop(self, seeded_db):
        """空 list 或單筆 → 安全回傳 0/0，不拋例外。"""
        mgr = CaseManager(seeded_db.connection)
        case = mgr.create_case(subject="A", body="x")

        assert mgr.manual_link_cases([]) == {"linked": 0, "already": 0}
        assert mgr.manual_link_cases([case.case_id]) == {"linked": 0, "already": 0}

    def test_nonexistent_case_id_is_ignored(self, seeded_db):
        """不存在的 case_id 安全略過，不影響其他案件串接。"""
        mgr = CaseManager(seeded_db.connection)
        repo = CaseRepository(seeded_db.connection)
        early = mgr.create_case(subject="A", body="x", sent_time="2026/03/10 09:00")
        late = mgr.create_case(subject="B", body="y", sent_time="2026/03/15 09:00")

        result = mgr.manual_link_cases([early.case_id, late.case_id, "CS-9999-9999"])

        assert result == {"linked": 1, "already": 0}
        assert repo.get_by_id(late.case_id).linked_case_id == early.case_id

    def test_link_to_existing_root_chain(self, seeded_db):
        """若選的「最早」案件本身已串接到別人，應追溯到 root 而非當新 root。"""
        mgr = CaseManager(seeded_db.connection)
        repo = CaseRepository(seeded_db.connection)
        real_root = mgr.create_case(subject="A", body="x", sent_time="2026/03/01 09:00")
        mid = mgr.create_case(subject="B", body="y", sent_time="2026/03/10 09:00")
        mgr.manual_link_cases([mid.case_id, real_root.case_id])
        # 此時 mid.linked_case_id == real_root.case_id
        new_case = mgr.create_case(subject="C", body="z", sent_time="2026/03/15 09:00")

        # 選取 mid + new_case：mid 雖是兩者中較早，但已串到 real_root
        # 應追溯 mid 的 root → real_root，把 new_case 串到 real_root
        result = mgr.manual_link_cases([mid.case_id, new_case.case_id])

        assert result["linked"] == 1
        assert repo.get_by_id(new_case.case_id).linked_case_id == real_root.case_id
