# 客戶與人員管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增「🏢 客戶管理」頁面，整合客戶公司（含負責客服/業務）、客服人員、業務人員的 CRUD 與批次貼上更新；收件時從寄件人 domain 找公司、再從公司找負責客服，自動填入 handler。

**Architecture:**
- 新增 `Staff` dataclass + `StaffRepository`（Data 層）
- `Company` 新增 `cs_staff_id` / `sales_staff_id` 欄位（FK → staff）
- 新增 `CustomerManager`（Core 層）封裝公司 + 人員的批次 upsert 邏輯
- 擴展 `Classifier._resolve_handler_from_domain()`：寄件人 domain → 查公司 → 取 cs_staff_id → 查 Staff.name → 填 handler
- 新增 `CustomerView`（UI 層），三個分頁：客戶公司 / 客服人員 / 業務人員，支援直接表格編輯 + 批次貼上更新；客戶公司分頁含「負責客服」「負責業務」下拉選單
- 在 `MainWindow` 導覽列插入「🏢 客戶管理」頁面

**分案邏輯：**
```
客戶寄信 customer@abc.com.tw
  ↓ 取 domain：abc.com.tw
  ↓ 查 companies WHERE domain = 'abc.com.tw'  → 找到「ABC 公司」
  ↓ 取 company.cs_staff_id = 'STAFF-001'
  ↓ 查 staff WHERE staff_id = 'STAFF-001'     → name = 'JILL'
  ↓ case.handler = 'JILL'
```

**Tech Stack:** Python 3.14、PySide6 6.10.2、SQLite、pytest

---

## 檔案異動總覽

| 路徑 | 動作 |
|------|------|
| `src/hcp_cms/data/models.py` | 修改：新增 `Staff` dataclass；`Company` 加 `cs_staff_id` / `sales_staff_id` |
| `src/hcp_cms/data/database.py` | 修改：新增 `staff` 表 schema；migrations 補 `companies` 兩欄 |
| `src/hcp_cms/data/repositories.py` | 修改：新增 `StaffRepository`；`CompanyRepository` 新增 `get_with_staff()` |
| `src/hcp_cms/core/customer_manager.py` | **新增** |
| `src/hcp_cms/core/classifier.py` | 修改：`_resolve_handler_from_domain()`；`__init__` 加 `StaffRepository` |
| `src/hcp_cms/ui/customer_view.py` | **新增** |
| `src/hcp_cms/ui/main_window.py` | 修改：插入客戶管理頁面 |
| `tests/unit/test_staff_repository.py` | **新增** |
| `tests/unit/test_customer_manager.py` | **新增** |
| `tests/unit/test_classifier_staff.py` | **新增** |

---

## Task 1: Staff 資料模型 + DB Schema

**Files:**
- Modify: `src/hcp_cms/data/models.py`
- Modify: `src/hcp_cms/data/database.py`

- [ ] **Step 1: 在 models.py 新增 `Staff` dataclass，並更新 `Company`**

在 `CaseLog` dataclass 之後加入：

```python
@dataclass
class Staff:
    """人員資料 — staff table."""
    staff_id: str          # 自動產生：STAFF-YYYYMMDDHHMMSS
    name: str              # 顯示名稱（如 JILL）
    email: str             # 完整 Email（如 jill@ares.com.tw）
    role: str              # 'cs'（客服）| 'sales'（業務）
    phone: str | None = None
    notes: str | None = None
    created_at: str | None = None
```

同時更新 `Company` dataclass，新增兩個欄位（加在 `created_at` 之前）：

```python
@dataclass
class Company:
    company_id: str
    name: str
    domain: str
    alias: str | None = None
    contact_info: str | None = None
    cs_staff_id: str | None = None      # FK → staff.staff_id（負責客服）
    sales_staff_id: str | None = None   # FK → staff.staff_id（負責業務）
    created_at: str | None = None
```

- [ ] **Step 2: 在 database.py 的 `_SCHEMA_SQL` 新增 `staff` 表**

在 `CREATE TABLE IF NOT EXISTS case_logs` 之後插入：

```sql
CREATE TABLE IF NOT EXISTS staff (
    staff_id   TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL UNIQUE,
    role       TEXT NOT NULL DEFAULT 'cs',
    phone      TEXT,
    notes      TEXT,
    created_at TEXT
);
```

- [ ] **Step 3: 在 `_apply_pending_migrations()` 補欄遷移**

在 `pending` list 末尾加入：

```python
"ALTER TABLE companies ADD COLUMN cs_staff_id TEXT",
"ALTER TABLE companies ADD COLUMN sales_staff_id TEXT",
```

- [ ] **Step 4: 驗證 DB 初始化正常**

```bash
cd D:\CMS
.venv/Scripts/python.exe -c "
from hcp_cms.data.database import DatabaseManager
import tempfile, pathlib
with tempfile.TemporaryDirectory() as d:
    db = DatabaseManager(pathlib.Path(d) / 'test.db')
    db.initialize()
    rows = db.connection.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
    print([r[0] for r in rows])
    db.close()
"
```

預期輸出包含 `'staff'`。

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/data/models.py src/hcp_cms/data/database.py
git commit -m "feat: 新增 Staff 資料模型；Company 加 cs_staff_id/sales_staff_id；staff DB 資料表"
```

---

## Task 2: StaffRepository — Data 層

**Files:**
- Modify: `src/hcp_cms/data/repositories.py`
- Create: `tests/unit/test_staff_repository.py`

- [ ] **Step 1: 建立測試檔案**

```python
# tests/unit/test_staff_repository.py
"""Tests for StaffRepository."""

import pytest

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Staff
from hcp_cms.data.repositories import StaffRepository


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(tmp_path / "test.db")
    manager.initialize()
    yield manager
    manager.close()


def _staff(staff_id="STAFF-001", name="JILL", email="jill@ares.com.tw", role="cs") -> Staff:
    return Staff(staff_id=staff_id, name=name, email=email, role=role)


