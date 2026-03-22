"""Tests for scheduler layer."""

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, Company, ClassificationRule, MantisTicket
from hcp_cms.data.repositories import CaseRepository, CompanyRepository, RuleRepository, MantisRepository
from hcp_cms.scheduler.scheduler import Scheduler, JobConfig
from hcp_cms.scheduler.email_job import EmailJob
from hcp_cms.scheduler.sync_job import SyncJob
from hcp_cms.scheduler.backup_job import BackupJob
from hcp_cms.scheduler.report_job import ReportJob
from hcp_cms.services.mail.base import RawEmail


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


class TestScheduler:
    def test_add_and_run_job(self):
        scheduler = Scheduler()
        result = {"called": False}

        def callback():
            result["called"] = True

        scheduler.add_job(JobConfig(name="test", interval_seconds=60, callback=callback))
        scheduler.run_now("test")
        assert result["called"] is True

    def test_get_job_status(self):
        scheduler = Scheduler()
        scheduler.add_job(JobConfig(name="test", interval_seconds=60, callback=lambda: None))
        status = scheduler.get_job_status()
        assert "test" in status
        assert status["test"]["enabled"] is True
        assert status["test"]["interval"] == 60

    def test_remove_job(self):
        scheduler = Scheduler()
        scheduler.add_job(JobConfig(name="test", interval_seconds=60, callback=lambda: None))
        scheduler.remove_job("test")
        status = scheduler.get_job_status()
        assert "test" not in status

    def test_start_stop_all(self):
        scheduler = Scheduler()
        call_count = {"n": 0}
        scheduler.add_job(JobConfig(name="fast", interval_seconds=1, callback=lambda: None))
        scheduler.start_all()
        assert scheduler._running is True
        scheduler.stop_all()
        assert scheduler._running is False

    def test_disabled_job_not_started(self):
        scheduler = Scheduler()
        result = {"called": False}
        scheduler.add_job(JobConfig(
            name="disabled", interval_seconds=1,
            callback=lambda: result.update({"called": True}),
            enabled=False,
        ))
        scheduler.start_all()
        time.sleep(0.1)
        scheduler.stop_all()
        assert result["called"] is False


class TestEmailJob:
    def test_process_messages(self, db):
        mock_provider = MagicMock()
        mock_provider.connect.return_value = True
        mock_provider.fetch_messages.return_value = [
            RawEmail(sender="user@test.com", subject="Test issue", body="Bug found", message_id="<msg1@test>"),
        ]

        job = EmailJob(db.connection, mock_provider)
        count = job.run()
        assert count == 1

        # Verify case was created
        cases = CaseRepository(db.connection).list_by_status("處理中")
        assert len(cases) >= 1

    def test_skip_duplicate(self, db):
        mock_provider = MagicMock()
        mock_provider.connect.return_value = True
        mock_provider.fetch_messages.return_value = [
            RawEmail(sender="user@test.com", subject="Test", body="Body", message_id="<dup@test>"),
        ]

        job = EmailJob(db.connection, mock_provider)
        assert job.run() == 1

        # Run again — should skip duplicate
        mock_provider.connect.return_value = True
        assert job.run() == 0

    def test_connect_failure(self, db):
        mock_provider = MagicMock()
        mock_provider.connect.return_value = False

        job = EmailJob(db.connection, mock_provider)
        assert job.run() == 0


class TestSyncJob:
    def test_sync_tickets(self, db):
        # Insert a ticket to sync
        MantisRepository(db.connection).upsert(MantisTicket(ticket_id="100", summary="Old"))

        mock_client = MagicMock()
        mock_client.connect.return_value = True

        from hcp_cms.services.mantis.base import MantisIssue
        mock_client.get_issue.return_value = MantisIssue(id="100", summary="Updated", status="resolved")

        job = SyncJob(db.connection, mock_client)
        count = job.run()
        assert count == 1

        # Verify updated
        ticket = MantisRepository(db.connection).get_by_id("100")
        assert ticket.summary == "Updated"


class TestBackupJob:
    def test_backup_creates_file(self, db, tmp_path):
        job = BackupJob(db.connection, tmp_path / "backups")
        path = job.run()
        assert path.exists()


class TestReportJob:
    def test_generate_reports(self, db, tmp_path):
        # Seed data
        CompanyRepository(db.connection).insert(Company(company_id="C1", name="Test", domain="test.com"))
        CaseRepository(db.connection).insert(Case(
            case_id="CS-2026-001", subject="Test", company_id="C1", sent_time="2026/03/10 09:00"
        ))

        job = ReportJob(db.connection, tmp_path / "reports")
        result = job.run(2026, 3)
        assert result["tracking"].exists()
        assert result["report"].exists()
