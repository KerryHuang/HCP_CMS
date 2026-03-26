# CSV 匯入精靈自訂欄位 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 CSV 匯入精靈能自動建立新資料庫欄位（cx_N），並在案件列表、詳情 Dialog、追蹤表報表全面顯示。

**Architecture:** `custom_columns` 中介資料表儲存欄位中繼資料（cx_1、cx_2…），`CustomColumnRepository` 封裝 DDL 操作，`CustomColumnManager` 作為 UI 層的唯一入口。`CaseRepository` 所有查詢方法改用 `_row_to_case()` 動態填入 `extra_fields`。

**Tech Stack:** Python 3.14、PySide6 6.10.2、SQLite（FTS5 不在此範圍）、pytest、re

---

## 檔案地圖

| 動作 | 路徑 | 說明 |
|------|------|------|
| 修改 | `src/hcp_cms/data/models.py` | 新增 `CustomColumn` dataclass；`Case` 加 `extra_fields` |
| 修改 | `src/hcp_cms/data/database.py` | `_SCHEMA_SQL` 加入 `custom_columns` 表 |
| 修改 | `src/hcp_cms/data/repositories.py` | 新增 `CustomColumnRepository`；`CaseRepository` 加 `_row_to_case`、`reload_custom_columns`、`update_extra_field` |
| 新增 | `src/hcp_cms/core/custom_column_manager.py` | `CustomColumnManager` + `STATIC_COL_LABELS` |
| 修改 | `src/hcp_cms/core/csv_import_engine.py` | 新增 `create_custom_columns()`；`execute()` 後 reload；`_import_row` 寫自訂欄 |
| 修改 | `src/hcp_cms/core/case_detail_manager.py` | 新增 `update_extra_field()` |
| 修改 | `src/hcp_cms/core/report_engine.py` | 建構子加 `CustomColumnManager`；追蹤表加自訂欄 |
| 修改 | `src/hcp_cms/ui/csv_import_dialog.py` | 步驟 2 下拉改顯示中文標籤；加「未對應欄位」區塊 |
| 修改 | `src/hcp_cms/ui/case_view.py` | `refresh()` 動態加自訂欄欄位 |
| 修改 | `src/hcp_cms/ui/case_detail_dialog.py` | Tab 1 動態加自訂欄 QLineEdit；儲存時 update_extra_field |
| 新增 | `tests/unit/test_custom_column_repository.py` | Repository 層測試 |
| 新增 | `tests/unit/test_custom_column_manager.py` | Manager 層測試 |
| 新增 | `tests/unit/test_case_repository_extra_fields.py` | `_row_to_case`、`update_extra_field` 測試 |
| 新增 | `tests/unit/test_csv_import_engine_custom.py` | Engine 自訂欄測試 |
| 新增 | `tests/unit/test_case_detail_manager_extra.py` | `update_extra_field` 委託測試 |
| 新增 | `tests/unit/test_report_engine_custom_cols.py` | 報表含自訂欄測試 |
| 新增 | `tests/integration/test_csv_wizard_custom_columns.py` | 完整流程整合測試 |

---

## Task 1：資料模型 + Schema（`models.py` + `database.py`）

**Files:**
- Modify: `src/hcp_cms/data/models.py`
- Modify: `src/hcp_cms/data/database.py`
- Test: `tests/unit/test_models_custom.py`

- [ ] **Step 1：撰寫失敗測試**

  建立 `tests/unit/test_models_custom.py`：

  ```python
  """CustomColumn + Case.extra_fields 模型測試。"""
  from hcp_cms.data.models import Case, CustomColumn


  class TestCustomColumnModel:
      def test_can_instantiate(self):
          col = CustomColumn(col_key="cx_1", col_label="測試欄", col_order=1)
          assert col.col_key == "cx_1"
          assert col.visible_in_list is True

  class TestCaseExtraFields:
      def test_extra_fields_default_empty(self):
          case = Case(
              case_id="CS-2026-001", subject="主旨", status="處理中",
              priority="中", replied="否",
          )
          assert case.extra_fields == {}

      def test_extra_fields_independent_per_instance(self):
          c1 = Case(case_id="A", subject="s", status="s", priority="中", replied="否")
          c2 = Case(case_id="B", subject="s", status="s", priority="中", replied="否")
          c1.extra_fields["cx_1"] = "v1"
          assert "cx_1" not in c2.extra_fields
  ```

- [ ] **Step 2：確認測試失敗**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/unit/test_models_custom.py -v
  ```

  Expected: FAIL（`CustomColumn` 不存在、`Case` 無 `extra_fields`）

- [ ] **Step 3：在 `models.py` 新增 `CustomColumn` dataclass**

  在 `CaseLog` class 之後加入：

  ```python
  @dataclass
  class CustomColumn:
      """自訂欄位中繼資料 — custom_columns table."""
      col_key: str           # cx_1, cx_2…
      col_label: str         # 中文顯示名稱
      col_order: int         # 建立序號
      visible_in_list: bool = True
  ```

- [ ] **Step 4：在 `Case` dataclass 加入 `extra_fields`**

  在 `Case` 的最後一個欄位後加：

  ```python
  extra_fields: dict[str, str | None] = field(default_factory=dict)
  ```

  確認 `from dataclasses import dataclass, field` import 已存在（若只有 `dataclass` 需補 `field`）。

- [ ] **Step 5：在 `database.py` 的 `_SCHEMA_SQL` 加入 `custom_columns` 表**

  在現有 `case_logs` 建表語句之後加：

  ```sql
  CREATE TABLE IF NOT EXISTS custom_columns (
      col_key          TEXT PRIMARY KEY,
      col_label        TEXT NOT NULL,
      col_order        INTEGER NOT NULL,
      visible_in_list  INTEGER NOT NULL DEFAULT 1
  );
  ```

- [ ] **Step 6：確認測試全通過**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/unit/test_models_custom.py -v
  ```

  Expected: 3 passed

- [ ] **Step 7：Commit**

  ```bash
  git add src/hcp_cms/data/models.py src/hcp_cms/data/database.py tests/unit/test_models_custom.py
  git commit -m "feat: CustomColumn dataclass + custom_columns schema + Case.extra_fields（Task 1）"
  ```

