"""Email processing background job."""

from __future__ import annotations

import hashlib
import sqlite3

from hcp_cms.core.case_manager import CaseManager
from hcp_cms.core.classifier import Classifier
from hcp_cms.data.models import CaseMantisLink, ProcessedFile
from hcp_cms.data.repositories import CaseMantisRepository, ProcessedFileRepository
from hcp_cms.services.mail.base import MailProvider, RawEmail


class EmailJob:
    """Processes new emails from a mail provider."""

    def __init__(self, conn: sqlite3.Connection, mail_provider: MailProvider) -> None:
        self._conn = conn
        self._provider = mail_provider
        self._case_mgr = CaseManager(conn)
        self._classifier = Classifier(conn)
        self._processed_repo = ProcessedFileRepository(conn)

    def run(self) -> int:
        """Fetch and process new emails. Returns count processed."""
        if not self._provider.connect():
            return 0

        try:
            messages = self._provider.fetch_messages()
            count = 0
            for msg in messages:
                if self._is_duplicate(msg):
                    continue
                self._process_message(msg)
                count += 1
            return count
        finally:
            self._provider.disconnect()

    def _is_duplicate(self, msg: RawEmail) -> bool:
        """Check if message was already processed."""
        if msg.message_id:
            h = hashlib.sha256(msg.message_id.encode()).hexdigest()
            return self._processed_repo.exists(h)
        return False

    def _process_message(self, msg: RawEmail) -> None:
        """Process a single email message."""
        # 先取得分類結果，以便後續建立 Mantis 連結
        classification = self._classifier.classify(
            subject=msg.subject,
            body=msg.body,
            sender_email=msg.sender,
            to_recipients=[],
        )

        case = self._case_mgr.create_case(
            subject=msg.subject,
            body=msg.body,
            sender_email=msg.sender,
            sent_time=msg.date,
        )

        # 若主旨含 ISSUE_YYYYMMDD_INNNNN_ 格式，自動建立 Mantis 連結
        if classification.get("mantis_ticket_id"):
            mantis_repo = CaseMantisRepository(self._conn)
            link = CaseMantisLink(
                case_id=case.case_id,
                ticket_id=classification["mantis_ticket_id"],
                summary=f"自主旨自動連結（{classification.get('mantis_issue_date', '')}）",
                issue_date=classification.get("mantis_issue_date"),
            )
            existing = mantis_repo.list_by_case_id(case.case_id)
            if not any(t.ticket_id == link.ticket_id for t in existing):
                mantis_repo.insert(link)

        # Record as processed
        file_hash = hashlib.sha256((msg.message_id or msg.subject + msg.sender).encode()).hexdigest()
        self._processed_repo.insert(
            ProcessedFile(
                file_hash=file_hash,
                filename=msg.source_file or "",
                message_id=msg.message_id,
            )
        )
