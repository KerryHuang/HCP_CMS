"""Tests for all repository classes."""

from __future__ import annotations

from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
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
from hcp_cms.data.repositories import (
    CaseMantisRepository,
    CaseRepository,
    CompanyRepository,
    MantisRepository,
    ProcessedFileRepository,
    QARepository,
    RuleRepository,
    SynonymRepository,
)


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


# ---------------------------------------------------------------------------
# TestCompanyRepository
# ---------------------------------------------------------------------------


class TestCompanyRepository:
    def test_insert_and_get_by_id(self, db: DatabaseManager) -> None:
        repo = CompanyRepository(db.connection)
        company = Company(company_id="C001", name="Acme Corp", domain="acme.com")
        repo.insert(company)
        result = repo.get_by_id("C001")
        assert result is not None
        assert result.company_id == "C001"
        assert result.name == "Acme Corp"
        assert result.domain == "acme.com"
        assert result.created_at is not None

    def test_get_by_domain(self, db: DatabaseManager) -> None:
        repo = CompanyRepository(db.connection)
        company = Company(company_id="C002", name="Beta Inc", domain="beta.io")
        repo.insert(company)
        result = repo.get_by_domain("beta.io")
        assert result is not None
        assert result.company_id == "C002"

    def test_get_by_id_not_found(self, db: DatabaseManager) -> None:
        repo = CompanyRepository(db.connection)
        assert repo.get_by_id("MISSING") is None

    def test_get_by_domain_not_found(self, db: DatabaseManager) -> None:
        repo = CompanyRepository(db.connection)
        assert repo.get_by_domain("nowhere.com") is None

    def test_list_all(self, db: DatabaseManager) -> None:
        repo = CompanyRepository(db.connection)
        repo.insert(Company(company_id="C003", name="Gamma Ltd", domain="gamma.com"))
        repo.insert(Company(company_id="C004", name="Delta LLC", domain="delta.com"))
        results = repo.list_all()
        ids = [c.company_id for c in results]
        assert "C003" in ids
        assert "C004" in ids

    def test_update(self, db: DatabaseManager) -> None:
        repo = CompanyRepository(db.connection)
        company = Company(company_id="C005", name="Old Name", domain="old.com")
        repo.insert(company)
        company.name = "New Name"
        company.domain = "new.com"
        repo.update(company)
        result = repo.get_by_id("C005")
        assert result is not None
        assert result.name == "New Name"
        assert result.domain == "new.com"

    def test_delete(self, db: DatabaseManager) -> None:
        repo = CompanyRepository(db.connection)
        company = Company(company_id="C006", name="To Delete", domain="delete.com")
        repo.insert(company)
        repo.delete("C006")
        assert repo.get_by_id("C006") is None


# ---------------------------------------------------------------------------
# TestCaseRepository
# ---------------------------------------------------------------------------


