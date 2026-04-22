from pathlib import Path

import pytest

from hcp_cms.core.case_manager import CaseManager
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import ClassificationRule, Company
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
        """5 筆孤兒案件（無公司），批次指定公司後應整併為 1 根 + 4 子。"""
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

        assert result["updated"] == 5

        cases = [repo.get_by_id(cid) for cid in case_ids]
        assert all(c.company_id == "C-CHI" for c in cases)

        root = min(cases, key=lambda c: c.sent_time or "")
        linked = [c for c in cases if c.case_id != root.case_id]
        assert all(c.linked_case_id == root.case_id for c in linked)
        assert result["merged"] == 4

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
