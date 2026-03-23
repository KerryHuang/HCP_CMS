"""Tests for seed_rules migration."""

from __future__ import annotations

from pathlib import Path

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.repositories import CompanyRepository, RuleRepository


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


class TestSeedRules:
    def test_seed_inserts_rules(self, db: DatabaseManager):
        from hcp_cms.data.seed_rules import seed
        stats = seed(db.connection, verbose=False)
        assert stats["rules_inserted"] > 30

    def test_seed_inserts_error_rules(self, db: DatabaseManager):
        from hcp_cms.data.seed_rules import seed
        seed(db.connection, verbose=False)
        repo = RuleRepository(db.connection)
        error_rules = repo.list_by_type("error")
        assert len(error_rules) >= 20

    def test_seed_inserts_issue_rules(self, db: DatabaseManager):
        from hcp_cms.data.seed_rules import seed
        seed(db.connection, verbose=False)
        repo = RuleRepository(db.connection)
        issue_rules = repo.list_by_type("issue")
        assert len(issue_rules) >= 7

    def test_seed_inserts_broadcast_rules(self, db: DatabaseManager):
        from hcp_cms.data.seed_rules import seed
        seed(db.connection, verbose=False)
        repo = RuleRepository(db.connection)
        broadcast_rules = repo.list_by_type("broadcast")
        assert len(broadcast_rules) >= 2

    def test_seed_inserts_companies(self, db: DatabaseManager):
        from hcp_cms.data.seed_rules import seed
        stats = seed(db.connection, verbose=False)
        assert stats["companies_inserted"] == 10
        repo = CompanyRepository(db.connection)
        company = repo.get_by_domain("aseglobal.com")
        assert company is not None
        assert company.name == "日月光集團"

    def test_seed_skips_existing_companies(self, db: DatabaseManager):
        from hcp_cms.data.seed_rules import seed
        seed(db.connection, verbose=False)
        stats2 = seed(db.connection, verbose=False)
        assert stats2["companies_skipped"] == 10

    def test_seed_replaces_old_rules(self, db: DatabaseManager):
        """移轉後舊的簡易規則應被完整規則取代。"""
        from hcp_cms.data.models import ClassificationRule
        from hcp_cms.data.seed_rules import seed

        # 先插入一條舊規則
        RuleRepository(db.connection).insert(
            ClassificationRule(rule_type="error", pattern="舊規則", value="舊值", priority=999)
        )
        seed(db.connection, verbose=False)
        # 舊規則應被刪除，不應存在
        rules = RuleRepository(db.connection).list_by_type("error")
        patterns = [r.pattern for r in rules]
        assert "舊規則" not in patterns