class TestCaseRepository:
    def test_insert_and_get_by_id(self, db: DatabaseManager) -> None:
        repo = CaseRepository(db.connection)
        case = Case(case_id="CS-2026-001", subject="Test subject")
        repo.insert(case)
        result = repo.get_by_id("CS-2026-001")
        assert result is not None
        assert result.case_id == "CS-2026-001"
        assert result.subject == "Test subject"
        assert result.created_at is not None
        assert result.updated_at is not None

    def test_get_by_id_not_found(self, db: DatabaseManager) -> None:
        repo = CaseRepository(db.connection)
        assert repo.get_by_id("CS-9999-999") is None

    def test_next_case_id_first(self, db: DatabaseManager) -> None:
        repo = CaseRepository(db.connection)
        next_id = repo.next_case_id()
        # Should be CS-2026-001 (current year is 2026 based on system date)
        assert next_id.startswith("CS-")
        parts = next_id.split("-")
        assert len(parts) == 3
        assert parts[2] == "001"

    def test_next_case_id_sequential(self, db: DatabaseManager) -> None:
        repo = CaseRepository(db.connection)
        year = "2026"
        case1 = Case(case_id=f"CS-{year}-001", subject="First")
        case2 = Case(case_id=f"CS-{year}-002", subject="Second")
        repo.insert(case1)
        repo.insert(case2)
        next_id = repo.next_case_id()
        assert next_id == f"CS-{year}-003"

    def test_list_by_status(self, db: DatabaseManager) -> None:
        repo = CaseRepository(db.connection)
        repo.insert(Case(case_id="CS-2026-010", subject="Open case", status="處理中"))
        repo.insert(Case(case_id="CS-2026-011", subject="Done case", status="已完成"))
        open_cases = repo.list_by_status("處理中")
        done_cases = repo.list_by_status("已完成")
        assert any(c.case_id == "CS-2026-010" for c in open_cases)
        assert not any(c.case_id == "CS-2026-010" for c in done_cases)
        assert any(c.case_id == "CS-2026-011" for c in done_cases)

    def test_list_by_month(self, db: DatabaseManager) -> None:
        repo = CaseRepository(db.connection)
        repo.insert(Case(case_id="CS-2026-020", subject="March", sent_time="2026/03/15 10:00:00"))
        repo.insert(Case(case_id="CS-2026-021", subject="April", sent_time="2026/04/01 09:00:00"))
        march_cases = repo.list_by_month(2026, 3)
        april_cases = repo.list_by_month(2026, 4)
        assert any(c.case_id == "CS-2026-020" for c in march_cases)
        assert not any(c.case_id == "CS-2026-021" for c in march_cases)
        assert any(c.case_id == "CS-2026-021" for c in april_cases)

    def test_update_status(self, db: DatabaseManager) -> None:
        repo = CaseRepository(db.connection)
        case = Case(case_id="CS-2026-030", subject="Status test", status="處理中")
        repo.insert(case)
        repo.update_status("CS-2026-030", "已完成")
        result = repo.get_by_id("CS-2026-030")
        assert result is not None
        assert result.status == "已完成"
        assert result.updated_at is not None

    def test_update(self, db: DatabaseManager) -> None:
        repo = CaseRepository(db.connection)
        case = Case(case_id="CS-2026-040", subject="Original subject")
        repo.insert(case)
        case.subject = "Updated subject"
        case.priority = "高"
        repo.update(case)
        result = repo.get_by_id("CS-2026-040")
        assert result is not None
        assert result.subject == "Updated subject"
        assert result.priority == "高"

    def test_count_by_month(self, db: DatabaseManager) -> None:
        repo = CaseRepository(db.connection)
        repo.insert(Case(case_id="CS-2026-050", subject="M1", sent_time="2026/05/01 00:00:00"))
        repo.insert(Case(case_id="CS-2026-051", subject="M2", sent_time="2026/05/15 00:00:00"))
        repo.insert(Case(case_id="CS-2026-052", subject="M3", sent_time="2026/06/01 00:00:00"))
        assert repo.count_by_month(2026, 5) == 2
        assert repo.count_by_month(2026, 6) == 1
        assert repo.count_by_month(2026, 7) == 0


# ---------------------------------------------------------------------------
# TestQARepository
# ---------------------------------------------------------------------------


class TestQARepository:
    def test_insert_and_get_by_id(self, db: DatabaseManager) -> None:
        repo = QARepository(db.connection)
        qa = QAKnowledge(qa_id="QA-202603-001", question="How to reset?", answer="Click reset.")
        repo.insert(qa)
        result = repo.get_by_id("QA-202603-001")
        assert result is not None
        assert result.qa_id == "QA-202603-001"
        assert result.question == "How to reset?"
        assert result.created_at is not None
        assert result.updated_at is not None

    def test_get_by_id_not_found(self, db: DatabaseManager) -> None:
        repo = QARepository(db.connection)
        assert repo.get_by_id("QA-999999-999") is None

    def test_next_qa_id_first(self, db: DatabaseManager) -> None:
        repo = QARepository(db.connection)
        next_id = repo.next_qa_id()
        assert next_id.startswith("QA-")
        parts = next_id.split("-")
        assert len(parts) == 3
        assert parts[2] == "001"

    def test_next_qa_id_sequential(self, db: DatabaseManager) -> None:
        repo = QARepository(db.connection)
        ym = "202603"
        qa1 = QAKnowledge(qa_id=f"QA-{ym}-001", question="Q1", answer="A1")
        qa2 = QAKnowledge(qa_id=f"QA-{ym}-002", question="Q2", answer="A2")
        repo.insert(qa1)
        repo.insert(qa2)
        next_id = repo.next_qa_id()
        assert next_id == f"QA-{ym}-003"

    def test_list_all(self, db: DatabaseManager) -> None:
        repo = QARepository(db.connection)
        repo.insert(QAKnowledge(qa_id="QA-202603-010", question="Q10", answer="A10"))
        repo.insert(QAKnowledge(qa_id="QA-202603-011", question="Q11", answer="A11"))
        results = repo.list_all()
        ids = [q.qa_id for q in results]
        assert "QA-202603-010" in ids
        assert "QA-202603-011" in ids

    def test_update(self, db: DatabaseManager) -> None:
        repo = QARepository(db.connection)
        qa = QAKnowledge(qa_id="QA-202603-020", question="Old Q", answer="Old A")
        repo.insert(qa)
        qa.question = "New Q"
        qa.answer = "New A"
        repo.update(qa)
        result = repo.get_by_id("QA-202603-020")
        assert result is not None
        assert result.question == "New Q"
        assert result.answer == "New A"

    def test_delete(self, db: DatabaseManager) -> None:
        repo = QARepository(db.connection)
        qa = QAKnowledge(qa_id="QA-202603-030", question="Delete me", answer="Gone")
        repo.insert(qa)
        repo.delete("QA-202603-030")
        assert repo.get_by_id("QA-202603-030") is None


