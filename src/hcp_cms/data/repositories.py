"""Repository classes for all data entities."""

from __future__ import annotations

import re as _re
import sqlite3
from datetime import datetime

from hcp_cms.data.models import (
    Case,
    CaseLog,
    CaseMantisLink,
    ClassificationRule,
    Company,
    CustomColumn,
    MantisTicket,
    ProcessedFile,
    QAKnowledge,
    Synonym,
)

_COL_KEY_RE = _re.compile(r"^cx_\d+$")


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
        self._custom_col_repo = CustomColumnRepository(conn)
        self._custom_cols = self._custom_col_repo.list_all()

    def _build_select(self) -> str:
        static = (
            "case_id, company_id, subject, status, priority, sent_time, "
            "contact_person, contact_method, system_product, issue_type, error_type, "
            "impact_period, progress, handler, actual_reply, reply_time, notes, "
            "rd_assignee, reply_count, linked_case_id, source, created_at, updated_at"
        )
        if not self._custom_cols:
            return f"SELECT {static} FROM cs_cases"
        cx_cols = ", ".join(col.col_key for col in self._custom_cols)
        return f"SELECT {static}, {cx_cols} FROM cs_cases"

    def _row_to_case(self, row: sqlite3.Row) -> Case:
        d = dict(row)
        extra = {col.col_key: d.pop(col.col_key, None) for col in self._custom_cols}
        return Case(**d, extra_fields=extra)

    def reload_custom_columns(self) -> None:
        self._custom_cols = self._custom_col_repo.list_all()

    def update_extra_field(self, case_id: str, col_key: str, value: str | None) -> None:
        if not _COL_KEY_RE.match(col_key):
            raise ValueError(f"非法 col_key：{col_key!r}")
        self._conn.execute(
            f"UPDATE cs_cases SET {col_key} = :v WHERE case_id = :id",
            {"v": value, "id": case_id},
        )
        self._conn.commit()

    def insert(self, case: Case) -> None:
        now = _now()
        case.created_at = now
        case.updated_at = now
        self._conn.execute(
            """
            INSERT INTO cs_cases (
                case_id, contact_method, status, priority, sent_time,
                company_id, contact_person, subject, system_product, issue_type,
                error_type, impact_period, progress, actual_reply, reply_time, notes,
                rd_assignee, handler, reply_count, linked_case_id, source,
                created_at, updated_at
            ) VALUES (
                :case_id, :contact_method, :status, :priority, :sent_time,
                :company_id, :contact_person, :subject, :system_product, :issue_type,
                :error_type, :impact_period, :progress, :actual_reply, :reply_time, :notes,
                :rd_assignee, :handler, :reply_count, :linked_case_id, :source,
                :created_at, :updated_at
            )
            """,
            {
                "case_id": case.case_id,
                "contact_method": case.contact_method,
                "status": case.status,
                "priority": case.priority,
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
                "reply_time": case.reply_time,
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
        sql = self._build_select() + " WHERE case_id = ?"
        row = self._conn.execute(sql, (case_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_case(row)

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

    def list_all(self) -> list[Case]:
        rows = self._conn.execute(self._build_select() + " ORDER BY sent_time DESC").fetchall()
        return [self._row_to_case(r) for r in rows]

    def list_by_status(self, status: str) -> list[Case]:
        rows = self._conn.execute(self._build_select() + " WHERE status = ?", (status,)).fetchall()
        return [self._row_to_case(r) for r in rows]

    def list_by_month(self, year: int, month: int) -> list[Case]:
        prefix = f"{year}/{month:02d}%"
        rows = self._conn.execute(self._build_select() + " WHERE sent_time LIKE ?", (prefix,)).fetchall()
        return [self._row_to_case(r) for r in rows]

    def list_by_date_range(self, start: str, end: str) -> list[Case]:
        """查詢 sent_time 在 [start, end] 區間的案件（格式 YYYY/MM/DD）。"""
        end_inclusive = end + " 23:59:59"
        rows = self._conn.execute(
            self._build_select() + " WHERE sent_time >= ? AND sent_time <= ?",
            (start, end_inclusive),
        ).fetchall()
        return [self._row_to_case(r) for r in rows]

    def list_recently_created(self, minutes: int = 10) -> list[Case]:
        """查詢 created_at 在近 N 分鐘內的案件。"""
        from datetime import datetime, timedelta

        cutoff = (datetime.now() - timedelta(minutes=minutes)).strftime("%Y/%m/%d %H:%M:%S")
        rows = self._conn.execute(
            self._build_select() + " WHERE created_at >= ? ORDER BY created_at DESC",
            (cutoff,),
        ).fetchall()
        return [self._row_to_case(r) for r in rows]

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
                reply_time = :reply_time,
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
                "reply_time": case.reply_time,
                "notes": case.notes,
                "rd_assignee": case.rd_assignee,
                "handler": case.handler,
                "reply_count": case.reply_count,
                "linked_case_id": case.linked_case_id,
                "source": case.source,
                "updated_at": case.updated_at,
            },
        )
        # 同步 FTS5 索引（subject / progress / notes 為可搜尋欄位）
        self._conn.execute(
            """
            UPDATE cases_fts SET
                subject  = :subject,
                progress = :progress,
                notes    = :notes
            WHERE case_id = :case_id
            """,
            {
                "case_id": case.case_id,
                "subject": case.subject,
                "progress": case.progress,
                "notes": case.notes,
            },
        )
        # 同步「待審查」KMS 條目的分類欄位
        self._conn.execute(
            """
            UPDATE qa_knowledge SET
                system_product = :system_product,
                issue_type     = :issue_type,
                error_type     = :error_type,
                company_id     = :company_id,
                updated_at     = :updated_at
            WHERE source_case_id = :case_id AND status = '待審查'
            """,
            {
                "case_id": case.case_id,
                "system_product": case.system_product,
                "issue_type": case.issue_type,
                "error_type": case.error_type,
                "company_id": case.company_id,
                "updated_at": case.updated_at,
            },
        )
        self._conn.commit()

    def count_by_month(self, year: int, month: int) -> int:
        prefix = f"{year}/{month:02d}%"
        row = self._conn.execute("SELECT COUNT(*) FROM cs_cases WHERE sent_time LIKE ?", (prefix,)).fetchone()
        return row[0] if row else 0

    def delete(self, case_id: str) -> None:
        """刪除單一案件，含 cascade 清除。KMS 僅刪除 status='待審查' 的條目；
        已審核條目的 source_case_id 設為 NULL 以解除 FK 約束。"""
        self._conn.execute("DELETE FROM case_mantis WHERE case_id = :id", {"id": case_id})
        self._conn.execute("DELETE FROM case_logs WHERE case_id = :id", {"id": case_id})
        self._conn.execute("DELETE FROM cases_fts WHERE case_id = :id", {"id": case_id})
        # 刪除「待審查」KMS；其餘已審核條目解除案件關聯（source_case_id → NULL）
        self._conn.execute(
            "DELETE FROM qa_knowledge WHERE source_case_id = :id AND status = '待審查'",
            {"id": case_id},
        )
        self._conn.execute(
            "UPDATE qa_knowledge SET source_case_id = NULL WHERE source_case_id = :id",
            {"id": case_id},
        )
        self._conn.execute("DELETE FROM cs_cases WHERE case_id = :id", {"id": case_id})
        self._conn.commit()

    def delete_by_date_range(self, start: str, end: str) -> int:
        """刪除 created_at 在 [start, end] 範圍內的所有案件，回傳刪除筆數。
        start/end 格式為 'YYYY/MM/DD'。"""
        rows = self._conn.execute(
            "SELECT case_id FROM cs_cases WHERE created_at >= :s AND created_at <= :e || ' 23:59:59'",
            {"s": start, "e": end},
        ).fetchall()
        case_ids = [r[0] for r in rows]
        for cid in case_ids:
            self.delete(cid)
        return len(case_ids)


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
                progress, notes, synced_at,
                severity, reporter, last_updated, description, notes_json, notes_count
            ) VALUES (
                :ticket_id, :created_time, :company_id, :summary, :priority, :status,
                :issue_type, :module, :handler, :planned_fix, :actual_fix,
                :progress, :notes, :synced_at,
                :severity, :reporter, :last_updated, :description, :notes_json, :notes_count
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
                synced_at = excluded.synced_at,
                severity = excluded.severity,
                reporter = excluded.reporter,
                last_updated = excluded.last_updated,
                description = excluded.description,
                notes_json = excluded.notes_json,
                notes_count = excluded.notes_count
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
                "severity": ticket.severity,
                "reporter": ticket.reporter,
                "last_updated": ticket.last_updated,
                "description": ticket.description,
                "notes_json": ticket.notes_json,
                "notes_count": ticket.notes_count,
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

    def exists_by_message_id(self, message_id: str) -> bool:
        """以 message_id 的 SHA256 hash 檢查是否已處理。"""
        import hashlib

        h = hashlib.sha256(message_id.encode()).hexdigest()
        return self.exists(h)


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

    def _row_to_link(self, row: sqlite3.Row) -> CaseMantisLink:
        d = dict(row)
        return CaseMantisLink(
            case_id=d["case_id"],
            ticket_id=d["ticket_id"],
            summary=d.get("summary"),
            issue_date=d.get("issue_date"),
        )

    def insert(self, link: CaseMantisLink) -> None:
        """新增 case-mantis 連結記錄（INSERT OR IGNORE，避免主鍵衝突）。"""
        self._conn.execute(
            """
            INSERT OR IGNORE INTO case_mantis (case_id, ticket_id, summary, issue_date)
            VALUES (:case_id, :ticket_id, :summary, :issue_date)
            """,
            {
                "case_id": link.case_id,
                "ticket_id": link.ticket_id,
                "summary": link.summary,
                "issue_date": link.issue_date,
            },
        )
        self._conn.commit()

    def link(self, link: CaseMantisLink) -> None:
        """向後相容的連結方法（等同 insert，不含 summary/issue_date）。"""
        self.insert(link)

    def list_by_case_id(self, case_id: str) -> list[CaseMantisLink]:
        """取得指定案件的所有 Mantis 連結記錄。"""
        rows = self._conn.execute(
            "SELECT case_id, ticket_id, summary, issue_date FROM case_mantis WHERE case_id = ?",
            (case_id,),
        ).fetchall()
        return [self._row_to_link(row) for row in rows]

    def get_tickets_for_case(self, case_id: str) -> list[str]:
        rows = self._conn.execute("SELECT ticket_id FROM case_mantis WHERE case_id = ?", (case_id,)).fetchall()
        return [row[0] for row in rows]

    def get_cases_for_ticket(self, ticket_id: str) -> list[str]:
        rows = self._conn.execute("SELECT case_id FROM case_mantis WHERE ticket_id = ?", (ticket_id,)).fetchall()
        return [row[0] for row in rows]

    def unlink(self, case_id: str, ticket_id: str) -> None:
        self._conn.execute(
            "DELETE FROM case_mantis WHERE case_id = ? AND ticket_id = ?",
            (case_id, ticket_id),
        )
        self._conn.commit()


# ---------------------------------------------------------------------------
# CaseLogRepository
# ---------------------------------------------------------------------------


class CaseLogRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def next_log_id(self) -> str:
        today = datetime.now().strftime("%Y%m%d")
        prefix = f"LOG-{today}-"
        row = self._conn.execute(
            "SELECT MAX(log_id) FROM case_logs WHERE log_id LIKE ?",
            (f"{prefix}%",),
        ).fetchone()
        max_id: str | None = row[0] if row else None
        try:
            next_num = int(max_id[-3:]) + 1 if max_id else 1
        except (TypeError, ValueError):
            next_num = 1
        return f"{prefix}{next_num:03d}"

    def insert(self, log: CaseLog) -> None:
        self._conn.execute(
            """
            INSERT INTO case_logs (log_id, case_id, direction, content, mantis_ref, logged_by, logged_at)
            VALUES (:log_id, :case_id, :direction, :content, :mantis_ref, :logged_by, :logged_at)
            """,
            {
                "log_id": log.log_id,
                "case_id": log.case_id,
                "direction": log.direction,
                "content": log.content,
                "mantis_ref": log.mantis_ref,
                "logged_by": log.logged_by,
                "logged_at": log.logged_at,
            },
        )
        self._conn.commit()

    def list_by_case(self, case_id: str) -> list[CaseLog]:
        rows = self._conn.execute(
            "SELECT * FROM case_logs WHERE case_id = ? ORDER BY logged_at ASC",
            (case_id,),
        ).fetchall()
        return [CaseLog(**dict(row)) for row in rows]

    def delete(self, log_id: str) -> None:
        self._conn.execute("DELETE FROM case_logs WHERE log_id = ?", (log_id,))
        self._conn.commit()


# ---------------------------------------------------------------------------
# CustomColumnRepository
# ---------------------------------------------------------------------------


class CustomColumnRepository:
    """自訂欄位中繼資料 CRUD。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def next_col_key(self) -> str:
        row = self._conn.execute("SELECT COALESCE(MAX(col_order), 0) + 1 FROM custom_columns").fetchone()
        n = row[0] if row else 1
        return f"cx_{n}"

    def insert(self, col_key: str, col_label: str, col_order: int) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO custom_columns (col_key, col_label, col_order, visible_in_list)"
            " VALUES (:k, :l, :o, 1)",
            {"k": col_key, "l": col_label, "o": col_order},
        )
        self._conn.commit()

    def list_all(self) -> list[CustomColumn]:
        rows = self._conn.execute(
            "SELECT col_key, col_label, col_order, visible_in_list FROM custom_columns ORDER BY col_order ASC"
        ).fetchall()
        return [
            CustomColumn(
                col_key=r["col_key"],
                col_label=r["col_label"],
                col_order=r["col_order"],
                visible_in_list=bool(r["visible_in_list"]),
            )
            for r in rows
        ]

    def add_column_to_cases(self, col_key: str) -> None:
        if not _COL_KEY_RE.match(col_key):
            raise ValueError(f"非法 col_key：{col_key!r}")
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(cs_cases)")}
        if col_key not in existing:
            self._conn.execute(f"ALTER TABLE cs_cases ADD COLUMN {col_key} TEXT")
            self._conn.commit()
