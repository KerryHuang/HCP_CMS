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

    def test_phrase_match_ranks_above_distant_match(self, fts: FTSManager) -> None:
        """多詞查詢時，tokens 相鄰出現的 QA 應排在分散出現的 QA 之前。

        重現使用者回報：建立 question='資料修改需求', keywords='資料修改' 的 QA 後
        搜尋'資料修改'，該 QA 應排在前面，而非被「answer 內分散出現 資料 與 修改」
        的舊 QA 擠到第 12 名。
        """
        # 分散出現：question/answer 各自含 資料、修改 多次，但「資料」與「修改」不相鄰
        fts.index_qa(
            "QA-OLD",
            "如何修改員工姓名",
            "可進行修改：先到資料建檔後修改設定資料內容，再修改設定",
            None,
            None,
        )
        # 相鄰出現：keywords 與 question 直接是「資料修改」
        fts.index_qa(
            "QA-NEW",
            "資料修改需求",
            "與內部確認後，因該欄位敏感，目前暫無法提供 SQL 語法供客戶自行更新",
            None,
            "資料修改",
        )

        results = fts.search_qa("資料修改")
        qa_ids = [r["qa_id"] for r in results]
        assert "QA-NEW" in qa_ids, f"QA-NEW 應出現在結果內：{qa_ids}"
        assert "QA-OLD" in qa_ids, f"QA-OLD 應出現在結果內：{qa_ids}"
        assert qa_ids.index("QA-NEW") < qa_ids.index("QA-OLD"), (
            f"預期 QA-NEW（相鄰）排在 QA-OLD（分散）之前，實際順序：{qa_ids}"
        )

    def test_single_token_query_unchanged(self, fts: FTSManager) -> None:
        """單一 token 查詢不應受 phrase 加強影響，行為與現況一致。"""
        fts.index_qa("QA-A", "薪資計算問題", "進入模組", None, None)
        fts.index_qa("QA-B", "另一個無關問題", "別的內容", None, None)
        results = fts.search_qa("薪資")
        qa_ids = [r["qa_id"] for r in results]
        assert "QA-A" in qa_ids
        assert "QA-B" not in qa_ids