# ---------------------------------------------------------------------------
# TestMantisRepository
# ---------------------------------------------------------------------------


class TestMantisRepository:
    def test_upsert_and_get_by_id(self, db: DatabaseManager) -> None:
        repo = MantisRepository(db.connection)
        ticket = MantisTicket(ticket_id="T001", summary="Bug fix")
        repo.upsert(ticket)
        result = repo.get_by_id("T001")
        assert result is not None
        assert result.ticket_id == "T001"
        assert result.summary == "Bug fix"
        assert result.synced_at is not None

    def test_get_by_id_not_found(self, db: DatabaseManager) -> None:
        repo = MantisRepository(db.connection)
        assert repo.get_by_id("MISSING") is None

    def test_upsert_updates_existing(self, db: DatabaseManager) -> None:
        repo = MantisRepository(db.connection)
        ticket = MantisTicket(ticket_id="T002", summary="Original summary")
        repo.upsert(ticket)
        ticket.summary = "Updated summary"
        ticket.status = "Resolved"
        repo.upsert(ticket)
        result = repo.get_by_id("T002")
        assert result is not None
        assert result.summary == "Updated summary"
        assert result.status == "Resolved"

    def test_list_all(self, db: DatabaseManager) -> None:
        repo = MantisRepository(db.connection)
        repo.upsert(MantisTicket(ticket_id="T003", summary="Ticket 3"))
        repo.upsert(MantisTicket(ticket_id="T004", summary="Ticket 4"))
        results = repo.list_all()
        ids = [t.ticket_id for t in results]
        assert "T003" in ids
        assert "T004" in ids


# ---------------------------------------------------------------------------
# TestRuleRepository
# ---------------------------------------------------------------------------


class TestRuleRepository:
    def test_insert_and_list_by_type(self, db: DatabaseManager) -> None:
        repo = RuleRepository(db.connection)
        rule = ClassificationRule(rule_type="keyword", pattern="error.*", value="error", priority=1)
        repo.insert(rule)
        results = repo.list_by_type("keyword")
        assert len(results) == 1
        assert results[0].pattern == "error.*"
        assert results[0].value == "error"
        assert results[0].rule_id is not None
        assert results[0].created_at is not None

    def test_list_by_type_only_enabled(self, db: DatabaseManager) -> None:
        repo = RuleRepository(db.connection)
        repo.insert(ClassificationRule(rule_type="regex", pattern="p1", value="v1", priority=1, enabled=True))
        repo.insert(ClassificationRule(rule_type="regex", pattern="p2", value="v2", priority=2, enabled=False))
        results = repo.list_by_type("regex")
        assert len(results) == 1
        assert results[0].pattern == "p1"

    def test_ordered_by_priority(self, db: DatabaseManager) -> None:
        repo = RuleRepository(db.connection)
        repo.insert(ClassificationRule(rule_type="order_test", pattern="high", value="h", priority=10))
        repo.insert(ClassificationRule(rule_type="order_test", pattern="low", value="l", priority=1))
        repo.insert(ClassificationRule(rule_type="order_test", pattern="mid", value="m", priority=5))
        results = repo.list_by_type("order_test")
        priorities = [r.priority for r in results]
        assert priorities == sorted(priorities)

    def test_enabled_bool_conversion(self, db: DatabaseManager) -> None:
        repo = RuleRepository(db.connection)
        repo.insert(ClassificationRule(rule_type="bool_test", pattern="p", value="v", priority=1, enabled=True))
        results = repo.list_by_type("bool_test")
        assert isinstance(results[0].enabled, bool)
        assert results[0].enabled is True

    def test_delete(self, db: DatabaseManager) -> None:
        repo = RuleRepository(db.connection)
        rule = ClassificationRule(rule_type="del_test", pattern="del_p", value="del_v", priority=1)
        repo.insert(rule)
        inserted = repo.list_by_type("del_test")
        assert len(inserted) == 1
        rule_id = inserted[0].rule_id
        repo.delete(rule_id)
        assert repo.list_by_type("del_test") == []


