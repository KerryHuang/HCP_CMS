"""MergeManager — merge two SQLite databases with configurable conflict resolution."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from enum import Enum


class ConflictStrategy(Enum):
    KEEP_LOCAL = "keep_local"
    KEEP_REMOTE = "keep_remote"


@dataclass
class MergePreview:
    cases_new: int = 0
    cases_conflict: int = 0
    cases_skip: int = 0
    qa_new: int = 0
    qa_conflict: int = 0
    companies_new: int = 0
    companies_conflict: int = 0


@dataclass
class MergeResult:
    imported: int = 0
    skipped: int = 0
    overwritten: int = 0


# (table_name, primary_key_column)
_MERGE_TABLES = [
    ("companies", "company_id"),
    ("cs_cases", "case_id"),
    ("qa_knowledge", "qa_id"),
    ("mantis_tickets", "ticket_id"),
]


class MergeManager:
    """Merges records from a remote database into the local database."""

    def __init__(self, local_conn: sqlite3.Connection) -> None:
        self._local = local_conn

    def preview(self, remote_conn: sqlite3.Connection) -> MergePreview:
        """Count how many records in remote are new vs conflicting with local."""
        preview = MergePreview()

        for table, pk in _MERGE_TABLES:
            remote_ids = {
                row[0]
                for row in remote_conn.execute(f"SELECT {pk} FROM {table}").fetchall()
            }
            local_ids = {
                row[0]
                for row in self._local.execute(f"SELECT {pk} FROM {table}").fetchall()
            }

            new_count = len(remote_ids - local_ids)
            conflict_count = len(remote_ids & local_ids)

            if table == "cs_cases":
                preview.cases_new = new_count
                preview.cases_conflict = conflict_count
            elif table == "qa_knowledge":
                preview.qa_new = new_count
                preview.qa_conflict = conflict_count
            elif table == "companies":
                preview.companies_new = new_count
                preview.companies_conflict = conflict_count

        return preview

    def merge(
        self, remote_conn: sqlite3.Connection, strategy: ConflictStrategy
    ) -> MergeResult:
        """Merge remote into local.

        - New records (not in local): always import.
        - Conflicting records:
            - KEEP_LOCAL: skip (local wins).
            - KEEP_REMOTE: overwrite (remote wins).
        """
        result = MergeResult()

        for table, pk in _MERGE_TABLES:
            # Get column names for this table
            cursor = remote_conn.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in cursor.fetchall()]
            if not columns:
                continue

            col_list = ", ".join(columns)
            placeholders = ", ".join("?" for _ in columns)

            local_ids = {
                row[0]
                for row in self._local.execute(f"SELECT {pk} FROM {table}").fetchall()
            }

            remote_rows = remote_conn.execute(
                f"SELECT {col_list} FROM {table}"
            ).fetchall()

            for row in remote_rows:
                row_dict = dict(zip(columns, row))
                pk_value = row_dict[pk]

                if pk_value in local_ids:
                    # Conflict
                    if strategy == ConflictStrategy.KEEP_LOCAL:
                        result.skipped += 1
                    else:  # KEEP_REMOTE
                        set_clause = ", ".join(
                            f"{col} = ?" for col in columns if col != pk
                        )
                        values = [row_dict[col] for col in columns if col != pk]
                        values.append(pk_value)
                        self._local.execute(
                            f"UPDATE {table} SET {set_clause} WHERE {pk} = ?",
                            values,
                        )
                        result.overwritten += 1
                else:
                    # New record — always import
                    self._local.execute(
                        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
                        [row_dict[col] for col in columns],
                    )
                    result.imported += 1

        self._local.commit()
        return result