---

## Task 2：`CustomColumnRepository`（TDD）

**Files:**
- Modify: `src/hcp_cms/data/repositories.py`
- Create: `tests/unit/test_custom_column_repository.py`

- [ ] **Step 1：撰寫失敗測試**

  建立 `tests/unit/test_custom_column_repository.py`：

  ```python
  """CustomColumnRepository 單元測試。"""
  import re
  import sqlite3

  import pytest

  from hcp_cms.data.database import init_db
  from hcp_cms.data.models import CustomColumn
  from hcp_cms.data.repositories import CustomColumnRepository


  @pytest.fixture
  def db():
      conn = init_db(":memory:")
      yield conn
      conn.close()


  @pytest.fixture
  def repo(db):
      return CustomColumnRepository(db)


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
      def test_adds_column_to_cs_cases(self, db, repo):
          repo.add_column_to_cases("cx_1")
          cols = {row[1] for row in db.execute("PRAGMA table_info(cs_cases)")}
          assert "cx_1" in cols

      def test_idempotent_when_column_exists(self, db, repo):
          repo.add_column_to_cases("cx_1")
          repo.add_column_to_cases("cx_1")  # 不應拋錯
          cols = {row[1] for row in db.execute("PRAGMA table_info(cs_cases)")}
          assert "cx_1" in cols

      def test_raises_on_invalid_col_key(self, repo):
          with pytest.raises(ValueError, match="非法 col_key"):
              repo.add_column_to_cases("bad_key")

      def test_raises_on_sql_injection_attempt(self, repo):
          with pytest.raises(ValueError, match="非法 col_key"):
              repo.add_column_to_cases("cx_1; DROP TABLE cs_cases--")
  ```

- [ ] **Step 2：確認測試失敗**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/unit/test_custom_column_repository.py -v
  ```

  Expected: 所有測試 FAIL（`ImportError: cannot import name 'CustomColumnRepository'`）

- [ ] **Step 3：實作 `CustomColumnRepository`**

  在 `repositories.py` 末尾（`CaseLogRepository` 之後）加入：

  ```python
  import re as _re
  _COL_KEY_RE = _re.compile(r'^cx_\d+$')


  class CustomColumnRepository:
      """自訂欄位中繼資料 CRUD。"""

      def __init__(self, conn: sqlite3.Connection) -> None:
          self._conn = conn

      def next_col_key(self) -> str:
          row = self._conn.execute(
              "SELECT COALESCE(MAX(col_order), 0) + 1 FROM custom_columns"
          ).fetchone()
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
              "SELECT col_key, col_label, col_order, visible_in_list"
              " FROM custom_columns ORDER BY col_order ASC"
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
  ```

  同時在 `repositories.py` 頂部確認 `CustomColumn` 已加入 models import：

  ```python
  from hcp_cms.data.models import (
      Case, CaseMantisLink, CaseLog, CustomColumn,  # 加入 CustomColumn
      Company, MantisTicket, QAKnowledge, Rule,
  )
  ```

- [ ] **Step 4：確認測試全通過**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/unit/test_custom_column_repository.py -v
  ```

  Expected: 8 passed

- [ ] **Step 5：Commit**

  ```bash
  git add src/hcp_cms/data/repositories.py tests/unit/test_custom_column_repository.py
  git commit -m "feat: CustomColumnRepository（Task 2）"
  ```

---

## Task 3：`CaseRepository` 重構 — `_row_to_case` + `update_extra_field`（TDD）

**Files:**
- Modify: `src/hcp_cms/data/repositories.py`
- Create: `tests/unit/test_case_repository_extra_fields.py`

- [ ] **Step 1：撰寫失敗測試**

  建立 `tests/unit/test_case_repository_extra_fields.py`：

  ```python
  """CaseRepository extra_fields 相關測試。"""
  import sqlite3

  import pytest

  from hcp_cms.data.database import init_db
  from hcp_cms.data.repositories import CaseRepository, CustomColumnRepository


  @pytest.fixture
  def db():
      conn = init_db(":memory:")
      yield conn
      conn.close()


  def _insert_case(conn, case_id="CS-2026-001"):
      conn.execute(
          "INSERT INTO cs_cases (case_id, subject, status, priority, replied,"
          " sent_time, created_at, updated_at)"
          " VALUES (?,?,?,?,?,?,?,?)",
          (case_id, "測試主旨", "處理中", "中", "否",
           "2026/03/26 10:00:00", "2026/03/26 10:00:00", "2026/03/26 10:00:00"),
      )
      conn.commit()


  class TestRowToCaseWithNoCustomCols:
      def test_extra_fields_empty_when_no_custom_cols(self, db):
          _insert_case(db)
          repo = CaseRepository(db)
          case = repo.get_by_id("CS-2026-001")
          assert case is not None
          assert case.extra_fields == {}

      def test_list_all_extra_fields_empty(self, db):
          _insert_case(db)
          repo = CaseRepository(db)
          cases = repo.list_all()
          assert cases[0].extra_fields == {}


  class TestRowToCaseWithCustomCols:
      def test_extra_fields_filled_after_add_column(self, db):
          ccr = CustomColumnRepository(db)
          ccr.add_column_to_cases("cx_1")
          ccr.insert("cx_1", "客製欄A", 1)
          _insert_case(db)
          db.execute("UPDATE cs_cases SET cx_1='測試值A' WHERE case_id='CS-2026-001'")
          db.commit()

          repo = CaseRepository(db)
          case = repo.get_by_id("CS-2026-001")
          assert case is not None
          assert case.extra_fields["cx_1"] == "測試值A"

      def test_list_by_status_includes_extra_fields(self, db):
          ccr = CustomColumnRepository(db)
          ccr.add_column_to_cases("cx_1")
          ccr.insert("cx_1", "客製欄A", 1)
          _insert_case(db)
          db.execute("UPDATE cs_cases SET cx_1='狀態值' WHERE case_id='CS-2026-001'")
          db.commit()

          repo = CaseRepository(db)
          cases = repo.list_by_status("處理中")
          assert cases[0].extra_fields["cx_1"] == "狀態值"

      def test_reload_custom_columns_picks_up_new_col(self, db):
          _insert_case(db)
          repo = CaseRepository(db)
          assert repo.get_by_id("CS-2026-001").extra_fields == {}

          # 建立新欄後 reload
          ccr = CustomColumnRepository(db)
          ccr.add_column_to_cases("cx_1")
          ccr.insert("cx_1", "動態欄", 1)
          db.execute("UPDATE cs_cases SET cx_1='after_reload' WHERE case_id='CS-2026-001'")
          db.commit()
          repo.reload_custom_columns()

          case = repo.get_by_id("CS-2026-001")
          assert case.extra_fields["cx_1"] == "after_reload"


  class TestUpdateExtraField:
      def test_update_extra_field_persists(self, db):
          ccr = CustomColumnRepository(db)
          ccr.add_column_to_cases("cx_1")
          ccr.insert("cx_1", "欄A", 1)
          _insert_case(db)

          repo = CaseRepository(db)
          repo.update_extra_field("CS-2026-001", "cx_1", "新值")

          case = repo.get_by_id("CS-2026-001")
          assert case.extra_fields["cx_1"] == "新值"

      def test_update_extra_field_raises_on_invalid_key(self, db):
          repo = CaseRepository(db)
          import pytest
          with pytest.raises(ValueError, match="非法 col_key"):
              repo.update_extra_field("CS-2026-001", "bad", "x")
  ```