class TestStaffRepository:
    def test_insert_and_get_by_id(self, db):
        repo = StaffRepository(db.connection)
        repo.insert(_staff())
        result = repo.get_by_id("STAFF-001")
        assert result is not None
        assert result.name == "JILL"
        assert result.email == "jill@ares.com.tw"

    def test_get_by_email(self, db):
        repo = StaffRepository(db.connection)
        repo.insert(_staff())
        result = repo.get_by_email("jill@ares.com.tw")
        assert result is not None
        assert result.staff_id == "STAFF-001"

    def test_get_by_email_case_insensitive(self, db):
        repo = StaffRepository(db.connection)
        repo.insert(_staff())
        result = repo.get_by_email("JILL@ARES.COM.TW")
        assert result is not None

    def test_list_by_role_cs(self, db):
        repo = StaffRepository(db.connection)
        repo.insert(_staff("STAFF-001", "JILL", "jill@ares.com.tw", "cs"))
        repo.insert(_staff("STAFF-002", "MIKE", "mike@ares.com.tw", "sales"))
        cs_list = repo.list_by_role("cs")
        assert len(cs_list) == 1
        assert cs_list[0].name == "JILL"

    def test_list_by_role_sales(self, db):
        repo = StaffRepository(db.connection)
        repo.insert(_staff("STAFF-001", "JILL", "jill@ares.com.tw", "cs"))
        repo.insert(_staff("STAFF-002", "MIKE", "mike@ares.com.tw", "sales"))
        sales_list = repo.list_by_role("sales")
        assert len(sales_list) == 1
        assert sales_list[0].name == "MIKE"

    def test_list_all(self, db):
        repo = StaffRepository(db.connection)
        repo.insert(_staff("STAFF-001", "JILL", "jill@ares.com.tw", "cs"))
        repo.insert(_staff("STAFF-002", "MIKE", "mike@ares.com.tw", "sales"))
        assert len(repo.list_all()) == 2

    def test_update(self, db):
        repo = StaffRepository(db.connection)
        s = _staff()
        repo.insert(s)
        s.name = "JILL-UPDATED"
        s.phone = "0912345678"
        repo.update(s)
        result = repo.get_by_id("STAFF-001")
        assert result.name == "JILL-UPDATED"
        assert result.phone == "0912345678"

    def test_delete(self, db):
        repo = StaffRepository(db.connection)
        repo.insert(_staff())
        repo.delete("STAFF-001")
        assert repo.get_by_id("STAFF-001") is None

    def test_upsert_insert_new(self, db):
        repo = StaffRepository(db.connection)
        repo.upsert(_staff())
        assert repo.get_by_email("jill@ares.com.tw") is not None

    def test_upsert_update_existing(self, db):
        repo = StaffRepository(db.connection)
        repo.upsert(_staff(name="OLD"))
        repo.upsert(_staff(name="NEW"))
        result = repo.get_by_email("jill@ares.com.tw")
        assert result.name == "NEW"
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
cd D:\CMS
.venv/Scripts/python.exe -m pytest tests/unit/test_staff_repository.py -v
```

預期：`ImportError: cannot import name 'StaffRepository'`

- [ ] **Step 3: 在 repositories.py 頂端 import 補上 `Staff`**

找到現有 import：
```python
from hcp_cms.data.models import (
    Case,
    CaseLog,
    CaseMantisLink,
    ClassificationRule,
    Company,
    CustomColumn,
    MantisTicket,
    ProcessedFile,
    QAKnowledge,
    Synonym,
)
```

替換為：
```python
from hcp_cms.data.models import (
    Case,
    CaseLog,
    CaseMantisLink,
    ClassificationRule,
    Company,
    CustomColumn,
    MantisTicket,
    ProcessedFile,
    QAKnowledge,
    Staff,
    Synonym,
)
```

- [ ] **Step 4: 在 repositories.py 的 `CompanyRepository` 之後（`CaseRepository` 之前）插入 `StaffRepository`**

```python
# ---------------------------------------------------------------------------
# StaffRepository
# ---------------------------------------------------------------------------


class StaffRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, staff: Staff) -> None:
        staff.created_at = _now()
        self._conn.execute(
            """
            INSERT INTO staff (staff_id, name, email, role, phone, notes, created_at)
            VALUES (:staff_id, :name, :email, :role, :phone, :notes, :created_at)
            """,
            {
                "staff_id": staff.staff_id,
                "name": staff.name,
                "email": staff.email,
                "role": staff.role,
                "phone": staff.phone,
                "notes": staff.notes,
                "created_at": staff.created_at,
            },
        )
        self._conn.commit()

    def get_by_id(self, staff_id: str) -> Staff | None:
        row = self._conn.execute(
            "SELECT * FROM staff WHERE staff_id = ?", (staff_id,)
        ).fetchone()
        return Staff(**dict(row)) if row else None

    def get_by_email(self, email: str) -> Staff | None:
        row = self._conn.execute(
            "SELECT * FROM staff WHERE lower(email) = lower(?)", (email,)
        ).fetchone()
        return Staff(**dict(row)) if row else None

    def list_all(self) -> list[Staff]:
        rows = self._conn.execute(
            "SELECT * FROM staff ORDER BY role, name"
        ).fetchall()
        return [Staff(**dict(row)) for row in rows]

    def list_by_role(self, role: str) -> list[Staff]:
        rows = self._conn.execute(
            "SELECT * FROM staff WHERE role = ? ORDER BY name", (role,)
        ).fetchall()
        return [Staff(**dict(row)) for row in rows]

    def update(self, staff: Staff) -> None:
        self._conn.execute(
            """
            UPDATE staff
            SET name = :name, email = :email, role = :role,
                phone = :phone, notes = :notes
            WHERE staff_id = :staff_id
            """,
            {
                "staff_id": staff.staff_id,
                "name": staff.name,
                "email": staff.email,
                "role": staff.role,
                "phone": staff.phone,
                "notes": staff.notes,
            },
        )
        self._conn.commit()

    def delete(self, staff_id: str) -> None:
        self._conn.execute("DELETE FROM staff WHERE staff_id = ?", (staff_id,))
        self._conn.commit()

    def upsert(self, staff: Staff) -> None:
        """依 email 判斷：已存在則更新，否則新增。"""
        existing = self.get_by_email(staff.email)
        if existing:
            staff.staff_id = existing.staff_id
            self.update(staff)
        else:
            self.insert(staff)
```

- [ ] **Step 5: 同時更新 `CompanyRepository.insert()` 與 `CompanyRepository.update()` 支援新欄位**

找到 `CompanyRepository.insert()`，替換 SQL 為：
```python
    def insert(self, company: Company) -> None:
        company.created_at = _now()
        self._conn.execute(
            """
            INSERT INTO companies
                (company_id, name, domain, alias, contact_info,
                 cs_staff_id, sales_staff_id, created_at)
            VALUES
                (:company_id, :name, :domain, :alias, :contact_info,
                 :cs_staff_id, :sales_staff_id, :created_at)
            """,
            {
                "company_id": company.company_id,
                "name": company.name,
                "domain": company.domain,
                "alias": company.alias,
                "contact_info": company.contact_info,
                "cs_staff_id": company.cs_staff_id,
                "sales_staff_id": company.sales_staff_id,
                "created_at": company.created_at,
            },
        )
        self._conn.commit()
```

找到 `CompanyRepository.update()`，替換 SQL 為：
```python
    def update(self, company: Company) -> None:
        self._conn.execute(
            """
            UPDATE companies
            SET name = :name, domain = :domain, alias = :alias,
                contact_info = :contact_info,
                cs_staff_id = :cs_staff_id, sales_staff_id = :sales_staff_id
            WHERE company_id = :company_id
            """,
            {
                "company_id": company.company_id,
                "name": company.name,
                "domain": company.domain,
                "alias": company.alias,
                "contact_info": company.contact_info,
                "cs_staff_id": company.cs_staff_id,
                "sales_staff_id": company.sales_staff_id,
            },
        )
        self._conn.commit()
