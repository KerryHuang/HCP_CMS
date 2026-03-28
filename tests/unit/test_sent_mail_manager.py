"""Unit tests for SentMailManager."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from hcp_cms.core.sent_mail_manager import EnrichedSentMail, SentMailManager
from hcp_cms.data.database import DatabaseManager
from hcp_cms.services.mail.base import MailProvider, RawEmail


class _MockProvider(MailProvider):
    def __init__(self, sent: list[RawEmail]) -> None:
        self._sent = sent

    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def fetch_messages(
        self, since=None, until=None, folder: str = "INBOX"
    ) -> list[RawEmail]:
        return []

    def fetch_sent_messages(self, since=None) -> list[RawEmail]:
        return self._sent

    def create_draft(
        self, to: list[str], subject: str, body: str, attachments=None
    ) -> bool:
        return False


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def seeded(db: DatabaseManager) -> DatabaseManager:
    conn = db.connection
    conn.execute(
        "INSERT INTO companies (company_id, name, domain) VALUES (?, ?, ?)",
        ("C1", "ABC 公司", "abc.com"),
    )
    conn.execute(
        "INSERT INTO companies (company_id, name, domain) VALUES (?, ?, ?)",
        ("C2", "XYZ 股份", "xyz.com"),
    )
    conn.execute(
        "INSERT INTO cs_cases (case_id, subject, company_id, status) VALUES (?, ?, ?, ?)",
        ("K001", "薪資異常問題", "C1", "處理中"),
    )
    conn.commit()
    return db


class TestSentMailManager:
    def test_resolve_company_by_case(self, seeded: DatabaseManager) -> None:
        mgr = SentMailManager(seeded.connection, _MockProvider([]))
        company_id, company_name = mgr._resolve_company("薪資異常問題", [])
        assert company_id == "C1"
        assert company_name == "ABC 公司"

    def test_resolve_company_by_domain(self, seeded: DatabaseManager) -> None:
        mgr = SentMailManager(seeded.connection, _MockProvider([]))
        company_id, company_name = mgr._resolve_company("無關主旨", ["user@xyz.com"])
        assert company_id == "C2"
        assert company_name == "XYZ 股份"

    def test_resolve_company_unknown(self, seeded: DatabaseManager) -> None:
        mgr = SentMailManager(seeded.connection, _MockProvider([]))
        company_id, company_name = mgr._resolve_company("不明主旨", ["nobody@unknown.com"])
        assert company_id is None
        assert company_name is None

    def test_fetch_and_enrich_counts(self, seeded: DatabaseManager) -> None:
        emails = [
            RawEmail(subject="A", to_recipients=["a@abc.com"], date="2026-03-28 10:00:00"),
            RawEmail(subject="B", to_recipients=["b@abc.com"], date="2026-03-28 11:00:00"),
            RawEmail(subject="C", to_recipients=["c@other.com"], date="2026-03-28 12:00:00"),
        ]
        mgr = SentMailManager(seeded.connection, _MockProvider(emails))
        results = mgr.fetch_and_enrich(
            since=datetime(2026, 3, 28),
            until=datetime(2026, 3, 28, 23, 59, 59),
        )
        abc_mails = [m for m in results if m.company_id == "C1"]
        assert len(abc_mails) == 2
        assert all(m.company_reply_count == 2 for m in abc_mails)
        other_mails = [m for m in results if m.company_id is None]
        assert all(m.company_reply_count == 0 for m in other_mails)

    def test_fetch_and_enrich_date_filter(self, seeded: DatabaseManager) -> None:
        emails = [
            RawEmail(subject="今日", to_recipients=[], date="2026-03-28 10:00:00"),
            RawEmail(subject="明日", to_recipients=[], date="2026-03-29 10:00:00"),
        ]
        mgr = SentMailManager(seeded.connection, _MockProvider(emails))
        results = mgr.fetch_and_enrich(
            since=datetime(2026, 3, 28),
            until=datetime(2026, 3, 28, 23, 59, 59),
        )
        assert len(results) == 1
        assert results[0].subject == "今日"