- [ ] **Step 2：確認測試失敗**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/unit/test_case_repository_extra_fields.py -v
  ```

  Expected: 多數 FAIL

- [ ] **Step 3：修改 `CaseRepository`**

  在 `CaseRepository.__init__` 末尾加：

  ```python
  self._custom_col_repo = CustomColumnRepository(conn)
  self._custom_cols = self._custom_col_repo.list_all()
  ```

  新增 `_build_select()`：

  ```python
  def _build_select(self) -> str:
      static = "case_id, company_id, subject, status, priority, replied, sent_time, " \
               "contact_person, contact_method, system_product, issue_type, error_type, " \
               "impact_period, progress, handler, actual_reply, reply_time, notes, " \
               "rd_assignee, reply_count, linked_case_id, source, created_at, updated_at"
      if not self._custom_cols:
          return f"SELECT {static} FROM cs_cases"
      cx_cols = ", ".join(col.col_key for col in self._custom_cols)
      return f"SELECT {static}, {cx_cols} FROM cs_cases"
  ```

  新增 `_row_to_case()`：

  ```python
  def _row_to_case(self, row: sqlite3.Row) -> Case:
      d = dict(row)
      extra = {col.col_key: d.pop(col.col_key, None) for col in self._custom_cols}
      return Case(**d, extra_fields=extra)
  ```

  新增 `reload_custom_columns()`：

  ```python
  def reload_custom_columns(self) -> None:
      self._custom_cols = self._custom_col_repo.list_all()
  ```

  新增 `update_extra_field()`：

  ```python
  def update_extra_field(self, case_id: str, col_key: str, value: str | None) -> None:
      if not _COL_KEY_RE.match(col_key):
          raise ValueError(f"非法 col_key：{col_key!r}")
      self._conn.execute(
          f"UPDATE cs_cases SET {col_key} = :v WHERE case_id = :id",
          {"v": value, "id": case_id},
      )
      self._conn.commit()
  ```

  **將所有 `Case(**dict(row))` 替換為 `self._row_to_case(row)`**，並將 SQL 由 `SELECT *` 改為呼叫 `self._build_select()`。

  受影響的 5 個方法（全部需要修改）：

  ```python
  # get_by_id
  def get_by_id(self, case_id: str) -> Case | None:
      sql = self._build_select() + " WHERE case_id = ?"
      row = self._conn.execute(sql, (case_id,)).fetchone()
      if row is None:
          return None
      return self._row_to_case(row)

  # list_all
  def list_all(self) -> list[Case]:
      rows = self._conn.execute(self._build_select() + " ORDER BY sent_time DESC").fetchall()
      return [self._row_to_case(r) for r in rows]

  # list_by_status
  def list_by_status(self, status: str) -> list[Case]:
      rows = self._conn.execute(self._build_select() + " WHERE status = ?", (status,)).fetchall()
      return [self._row_to_case(r) for r in rows]

  # list_by_month
  def list_by_month(self, year: int, month: int) -> list[Case]:
      prefix = f"{year}/{month:02d}%"
      rows = self._conn.execute(self._build_select() + " WHERE sent_time LIKE ?", (prefix,)).fetchall()
      return [self._row_to_case(r) for r in rows]

  # list_by_date_range
  def list_by_date_range(self, start: str, end: str) -> list[Case]:
      end_inclusive = end + " 23:59:59"
      rows = self._conn.execute(
          self._build_select() + " WHERE sent_time >= ? AND sent_time <= ?",
          (start, end_inclusive),
      ).fetchall()
      return [self._row_to_case(r) for r in rows]
  ```

- [ ] **Step 4：確認測試全通過**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/unit/test_case_repository_extra_fields.py -v
  ```

  Expected: 7 passed

- [ ] **Step 5：確認舊測試不受影響**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -20
  ```

  Expected: 所有既有測試仍通過

- [ ] **Step 6：Commit**

  ```bash
  git add src/hcp_cms/data/repositories.py tests/unit/test_case_repository_extra_fields.py
  git commit -m "feat: CaseRepository _row_to_case + reload_custom_columns + update_extra_field（Task 3）"
  ```

---

## Task 4：`CustomColumnManager`（TDD）

**Files:**
- Create: `src/hcp_cms/core/custom_column_manager.py`
- Create: `tests/unit/test_custom_column_manager.py`

- [ ] **Step 1：撰寫失敗測試**

  建立 `tests/unit/test_custom_column_manager.py`：

  ```python
  """CustomColumnManager 單元測試。"""
  import pytest

  from hcp_cms.data.database import init_db
  from hcp_cms.core.custom_column_manager import CustomColumnManager


  @pytest.fixture
  def db():
      conn = init_db(":memory:")
      yield conn
      conn.close()


  @pytest.fixture
  def mgr(db):
      return CustomColumnManager(db)


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
          cols = {row[1] for row in db.execute("PRAGMA table_info(cs_cases)")}
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
  ```

- [ ] **Step 2：確認測試失敗**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/unit/test_custom_column_manager.py -v
  ```

  Expected: 全部 FAIL（`ModuleNotFoundError`）

