"""資料庫 schema 初始化測試"""

import sqlite3


def test_schema_creates_all_tables(db: sqlite3.Connection) -> None:
    """驗證所有主表都被建立"""
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    tables = {row["name"] for row in cursor.fetchall()}

    # 主表必須存在
    for t in ["companies", "cs_cases", "mantis_tickets", "case_mantis",
              "qa_knowledge", "processed_files", "rules", "synonyms"]:
        assert t in tables, f"缺少表：{t}"


def test_foreign_keys_enabled(db: sqlite3.Connection) -> None:
    """驗證外鍵約束已啟用"""
    result = db.execute("PRAGMA foreign_keys").fetchone()
    assert result[0] == 1