```

- [ ] **Step 6: 執行測試確認通過**

```bash
cd D:\CMS
.venv/Scripts/python.exe -m pytest tests/unit/test_staff_repository.py -v
```

預期：10 個測試全部 PASSED

- [ ] **Step 7: 執行既有測試確認無回歸**

```bash
cd D:\CMS
.venv/Scripts/python.exe -m pytest tests/unit/ -v --tb=short 2>&1 | tail -20
```

預期：新增 10 個 PASSED，既有測試無新增失敗。

- [ ] **Step 8: Commit**

```bash
git add src/hcp_cms/data/repositories.py tests/unit/test_staff_repository.py
git commit -m "feat: 新增 StaffRepository；CompanyRepository 支援 cs_staff_id/sales_staff_id"
```

---

## Task 3: CustomerManager — Core 層

**Files:**
- Create: `src/hcp_cms/core/customer_manager.py`
- Create: `tests/unit/test_customer_manager.py`

- [ ] **Step 1: 建立測試檔案**

```python
# tests/unit/test_customer_manager.py
"""Tests for CustomerManager."""

import pytest

from hcp_cms.core.customer_manager import CustomerManager
from hcp_cms.data.database import DatabaseManager


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(tmp_path / "test.db")
    manager.initialize()
    yield manager
    manager.close()


class TestBulkUpsertCompanies:
    def test_insert_new_companies(self, db):
        mgr = CustomerManager(db.connection)
        rows = [
            {"name": "ABC 公司", "domain": "abc.com.tw", "alias": "ABC",
             "contact_info": "", "cs_staff_id": None, "sales_staff_id": None},
            {"name": "XYZ 股份", "domain": "xyz.com.tw", "alias": "",
             "contact_info": "", "cs_staff_id": None, "sales_staff_id": None},
        ]
        inserted, updated = mgr.bulk_upsert_companies(rows)
        assert inserted == 2
        assert updated == 0

    def test_update_existing_company(self, db):
        mgr = CustomerManager(db.connection)
        rows = [{"name": "ABC 公司", "domain": "abc.com.tw", "alias": "",
                 "contact_info": "", "cs_staff_id": None, "sales_staff_id": None}]
        mgr.bulk_upsert_companies(rows)
        rows2 = [{"name": "ABC 公司 v2", "domain": "abc.com.tw", "alias": "ABC2",
                  "contact_info": "", "cs_staff_id": None, "sales_staff_id": None}]
        inserted, updated = mgr.bulk_upsert_companies(rows2)
        assert inserted == 0
        assert updated == 1

    def test_empty_domain_skipped(self, db):
        mgr = CustomerManager(db.connection)
        rows = [{"name": "無網域公司", "domain": "", "alias": "",
                 "contact_info": "", "cs_staff_id": None, "sales_staff_id": None}]
        inserted, updated = mgr.bulk_upsert_companies(rows)
        assert inserted == 0

    def test_returns_count_tuple(self, db):
        mgr = CustomerManager(db.connection)
        result = mgr.bulk_upsert_companies([])
        assert result == (0, 0)

    def test_company_stores_cs_staff_id(self, db):
        """bulk_upsert_companies 應儲存 cs_staff_id。"""
        from hcp_cms.data.models import Staff
        from hcp_cms.data.repositories import CompanyRepository, StaffRepository
        # 先建 staff
        StaffRepository(db.connection).insert(
            Staff(staff_id="STAFF-001", name="JILL", email="jill@ares.com.tw", role="cs")
        )
        mgr = CustomerManager(db.connection)
        rows = [{"name": "ABC 公司", "domain": "abc.com.tw", "alias": "",
                 "contact_info": "", "cs_staff_id": "STAFF-001", "sales_staff_id": None}]
        mgr.bulk_upsert_companies(rows)
        company = CompanyRepository(db.connection).get_by_domain("abc.com.tw")
        assert company.cs_staff_id == "STAFF-001"


class TestBulkUpsertStaff:
    def test_insert_new_staff(self, db):
        mgr = CustomerManager(db.connection)
        rows = [
            {"name": "JILL", "email": "jill@ares.com.tw", "role": "cs",
             "phone": "", "notes": ""},
            {"name": "MIKE", "email": "mike@ares.com.tw", "role": "sales",
             "phone": "", "notes": ""},
        ]
        inserted, updated = mgr.bulk_upsert_staff(rows)
        assert inserted == 2

    def test_update_existing_staff(self, db):
        mgr = CustomerManager(db.connection)
        rows = [{"name": "JILL", "email": "jill@ares.com.tw", "role": "cs",
                 "phone": "", "notes": ""}]
        mgr.bulk_upsert_staff(rows)
        rows2 = [{"name": "JILL-NEW", "email": "jill@ares.com.tw", "role": "cs",
                  "phone": "0912", "notes": ""}]
        inserted, updated = mgr.bulk_upsert_staff(rows2)
        assert inserted == 0
        assert updated == 1

    def test_empty_email_skipped(self, db):
        mgr = CustomerManager(db.connection)
        rows = [{"name": "無 Email", "email": "", "role": "cs",
                 "phone": "", "notes": ""}]
        inserted, updated = mgr.bulk_upsert_staff(rows)
        assert inserted == 0