- [ ] **Step 3：實作 `CustomColumnManager`**

  建立 `src/hcp_cms/core/custom_column_manager.py`：

  ```python
  """自訂欄位管理 — Core 層。UI 層透過此 Manager 操作自訂欄位，不直接存取 Repository。"""

  import sqlite3

  from hcp_cms.data.models import CustomColumn
  from hcp_cms.data.repositories import CustomColumnRepository

  STATIC_COL_LABELS: dict[str, str] = {
      "case_id":        "案件編號",
      "company_id":     "公司 ID",
      "subject":        "主旨",
      "status":         "狀態",
      "priority":       "優先等級",
      "replied":        "是否已回覆",
      "sent_time":      "寄件時間",
      "contact_person": "聯絡人",
      "contact_method": "聯絡方式",
      "system_product": "系統／產品",
      "issue_type":     "問題類型",
      "error_type":     "錯誤類型",
      "impact_period":  "影響期間",
      "progress":       "處理進度",
      "handler":        "負責人",
      "actual_reply":   "實際回覆時間",
      "reply_time":     "預計回覆時間",
      "rd_assignee":    "RD 負責人",
      "notes":          "備註",
  }


  class CustomColumnManager:
      """自訂欄位的建立與查詢，UI 層唯一入口。"""

      def __init__(self, conn: sqlite3.Connection) -> None:
          self._repo = CustomColumnRepository(conn)

      def list_columns(self) -> list[CustomColumn]:
          """回傳所有自訂欄，依 col_order ASC。"""
          return self._repo.list_all()

      def create_column(self, col_label: str) -> CustomColumn:
          """建立新自訂欄，ALTER TABLE + INSERT，回傳 CustomColumn。"""
          col_key = self._repo.next_col_key()
          n = int(col_key.split("_")[1])
          self._repo.add_column_to_cases(col_key)
          self._repo.insert(col_key, col_label, n)
          return CustomColumn(col_key=col_key, col_label=col_label, col_order=n)

      def get_mappable_columns(self) -> list[tuple[str, str]]:
          """回傳 (col_key, col_label) 清單；靜態欄在前，自訂欄在後。"""
          static = list(STATIC_COL_LABELS.items())
          custom = [(c.col_key, c.col_label) for c in self._repo.list_all()]
          return static + custom
  ```

- [ ] **Step 4：確認測試全通過**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/unit/test_custom_column_manager.py -v
  ```

  Expected: 10 passed

- [ ] **Step 5：Commit**

  ```bash
  git add src/hcp_cms/core/custom_column_manager.py tests/unit/test_custom_column_manager.py
  git commit -m "feat: CustomColumnManager + STATIC_COL_LABELS（Task 4）"
  ```

---

## Task 5：`CsvImportEngine` 自訂欄擴充（TDD）

**Files:**
- Modify: `src/hcp_cms/core/csv_import_engine.py`
- Create: `tests/unit/test_csv_import_engine_custom.py`

- [ ] **Step 1：撰寫失敗測試**

  建立 `tests/unit/test_csv_import_engine_custom.py`：

  ```python
  """CsvImportEngine 自訂欄位功能測試。"""
  import csv
  import tempfile
  from pathlib import Path

  import pytest

  from hcp_cms.data.database import init_db
  from hcp_cms.data.repositories import CaseRepository, CustomColumnRepository
  from hcp_cms.core.csv_import_engine import CsvImportEngine, ConflictStrategy


  @pytest.fixture
  def db():
      conn = init_db(":memory:")
      yield conn
      conn.close()


  @pytest.fixture
  def engine(db):
      return CsvImportEngine(db)


  def _write_csv(path: Path, rows: list[dict]) -> None:
      with path.open("w", encoding="utf-8", newline="") as f:
          writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
          writer.writeheader()
          writer.writerows(rows)


  class TestCreateCustomColumns:
      def test_creates_columns_and_returns_list(self, db, engine):
          cols = engine.create_custom_columns([("備註欄", "特殊備註"), ("來源欄", "來源系統")])
          assert len(cols) == 2
          assert cols[0].col_key == "cx_1"
          assert cols[0].col_label == "特殊備註"
          assert cols[1].col_key == "cx_2"

      def test_columns_exist_in_db_after_create(self, db, engine):
          engine.create_custom_columns([("備註欄", "特殊備註")])
          db_cols = {row[1] for row in db.execute("PRAGMA table_info(cs_cases)")}
          assert "cx_1" in db_cols


  class TestImportWithCustomCols:
      def test_import_fills_extra_field(self, db, engine, tmp_path):
          # 先建立自訂欄
          engine.create_custom_columns([("自訂欄位", "客製資訊")])
          db.execute("UPDATE cs_cases SET cx_1=NULL")  # reset

          csv_path = tmp_path / "test.csv"
          _write_csv(csv_path, [{
              "主旨": "測試案件",
              "寄件時間": "2026/03/26 10:00:00",
              "公司": "測試公司",
              "自訂欄位": "自訂值123",
          }])

          mapping = {
              "主旨": "subject",
              "寄件時間": "sent_time",
              "公司": "company_id",
              "自訂欄位": "cx_1",
          }
          result = engine.execute(csv_path, mapping, ConflictStrategy.SKIP)
          assert result.success == 1

          repo = CaseRepository(db)
          cases = repo.list_all()
          assert len(cases) == 1
          assert cases[0].extra_fields.get("cx_1") == "自訂值123"

      def test_execute_reloads_case_repository(self, db, engine, tmp_path):
          engine.create_custom_columns([("標籤欄", "標籤")])
          csv_path = tmp_path / "test.csv"
          _write_csv(csv_path, [{
              "主旨": "案件A", "寄件時間": "2026/03/26 10:00:00",
              "公司": "公司A", "標籤欄": "tagX",
          }])
          mapping = {"主旨": "subject", "寄件時間": "sent_time",
                     "公司": "company_id", "標籤欄": "cx_1"}
          engine.execute(csv_path, mapping, ConflictStrategy.SKIP)

          # 驗證 engine 內部的 _case_repo 已 reload
          cases = engine._case_repo.list_all()
          assert cases[0].extra_fields.get("cx_1") == "tagX"
  ```

- [ ] **Step 2：確認測試失敗**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/unit/test_csv_import_engine_custom.py -v
  ```

  Expected: FAIL（`AttributeError: 'CsvImportEngine' object has no attribute 'create_custom_columns'`）

