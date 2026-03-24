"""Repository classes for all data entities."""

from __future__ import annotations

import sqlite3
from datetime import datetime

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


def _now() -> str:
    return datetime.now().strftime("%Y/%m/%d %H:%M:%S")


# ---------------------------------------------------------------------------
# CompanyRepository
# ---------------------------------------------------------------------------


class CompanyRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, company: Company) -> None:
        company.created_at = _now()
        self._conn.execute(
            """
            INSERT INTO companies (company_id, name, domain, alias, contact_info, created_at)
            VALUES (:company_id, :name, :domain, :alias, :contact_info, :created_at)
            """,
            {
                "company_id": company.company_id,
                "name": company.name,
                "domain": company.domain,
                "alias": company.alias,
                "contact_info": company.contact_info,
                "created_at": company.created_at,
            },
        )
        self._conn.commit()

    def get_by_id(self, company_id: str) -> Company | None:
        row = self._conn.execute("SELECT * FROM companies WHERE company_id = ?", (company_id,)).fetchone()
        if row is None:
            return None
        return Company(**dict(row))

    def get_by_domain(self, domain: str) -> Company | None:
        row = self._conn.execute("SELECT * FROM companies WHERE domain = ?", (domain,)).fetchone()
        if row is None:
            return None
        return Company(**dict(row))

    def list_all(self) -> list[Company]:
        rows = self._conn.execute("SELECT * FROM companies").fetchall()
        return [Company(**dict(row)) for row in rows]

    def update(self, company: Company) -> None:
        self._conn.execute(
            """
            UPDATE companies
            SET name = :name, domain = :domain, alias = :alias,
                contact_info = :contact_info
            WHERE company_id = :company_id
            """,
            {
                "company_id": company.company_id,
                "name": company.name,
                "domain": company.domain,
                "alias": company.alias,
                "contact_info": company.contact_info,
            },
        )
        self._conn.commit()

    def delete(self, company_id: str) -> None:
        self._conn.execute("DELETE FROM companies WHERE company_id = ?", (company_id,))
        self._conn.commit()


# ---------------------------------------------------------------------------
# CaseRepository
# ---------------------------------------------------------------------------


class CaseRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, case: Case) -> None:
        now = _now()
        case.created_at = now
        case.updated_at = now
        self._conn.execute(
            """
            INSERT INTO cs_cases (
                case_id, contact_method, status, priority, replied, sent_time,
                company_id, contact_person, subject, system_product, issue_type,
                error_type, impact_period, progress, actual_reply, notes,
                rd_assignee, handler, reply_count, linked_case_id, source,
                created_at, updated_at
            ) VALUES (
                :case_id, :contact_method, :status, :priority, :replied, :sent_time,
                :company_id, :contact_person, :subject, :system_product, :issue_type,
                :error_type, :impact_period, :progress, :actual_reply, :notes,
                :rd_assignee, :handler, :reply_count, :linked_case_id, :source,
                :created_at, :updated_at
            )
            """,
            {
                "case_id": case.case_id,
                "contact_method": case.contact_method,
                "status": case.status,
                "priority": case.priority,
                "replied": case.replied,
                "sent_time": case.sent_time,
                "company_id": case.company_id,
                "contact_person": case.contact_person,
                "subject": case.subject,
                "system_product": case.system_product,
                "issue_type": case.issue_type,
                "error_type": case.error_type,
                "impact_period": case.impact_period,
                "progress": case.progress,
                "actual_reply": case.actual_reply,
                "notes": case.notes,
                "rd_assignee": case.rd_assignee,
                "handler": case.handler,
                "reply_count": case.reply_count,
                "linked_case_id": case.linked_case_id,
                "source": case.source,
                "created_at": case.created_at,
                "updated_at": case.updated_at,
            },
        )
        self._conn.commit()

    def get_by_id(self, case_id: str) -> Case | None:
        row = self._conn.execute("SELECT * FROM cs_cases WHERE case_id = ?", (case_id,)).fetchone()
        if row is None:
            return None
        return Case(**dict(row))

    def next_case_id(self) -> str:
        year = datetime.now().strftime("%Y")
        prefix = f"CS-{year}-"
        row = self._conn.execute(
            "SELECT MAX(case_id) FROM cs_cases WHERE case_id LIKE ?",
            (f"{prefix}%",),
        ).fetchone()
        max_id: str | None = row[0] if row else None
        if max_id is None:
            next_num = 1
        else:
            # Extract the numeric suffix
            suffix = max_id[len(prefix) :]
            next_num = int(suffix) + 1
        return f"{prefix}{next_num:03d}"

    def list_by_status(self, status: str) -> list[Case]:
        rows = self._conn.execute("SELECT * FROM cs_cases WHERE status = ?", (status,)).fetchall()
        return [Case(**dict(row)) for row in rows]

    def list_by_month(self, year: int, month: int) -> list[Case]:
        prefix = f"{year}/{month:02d}%"
        rows = self._conn.execute("SELECT * FROM cs_cases WHERE sent_time LIKE ?", (prefix,)).fetchall()
        return [Case(**dict(row)) for row in rows]

    def list_by_date_range(self, start: str, end: str) -> list[Case]:
        """查詢 sent_time 在 [start, end] 區間的案件（格式 YYYY/MM/DD）。"""
        end_inclusive = end + " 23:59:59"
        rows = self._conn.execute(
            "SELECT * FROM cs_cases WHERE sent_time >= ? AND sent_time <= ?",
            (start, end_inclusive),
        ).fetchall()
        return [Case(**dict(row)) for row in rows]

    def update_status(self, case_id: str, status: str) -> None:
        self._conn.execute(
            "UPDATE cs_cases SET status = ?, updated_at = ? WHERE case_id = ?",
            (status, _now(), case_id),
        )
        self._conn.commit()

    def update(self, case: Case) -> None:
        case.updated_at = _now()
        self._conn.execute(
            """
            UPDATE cs_cases SET
                contact_method = :contact_method,
                status = :status,
                priority = :priority,
                replied = :replied,
                sent_time = :sent_time,
                company_id = :company_id,
                contact_person = :contact_person,
                subject = :subject,
                system_product = :system_product,
                issue_type = :issue_type,
                error_type = :error_type,
                impact_period = :impact_period,
                progress = :progress,
                actual_reply = :actual_reply,
                notes = :notes,
                rd_assignee = :rd_assignee,
                handler = :handler,
                reply_count = :reply_count,
                linked_case_id = :linked_case_id,
                source = :source,
                updated_at = :updated_at
            WHERE case_id = :case_id
            """,
            {
                "case_id": case.case_id,
                "contact_method": case.contact_method,
                "status": case.status,
                "priority": case.priority,
                "replied": case.replied,
                "sent_time": case.sent_time,
                "company_id": case.company_id,
                "contact_person": case.contact_person,
                "subject": case.subject,
                "system_product": case.system_product,
                "issue_type": case.issue_type,
                "error_type": case.error_type,
                "impact_period": case.impact_period,
                "progress": case.progress,
                "actual_reply": case.actual_reply,
                "notes": case.notes,
                "rd_assignee": case.rd_assignee,
                "handler": case.handler,
                "reply_count": case.reply_count,
                "linked_case_id": case.linked_case_id,
                "source": case.source,
                "updated_at": case.updated_at,
            },
        )
        self._conn.commit()

    def count_by_month(self, year: int, month: int) -> int:
        prefix = f"{year}/{month:02d}%"
        row = self._conn.execute("SELECT COUNT(*) FROM cs_cases WHERE sent_time LIKE ?", (prefix,)).fetchone()
        return row[0] if row else 0


# ---------------------------------------------------------------------------
# QARepository
# ---------------------------------------------------------------------------


class QARepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, qa: QAKnowledge) -> None:
        now = _now()
        qa.created_at = now
        qa.updated_at = now
        self._conn.execute(
            """
            INSERT INTO qa_knowledge (
                qa_id, system_product, issue_type, error_type, question, answer,
                solution, keywords, has_image, doc_name, company_id, source_case_id,
                source, status, created_by, created_at, updated_at, notes
            ) VALUES (
                :qa_id, :system_product, :issue_type, :error_type, :question, :answer,
                :solution, :keywords, :has_image, :doc_name, :company_id, :source_case_id,
                :source, :status, :created_by, :created_at, :updated_at, :notes
            )
            """,
            {
                "qa_id": qa.qa_id,
                "system_product": qa.system_product,
                "issue_type": qa.issue_type,
                "error_type": qa.error_type,
                "question": qa.question,
                "answer": qa.answer,
                "solution": qa.solution,
                "keywords": qa.keywords,
                "has_image": qa.has_image,
                "doc_name": qa.doc_name,
                "company_id": qa.company_id,
                "source_case_id": qa.source_case_id,
                "source": qa.source,
                "status": qa.status,
                "created_by": qa.created_by,
                "created_at": qa.created_at,
                "updated_at": qa.updated_at,
                "notes": qa.notes,
            },
        )
        self._conn.commit()

    def get_by_id(self, qa_id: str) -> QAKnowledge | None:
        row = self._conn.execute("SELECT * FROM qa_knowledge WHERE qa_id = ?", (qa_id,)).fetchone()
        if row is None:
            return None
        return QAKnowledge(**dict(row))

    def next_qa_id(self) -> str:
        ym = datetime.now().strftime("%Y%m")
        prefix = f"QA-{ym}-"
        row = self._conn.execute(
            "SELECT MAX(qa_id) FROM qa_knowledge WHERE qa_id LIKE ?",
            (f"{prefix}%",),
        ).fetchone()
        max_id: str | None = row[0] if row else None
        if max_id is None:
            next_num = 1
        else:
            suffix = max_id[len(prefix) :]
            next_num = int(suffix) + 1
        return f"{prefix}{next_num:03d}"

    def list_all(self) -> list[QAKnowledge]:
        rows = self._conn.execute("SELECT * FROM qa_knowledge").fetchall()
        return [QAKnowledge(**dict(row)) for row in rows]

    def list_by_status(self, status: str) -> list[QAKnowledge]:
        rows = self._conn.execute("SELECT * FROM qa_knowledge WHERE status = ?", (status,)).fetchall()
        return [QAKnowledge(**dict(row)) for row in rows]

    def list_approved(self) -> list[QAKnowledge]:
        return self.list_by_status("已完成")

    def update(self, qa: QAKnowledge) -> None:
        qa.updated_at = _now()
        self._conn.execute(
            """
            UPDATE qa_knowledge SET
                system_product = :system_product,
                issue_type = :issue_type,
                error_type = :error_type,
                question = :question,
                answer = :answer,
                solution = :solution,
                keywords = :keywords,
                has_image = :has_image,
                doc_name = :doc_name,
                company_id = :company_id,
                source_case_id = :source_case_id,
                source = :source,
                status = :status,
                created_by = :created_by,
                updated_at = :updated_at,
                notes = :notes
            WHERE qa_id = :qa_id
            """,
            {
                "qa_id": qa.qa_id,
                "system_product": qa.system_product,
                "issue_type": qa.issue_type,
                "error_type": qa.error_type,
                "question": qa.question,
                "answer": qa.answer,
                "solution": qa.solution,
                "keywords": qa.keywords,
                "has_image": qa.has_image,
                "doc_name": qa.doc_name,
                "company_id": qa.company_id,
                "source_case_id": qa.source_case_id,
                "source": qa.source,
                "status": qa.status,
                "created_by": qa.created_by,
                "updated_at": qa.updated_at,
                "notes": qa.notes,
            },
        )
        self._conn.commit()

    def delete(self, qa_id: str) -> None:
        self._conn.execute("DELETE FROM qa_knowledge WHERE qa_id = ?", (qa_id,))
        self._conn.commit()


