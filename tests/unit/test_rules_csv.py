"""Tests for rules CSV import/export functionality."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import ClassificationRule
from hcp_cms.data.repositories import RuleRepository


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def repo(db: DatabaseManager) -> RuleRepository:
    return RuleRepository(db.connection)


class TestRulesCSVExport:
    def test_export_empty(self, repo: RuleRepository, tmp_path: Path):
        """匯出空規則應產生只有標頭的 CSV。"""
        out = tmp_path / "rules.csv"
        repo.export_csv(out)
        rows = list(csv.DictReader(out.open(encoding="utf-8-sig")))
        assert rows == []

    def test_export_single_rule(self, repo: RuleRepository, tmp_path: Path):
        """匯出單筆規則應正確寫入欄位。"""
        repo.insert(ClassificationRule(rule_type="handler", pattern="薪資", value="王小明", priority=10))
        out = tmp_path / "rules.csv"
        repo.export_csv(out)
        rows = list(csv.DictReader(out.open(encoding="utf-8-sig")))
        assert len(rows) == 1
        assert rows[0]["rule_type"] == "handler"
        assert rows[0]["pattern"] == "薪資"
        assert rows[0]["value"] == "王小明"
        assert rows[0]["priority"] == "10"

    def test_export_multiple_types(self, repo: RuleRepository, tmp_path: Path):
        """匯出多種類型規則應全部包含。"""
        repo.insert(ClassificationRule(rule_type="handler", pattern="薪資", value="王小明", priority=10))
        repo.insert(ClassificationRule(rule_type="priority", pattern="緊急", value="高", priority=5))
        repo.insert(ClassificationRule(rule_type="issue", pattern="bug", value="BUG", priority=10))
        out = tmp_path / "rules.csv"
        repo.export_csv(out)
        rows = list(csv.DictReader(out.open(encoding="utf-8-sig")))
        assert len(rows) == 3

    def test_export_csv_headers(self, repo: RuleRepository, tmp_path: Path):
        """匯出 CSV 標頭欄位必須正確。"""
        repo.insert(ClassificationRule(rule_type="handler", pattern="測試", value="測試值", priority=0))
        out = tmp_path / "rules.csv"
        repo.export_csv(out)
        reader = csv.DictReader(out.open(encoding="utf-8-sig"))
        assert set(reader.fieldnames) == {"rule_type", "pattern", "value", "priority"}


class TestRulesCSVImport:
    def test_import_single_row(self, repo: RuleRepository, tmp_path: Path):
        """匯入單筆 CSV 應新增至資料庫。"""
        csv_file = tmp_path / "rules.csv"
        csv_file.write_text(
            "rule_type,pattern,value,priority\nhandler,薪資,王小明,10\n",
            encoding="utf-8-sig",
        )
        imported, skipped = repo.import_csv(csv_file)
        assert imported == 1
        assert skipped == 0
        rules = repo.list_by_type("handler")
        assert len(rules) == 1
        assert rules[0].value == "王小明"

    def test_import_multiple_rows(self, repo: RuleRepository, tmp_path: Path):
        """匯入多筆 CSV 應全部寫入資料庫。"""
        csv_file = tmp_path / "rules.csv"
        csv_file.write_text(
            "rule_type,pattern,value,priority\n"
            "handler,薪資,王小明,10\n"
            "handler,報表,陳小華,20\n"
            "progress,緊急,優先處理,5\n",
            encoding="utf-8-sig",
        )
        imported, skipped = repo.import_csv(csv_file)
        assert imported == 3
        assert skipped == 0

    def test_import_skips_invalid_rows(self, repo: RuleRepository, tmp_path: Path):
        """缺少必要欄位的列應跳過並計入 skipped。"""
        csv_file = tmp_path / "rules.csv"
        csv_file.write_text(
            "rule_type,pattern,value,priority\n"
            "handler,,王小明,10\n"   # pattern 為空 → 跳過
            "handler,薪資,,10\n"    # value 為空 → 跳過
            "handler,報表,陳小華,20\n",  # 正確
            encoding="utf-8-sig",
        )
        imported, skipped = repo.import_csv(csv_file)
        assert imported == 1
        assert skipped == 2

    def test_import_default_priority(self, repo: RuleRepository, tmp_path: Path):
        """priority 欄位可省略，預設為 0。"""
        csv_file = tmp_path / "rules.csv"
        csv_file.write_text(
            "rule_type,pattern,value\nhandler,薪資,王小明\n",
            encoding="utf-8-sig",
        )
        imported, skipped = repo.import_csv(csv_file)
        assert imported == 1
        rules = repo.list_by_type("handler")
        assert rules[0].priority == 0

    def test_import_roundtrip(self, repo: RuleRepository, tmp_path: Path):
        """匯出後再匯入應得到相同規則。"""
        repo.insert(ClassificationRule(rule_type="handler", pattern="薪資", value="王小明", priority=10))
        repo.insert(ClassificationRule(rule_type="priority", pattern="緊急", value="高", priority=5))

        csv_file = tmp_path / "rules.csv"
        repo.export_csv(csv_file)

        # 清空後重新匯入
        repo2 = RuleRepository(repo._conn)
        # 先刪除所有規則（直接用 conn）
        repo._conn.execute("DELETE FROM classification_rules")
        repo._conn.commit()

        imported, skipped = repo2.import_csv(csv_file)
        assert imported == 2
        assert skipped == 0
        assert len(repo2.list_by_type("handler")) == 1
        assert len(repo2.list_by_type("priority")) == 1