- [ ] **Step 3：修改 `CsvImportEngine`**

  在 `__init__` 末尾加：

  ```python
  from hcp_cms.core.custom_column_manager import CustomColumnManager
  self._custom_col_mgr = CustomColumnManager(conn)
  ```

  新增 `create_custom_columns()` 方法：

  ```python
  def create_custom_columns(
      self, requests: list[tuple[str, str]]
  ) -> list["CustomColumn"]:
      """批次建立自訂欄位。requests = [(csv_col_name, col_label), …]"""
      result = []
      for _csv_col, col_label in requests:
          col = self._custom_col_mgr.create_column(col_label)
          result.append(col)
      self._case_repo.reload_custom_columns()
      return result
  ```

  在 `execute()` 末尾（`return result` 之前）加：

  ```python
  self._case_repo.reload_custom_columns()
  ```

  在 `_import_row` 邏輯中（`execute()` 內的寫入區塊之後），針對 custom col mapping 呼叫 `update_extra_field`。在 `_insert_case(case_dict)` 或 `_overwrite_case(...)` 呼叫之後加：

  ```python
  # 寫入自訂欄
  for csv_col, db_col in mapping.items():
      if db_col.startswith("cx_"):
          self._case_repo.update_extra_field(
              case_id, db_col, (row.get(csv_col) or "").strip() or None
          )
  ```

  **注意**：此段程式碼加在 `_insert_case` / `_overwrite_case` 呼叫之後、`result.success += 1` / `result.overwritten += 1` **之前**。如此若 `update_extra_field` 拋出例外，會被 `except` 捕捉，計數不會誤增。

- [ ] **Step 4：確認測試全通過**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/unit/test_csv_import_engine_custom.py -v
  ```

  Expected: 5 passed

- [ ] **Step 5：確認全部測試通過**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -20
  ```

  Expected: 全通過

- [ ] **Step 6：Commit**

  ```bash
  git add src/hcp_cms/core/csv_import_engine.py tests/unit/test_csv_import_engine_custom.py
  git commit -m "feat: CsvImportEngine create_custom_columns + 自訂欄匯入（Task 5）"
  ```

---

## Task 6：`CaseDetailManager.update_extra_field`（TDD）

**Files:**
- Modify: `src/hcp_cms/core/case_detail_manager.py`
- Create: `tests/unit/test_case_detail_manager_extra.py`

- [ ] **Step 1：撰寫失敗測試**

  建立 `tests/unit/test_case_detail_manager_extra.py`：

  ```python
  """CaseDetailManager.update_extra_field 測試。"""
  import pytest

  from hcp_cms.data.database import init_db
  from hcp_cms.data.repositories import CaseRepository, CustomColumnRepository
  from hcp_cms.core.case_detail_manager import CaseDetailManager


  @pytest.fixture
  def db():
      conn = init_db(":memory:")
      yield conn
      conn.close()


  def _setup(db):
      ccr = CustomColumnRepository(db)
      ccr.add_column_to_cases("cx_1")
      ccr.insert("cx_1", "客製欄", 1)
      db.execute(
          "INSERT INTO cs_cases (case_id, subject, status, priority, replied,"
          " sent_time, created_at, updated_at)"
          " VALUES (?,?,?,?,?,?,?,?)",
          ("CS-2026-001", "主旨", "處理中", "中", "否",
           "2026/03/26 10:00:00", "2026/03/26 10:00:00", "2026/03/26 10:00:00"),
      )
      db.commit()


  class TestUpdateExtraField:
      def test_delegates_to_repository(self, db):
          _setup(db)
          mgr = CaseDetailManager(db)
          mgr.update_extra_field("CS-2026-001", "cx_1", "測試值")

          repo = CaseRepository(db)
          case = repo.get_by_id("CS-2026-001")
          assert case.extra_fields.get("cx_1") == "測試值"

      def test_raises_on_invalid_col_key(self, db):
          _setup(db)
          mgr = CaseDetailManager(db)
          with pytest.raises(ValueError):
              mgr.update_extra_field("CS-2026-001", "invalid", "x")
  ```

- [ ] **Step 2：確認測試失敗**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/unit/test_case_detail_manager_extra.py -v
  ```

  Expected: FAIL

- [ ] **Step 3：在 `case_detail_manager.py` 加入方法**

  在 `CaseDetailManager` 類別末尾加：

  ```python
  def update_extra_field(self, case_id: str, col_key: str, value: str | None) -> None:
      """更新案件自訂欄位值，委託 CaseRepository。"""
      self._case_repo.update_extra_field(case_id, col_key, value)
  ```

- [ ] **Step 4：確認測試全通過**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/unit/test_case_detail_manager_extra.py -v
  ```

  Expected: 2 passed

- [ ] **Step 5：Commit**

  ```bash
  git add src/hcp_cms/core/case_detail_manager.py tests/unit/test_case_detail_manager_extra.py
  git commit -m "feat: CaseDetailManager.update_extra_field（Task 6）"
  ```

---

## Task 7：`ReportEngine` 追蹤表含自訂欄（TDD）

**Files:**
- Modify: `src/hcp_cms/core/report_engine.py`
- Create: `tests/unit/test_report_engine_custom_cols.py`

