"""Email processing background job."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from hcp_cms.core.case_manager import CaseManager
from hcp_cms.data.models import ProcessedFile
from hcp_cms.data.repositories import ProcessedFileRepository
from hcp_cms.services.mail.base import MailProvider, RawEmail


class EmailJob:
    """Processes new emails from a mail provider."""

    def __init__(self, conn: sqlite3.Connection, mail_provider: MailProvider) -> None:
        self._conn = conn
        self._provider = mail_provider
        self._case_mgr = CaseManager(conn)
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
        self._case_mgr.create_case(
            subject=msg.subject,
            body=msg.body,
            sender_email=msg.sender,
            sent_time=msg.date,
        )

        # Record as processed
        file_hash = hashlib.sha256(
            (msg.message_id or msg.subject + msg.sender).encode()
        ).hexdigest()
        self._processed_repo.insert(ProcessedFile(
            file_hash=file_hash,
            filename=msg.source_file or "",
            message_id=msg.message_id,
        ))