class TestResolveHandlerByDomain:
    def test_resolve_handler_from_domain(self, db):
        """domain 比對到公司，公司有 cs_staff_id，回傳 staff.name。"""
        from hcp_cms.data.models import Company, Staff
        from hcp_cms.data.repositories import CompanyRepository, StaffRepository
        StaffRepository(db.connection).insert(
            Staff(staff_id="STAFF-001", name="JILL", email="jill@ares.com.tw", role="cs")
        )
        CompanyRepository(db.connection).insert(
            Company(company_id="COMP-001", name="ABC 公司", domain="abc.com.tw",
                    cs_staff_id="STAFF-001")
        )
        mgr = CustomerManager(db.connection)
        handler = mgr.resolve_handler_by_domain("abc.com.tw")
        assert handler == "JILL"

    def test_resolve_handler_no_company(self, db):
        """domain 找不到公司時回傳 None。"""
        mgr = CustomerManager(db.connection)
        assert mgr.resolve_handler_by_domain("unknown.com") is None

    def test_resolve_handler_no_staff_assigned(self, db):
        """公司存在但 cs_staff_id 為 None 時回傳 None。"""
        from hcp_cms.data.models import Company
        from hcp_cms.data.repositories import CompanyRepository
        CompanyRepository(db.connection).insert(
            Company(company_id="COMP-001", name="XYZ 公司", domain="xyz.com.tw")
        )
        mgr = CustomerManager(db.connection)
        assert mgr.resolve_handler_by_domain("xyz.com.tw") is None
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
cd D:\CMS
.venv/Scripts/python.exe -m pytest tests/unit/test_customer_manager.py -v
```

預期：`ImportError: cannot import name 'CustomerManager'`

- [ ] **Step 3: 建立 `customer_manager.py`**

```python
# src/hcp_cms/core/customer_manager.py
"""CustomerManager — 客戶公司與人員的業務邏輯層。"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from hcp_cms.data.models import Company, Staff
from hcp_cms.data.repositories import CompanyRepository, StaffRepository


def _gen_company_id() -> str:
    return f"COMP-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"


def _gen_staff_id() -> str:
    return f"STAFF-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"


class CustomerManager:
    """管理客戶公司與人員資料，提供批次 upsert 與 handler 解析。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._company_repo = CompanyRepository(conn)
        self._staff_repo = StaffRepository(conn)

    # ── 公司 ──────────────────────────────────────────────────────────────

    def bulk_upsert_companies(self, rows: list[dict]) -> tuple[int, int]:
        """批次新增/更新客戶公司。

        Args:
            rows: list of dict，每筆需含 name / domain / alias / contact_info /
                  cs_staff_id / sales_staff_id。domain 為空則跳過。

        Returns:
            (inserted, updated) 計數
        """
        inserted = updated = 0
        for row in rows:
            domain = (row.get("domain") or "").strip().lower()
            name = (row.get("name") or "").strip()
            if not domain or not name:
                continue
            existing = self._company_repo.get_by_domain(domain)
            if existing:
                existing.name = name
                existing.alias = (row.get("alias") or "").strip() or existing.alias
                existing.contact_info = (row.get("contact_info") or "").strip() or existing.contact_info
                # 更新人員綁定（允許設為 None 來清除）
                if "cs_staff_id" in row:
                    existing.cs_staff_id = row["cs_staff_id"] or None
                if "sales_staff_id" in row:
                    existing.sales_staff_id = row["sales_staff_id"] or None
                self._company_repo.update(existing)
                updated += 1
            else:
                company = Company(
                    company_id=_gen_company_id(),
                    name=name,
                    domain=domain,
                    alias=(row.get("alias") or "").strip() or None,
                    contact_info=(row.get("contact_info") or "").strip() or None,
                    cs_staff_id=row.get("cs_staff_id") or None,
                    sales_staff_id=row.get("sales_staff_id") or None,
                )
                self._company_repo.insert(company)
                inserted += 1
        return inserted, updated

    def list_companies(self) -> list[Company]:
        return self._company_repo.list_all()

    def delete_company(self, company_id: str) -> None:
        self._company_repo.delete(company_id)

    # ── 人員 ──────────────────────────────────────────────────────────────

    def bulk_upsert_staff(self, rows: list[dict]) -> tuple[int, int]:
        """批次新增/更新人員。

        Args:
            rows: list of dict，每筆需含 name / email / role / phone / notes。
                  email 空字串視為無效，跳過。

        Returns:
            (inserted, updated) 計數
        """
        inserted = updated = 0
        for row in rows:
            email = (row.get("email") or "").strip().lower()
            name = (row.get("name") or "").strip()
            if not email or not name:
                continue
            role = (row.get("role") or "cs").strip()
            staff = Staff(
                staff_id=_gen_staff_id(),
                name=name,
                email=email,
                role=role,
                phone=(row.get("phone") or "").strip() or None,
                notes=(row.get("notes") or "").strip() or None,
            )
            existing = self._staff_repo.get_by_email(email)
            if existing:
                staff.staff_id = existing.staff_id
                self._staff_repo.update(staff)
                updated += 1
            else:
                self._staff_repo.insert(staff)
                inserted += 1
        return inserted, updated

    def list_staff(self, role: str | None = None) -> list[Staff]:
        if role:
            return self._staff_repo.list_by_role(role)
        return self._staff_repo.list_all()

    def delete_staff(self, staff_id: str) -> None:
        self._staff_repo.delete(staff_id)

    # ── 分案解析 ──────────────────────────────────────────────────────────

    def resolve_handler_by_domain(self, domain: str) -> str | None:
        """從 domain 找公司 → 取公司的 cs_staff_id → 回傳 staff.name。

        用於信件收件時自動填入 handler。
        回傳 None 表示無法判斷（公司不存在或未綁定客服）。
        """
        company = self._company_repo.get_by_domain(domain)
        if not company or not company.cs_staff_id:
            return None
        staff = self._staff_repo.get_by_id(company.cs_staff_id)
        return staff.name if staff else None
```

- [ ] **Step 4: 執行測試確認通過**

```bash
cd D:\CMS
.venv/Scripts/python.exe -m pytest tests/unit/test_customer_manager.py -v
```

預期：11 個測試全部 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/core/customer_manager.py tests/unit/test_customer_manager.py
git commit -m "feat: 新增 CustomerManager，支援批次 upsert 與 domain → handler 解析"
```

---

## Task 4: Classifier 擴展 — domain 自動對應 handler

**Files:**
- Modify: `src/hcp_cms/core/classifier.py`
- Create: `tests/unit/test_classifier_staff.py`

**邏輯：** 寄件人 domain → `CustomerManager.resolve_handler_by_domain()` → handler 名稱
優先序：① 主旨 `(RD_XXX)` 標記 → ② domain 查公司 + 客服 → ③ 分類規則

- [ ] **Step 1: 建立測試檔案**