- [ ] **Step 1：撰寫失敗測試**

  建立 `tests/unit/test_report_engine_custom_cols.py`：

  ```python
  """ReportEngine 自訂欄位整合測試。"""
  import sqlite3
  import tempfile
  from pathlib import Path

  import openpyxl
  import pytest

  from hcp_cms.data.database import init_db
  from hcp_cms.data.repositories import CustomColumnRepository, CaseRepository
  from hcp_cms.core.report_engine import ReportEngine


  @pytest.fixture
  def db():
      conn = init_db(":memory:")
      yield conn
      conn.close()


  def _insert_case(db, case_id="CS-2026-001", cx_1_val=None):
      db.execute(
          "INSERT INTO cs_cases (case_id, subject, status, priority, replied,"
          " sent_time, created_at, updated_at)"
          " VALUES (?,?,?,?,?,?,?,?)",
          (case_id, "測試主旨", "處理中", "中", "否",
           "2026/03/26 10:00:00", "2026/03/26 10:00:00", "2026/03/26 10:00:00"),
      )
      if cx_1_val is not None:
          db.execute(f"UPDATE cs_cases SET cx_1=? WHERE case_id=?", (cx_1_val, case_id))
      db.commit()


  class TestTrackingTableWithCustomCols:
      def test_custom_col_header_in_tracking_table(self, db, tmp_path):
          ccr = CustomColumnRepository(db)
          ccr.add_column_to_cases("cx_1")
          ccr.insert("cx_1", "特殊備註", 1)
          _insert_case(db, cx_1_val="特殊值ABC")

          engine = ReportEngine(db)
          out = tmp_path / "report.xlsx"
          engine.generate_tracking_table("2026/03/01", "2026/03/31", out)

          wb = openpyxl.load_workbook(out)
          ws2 = wb["問題追蹤總表"]
          headers = [ws2.cell(row=1, column=c).value for c in range(1, ws2.max_column + 1)]
          assert "特殊備註" in headers

      def test_custom_col_value_in_tracking_table(self, db, tmp_path):
          ccr = CustomColumnRepository(db)
          ccr.add_column_to_cases("cx_1")
          ccr.insert("cx_1", "特殊備註", 1)
          _insert_case(db, cx_1_val="特殊值ABC")

          engine = ReportEngine(db)
          out = tmp_path / "report.xlsx"
          engine.generate_tracking_table("2026/03/01", "2026/03/31", out)

          wb = openpyxl.load_workbook(out)
          ws2 = wb["問題追蹤總表"]
          headers = [ws2.cell(row=1, column=c).value for c in range(1, ws2.max_column + 1)]
          col_idx = headers.index("特殊備註") + 1
          data_val = ws2.cell(row=2, column=col_idx).value
          assert data_val == "特殊值ABC"

      def test_company_sheet_includes_custom_col(self, db, tmp_path):
          """個別公司頁籤也需包含自訂欄標題與值。"""
          # 插入公司
          db.execute(
              "INSERT INTO companies (company_id, name) VALUES (?,?)",
              ("COMP-001", "測試公司"),
          )
          db.commit()
          ccr = CustomColumnRepository(db)
          ccr.add_column_to_cases("cx_1")
          ccr.insert("cx_1", "特殊備註", 1)
          _insert_case(db, cx_1_val="公司特殊值")
          db.execute("UPDATE cs_cases SET company_id='COMP-001'")
          db.commit()

          engine = ReportEngine(db)
          out = tmp_path / "report.xlsx"
          engine.generate_tracking_table("2026/03/01", "2026/03/31", out)

          wb = openpyxl.load_workbook(out)
          # 個別公司頁籤名稱含公司名
          company_sheets = [s for s in wb.sheetnames if "測試公司" in s or "COMP" in s]
          assert len(company_sheets) >= 1
          ws_c = wb[company_sheets[0]]
          # 取第 2 列（表頭）
          headers = [ws_c.cell(row=2, column=c).value for c in range(1, ws_c.max_column + 1)]
          assert "特殊備註" in headers
  ```

- [ ] **Step 2：確認測試失敗**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/unit/test_report_engine_custom_cols.py -v
  ```

  Expected: FAIL

- [ ] **Step 3：修改 `ReportEngine`**

  在 `__init__` 末尾加：

  ```python
  from hcp_cms.core.custom_column_manager import CustomColumnManager
  self._custom_col_mgr = CustomColumnManager(conn)
  ```

  在 `generate_tracking_table()` 的 `main_headers` 定義之後加：

  ```python
  custom_cols = self._custom_col_mgr.list_columns()
  main_headers = main_headers + [col.col_label for col in custom_cols]
  ```

  在 `ws2.append(_clean_row([...]))` 的 list 末尾加：

  ```python
  + [_clean(case.extra_fields.get(col.col_key, "")) for col in custom_cols]
  ```

  個別公司頁籤（`comp_case_headers` / `ws_c.cell(...)`）同理：
  - `comp_case_headers` 末尾加 `+ [col.col_label for col in custom_cols]`
  - 每列資料末尾加對應 `extra_fields` 值（從 `max_col + 1` 開始寫入）

- [ ] **Step 4：確認測試全通過**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/unit/test_report_engine_custom_cols.py -v
  ```

  Expected: 2 passed

- [ ] **Step 5：Commit**

  ```bash
  git add src/hcp_cms/core/report_engine.py tests/unit/test_report_engine_custom_cols.py
  git commit -m "feat: ReportEngine 追蹤表含自訂欄（Task 7）"
  ```

---

## Task 8：CSV 精靈 UI — 中文標籤下拉 + 未對應欄位區塊

**Files:**
- Modify: `src/hcp_cms/ui/csv_import_dialog.py`

> 無 UI 單元測試（PySide6 Widget 需 QApplication）；以手動測試驗證。

- [ ] **Step 1：在 `CsvImportDialog` 加入 `CustomColumnManager` 實例**

  在 `__init__` 內（`self._engine = ...` 之後）加：

  ```python
  from hcp_cms.core.custom_column_manager import CustomColumnManager
  self._custom_col_mgr = CustomColumnManager(conn) if conn else None
  ```

  > 若 `CsvImportDialog` 是在步驟 3 才建立 conn，則在 `_populate_step3` 前取得 conn 時一併建立 manager。確認現有 conn 取得時機，依實際程式碼調整。