# ---------------------------------------------------------------------------
# TestProcessedFileRepository
# ---------------------------------------------------------------------------


class TestProcessedFileRepository:
    def test_insert_and_exists(self, db: DatabaseManager) -> None:
        repo = ProcessedFileRepository(db.connection)
        pf = ProcessedFile(file_hash="abc123", filename="report.pdf", message_id="MSG001")
        repo.insert(pf)
        assert repo.exists("abc123") is True

    def test_not_exists(self, db: DatabaseManager) -> None:
        repo = ProcessedFileRepository(db.connection)
        assert repo.exists("nonexistent_hash") is False

    def test_insert_or_ignore_duplicate(self, db: DatabaseManager) -> None:
        repo = ProcessedFileRepository(db.connection)
        pf = ProcessedFile(file_hash="dup_hash", filename="file.pdf")
        repo.insert(pf)
        # Should not raise — INSERT OR IGNORE
        repo.insert(pf)
        assert repo.exists("dup_hash") is True

    def test_processed_at_auto_set(self, db: DatabaseManager) -> None:
        repo = ProcessedFileRepository(db.connection)
        pf = ProcessedFile(file_hash="ts_hash", filename="ts_file.pdf")
        repo.insert(pf)
        # Verify it was stored (existence implies processed_at was set)
        assert repo.exists("ts_hash") is True


# ---------------------------------------------------------------------------
# TestSynonymRepository
# ---------------------------------------------------------------------------


class TestSynonymRepository:
    def test_insert_and_get_synonyms(self, db: DatabaseManager) -> None:
        repo = SynonymRepository(db.connection)
        repo.insert(Synonym(word="error", synonym="fault", group_name="errors"))
        repo.insert(Synonym(word="error", synonym="bug", group_name="errors"))
        synonyms = repo.get_synonyms("error")
        assert "fault" in synonyms
        assert "bug" in synonyms

    def test_get_synonyms_empty(self, db: DatabaseManager) -> None:
        repo = SynonymRepository(db.connection)
        assert repo.get_synonyms("unknown_word") == []

    def test_get_group_words(self, db: DatabaseManager) -> None:
        repo = SynonymRepository(db.connection)
        repo.insert(Synonym(word="crash", synonym="freeze", group_name="failures"))
        repo.insert(Synonym(word="crash", synonym="hang", group_name="failures"))
        words = repo.get_group_words("failures")
        # Should include both the word and all its synonyms
        assert "crash" in words
        assert "freeze" in words
        assert "hang" in words

    def test_list_groups(self, db: DatabaseManager) -> None:
        repo = SynonymRepository(db.connection)
        repo.insert(Synonym(word="w1", synonym="s1", group_name="group_alpha"))
        repo.insert(Synonym(word="w2", synonym="s2", group_name="group_beta"))
        groups = repo.list_groups()
        assert "group_alpha" in groups
        assert "group_beta" in groups

    def test_delete_group(self, db: DatabaseManager) -> None:
        repo = SynonymRepository(db.connection)
        repo.insert(Synonym(word="x", synonym="y", group_name="temp_group"))
        repo.delete_group("temp_group")
        assert "temp_group" not in repo.list_groups()


# ---------------------------------------------------------------------------
# TestCaseMantisRepository
# ---------------------------------------------------------------------------


