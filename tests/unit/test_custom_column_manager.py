"""CustomColumnManager 單元測試。"""

from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.core.custom_column_manager import CustomColumnManager


@pytest.fixture
def db(tmp_db_path: Path):
    mgr = DatabaseManager(tmp_db_path)
    mgr.initialize()
    yield mgr
    mgr.close()


@pytest.fixture
def mgr(db: DatabaseManager):
    return CustomColumnManager(db.connection)


class TestCreateColumn:
    def test_creates_column_with_label(self, db, mgr):
        col = mgr.create_column("客製欄A")
        assert col.col_key == "cx_1"
        assert col.col_label == "客製欄A"

    def test_second_column_is_cx_2(self, db, mgr):
        mgr.create_column("欄A")
        col = mgr.create_column("欄B")
        assert col.col_key == "cx_2"

    def test_column_exists_in_cs_cases(self, db, mgr):
        mgr.create_column("新欄")
        cols = {row[1] for row in db.connection.execute("PRAGMA table_info(cs_cases)")}
        assert "cx_1" in cols


class TestListColumns:
    def test_list_columns_empty(self, mgr):
        assert mgr.list_columns() == []

    def test_list_columns_ordered(self, db, mgr):
        mgr.create_column("欄A")
        mgr.create_column("欄B")
        cols = mgr.list_columns()
        assert [c.col_key for c in cols] == ["cx_1", "cx_2"]


class TestGetMappableColumns:
    def test_static_cols_included(self, mgr):
        pairs = mgr.get_mappable_columns()
        keys = [k for k, _ in pairs]
        assert "subject" in keys
        assert "status" in keys
        assert "sent_time" in keys

    def test_custom_cols_at_end(self, db, mgr):
        mgr.create_column("客製欄")
        pairs = mgr.get_mappable_columns()
        last_key, last_label = pairs[-1]
        assert last_key == "cx_1"
        assert last_label == "客製欄"

    def test_labels_are_chinese(self, mgr):
        pairs = mgr.get_mappable_columns()
        label_map = dict(pairs)
        assert label_map["subject"] == "主旨"
        assert label_map["rd_assignee"] == "RD 負責人"