```python
# tests/unit/test_classifier_staff.py
"""Tests for Classifier domain → handler resolution via Staff table."""

import pytest

from hcp_cms.core.classifier import Classifier
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Company, Staff
from hcp_cms.data.repositories import CompanyRepository, StaffRepository


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(tmp_path / "test.db")
    manager.initialize()
    yield manager
    manager.close()


@pytest.fixture
def db_with_company_staff(db):
    """插入 JILL（客服）並綁定到 ABC 公司（domain: abc.com.tw）。"""
    StaffRepository(db.connection).insert(
        Staff(staff_id="STAFF-001", name="JILL", email="jill@ares.com.tw", role="cs")
    )
    CompanyRepository(db.connection).insert(
        Company(company_id="COMP-001", name="ABC 公司", domain="abc.com.tw",
                cs_staff_id="STAFF-001")
    )
    return db


class TestClassifierDomainToHandler:
    def test_handler_resolved_from_sender_domain(self, db_with_company_staff):
        """寄件人 abc.com.tw 應自動設 handler = JILL。"""
        clf = Classifier(db_with_company_staff.connection)
        result = clf.classify(
            subject="系統問題",
            body="請幫忙處理",
            sender_email="customer@abc.com.tw",
            to_recipients=["hcpservice@ares.com.tw"],
        )
        assert result["handler"] == "JILL"

    def test_subject_tag_overrides_domain_handler(self, db_with_company_staff):
        """主旨含 (RD_TONY) 時，標記優先於 domain 查詢。"""
        clf = Classifier(db_with_company_staff.connection)
        result = clf.classify(
            subject="問題 (RD_TONY)",
            body="內容",
            sender_email="customer@abc.com.tw",
            to_recipients=["hcpservice@ares.com.tw"],
        )
        assert result["handler"] == "TONY"

    def test_no_handler_if_company_not_in_db(self, db_with_company_staff):
        """寄件人 domain 不在 companies 表時，handler 為 None。"""
        clf = Classifier(db_with_company_staff.connection)
        result = clf.classify(
            subject="問題",
            body="內容",
            sender_email="someone@unknown.com",
            to_recipients=["hcpservice@ares.com.tw"],
        )
        assert result["handler"] is None or result["handler"] == ""

    def test_no_handler_if_company_has_no_staff(self, db):
        """公司存在但未綁定客服時，handler 為 None。"""
        CompanyRepository(db.connection).insert(
            Company(company_id="COMP-002", name="XYZ 公司", domain="xyz.com.tw")
        )
        clf = Classifier(db.connection)
        result = clf.classify(
            subject="問題",
            body="內容",
            sender_email="someone@xyz.com.tw",
            to_recipients=["hcpservice@ares.com.tw"],
        )
        assert result["handler"] is None or result["handler"] == ""

    def test_subdomain_fallback(self, db_with_company_staff):
        """寄件人為子網域 mail.abc.com.tw 時，fallback 比對 abc.com.tw。"""
        clf = Classifier(db_with_company_staff.connection)
        result = clf.classify(
            subject="問題",
            body="內容",
            sender_email="user@mail.abc.com.tw",
            to_recipients=["hcpservice@ares.com.tw"],
        )
        assert result["handler"] == "JILL"
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
cd D:\CMS
.venv/Scripts/python.exe -m pytest tests/unit/test_classifier_staff.py -v
```

預期：大部分測試失敗（handler 仍為 None）

- [ ] **Step 3: 修改 `classifier.py`**

在 `__init__` 加入 `CustomerManager`：

```python
from hcp_cms.core.customer_manager import CustomerManager
from hcp_cms.data.repositories import CompanyRepository, RuleRepository

class Classifier:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._rule_repo = RuleRepository(conn)
        self._company_repo = CompanyRepository(conn)
        self._customer_mgr = CustomerManager(conn)
```

新增 `_resolve_handler_from_domain()` 方法（在 `_check_broadcast` 之後）：

```python
    def _resolve_handler_from_domain(self, sender_email: str) -> str | None:
        """從寄件人 domain 查公司，再取公司的負責客服名稱。

        支援子網域 fallback：mail.abc.com.tw → abc.com.tw。
        """
        if not sender_email or "@" not in sender_email:
            return None
        from email.utils import parseaddr
        _, addr = parseaddr(sender_email)
        if not addr:
            addr = sender_email
        addr = addr.lower().strip()
        if "@" not in addr:
            return None
        domain = addr.split("@")[1]
        # 直接查詢
        handler = self._customer_mgr.resolve_handler_by_domain(domain)
        if handler:
            return handler
        # 子網域 fallback：mail.abc.com.tw → abc.com.tw
        parts = domain.split(".")
        if len(parts) > 2:
            parent_domain = ".".join(parts[1:])
            handler = self._customer_mgr.resolve_handler_by_domain(parent_domain)
        return handler
```

修改 `classify()` 方法，更新 handler 解析邏輯（完整替換）：

```python
    def classify(self, subject: str, body: str, sender_email: str = "", to_recipients: list[str] | None = None) -> dict:
        text = f"{subject} {body[:300]}"
        tags = self.parse_tags(subject)
        company_id, company_display = self._resolve_company(sender_email, to_recipients or [])

        mantis_ticket_id: str | None = None
        mantis_issue_date: str | None = None
        m_issue = _ISSUE_RE.search(subject or "")
        if m_issue:
            raw_date = m_issue.group(1)
            mantis_ticket_id = m_issue.group(2)
            mantis_issue_date = f"{raw_date[:4]}/{raw_date[4:6]}/{raw_date[6:]}"

        # handler 優先序：① 主旨 (RD_XXX) ② 寄件人 domain → 公司 → 客服 ③ 分類規則
        subject_handler = tags.get("handler")
        domain_handler: str | None = None
        if not subject_handler:
            # 若寄件人是我方，從收件人中找客戶 domain
            from email.utils import parseaddr
            _, saddr = parseaddr(sender_email)
            sender_domain = saddr.split("@")[1].lower() if "@" in saddr else ""
            if sender_domain == OUR_DOMAIN or sender_domain.endswith(f".{OUR_DOMAIN}"):
                # 我方寄出 → 從收件人找客戶
                for r in (to_recipients or []):
                    _, raddr = parseaddr(r)
                    if not raddr:
                        raddr = r
                    raddr = raddr.lower()
                    if "@" in raddr:
                        rdomain = raddr.split("@")[1]
                        if rdomain != OUR_DOMAIN and not rdomain.endswith(f".{OUR_DOMAIN}"):
                            domain_handler = self._resolve_handler_from_domain(r)
                            if domain_handler:
                                break
            else:
                domain_handler = self._resolve_handler_from_domain(sender_email)

        result = {
            "system_product": self._match_rules("product", text, "HCP"),
            "issue_type":     self._match_rules("issue", text, "OTH"),
            "error_type":     self._match_rules("error", text, "人事資料管理"),
            "priority":       self._match_rules("priority", text, "中"),
            "company_id":     company_id,
            "company_display": company_display,
            "is_broadcast":   self._check_broadcast(text),
            "handler":        subject_handler
                              or domain_handler
                              or self._match_rules("handler", text, "")
                              or None,
            "progress":       tags.get("progress") or self._match_rules("progress", text, "") or None,
            "issue_number":   tags.get("issue_number"),
            "mantis_ticket_id": mantis_ticket_id,
            "mantis_issue_date": mantis_issue_date,
        }
        return result
```

- [ ] **Step 4: 執行測試確認通過**

```bash
cd D:\CMS
.venv/Scripts/python.exe -m pytest tests/unit/test_classifier_staff.py -v
```

預期：5 個測試全部 PASSED

- [ ] **Step 5: 執行既有分類器測試確認無回歸**

```bash
cd D:\CMS
.venv/Scripts/python.exe -m pytest tests/unit/test_classifier.py tests/unit/test_classifier_staff.py -v
```