# ---------------------------------------------------------------------------
# MantisRepository
# ---------------------------------------------------------------------------


class MantisRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, ticket: MantisTicket) -> None:
        ticket.synced_at = _now()
        self._conn.execute(
            """
            INSERT INTO mantis_tickets (
                ticket_id, created_time, company_id, summary, priority, status,
                issue_type, module, handler, planned_fix, actual_fix,
                progress, notes, synced_at
            ) VALUES (
                :ticket_id, :created_time, :company_id, :summary, :priority, :status,
                :issue_type, :module, :handler, :planned_fix, :actual_fix,
                :progress, :notes, :synced_at
            )
            ON CONFLICT(ticket_id) DO UPDATE SET
                created_time = excluded.created_time,
                company_id = excluded.company_id,
                summary = excluded.summary,
                priority = excluded.priority,
                status = excluded.status,
                issue_type = excluded.issue_type,
                module = excluded.module,
                handler = excluded.handler,
                planned_fix = excluded.planned_fix,
                actual_fix = excluded.actual_fix,
                progress = excluded.progress,
                notes = excluded.notes,
                synced_at = excluded.synced_at
            """,
            {
                "ticket_id": ticket.ticket_id,
                "created_time": ticket.created_time,
                "company_id": ticket.company_id,
                "summary": ticket.summary,
                "priority": ticket.priority,
                "status": ticket.status,
                "issue_type": ticket.issue_type,
                "module": ticket.module,
                "handler": ticket.handler,
                "planned_fix": ticket.planned_fix,
                "actual_fix": ticket.actual_fix,
                "progress": ticket.progress,
                "notes": ticket.notes,
                "synced_at": ticket.synced_at,
            },
        )
        self._conn.commit()

    def get_by_id(self, ticket_id: str) -> MantisTicket | None:
        row = self._conn.execute("SELECT * FROM mantis_tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        if row is None:
            return None
        return MantisTicket(**dict(row))

    def list_all(self) -> list[MantisTicket]:
        rows = self._conn.execute("SELECT * FROM mantis_tickets").fetchall()
        return [MantisTicket(**dict(row)) for row in rows]


# ---------------------------------------------------------------------------
# RuleRepository
# ---------------------------------------------------------------------------


class RuleRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, rule: ClassificationRule) -> None:
        rule.created_at = _now()
        cursor = self._conn.execute(
            """
            INSERT INTO classification_rules (rule_type, pattern, value, priority, enabled, created_at)
            VALUES (:rule_type, :pattern, :value, :priority, :enabled, :created_at)
            """,
            {
                "rule_type": rule.rule_type,
                "pattern": rule.pattern,
                "value": rule.value,
                "priority": rule.priority,
                "enabled": 1 if rule.enabled else 0,
                "created_at": rule.created_at,
            },
        )
        rule.rule_id = cursor.lastrowid
        self._conn.commit()

    def list_by_type(self, rule_type: str) -> list[ClassificationRule]:
        rows = self._conn.execute(
            """
            SELECT * FROM classification_rules
            WHERE rule_type = ? AND enabled = 1
            ORDER BY priority ASC
            """,
            (rule_type,),
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["enabled"] = bool(d["enabled"])
            result.append(ClassificationRule(**d))
        return result

    def update(self, rule: ClassificationRule) -> None:
        if rule.rule_id is None:
            return
        self._conn.execute(
            """
            UPDATE classification_rules
            SET pattern = :pattern, value = :value, priority = :priority
            WHERE rule_id = :rule_id
            """,
            {"pattern": rule.pattern, "value": rule.value, "priority": rule.priority, "rule_id": rule.rule_id},
        )
        self._conn.commit()

    def delete(self, rule_id: int | None) -> None:
        if rule_id is None:
            return
        self._conn.execute("DELETE FROM classification_rules WHERE rule_id = ?", (rule_id,))
        self._conn.commit()

    def export_csv(self, path) -> None:
        """將所有啟用中的規則匯出至 CSV 檔案。"""
        import csv
        from pathlib import Path

        sql = (
            "SELECT rule_type, pattern, value, priority"
            " FROM classification_rules"
            " WHERE enabled = 1 ORDER BY rule_type, priority ASC"
        )
        rows = self._conn.execute(sql).fetchall()
        with Path(path).open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["rule_type", "pattern", "value", "priority"])
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))

    def import_csv(self, path) -> tuple[int, int]:
        """從 CSV 檔案批次匯入規則。返回 (imported, skipped) 計數。"""
        import csv
        from pathlib import Path

        imported = 0
        skipped = 0
        with Path(path).open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rule_type = row.get("rule_type", "").strip()
                pattern = row.get("pattern", "").strip()
                value = row.get("value", "").strip()
                if not rule_type or not pattern or not value:
                    skipped += 1
                    continue
                try:
                    priority = int(row.get("priority", 0) or 0)
                except ValueError:
                    priority = 0
                self.insert(
                    ClassificationRule(
                        rule_type=rule_type,
                        pattern=pattern,
                        value=value,
                        priority=priority,
                    )
                )
                imported += 1
        return imported, skipped