- [ ] **Step 2：修改 `_populate_step2()` 右側下拉**

  將：

  ```python
  combo.addItems(MAPPABLE_DB_COLS)
  ```

  改為：

  ```python
  mappable = self._custom_col_mgr.get_mappable_columns() if self._custom_col_mgr else []
  items = ["skip"] + [f"{label} ({key})" for key, label in mappable]
  combo.addItems(items)
  # 預設值（原邏輯：依 DEFAULT_MAPPING 尋找）
  default_db_col = DEFAULT_MAPPING.get(csv_col, "skip")
  # 嘗試依 col_key 比對
  target_text = next(
      (f"{label} ({key})" for key, label in mappable if key == default_db_col),
      "skip"
  )
  idx = combo.findText(target_text)
  if idx >= 0:
      combo.setCurrentIndex(idx)
  ```

- [ ] **Step 3：修改 `_collect_mapping()` 解析顯示格式**

  下拉選項格式為 `"中文 (col_key)"`，需解析回 col_key：

  在 `csv_import_dialog.py` 檔案頂部的 import 區加入（若尚未存在）：

  ```python
  import re as _re
  _COMBO_KEY_RE = _re.compile(r'\(([^)]+)\)$')
  ```

  修改 `_collect_mapping()`（不在函式內 import）：

  ```python
  def _collect_mapping(self) -> None:
      result = {}
      for csv_col, combo in self._combo_map.items():
          text = combo.currentText()
          m = _COMBO_KEY_RE.search(text)
          result[csv_col] = m.group(1) if m else "skip"
      self._mapping = result
  ```

- [ ] **Step 4：在步驟 2 底部加「未對應欄位」區塊**

  在步驟 2 的 layout 底部加一個可捲動的 `QGroupBox`（初始隱藏）：

  ```python
  # 在 _setup_ui 的步驟 2 頁建立
  self._unmatched_group = QGroupBox("尚未對應的 CSV 欄位 — 勾選可自動建立新欄位：")
  self._unmatched_group.setVisible(False)
  self._unmatched_layout = QVBoxLayout(self._unmatched_group)
  self._unmatched_checks: dict[str, tuple[QCheckBox, QLineEdit]] = {}
  # 加到步驟 2 的 scroll area 或 layout 末尾
  ```

  在 `_populate_step2()` 末尾呼叫：

  ```python
  self._refresh_unmatched_section()
  ```

  為每個 combo 的 `currentIndexChanged` 連結 `self._refresh_unmatched_section`。

  新增方法（使用檔案頂部已定義的 `_COMBO_KEY_RE`，不在函式內 import）：

  ```python
  def _refresh_unmatched_section(self) -> None:
      """重算未對應 CSV 欄位，更新 unmatched_group。"""
      # 清除舊內容
      for i in reversed(range(self._unmatched_layout.count())):
          w = self._unmatched_layout.itemAt(i).widget()
          if w:
              w.setParent(None)
      self._unmatched_checks.clear()

      unmatched = []
      for csv_col, combo in self._combo_map.items():
          text = combo.currentText()
          m = _COMBO_KEY_RE.search(text)
          db_col = m.group(1) if m else "skip"
          if db_col == "skip":
              unmatched.append(csv_col)

      self._unmatched_group.setVisible(bool(unmatched))
      for csv_col in unmatched:
          row_widget = QWidget()
          row_layout = QHBoxLayout(row_widget)
          row_layout.setContentsMargins(0, 0, 0, 0)
          chk = QCheckBox(csv_col)
          chk.setChecked(True)
          label_input = QLineEdit(csv_col)
          label_input.setPlaceholderText("中文標籤")
          row_layout.addWidget(chk)
          row_layout.addWidget(QLabel("  中文標籤："))
          row_layout.addWidget(label_input)
          self._unmatched_layout.addWidget(row_widget)
          self._unmatched_checks[csv_col] = (chk, label_input)
  ```

- [ ] **Step 5：修改步驟 3 執行流程（建立自訂欄後再 execute）**

  在 `_populate_step3()` 中，呼叫 `engine.execute()` 之前插入：

  ```python
  # 建立勾選的自訂欄
  requests = [
      (csv_col, line_edit.text().strip() or csv_col)
      for csv_col, (chk, line_edit) in self._unmatched_checks.items()
      if chk.isChecked()
  ]
  if requests:
      new_cols = engine.create_custom_columns(requests)
      # 更新 mapping：csv_col → cx_N
      for (csv_col, _), col in zip(requests, new_cols):
          if csv_col in self._mapping and self._mapping[csv_col] == "skip":
              self._mapping[csv_col] = col.col_key
  ```

- [ ] **Step 6：手動測試**

  啟動應用，進入案件管理 → 匯入 CSV，確認：
  - 步驟 2 右側下拉顯示「主旨 (subject)」格式
  - 有未對應欄位時，底部出現勾選區塊
  - 勾選後完成匯入，案件列表出現新欄

- [ ] **Step 7：Commit**

  ```bash
  git add src/hcp_cms/ui/csv_import_dialog.py
  git commit -m "feat: CSV 精靈步驟 2 中文標籤下拉 + 未對應欄位自動建立（Task 8）"
  ```

---

## Task 9：`CaseView` 動態顯示自訂欄

**Files:**
- Modify: `src/hcp_cms/ui/case_view.py`

- [ ] **Step 1：在 `CaseView.__init__` 持有 `CustomColumnManager` 實例**

  在 `__init__` 的 `self._conn = conn` 之後加：

  ```python
  from hcp_cms.core.custom_column_manager import CustomColumnManager
  self._custom_col_mgr = CustomColumnManager(conn) if conn else None
  ```

- [ ] **Step 2：修改 `CaseView.refresh()` 使用持有的實例**

  在 `refresh()` 開頭取得 custom cols（使用已持有的實例，不每次建立）：

  ```python
  custom_cols = self._custom_col_mgr.list_columns() if self._custom_col_mgr else []
  visible_cols = [c for c in custom_cols if c.visible_in_list]
  ```

  在設定 `self._table` 欄位數時，將固定欄數加上 `len(visible_cols)`。

  在設定 header labels 時，固定標題後追加：

  ```python
  headers += [col.col_label for col in visible_cols]
  self._table.setHorizontalHeaderLabels(headers)
  ```

  在填入每列資料時（case row），追加：

  ```python
  for j, col in enumerate(visible_cols):
      val = case.extra_fields.get(col.col_key) or ""
      self._table.setItem(row_idx, fixed_col_count + j, QTableWidgetItem(val))
  ```

