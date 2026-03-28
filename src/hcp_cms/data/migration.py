"""MigrationManager — migrate legacy SQLite databases to the new schema."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


def _add_qa_status_column(conn: sqlite3.Connection) -> None:
    """替既有 qa_knowledge 表加入 status 欄位，冪等（欄位已存在時跳過）。"""
    try:
        conn.execute("ALTER TABLE qa_knowledge ADD COLUMN status TEXT DEFAULT '已完成'")
        conn.commit()
    except sqlite3.OperationalError:
        pass


@dataclass
class MigrationPreview:
    cases_count: int = 0
    qa_count: int = 0
    mantis_count: int = 0


class MigrationManager:
    """Detects legacy schema and migrates data to the new schema."""

    def __init__(self, new_conn: sqlite3.Connection) -> None:
        self._new = new_conn

    # ------------------------------------------------------------------
    # Schema detection
    # ------------------------------------------------------------------

    def is_legacy_schema(self, old_db_path: Path) -> bool:
        """Return True if the database at old_db_path uses the legacy schema.

        The legacy schema has a 'company' TEXT column in cs_cases.
        The new schema uses 'company_id' as a FK column instead.
        """
        conn = sqlite3.connect(str(old_db_path))
        try:
            cursor = conn.execute("PRAGMA table_info(cs_cases)")
            columns = {row[1] for row in cursor.fetchall()}
            return "company" in columns and "company_id" not in columns
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def preview(self, old_db_path: Path) -> MigrationPreview:
        """Return record counts in the legacy database without migrating."""
        conn = sqlite3.connect(str(old_db_path))
        try:
            cases_count = conn.execute("SELECT COUNT(*) FROM cs_cases").fetchone()[0]
            qa_count = conn.execute("SELECT COUNT(*) FROM qa_knowledge").fetchone()[0]
            mantis_count = conn.execute("SELECT COUNT(*) FROM mantis_tickets").fetchone()[0]
        finally:
            conn.close()

        return MigrationPreview(
            cases_count=cases_count,
            qa_count=qa_count,
            mantis_count=mantis_count,
        )

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def migrate(self, old_db_path: Path) -> MigrationPreview:
        """Migrate data from a legacy database into the new schema.

        Steps:
        1. Extract unique company domains → insert into companies table.
        2. Migrate cs_cases (map company text → company_id FK).
        3. Migrate qa_knowledge (map company text → company_id FK).
        4. Migrate mantis_tickets + split related_cs_case "CS-001;CS-002"
           into individual case_mantis link rows.

        Returns a MigrationPreview with counts of migrated records.
        """
        old = sqlite3.connect(str(old_db_path))
        old.row_factory = sqlite3.Row
        try:
            preview = self._migrate(old)
        finally:
            old.close()
        return preview

    def _migrate(self, old: sqlite3.Connection) -> MigrationPreview:
        # ---- Step 1: companies ----------------------------------------
        # Collect unique domain values from cs_cases and qa_knowledge
        domain_set: set[str] = set()

        for row in old.execute("SELECT company FROM cs_cases WHERE company IS NOT NULL"):
            domain = row[0].strip()
            if domain:
                domain_set.add(domain)

        for row in old.execute("SELECT company FROM qa_knowledge WHERE company IS NOT NULL"):
            domain = row[0].strip()
            if domain:
                domain_set.add(domain)

        # company_id = domain (use domain as the PK directly for simplicity)
        domain_to_id: dict[str, str] = {}
        for domain in sorted(domain_set):
            company_id = domain
            domain_to_id[domain] = company_id
            self._new.execute(
                "INSERT OR IGNORE INTO companies (company_id, name, domain) VALUES (?, ?, ?)",
                (company_id, domain, domain),
            )

        # ---- Step 2: cs_cases ----------------------------------------
        cases_count = 0
        for row in old.execute("SELECT * FROM cs_cases"):
            row_dict = dict(row)
            company_text = (row_dict.pop("company", None) or "").strip()
            case_company_id: str | None = domain_to_id.get(company_text)

            self._new.execute(
                """INSERT OR IGNORE INTO cs_cases (
                    case_id, contact_method, status, priority,
                    sent_time, company_id, contact_person, subject,
                    system_product, issue_type, error_type, impact_period,
                    progress, actual_reply, notes, rd_assignee, handler
                ) VALUES (
                    :case_id, :contact_method, :status, :priority,
                    :sent_time, :company_id, :contact_person, :subject,
                    :system_product, :issue_type, :error_type, :impact_period,
                    :progress, :actual_reply, :notes, :rd_assignee, :handler
                )""",
                {
                    "case_id": row_dict.get("case_id"),
                    "contact_method": row_dict.get("contact_method"),
                    "status": row_dict.get("status"),
                    "priority": row_dict.get("priority"),
                    "sent_time": row_dict.get("sent_time"),
                    "company_id": case_company_id,
                    "contact_person": row_dict.get("contact_person"),
                    "subject": row_dict.get("subject"),
                    "system_product": row_dict.get("system_product"),
                    "issue_type": row_dict.get("issue_type"),
                    "error_type": row_dict.get("error_type"),
                    "impact_period": row_dict.get("impact_period"),
                    "progress": row_dict.get("progress"),
                    "actual_reply": row_dict.get("actual_reply"),
                    "notes": row_dict.get("notes"),
                    "rd_assignee": row_dict.get("rd_assignee"),
                    "handler": row_dict.get("handler"),
                },
            )
            cases_count += 1

        # ---- Step 3: qa_knowledge ------------------------------------
        qa_count = 0
        for row in old.execute("SELECT * FROM qa_knowledge"):
            row_dict = dict(row)
            company_text = (row_dict.pop("company", None) or "").strip()
            qa_company_id: str | None = domain_to_id.get(company_text)

            # created_date → created_at mapping
            created_at = row_dict.pop("created_date", None)

            self._new.execute(
                """INSERT OR IGNORE INTO qa_knowledge (
                    qa_id, system_product, issue_type, error_type,
                    question, answer, has_image, company_id,
                    created_by, created_at, notes
                ) VALUES (
                    :qa_id, :system_product, :issue_type, :error_type,
                    :question, :answer, :has_image, :company_id,
                    :created_by, :created_at, :notes
                )""",
                {
                    "qa_id": row_dict.get("qa_id"),
                    "system_product": row_dict.get("system_product"),
                    "issue_type": row_dict.get("issue_type"),
                    "error_type": row_dict.get("error_type"),
                    "question": row_dict.get("question"),
                    "answer": row_dict.get("answer"),
                    "has_image": row_dict.get("has_image"),
                    "company_id": qa_company_id,
                    "created_by": row_dict.get("created_by"),
                    "created_at": created_at,
                    "notes": row_dict.get("notes"),
                },
            )
            qa_count += 1

        # ---- Step 4: mantis_tickets + case_mantis links ---------------
        mantis_count = 0
        for row in old.execute("SELECT * FROM mantis_tickets"):
            row_dict = dict(row)
            related_cs_case = row_dict.pop("related_cs_case", None) or ""
            customer = row_dict.pop("customer", None)
            issue_summary = row_dict.pop("issue_summary", None)

            # Map customer domain to company_id
            mantis_company_id: str | None = domain_to_id.get((customer or "").strip())

            self._new.execute(
                """INSERT OR IGNORE INTO mantis_tickets (
                    ticket_id, created_time, company_id, summary,
                    priority, status, notes
                ) VALUES (
                    :ticket_id, :created_time, :company_id, :summary,
                    :priority, :status, :notes
                )""",
                {
                    "ticket_id": row_dict.get("ticket_id"),
                    "created_time": row_dict.get("created_time"),
                    "company_id": mantis_company_id,
                    "summary": issue_summary,
                    "priority": row_dict.get("priority"),
                    "status": row_dict.get("status"),
                    "notes": row_dict.get("notes"),
                },
            )

            # Split related_cs_case by ";" and create case_mantis links
            ticket_id = row_dict.get("ticket_id")
            if related_cs_case and ticket_id:
                for case_ref in related_cs_case.split(";"):
                    case_id = case_ref.strip()
                    if case_id:
                        # Only insert if the case exists in the new DB
                        exists = self._new.execute("SELECT 1 FROM cs_cases WHERE case_id = ?", (case_id,)).fetchone()
                        if exists:
                            self._new.execute(
                                "INSERT OR IGNORE INTO case_mantis (case_id, ticket_id) VALUES (?, ?)",
                                (case_id, ticket_id),
                            )

            mantis_count += 1

        _add_qa_status_column(self._new)
        self._new.commit()

        return MigrationPreview(
            cases_count=cases_count,
            qa_count=qa_count,
            mantis_count=mantis_count,
        )
