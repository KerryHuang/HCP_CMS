"""Tests for data models."""

from hcp_cms.data.models import (
    Case,
    CaseMantisLink,
    ClassificationRule,
    Company,
    MantisTicket,
    ProcessedFile,
    QAKnowledge,
    Synonym,
)


class TestCase:
    def test_create_case_with_defaults(self):
        case = Case(case_id="CS-2026-001", subject="Test issue")
        assert case.case_id == "CS-2026-001"
        assert case.status == "處理中"
        assert case.priority == "中"
        assert case.replied == "否"
        assert case.reply_count == 0
        assert case.source == "email"

    def test_case_is_open(self):
        case = Case(case_id="CS-2026-001", subject="Test")
        assert case.is_open is True
        case.status = "已完成"
        assert case.is_open is False
        case.status = "Closed"
        assert case.is_open is False

    def test_case_is_overdue_sla(self):
        case = Case(
            case_id="CS-2026-001",
            subject="Test",
            priority="高",
            sent_time="2026/03/20 09:00",
            replied="否",
        )
        assert case.sla_hours == 4

    def test_case_sla_hours_by_priority(self):
        normal = Case(case_id="CS-2026-001", subject="Test", priority="中")
        assert normal.sla_hours == 24

        high = Case(case_id="CS-2026-002", subject="Test", priority="高")
        assert high.sla_hours == 4

    def test_case_sla_hours_custom(self):
        custom = Case(
            case_id="CS-2026-003",
            subject="Test",
            issue_type="客制需求",
        )
        assert custom.sla_hours == 48


class TestCompany:
    def test_create_company(self):
        company = Company(
            company_id="COMP-001",
            name="日月光集團",
            domain="aseglobal.com",
        )
        assert company.company_id == "COMP-001"
        assert company.name == "日月光集團"
        assert company.domain == "aseglobal.com"
        assert company.alias is None


class TestQAKnowledge:
    def test_create_qa(self):
        qa = QAKnowledge(
            qa_id="QA-202603-001",
            question="如何計算薪資？",
            answer="進入薪資模組...",
        )
        assert qa.qa_id == "QA-202603-001"
        assert qa.source == "manual"


class TestMantisTicket:
    def test_create_ticket(self):
        ticket = MantisTicket(ticket_id="15562", summary="加班費計算")
        assert ticket.ticket_id == "15562"
        assert ticket.status is None


class TestClassificationRule:
    def test_create_rule(self):
        rule = ClassificationRule(
            rule_type="issue",
            pattern=r"bug|錯誤|異常",
            value="BUG",
            priority=1,
        )
        assert rule.enabled is True
        assert rule.rule_id is None


class TestProcessedFile:
    def test_create_processed_file(self):
        pf = ProcessedFile(file_hash="abc123", filename="test.msg")
        assert pf.file_hash == "abc123"
        assert pf.message_id is None


class TestSynonym:
    def test_create_synonym(self):
        syn = Synonym(word="薪水", synonym="薪資", group_name="薪資相關")
        assert syn.word == "薪水"
        assert syn.id is None


class TestCaseMantisLink:
    def test_create_link(self):
        link = CaseMantisLink(case_id="CS-2026-001", ticket_id="15562")
        assert link.case_id == "CS-2026-001"