- [ ] **Step 2：手動驗證**

  啟動應用，確認：
  - 匯入含自訂欄的 CSV 後，案件列表自動顯示新欄
  - 重新整理後仍顯示

- [ ] **Step 3：Commit**

  ```bash
  git add src/hcp_cms/ui/case_view.py
  git commit -m "feat: CaseView 動態顯示自訂欄（Task 9）"
  ```

---

## Task 10：`CaseDetailDialog` Tab 1 動態自訂欄

**Files:**
- Modify: `src/hcp_cms/ui/case_detail_dialog.py`

- [ ] **Step 1：在 `_load_case()` 後動態加自訂欄欄位**

  在 Tab 1 的「備註」欄位後，動態建立 QLabel + QLineEdit：

  ```python
  from hcp_cms.core.custom_column_manager import CustomColumnManager
  custom_cols = CustomColumnManager(self._conn).list_columns()
  self._extra_field_widgets: dict[str, QLineEdit] = {}
  for col in custom_cols:
      le = QLineEdit(self._case.extra_fields.get(col.col_key) or "")
      # 加到 Tab 1 的 form layout
      self._extra_field_widgets[col.col_key] = le
  ```

- [ ] **Step 2：在 `_save_case()` 加入自訂欄儲存**

  在 `_save_case()` 的儲存成功後加：

  ```python
  for col_key, le in self._extra_field_widgets.items():
      val = le.text().strip() or None
      self._mgr.update_extra_field(self._case_id, col_key, val)
  ```

- [ ] **Step 3：手動驗證**

  開啟案件詳情，確認：
  - 自訂欄出現在備註下方
  - 修改後按「儲存」，重開 Dialog 值仍保留

- [ ] **Step 4：Commit**

  ```bash
  git add src/hcp_cms/ui/case_detail_dialog.py
  git commit -m "feat: CaseDetailDialog Tab 1 動態自訂欄（Task 10）"
  ```

---

## Task 11：整合測試

**Files:**
- Create: `tests/integration/test_csv_wizard_custom_columns.py`

- [ ] **Step 1：建立整合測試（驗證完整流程）**

  建立 `tests/integration/test_csv_wizard_custom_columns.py`：

  ```python
  """CSV 精靈自訂欄位完整流程整合測試。"""
  import csv
  from pathlib import Path

  import openpyxl
  import pytest

  from hcp_cms.data.database import init_db
  from hcp_cms.data.repositories import CaseRepository
  from hcp_cms.core.csv_import_engine import CsvImportEngine, ConflictStrategy
  from hcp_cms.core.custom_column_manager import CustomColumnManager
  from hcp_cms.core.report_engine import ReportEngine


  @pytest.fixture
  def db():
      conn = init_db(":memory:")
      yield conn
      conn.close()


  def _write_csv(path: Path, rows: list[dict]) -> None:
      with path.open("w", encoding="utf-8", newline="") as f:
          writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
          writer.writeheader()
          writer.writerows(rows)


  class TestFullFlow:
      def test_create_import_verify_report(self, db, tmp_path):
          """建立自訂欄 → 匯入 → DB 驗證 → 報表驗證。"""
          engine = CsvImportEngine(db)

          # 1. 建立自訂欄
          cols = engine.create_custom_columns([("來源系統", "來源系統")])
          assert cols[0].col_key == "cx_1"

          # 2. 匯入 CSV
          csv_path = tmp_path / "data.csv"
          _write_csv(csv_path, [{
              "主旨": "整合測試案件", "寄件時間": "2026/03/26 10:00:00",
              "公司": "測試公司整合", "來源系統": "SAP",
          }])
          mapping = {
              "主旨": "subject", "寄件時間": "sent_time",
              "公司": "company_id", "來源系統": "cx_1",
          }
          result = engine.execute(csv_path, mapping, ConflictStrategy.SKIP)
          assert result.success == 1

          # 3. 驗證 Case.extra_fields
          case_repo = CaseRepository(db)
          cases = case_repo.list_all()
          assert len(cases) == 1
          assert cases[0].extra_fields.get("cx_1") == "SAP"

          # 4. 驗證 CustomColumnManager 可取得欄位
          mgr = CustomColumnManager(db)
          custom_cols = mgr.list_columns()
          assert any(c.col_label == "來源系統" for c in custom_cols)

          # 5. 驗證報表含自訂欄
          report_engine = ReportEngine(db)
          out = tmp_path / "report.xlsx"
          report_engine.generate_tracking_table("2026/03/01", "2026/03/31", out)
          wb = openpyxl.load_workbook(out)
          ws2 = wb["問題追蹤總表"]
          headers = [ws2.cell(row=1, column=c).value for c in range(1, ws2.max_column + 1)]
          assert "來源系統" in headers
  ```

- [ ] **Step 2：執行整合測試**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/integration/test_csv_wizard_custom_columns.py -v
  ```

  Expected: 1 passed

- [ ] **Step 3：Commit**

  ```bash
  git add tests/integration/test_csv_wizard_custom_columns.py
  git commit -m "test: 自訂欄位完整流程整合測試（Task 11）"
  ```

---

## Task 12：全套測試 + 最終驗證

- [ ] **Step 1：執行完整測試套件**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/ -v 2>&1 | tail -30
  ```

  Expected: 所有測試通過，無 FAIL

- [ ] **Step 2：Lint 檢查**

  ```bash
  .venv/Scripts/ruff.exe check src/ tests/
  ```

  Expected: 無 error

- [ ] **Step 3：手動完整流程測試**

  1. 啟動應用
  2. 進入案件管理 → 匯入 CSV（含未知欄位）
  3. 步驟 2 確認下拉顯示中文標籤
  4. 步驟 2 底部確認有未對應欄位清單
  5. 勾選並輸入中文標籤 → 完成匯入
  6. 確認案件列表出現新欄位
  7. 雙擊開啟案件詳情，確認 Tab 1 底部有自訂欄且值正確
  8. 報表中心 → 產生追蹤表，確認自訂欄出現在表格中

- [ ] **Step 4：Final commit（若有未提交的調整）**

  ```bash
  git status
  # 若有修改：
  git add <修改的檔案>
  git commit -m "fix: 最終調整（Task 12）"
  ```
