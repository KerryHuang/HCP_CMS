"""KMS knowledge management — search, CRUD, auto-extract, Excel import/export."""

import sqlite3
from pathlib import Path

import openpyxl

from hcp_cms.data.models import Case, QAKnowledge
from hcp_cms.data.repositories import QARepository
from hcp_cms.data.fts import FTSManager
from hcp_cms.core.anonymizer import Anonymizer


# Question detection patterns
_QUESTION_PATTERNS = ["請問", "如何", "是否", "怎麼", "可否", "能否", "為什麼", "為何"]


class KMSEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._qa_repo = QARepository(conn)
        self._fts = FTSManager(conn)
        self._anonymizer = Anonymizer()

    def search(self, query: str, system_product: str | None = None) -> list[QAKnowledge]:
        """Search QA via FTS5, return full QAKnowledge objects."""
        fts_results = self._fts.search_qa(query)
        qa_list = []
        for result in fts_results:
            qa = self._qa_repo.get_by_id(result["qa_id"])
            if qa:
                if system_product and qa.system_product != system_product:
                    continue
                qa_list.append(qa)
        return qa_list

    def create_qa(
        self,
        question: str,
        answer: str,
        solution: str | None = None,
        keywords: str | None = None,
        system_product: str | None = None,
        issue_type: str | None = None,
        error_type: str | None = None,
        source: str = "manual",
        source_case_id: str | None = None,
        created_by: str | None = None,
    ) -> QAKnowledge:
        """Create a new QA entry and index it."""
        qa_id = self._qa_repo.next_qa_id()
        qa = QAKnowledge(
            qa_id=qa_id,
            question=question,
            answer=answer,
            solution=solution,
            keywords=keywords,
            system_product=system_product,
            issue_type=issue_type,
            error_type=error_type,
            source=source,
            source_case_id=source_case_id,
            created_by=created_by,
        )
        self._qa_repo.insert(qa)
        self._fts.index_qa(qa_id, question, answer, solution, keywords)
        return qa

    def update_qa(self, qa_id: str, **fields: str | None) -> QAKnowledge | None:
        """Update QA fields and rebuild FTS index."""
        qa = self._qa_repo.get_by_id(qa_id)
        if not qa:
            return None
        for key, value in fields.items():
            if hasattr(qa, key):
                setattr(qa, key, value)
        self._qa_repo.update(qa)
        self._fts.update_qa_index(qa_id, qa.question, qa.answer, qa.solution, qa.keywords)
        return qa

    def delete_qa(self, qa_id: str) -> None:
        """Delete QA and remove FTS index."""
        self._qa_repo.delete(qa_id)
        self._fts.remove_qa_index(qa_id)

    def auto_extract_qa(
        self,
        case: Case,
        company_domain: str = "",
        company_aliases: list[str] | None = None,
    ) -> QAKnowledge | None:
        """Auto-extract QA from a case if it contains a question pattern.
        Returns QA with source='email' or None if no question detected."""
        if not case.subject:
            return None

        text = f"{case.subject} {case.progress or ''}"
        has_question = any(p in text for p in _QUESTION_PATTERNS)
        if not has_question:
            return None

        question = self._anonymizer.anonymize(case.subject, company_domain, company_aliases)
        answer = self._anonymizer.anonymize(case.progress or "", company_domain, company_aliases)

        return self.create_qa(
            question=question,
            answer=answer,
            system_product=case.system_product,
            issue_type=case.issue_type,
            error_type=case.error_type,
            source="email",
            source_case_id=case.case_id,
        )

    def import_from_excel(self, file_path: Path) -> int:
        """Import QA entries from Excel file. Returns count imported."""
        wb = openpyxl.load_workbook(str(file_path), read_only=True)
        ws = wb.active
        count = 0

        rows = list(ws.iter_rows(min_row=2, values_only=True))  # Skip header
        for row in rows:
            if len(row) < 2 or not row[0]:
                continue
            question = str(row[0]) if row[0] else ""
            answer = str(row[1]) if len(row) > 1 and row[1] else ""
            solution = str(row[2]) if len(row) > 2 and row[2] else None
            keywords = str(row[3]) if len(row) > 3 and row[3] else None

            if question:
                self.create_qa(question=question, answer=answer, solution=solution, keywords=keywords, source="import")
                count += 1

        wb.close()
        return count

    def export_to_excel(self, file_path: Path, qa_list: list[QAKnowledge] | None = None) -> Path:
        """Export QA entries to Excel. If qa_list is None, export all."""
        if qa_list is None:
            qa_list = self._qa_repo.list_all()

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "QA知識庫"

        # Header
        headers = ["QA編號", "問題", "回覆", "解決方案", "關鍵字", "產品", "問題類型", "錯誤類型", "來源", "建立日期"]
        ws.append(headers)

        for qa in qa_list:
            ws.append([
                qa.qa_id, qa.question, qa.answer, qa.solution, qa.keywords,
                qa.system_product, qa.issue_type, qa.error_type, qa.source, qa.created_at,
            ])

        wb.save(str(file_path))
        return file_path