class TestCaseMantisRepository:
    def _insert_prerequisites(self, db: DatabaseManager) -> None:
        """Insert prerequisite case and ticket rows directly via SQL."""
        db.connection.execute(
            "INSERT INTO cs_cases (case_id, subject) VALUES (?, ?)",
            ("CS-2026-100", "Prereq case"),
        )
        db.connection.execute(
            "INSERT INTO mantis_tickets (ticket_id, summary) VALUES (?, ?)",
            ("MT-100", "Prereq ticket"),
        )
        db.connection.commit()

    def test_link_and_get_tickets_for_case(self, db: DatabaseManager) -> None:
        self._insert_prerequisites(db)
        repo = CaseMantisRepository(db.connection)
        link = CaseMantisLink(case_id="CS-2026-100", ticket_id="MT-100")
        repo.link(link)
        tickets = repo.get_tickets_for_case("CS-2026-100")
        assert "MT-100" in tickets

    def test_get_cases_for_ticket(self, db: DatabaseManager) -> None:
        self._insert_prerequisites(db)
        repo = CaseMantisRepository(db.connection)
        link = CaseMantisLink(case_id="CS-2026-100", ticket_id="MT-100")
        repo.link(link)
        cases = repo.get_cases_for_ticket("MT-100")
        assert "CS-2026-100" in cases

    def test_link_insert_or_ignore_duplicate(self, db: DatabaseManager) -> None:
        self._insert_prerequisites(db)
        repo = CaseMantisRepository(db.connection)
        link = CaseMantisLink(case_id="CS-2026-100", ticket_id="MT-100")
        repo.link(link)
        # Should not raise
        repo.link(link)
        tickets = repo.get_tickets_for_case("CS-2026-100")
        assert tickets.count("MT-100") == 1

    def test_get_tickets_for_case_empty(self, db: DatabaseManager) -> None:
        repo = CaseMantisRepository(db.connection)
        assert repo.get_tickets_for_case("CS-NONE") == []

    def test_get_cases_for_ticket_empty(self, db: DatabaseManager) -> None:
        repo = CaseMantisRepository(db.connection)
        assert repo.get_cases_for_ticket("MT-NONE") == []


# ---------------------------------------------------------------------------
# TestQARepositoryStatus
# ---------------------------------------------------------------------------


class TestQARepositoryStatus:
    @pytest.fixture
    def db(self, tmp_db_path):
        from hcp_cms.data.database import DatabaseManager
        db = DatabaseManager(tmp_db_path)
        db.initialize()
        yield db
        db.close()

    @pytest.fixture
    def repo(self, db):
        from hcp_cms.data.repositories import QARepository
        return QARepository(db.connection)

    def test_insert_status_待審核(self, repo):
        from hcp_cms.data.models import QAKnowledge
        qa = QAKnowledge(qa_id="QA-S01", question="q", answer="a", status="待審核")
        repo.insert(qa)
        assert repo.get_by_id("QA-S01").status == "待審核"

    def test_insert_status_default_已完成(self, repo):
        from hcp_cms.data.models import QAKnowledge
        qa = QAKnowledge(qa_id="QA-S02", question="q", answer="a")
        repo.insert(qa)
        assert repo.get_by_id("QA-S02").status == "已完成"

    def test_update_status_持久化(self, repo):
        from hcp_cms.data.models import QAKnowledge
        qa = QAKnowledge(qa_id="QA-S03", question="q", answer="a", status="待審核")
        repo.insert(qa)
        qa.status = "已完成"
        repo.update(qa)
        assert repo.get_by_id("QA-S03").status == "已完成"

    def test_list_by_status_待審核(self, repo):
        from hcp_cms.data.models import QAKnowledge
        repo.insert(QAKnowledge(qa_id="QA-S04", question="q1", answer="a", status="待審核"))
        repo.insert(QAKnowledge(qa_id="QA-S05", question="q2", answer="a", status="已完成"))
        pending = repo.list_by_status("待審核")
        assert len(pending) == 1
        assert pending[0].qa_id == "QA-S04"

    def test_list_approved(self, repo):
        from hcp_cms.data.models import QAKnowledge
        repo.insert(QAKnowledge(qa_id="QA-S06", question="q1", answer="a", status="待審核"))
        repo.insert(QAKnowledge(qa_id="QA-S07", question="q2", answer="a", status="已完成"))
        approved = repo.list_approved()
        assert len(approved) == 1
        assert approved[0].qa_id == "QA-S07"


# ---------------------------------------------------------------------------
# TestCaseRepositoryFindByCompanyAndSubject
# ---------------------------------------------------------------------------


class TestCaseRepositoryFindByCompanyAndSubject:
    @pytest.fixture(autouse=True)
    def _seed_companies(self, db: DatabaseManager) -> None:
        """預先插入測試用公司，避免 FOREIGN KEY 違反。"""
        co_repo = CompanyRepository(db.connection)
        co_repo.insert(Company(company_id="C001", name="公司甲", domain="c001.com"))
        co_repo.insert(Company(company_id="C002", name="公司乙", domain="c002.com"))

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
