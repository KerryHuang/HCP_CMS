"""Tests for FTSManager — FTS5 full-text search with jieba tokenization."""

from __future__ import annotations

from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.fts import FTSManager


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def fts(db: DatabaseManager) -> FTSManager:
    return FTSManager(db.connection)


class TestFTSManager:
    def test_index_qa_and_search(self, fts: FTSManager) -> None:
        fts.index_qa("QA-001", "員工離職薪資如何計算", "進入薪資模組設定", "按比例計算", "薪資 離職")
        results = fts.search_qa("薪資")
        assert len(results) > 0
        assert results[0]["qa_id"] == "QA-001"

    def test_search_qa_with_synonym_expansion(self, fts: FTSManager, db: DatabaseManager) -> None:
        db.connection.execute(
            "INSERT INTO synonyms (word, synonym, group_name) VALUES (?,?,?)",
            ("薪水", "薪資", "薪資相關"),
        )
        db.connection.commit()
        fts.index_qa("QA-001", "員工薪資計算", "進入薪資模組", None, None)
        results = fts.search_qa("薪水")
        assert len(results) > 0

    def test_search_qa_no_results(self, fts: FTSManager) -> None:
        fts.index_qa("QA-001", "薪資計算", "進入模組", None, None)
        results = fts.search_qa("完全不相關的詞")
        assert len(results) == 0

    def test_index_case_and_search(self, fts: FTSManager) -> None:
        fts.index_case("CS-2026-001", "薪資計算異常", "已回覆客戶", "需確認設定")
        results = fts.search_cases("薪資")
        assert len(results) > 0
        assert results[0]["case_id"] == "CS-2026-001"

    def test_remove_qa_index(self, fts: FTSManager) -> None:
        fts.index_qa("QA-001", "薪資", "回覆", None, None)
        fts.remove_qa_index("QA-001")
        results = fts.search_qa("薪資")
        assert len(results) == 0

    def test_update_qa_index(self, fts: FTSManager) -> None:
        fts.index_qa("QA-001", "舊問題", "舊回覆", None, None)
        fts.update_qa_index("QA-001", "新問題關於請假", "新回覆", None, None)
        assert len(fts.search_qa("請假")) > 0
        assert len(fts.search_qa("舊問題")) == 0

    def test_tokenize_chinese(self, fts: FTSManager) -> None:
        tokens = fts.tokenize("員工離職薪水怎麼算")
        assert isinstance(tokens, str)
        assert " " in tokens
