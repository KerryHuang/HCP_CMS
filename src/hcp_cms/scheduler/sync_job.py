"""Mantis synchronization background job."""

from __future__ import annotations

import sqlite3

from hcp_cms.data.models import MantisTicket
from hcp_cms.data.repositories import MantisRepository
from hcp_cms.services.mantis.base import MantisClient


class SyncJob:
    """Syncs Mantis tickets to local database."""

    def __init__(self, conn: sqlite3.Connection, mantis_client: MantisClient) -> None:
        self._conn = conn
        self._mantis_repo = MantisRepository(conn)
        self._client = mantis_client

    def run(self) -> int:
        """Sync all tickets. Returns count synced."""
        if not self._client.connect():
            return 0

        # Get existing ticket IDs from DB
        existing = self._mantis_repo.list_all()
        count = 0

        for ticket in existing:
            issue = self._client.get_issue(ticket.ticket_id)
            if issue:
                self._mantis_repo.upsert(MantisTicket(
                    ticket_id=issue.id,
                    summary=issue.summary,
                    status=issue.status,
                    priority=issue.priority,
                    handler=issue.handler,
                ))
                count += 1

        return count
