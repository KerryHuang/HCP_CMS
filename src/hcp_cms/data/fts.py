"""FTS5 full-text search manager with jieba tokenization and synonym expansion."""

from __future__ import annotations

import sqlite3

import jieba


class FTSManager:
    """Manages FTS5 virtual tables for QA knowledge and CS cases."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Tokenization
    # ------------------------------------------------------------------

    def tokenize(self, text: str) -> str:
        """Tokenize Chinese text using jieba, return space-separated tokens."""
        tokens = jieba.cut(text, cut_all=False)
        return " ".join(t for t in tokens if t.strip())

    # ------------------------------------------------------------------
    # Synonym expansion
    # ------------------------------------------------------------------

    def _expand_with_synonyms(self, query: str) -> str:
        """Expand query terms with synonyms from synonyms table.

        Tokenizes the query with jieba first, then looks up synonyms in three ways:
        1. Direct: word == query term  → collect synonym values
        2. Reverse: synonym == query term → collect word values
        3. Group-based: find group_name for the term, collect all words/synonyms in that group

        Multi-character tokens are also expanded into individual characters as OR alternatives
        to handle cases where jieba splits the same phrase differently depending on context.

        Returns 'term1 OR term2 OR ...' (de-duplicated, original term included).
        """
        terms: set[str] = set()
        # Tokenize query through jieba to align with how documents are indexed
        jieba_tokens = [t for t in jieba.cut(query, cut_all=False) if t.strip()]
        for token in jieba_tokens:
            terms.add(token)
            # Also add individual characters to handle context-dependent segmentation
            if len(token) > 1:
                terms.update(list(token))

        for token in list(terms.copy()):
            # Direct synonyms: word = token → get synonym
            rows = self._conn.execute(
                "SELECT synonym, group_name FROM synonyms WHERE word = ?", (token,)
            ).fetchall()
            group_names: set[str] = set()
            for row in rows:
                terms.add(row[0])
                if row[1]:
                    group_names.add(row[1])

            # Reverse synonyms: synonym = token → get word
            rows = self._conn.execute(
                "SELECT word, group_name FROM synonyms WHERE synonym = ?", (token,)
            ).fetchall()
            for row in rows:
                terms.add(row[0])
                if row[1]:
                    group_names.add(row[1])

            # Group-based: collect all terms in same group
            for group in group_names:
                group_rows = self._conn.execute(
                    "SELECT word, synonym FROM synonyms WHERE group_name = ?", (group,)
                ).fetchall()
                for row in group_rows:
                    terms.add(row[0])
                    terms.add(row[1])

        return " OR ".join(terms)

    # ------------------------------------------------------------------
    # QA FTS
    # ------------------------------------------------------------------

    def index_qa(
        self,
        qa_id: str,
        question: str | None,
        answer: str | None,
        solution: str | None,
        keywords: str | None,
    ) -> None:
        """DELETE then INSERT into qa_fts. Tokenize all text fields before inserting."""
        question = question or ""
        answer = answer or ""
        solution = solution or ""
        keywords = keywords or ""

        self._conn.execute("DELETE FROM qa_fts WHERE qa_id = ?", (qa_id,))
        self._conn.execute(
            "INSERT INTO qa_fts (qa_id, question, answer, solution, keywords) VALUES (?,?,?,?,?)",
            (
                qa_id,
                self.tokenize(question),
                self.tokenize(answer),
                self.tokenize(solution),
                self.tokenize(keywords),
            ),
        )
        self._conn.commit()

    def remove_qa_index(self, qa_id: str) -> None:
        """Remove a QA entry from the FTS index."""
        self._conn.execute("DELETE FROM qa_fts WHERE qa_id = ?", (qa_id,))
        self._conn.commit()

    def update_qa_index(
        self,
        qa_id: str,
        question: str | None,
        answer: str | None,
        solution: str | None,
        keywords: str | None,
    ) -> None:
        """Update QA FTS index (delete + insert)."""
        self.index_qa(qa_id, question, answer, solution, keywords)

    def search_qa(self, query: str, limit: int = 50) -> list[dict[str, str]]:
        """Search qa_fts with synonym expansion.

        Returns list of dicts with keys 'qa_id' and 'rank'.
        """
        expanded = self._expand_with_synonyms(query)
        try:
            rows = self._conn.execute(
                "SELECT qa_id, rank FROM qa_fts WHERE qa_fts MATCH ? ORDER BY rank LIMIT ?",
                (expanded, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [{"qa_id": row[0], "rank": str(row[1])} for row in rows]

    # ------------------------------------------------------------------
    # Case FTS
    # ------------------------------------------------------------------

    def index_case(
        self,
        case_id: str,
        subject: str | None,
        progress: str | None,
        notes: str | None,
    ) -> None:
        """DELETE then INSERT into cases_fts. Tokenize all text fields before inserting."""
        subject = subject or ""
        progress = progress or ""
        notes = notes or ""

        self._conn.execute("DELETE FROM cases_fts WHERE case_id = ?", (case_id,))
        self._conn.execute(
            "INSERT INTO cases_fts (case_id, subject, progress, notes) VALUES (?,?,?,?)",
            (
                case_id,
                self.tokenize(subject),
                self.tokenize(progress),
                self.tokenize(notes),
            ),
        )
        self._conn.commit()

    def search_cases(self, query: str, limit: int = 50) -> list[dict[str, str]]:
        """Search cases_fts with synonym expansion.

        Returns list of dicts with keys 'case_id' and 'rank'.
        """
        expanded = self._expand_with_synonyms(query)
        try:
            rows = self._conn.execute(
                "SELECT case_id, rank FROM cases_fts WHERE cases_fts MATCH ? ORDER BY rank LIMIT ?",
                (expanded, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [{"case_id": row[0], "rank": str(row[1])} for row in rows]