預期：全部 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/hcp_cms/core/classifier.py tests/unit/test_classifier_staff.py
git commit -m "feat: Classifier 新增 domain → 公司 → 客服 handler 自動對應"
```

---

## Task 5: CustomerView — UI 客戶管理頁面

**Files:**
- Create: `src/hcp_cms/ui/customer_view.py`

> UI 層不寫單元測試，手動執行應用程式驗證。

三個分頁：
1. **🏢 客戶公司** — 表格顯示；「負責客服」「負責業務」欄位為下拉選單（從 Staff 選）；批次貼上格式：`公司名稱\t網域\t別名\t聯絡資訊`（人員欄批次貼上後在頁面手動選）
2. **👩‍💼 客服人員** — 表格顯示；批次貼上格式：`姓名\tEmail\t電話\t備註`
3. **🤝 業務人員** — 同上

- [ ] **Step 1: 建立 `customer_view.py`**

```python
# src/hcp_cms/ui/customer_view.py
"""Customer & Staff management view."""

from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.customer_manager import CustomerManager
from hcp_cms.ui.theme import ColorPalette, ThemeManager

# 客戶公司固定欄（不含負責客服/業務，後者用 QComboBox）
_COMPANY_FIXED_COLS: list[tuple[str, str]] = [
    ("公司名稱 *", "name"),
    ("網域 *（@後）", "domain"),
    ("別名", "alias"),
    ("聯絡資訊", "contact_info"),
]
_COMPANY_TOTAL_COLS = len(_COMPANY_FIXED_COLS) + 2  # +負責客服 +負責業務

_STAFF_COLS: list[tuple[str, str]] = [
    ("姓名 *", "name"),
    ("Email *", "email"),
    ("電話", "phone"),
    ("備註", "notes"),
]

_NO_ASSIGN = "（未指定）"


