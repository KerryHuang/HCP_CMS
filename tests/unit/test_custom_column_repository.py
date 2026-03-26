"""CustomColumnRepository 單元測試。"""

from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.repositories import CustomColumnRepository


@pytest.fixture
def db(tmp_db_path: Path):
    mgr = DatabaseManager(tmp_db_path)
    mgr.initialize()
    yield mgr
    mgr.close()


@pytest.fixture
def repo(db: DatabaseManager):
    return CustomColumnRepository(db.connection)


class TestNextColKey:
    def test_first_key_is_cx_1(self, repo):
        assert repo.next_col_key() == "cx_1"

    def test_second_key_after_insert(self, repo):
        repo.insert("cx_1", "測試欄A", 1)
        assert repo.next_col_key() == "cx_2"


class TestInsert:
    def test_insert_and_list(self, repo):
        repo.insert("cx_1", "客製欄位", 1)
        cols = repo.list_all()
        assert len(cols) == 1
        assert cols[0].col_key == "cx_1"
        assert cols[0].col_label == "客製欄位"
        assert cols[0].visible_in_list is True

    def test_insert_idempotent(self, repo):
        repo.insert("cx_1", "欄A", 1)
        repo.insert("cx_1", "欄A重複", 1)  # INSERT OR IGNORE
        assert len(repo.list_all()) == 1

    def test_visible_in_list_bool_conversion(self, repo):
        repo.insert("cx_1", "欄A", 1)
        # 直接塞 INTEGER 0 進去
        repo._conn.execute("UPDATE custom_columns SET visible_in_list=0 WHERE col_key='cx_1'")
        cols = repo.list_all()
        assert cols[0].visible_in_list is False


class TestAddColumnToCases:
    def test_adds_column_to_cs_cases(self, db: DatabaseManager, repo):
        repo.add_column_to_cases("cx_1")
        cols = {row[1] for row in db.connection.execute("PRAGMA table_info(cs_cases)")}
        assert "cx_1" in cols

    def test_idempotent_when_column_exists(self, db: DatabaseManager, repo):
        repo.add_column_to_cases("cx_1")
        repo.add_column_to_cases("cx_1")  # 不應拋錯
        cols = {row[1] for row in db.connection.execute("PRAGMA table_info(cs_cases)")}
        assert "cx_1" in cols

    def test_raises_on_invalid_col_key(self, repo):
        with pytest.raises(ValueError, match="非法 col_key"):
            repo.add_column_to_cases("bad_key")

    def test_raises_on_sql_injection_attempt(self, repo):
        with pytest.raises(ValueError, match="非法 col_key"):
            repo.add_column_to_cases("cx_1; DROP TABLE cs_cases--")