# ---------------------------------------------------------------------------
# ProcessedFileRepository
# ---------------------------------------------------------------------------


class ProcessedFileRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, pf: ProcessedFile) -> None:
        pf.processed_at = _now()
        self._conn.execute(
            """
            INSERT OR IGNORE INTO processed_files (file_hash, filename, message_id, processed_at)
            VALUES (:file_hash, :filename, :message_id, :processed_at)
            """,
            {
                "file_hash": pf.file_hash,
                "filename": pf.filename,
                "message_id": pf.message_id,
                "processed_at": pf.processed_at,
            },
        )
        self._conn.commit()

    def exists(self, file_hash: str) -> bool:
        row = self._conn.execute("SELECT 1 FROM processed_files WHERE file_hash = ?", (file_hash,)).fetchone()
        return row is not None


# ---------------------------------------------------------------------------
# SynonymRepository
# ---------------------------------------------------------------------------


class SynonymRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, syn: Synonym) -> None:
        cursor = self._conn.execute(
            "INSERT INTO synonyms (word, synonym, group_name) VALUES (?, ?, ?)",
            (syn.word, syn.synonym, syn.group_name),
        )
        syn.id = cursor.lastrowid
        self._conn.commit()

    def get_synonyms(self, word: str) -> list[str]:
        rows = self._conn.execute("SELECT synonym FROM synonyms WHERE word = ?", (word,)).fetchall()
        return [row[0] for row in rows]

    def get_group_words(self, group_name: str) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT word FROM synonyms WHERE group_name = ?
            UNION
            SELECT synonym FROM synonyms WHERE group_name = ?
            """,
            (group_name, group_name),
        ).fetchall()
        return [row[0] for row in rows]

    def list_groups(self) -> list[str]:
        rows = self._conn.execute("SELECT DISTINCT group_name FROM synonyms").fetchall()
        return [row[0] for row in rows]

    def delete_group(self, group_name: str) -> None:
        self._conn.execute("DELETE FROM synonyms WHERE group_name = ?", (group_name,))
        self._conn.commit()


# ---------------------------------------------------------------------------
# CaseMantisRepository
# ---------------------------------------------------------------------------


class CaseMantisRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def link(self, link: CaseMantisLink) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO case_mantis (case_id, ticket_id) VALUES (?, ?)",
            (link.case_id, link.ticket_id),
        )
        self._conn.commit()

    def get_tickets_for_case(self, case_id: str) -> list[str]:
        rows = self._conn.execute("SELECT ticket_id FROM case_mantis WHERE case_id = ?", (case_id,)).fetchall()
        return [row[0] for row in rows]

    def get_cases_for_ticket(self, ticket_id: str) -> list[str]:
        rows = self._conn.execute("SELECT case_id FROM case_mantis WHERE ticket_id = ?", (ticket_id,)).fetchall()
        return [row[0] for row in rows]