class PasteImportDialog(QDialog):
    """批次貼上對話框——從 Excel 複製 Tab 分隔資料後貼入。"""

    def __init__(self, col_hints: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("批次貼上更新")
        self.resize(640, 400)
        layout = QVBoxLayout(self)
        hint = QLabel(
            f"請貼入 Tab 分隔的資料（可從 Excel 直接複製）\n"
            f"欄位順序：{col_hints}"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._text = QPlainTextEdit()
        self._text.setPlaceholderText("在此貼入資料…")
        layout.addWidget(self._text)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_rows(self) -> list[list[str]]:
        lines = self._text.toPlainText().splitlines()
        result = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            result.append(line.split("\t"))
        return result


class CustomerView(QWidget):
    """客戶管理頁面：客戶公司 / 客服人員 / 業務人員。"""

    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        theme_mgr: ThemeManager | None = None,
    ) -> None:
        super().__init__()
        self._conn = conn
        self._theme_mgr = theme_mgr
        self._cs_staff_options: list[tuple[str, str]] = []   # [(name, staff_id), ...]
        self._sales_staff_options: list[tuple[str, str]] = []
        self._setup_ui()
        if theme_mgr:
            self._apply_theme(theme_mgr.current_palette())
            theme_mgr.theme_changed.connect(self._apply_theme)

    # ── UI 建立 ────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("🏢 客戶管理")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_company_tab(), "🏢 客戶公司")
        self._tabs.addTab(self._build_staff_tab("cs"), "👩‍💼 客服人員")
        self._tabs.addTab(self._build_staff_tab("sales"), "🤝 業務人員")
        layout.addWidget(self._tabs)

        self._tabs.currentChanged.connect(self._on_tab_changed)
        self.refresh()

    def _make_toolbar(self, save_slot, paste_slot, add_slot, delete_slot) -> QWidget:
        bar = QWidget()
        hlay = QHBoxLayout(bar)
        hlay.setContentsMargins(0, 0, 0, 4)
        hlay.setSpacing(6)
        save_btn = QPushButton("💾 儲存變更")
        save_btn.clicked.connect(save_slot)
        hlay.addWidget(save_btn)
        add_btn = QPushButton("➕ 新增一列")
        add_btn.clicked.connect(add_slot)
        hlay.addWidget(add_btn)
        paste_btn = QPushButton("📋 批次貼上")
        paste_btn.clicked.connect(paste_slot)
        hlay.addWidget(paste_btn)
        del_btn = QPushButton("🗑 刪除選取")
        del_btn.setObjectName("dangerBtn")
        del_btn.clicked.connect(delete_slot)
        hlay.addWidget(del_btn)
        hlay.addStretch()
        return bar

    def _build_company_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 8, 0, 0)
        toolbar = self._make_toolbar(
            self._on_save_companies,
            self._on_paste_companies,
            self._on_add_company_row,
            self._on_delete_company,
        )
        layout.addWidget(toolbar)
        headers = [c[0] for c in _COMPANY_FIXED_COLS] + ["負責客服", "負責業務"]
        self._company_table = QTableWidget(0, _COMPANY_TOTAL_COLS)
        self._company_table.setHorizontalHeaderLabels(headers)
        self._company_table.horizontalHeader().setStretchLastSection(True)
        self._company_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._company_table)
        return w

    def _build_staff_tab(self, role: str) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 8, 0, 0)
        if role == "cs":
            toolbar = self._make_toolbar(
                self._on_save_cs_staff, self._on_paste_cs_staff,
                self._on_add_cs_row, self._on_delete_cs_staff,
            )
            self._cs_table = QTableWidget(0, len(_STAFF_COLS))
            self._cs_table.setHorizontalHeaderLabels([c[0] for c in _STAFF_COLS])
            self._cs_table.horizontalHeader().setStretchLastSection(True)
            self._cs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            layout.addWidget(toolbar)
            layout.addWidget(self._cs_table)
        else:
            toolbar = self._make_toolbar(
                self._on_save_sales_staff, self._on_paste_sales_staff,
                self._on_add_sales_row, self._on_delete_sales_staff,
            )
            self._sales_table = QTableWidget(0, len(_STAFF_COLS))
            self._sales_table.setHorizontalHeaderLabels([c[0] for c in _STAFF_COLS])
            self._sales_table.horizontalHeader().setStretchLastSection(True)
            self._sales_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            layout.addWidget(toolbar)
            layout.addWidget(self._sales_table)
        return w

    # ── 載入資料 ──────────────────────────────────────────────────────────

    def refresh(self) -> None:
        if not self._conn:
            return
        mgr = CustomerManager(self._conn)
        # 預先建立下拉選項快取
        cs_list = mgr.list_staff("cs")
        sales_list = mgr.list_staff("sales")
        self._cs_staff_options = [(_NO_ASSIGN, "")] + [(s.name, s.staff_id) for s in cs_list]
        self._sales_staff_options = [(_NO_ASSIGN, "")] + [(s.name, s.staff_id) for s in sales_list]
        self._load_companies()
        self._load_staff_table("cs")
        self._load_staff_table("sales")

    def _load_companies(self) -> None:
        if not self._conn:
            return
        mgr = CustomerManager(self._conn)
        companies = mgr.list_companies()
        tbl = self._company_table
        tbl.setRowCount(0)
        for comp in companies:
            row = tbl.rowCount()
            tbl.insertRow(row)
            vals = [comp.name, comp.domain, comp.alias or "", comp.contact_info or ""]
            for col, val in enumerate(vals):
                tbl.setItem(row, col, QTableWidgetItem(val))
            # 負責客服下拉（col 4）
            cs_cb = self._make_staff_combo(self._cs_staff_options, comp.cs_staff_id)
            tbl.setCellWidget(row, 4, cs_cb)
            # 負責業務下拉（col 5）
            sales_cb = self._make_staff_combo(self._sales_staff_options, comp.sales_staff_id)
            tbl.setCellWidget(row, 5, sales_cb)

    def _make_staff_combo(self, options: list[tuple[str, str]], current_id: str | None) -> QComboBox:
        cb = QComboBox()
        for name, sid in options:
            cb.addItem(name, sid)
        # 選取對應的選項
        if current_id:
            for i, (_, sid) in enumerate(options):
                if sid == current_id:
                    cb.setCurrentIndex(i)
                    break
        return cb

    def _load_staff_table(self, role: str) -> None:
        if not self._conn:
            return
        mgr = CustomerManager(self._conn)
        staff_list = mgr.list_staff(role)
        tbl = self._cs_table if role == "cs" else self._sales_table
        tbl.setRowCount(0)
        for s in staff_list:
            row = tbl.rowCount()
            tbl.insertRow(row)
            vals = [s.name, s.email, s.phone or "", s.notes or ""]
            for col, val in enumerate(vals):
                tbl.setItem(row, col, QTableWidgetItem(val))

    # ── 新增列 ────────────────────────────────────────────────────────────

    def _on_add_company_row(self) -> None:
        tbl = self._company_table
        row = tbl.rowCount()
        tbl.insertRow(row)
        for col in range(len(_COMPANY_FIXED_COLS)):
            tbl.setItem(row, col, QTableWidgetItem(""))
        cs_cb = self._make_staff_combo(self._cs_staff_options, None)
        tbl.setCellWidget(row, 4, cs_cb)
        sales_cb = self._make_staff_combo(self._sales_staff_options, None)
        tbl.setCellWidget(row, 5, sales_cb)

    def _on_add_cs_row(self) -> None:
        tbl = self._cs_table
        row = tbl.rowCount()
        tbl.insertRow(row)
        for col in range(len(_STAFF_COLS)):
            tbl.setItem(row, col, QTableWidgetItem(""))

    def _on_add_sales_row(self) -> None:
        tbl = self._sales_table
        row = tbl.rowCount()
        tbl.insertRow(row)
        for col in range(len(_STAFF_COLS)):
            tbl.setItem(row, col, QTableWidgetItem(""))

    # ── 收集表格資料 ──────────────────────────────────────────────────────

    def _collect_company_rows(self) -> list[dict]:
        tbl = self._company_table
        rows = []
        for r in range(tbl.rowCount()):
            cs_cb = tbl.cellWidget(r, 4)
            sales_cb = tbl.cellWidget(r, 5)
            rows.append({
                "name":          (tbl.item(r, 0).text() if tbl.item(r, 0) else "").strip(),
                "domain":        (tbl.item(r, 1).text() if tbl.item(r, 1) else "").strip(),
                "alias":         (tbl.item(r, 2).text() if tbl.item(r, 2) else "").strip(),
                "contact_info":  (tbl.item(r, 3).text() if tbl.item(r, 3) else "").strip(),
                "cs_staff_id":   cs_cb.currentData() if cs_cb else None,
                "sales_staff_id": sales_cb.currentData() if sales_cb else None,
            })
        return rows

    def _collect_staff_rows(self, role: str) -> list[dict]:
        tbl = self._cs_table if role == "cs" else self._sales_table
        rows = []
        for r in range(tbl.rowCount()):
            rows.append({
                "name":  (tbl.item(r, 0).text() if tbl.item(r, 0) else "").strip(),
                "email": (tbl.item(r, 1).text() if tbl.item(r, 1) else "").strip(),
                "phone": (tbl.item(r, 2).text() if tbl.item(r, 2) else "").strip(),
                "notes": (tbl.item(r, 3).text() if tbl.item(r, 3) else "").strip(),
                "role":  role,
            })
        return rows

    # ── 儲存 ──────────────────────────────────────────────────────────────

    def _on_save_companies(self) -> None:
        if not self._conn:
            return
        rows = self._collect_company_rows()
        mgr = CustomerManager(self._conn)
        inserted, updated = mgr.bulk_upsert_companies(rows)
        QMessageBox.information(self, "儲存完成", f"新增 {inserted} 筆，更新 {updated} 筆。")
        self.refresh()

    def _on_save_cs_staff(self) -> None:
        self._save_staff("cs")

    def _on_save_sales_staff(self) -> None:
        self._save_staff("sales")

    def _save_staff(self, role: str) -> None:
        if not self._conn:
            return
        rows = self._collect_staff_rows(role)
        mgr = CustomerManager(self._conn)
        inserted, updated = mgr.bulk_upsert_staff(rows)
        QMessageBox.information(self, "儲存完成", f"新增 {inserted} 筆，更新 {updated} 筆。")
        self.refresh()

    # ── 批次貼上 ──────────────────────────────────────────────────────────

    def _on_paste_companies(self) -> None:
        hint = "公司名稱\t網域（@後）\t別名\t聯絡資訊"
        dlg = PasteImportDialog(hint, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        paste_rows = dlg.get_rows()
        if not paste_rows:
            return
        col_keys = [c[1] for c in _COMPANY_FIXED_COLS]
        rows = []
        for pr in paste_rows:
            row: dict = {"cs_staff_id": None, "sales_staff_id": None}
            for i, key in enumerate(col_keys):
                row[key] = pr[i].strip() if i < len(pr) else ""
            rows.append(row)
        mgr = CustomerManager(self._conn)
        inserted, updated = mgr.bulk_upsert_companies(rows)
        QMessageBox.information(
            self, "批次貼上完成",
            f"新增 {inserted} 筆，更新 {updated} 筆。\n負責客服/業務請在表格中手動選取後再儲存。"
        )
        self.refresh()

    def _on_paste_cs_staff(self) -> None:
        self._paste_staff("cs")

    def _on_paste_sales_staff(self) -> None:
        self._paste_staff("sales")

    def _paste_staff(self, role: str) -> None:
        hint = "姓名\tEmail\t電話\t備註"
        dlg = PasteImportDialog(hint, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        paste_rows = dlg.get_rows()
        if not paste_rows:
            return
        col_keys = [c[1] for c in _STAFF_COLS]
        rows = []
        for pr in paste_rows:
            row: dict = {"role": role}
            for i, key in enumerate(col_keys):
                row[key] = pr[i].strip() if i < len(pr) else ""
            rows.append(row)
        mgr = CustomerManager(self._conn)
        inserted, updated = mgr.bulk_upsert_staff(rows)
        QMessageBox.information(self, "批次貼上完成", f"新增 {inserted} 筆，更新 {updated} 筆。")
        self.refresh()

    # ── 刪除 ──────────────────────────────────────────────────────────────

    def _on_delete_company(self) -> None:
        tbl = self._company_table
        rows = tbl.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "未選取", "請先選取要刪除的列。")
            return
        reply = QMessageBox.warning(
            self, "確認刪除", f"確定刪除選取的 {len(rows)} 筆客戶？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        mgr = CustomerManager(self._conn)
        for index in sorted(rows, key=lambda i: i.row(), reverse=True):
            domain_item = tbl.item(index.row(), 1)
            if domain_item:
                company = mgr._company_repo.get_by_domain(domain_item.text().strip())
                if company:
                    mgr.delete_company(company.company_id)
        self.refresh()

    def _on_delete_cs_staff(self) -> None:
        self._delete_staff("cs")

    def _on_delete_sales_staff(self) -> None:
        self._delete_staff("sales")

    def _delete_staff(self, role: str) -> None:
        tbl = self._cs_table if role == "cs" else self._sales_table
        rows = tbl.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "未選取", "請先選取要刪除的列。")
            return
        reply = QMessageBox.warning(
            self, "確認刪除", f"確定刪除選取的 {len(rows)} 筆人員？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        from hcp_cms.data.repositories import StaffRepository
        repo = StaffRepository(self._conn)
        mgr = CustomerManager(self._conn)
        for index in sorted(rows, key=lambda i: i.row(), reverse=True):
            email_item = tbl.item(index.row(), 1)
            if email_item:
                staff = repo.get_by_email(email_item.text().strip())
                if staff:
                    mgr.delete_staff(staff.staff_id)
        self.refresh()

    # ── Tab 切換 ──────────────────────────────────────────────────────────

    def _on_tab_changed(self, _index: int) -> None:
        pass

    # ── 主題 ──────────────────────────────────────────────────────────────

    def _apply_theme(self, p: ColorPalette) -> None:
        pass
```

- [ ] **Step 2: 驗證語法**

```bash
cd D:\CMS
.venv/Scripts/python.exe -c "from hcp_cms.ui.customer_view import CustomerView; print('OK')"
```

預期輸出：`OK`

- [ ] **Step 3: Commit**

```bash
git add src/hcp_cms/ui/customer_view.py
git commit -m "feat: 新增 CustomerView 客戶管理頁面（公司/客服/業務三分頁，含下拉選單）"
```

---

## Task 6: MainWindow 整合

**Files:**
- Modify: `src/hcp_cms/ui/main_window.py`

- [ ] **Step 1: import CustomerView**

在 `from hcp_cms.ui.report_view import ReportView` 之後加入：

```python
from hcp_cms.ui.customer_view import CustomerView
```

- [ ] **Step 2: 在 `nav_items` 插入客戶管理（index 2）**

在 `("📋 案件管理", "cases", "⇧C"),` 之後插入：

```python
            ("🏢 客戶管理", "customers", "⇧U"),
```

- [ ] **Step 3: 在 `self._views` 加入 CustomerView**

在 `"cases": CaseView(...)` 之後插入：

```python
            "customers": CustomerView(self._conn, theme_mgr=self._theme_mgr),
```

- [ ] **Step 4: 更新 `_setup_shortcuts()` 的 index（新增後舊 index 全部 +1）**

替換整個 `_setup_shortcuts()` 方法：

```python
    def _setup_shortcuts(self) -> None:
        shortcuts = [
            ("Ctrl+Shift+H", 0),  # 儀表板
            ("Ctrl+Shift+C", 1),  # 案件管理
            ("Ctrl+Shift+U", 2),  # 客戶管理（新增）
            ("Ctrl+Shift+K", 3),  # KMS 知識庫
            ("Ctrl+Shift+E", 4),  # 信件處理
            ("Ctrl+Shift+M", 5),  # Mantis 同步
            ("Ctrl+Shift+R", 6),  # 報表中心
            ("Ctrl+Shift+L", 7),  # 規則設定
            ("Ctrl+Shift+S", 8),  # 系統設定
        ]
        for key, index in shortcuts:
            action = QAction(key, self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(lambda checked=False, i=index: self._nav_list.setCurrentRow(i))
            self.addAction(action)

        help_action = QAction("F1", self)
        help_action.setShortcut(QKeySequence("F1"))
        help_action.triggered.connect(self._on_help_requested)
        self.addAction(help_action)
```

- [ ] **Step 5: 修正 `_on_nav_changed()` 信件處理 index（3 → 4）**

找到：
```python
        if index == 3:  # 信件處理 = index 3
```

改為：
```python
        if index == 4:  # 信件處理 = index 4（客戶管理插入後）
```

- [ ] **Step 6: 執行全部測試確認無回歸**

```bash
cd D:\CMS
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -25
```

預期：全部 PASSED（既有 7 個失敗與本次無關）

- [ ] **Step 7: Commit**

```bash
git add src/hcp_cms/ui/main_window.py
git commit -m "feat: MainWindow 新增「🏢 客戶管理」導覽頁面（Ctrl+Shift+U）"
```

---

## 自我審查

### 規格涵蓋度

| 需求 | Task |
|------|------|
| 客戶公司清單（名稱、網域、別名、聯絡資訊） | Task 1, 5 |
| 公司綁定負責客服 / 業務（下拉選單） | Task 1, 2, 5 |
| 客服人員資訊 | Task 1, 2, 3, 5 |
| 業務人員資訊 | Task 1, 2, 3, 5 |
| 逐筆修正（直接編輯後儲存） | Task 5 `_on_save_*` |
| 全部貼上（批次貼上對話框） | Task 5 `PasteImportDialog` |
| 收件時 domain → 公司 → 客服 → handler | Task 3 `resolve_handler_by_domain()`, Task 4 |
| 新增列功能 | Task 5 `_on_add_*_row()` |

### 分案邏輯確認

```
客戶寄信 customer@abc.com.tw（非 ares.com.tw）
  ↓ Classifier.classify() 偵測非我方 domain
  ↓ _resolve_handler_from_domain("customer@abc.com.tw")
  ↓ CustomerManager.resolve_handler_by_domain("abc.com.tw")
  ↓ CompanyRepository.get_by_domain("abc.com.tw") → Company(cs_staff_id="STAFF-001")
  ↓ StaffRepository.get_by_id("STAFF-001") → Staff(name="JILL")
  ↓ result["handler"] = "JILL"
```

### 型別一致性

- `Company.cs_staff_id: str | None` ✓
- `CustomerManager.resolve_handler_by_domain(domain: str) → str | None` ✓
- `Classifier._resolve_handler_from_domain(sender_email: str) → str | None` ✓
- `bulk_upsert_*` → `tuple[int, int]` ✓
