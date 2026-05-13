# 案件 Header 格式化工具函數 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `format_case_header(case, company_name)` 通用格式化函數，套用至 Mantis 推送 summary 與 bugnote header，對齊客服專區提問格式「2026/5/4 (週一) 下午 04:46【欣興】加班取小值確認」。

**Architecture:** 純函數放 `core/case_formatter.py`，公司名稱由 caller 從 `CompanyRepository` 取。`MantisPushManager.push_case_as_new_ticket` 拒絕推送格式不完整案件；`push_case_as_bugnote` 缺資料時 fallback 為舊格式繼續推。

**Tech Stack:** Python 3.14、既有 `hcp_cms.core.thread_tracker.ThreadTracker.clean_subject`、PySide6（無）、SQLite

**Spec:** [`docs/superpowers/specs/2026-05-13-case-header-format-design.md`](../specs/2026-05-13-case-header-format-design.md)

---

## 檔案結構規劃

### 新增
```
src/hcp_cms/core/case_formatter.py      # format_case_header 純函數
tests/unit/test_case_formatter.py       # 16 個單元測試
```

### 修改
```
src/hcp_cms/core/mantis_push.py         # __init__ 注入 CompanyRepository
                                        # push_case_as_new_ticket 用 format_case_header 產生 summary
                                        # _build_bugnote_text 第一行用 format_case_header（失敗 fallback）
tests/unit/test_mantis_push_manager.py  # setup fixture 補 Company + company_id
                                        # 新增 3 個整合測試（格式套用 / 缺 company / 不存在 company）
```

---

## Task 1：`format_case_header` 純函數 + 單元測試

**Files:**
- Create: `src/hcp_cms/core/case_formatter.py`
- Create: `tests/unit/test_case_formatter.py`

**目的：** 純函數對齊客服專區格式，邊界情況用 ValueError 表達。

- [ ] **Step 1：寫失敗測試**

新增 `tests/unit/test_case_formatter.py`：

```python
"""format_case_header 工具函數單元測試。"""
import pytest

from hcp_cms.core.case_formatter import format_case_header
from hcp_cms.data.models import Case


def _case(**overrides) -> Case:
    """測試用 Case factory，預設值充分滿足格式要求。"""
    defaults = dict(
        case_id="C-1",
        subject="加班取小值確認",
        sent_time="2026/05/04 16:46:00",
    )
    defaults.update(overrides)
    return Case(**defaults)


# ============= 完整格式 =============


def test_full_format_with_all_fields() -> None:
    case = _case()
    assert format_case_header(case, "欣興") == (
        "2026/5/4 (週一) 下午 04:46【欣興】加班取小值確認"
    )


# ============= 主旨清理 =============


def test_strips_re_prefix() -> None:
    case = _case(subject="RE: 加班取小值確認")
    assert "RE:" not in format_case_header(case, "欣興")


def test_strips_multiple_prefixes() -> None:
    case = _case(subject="RE: FW: 加班取小值確認")
    result = format_case_header(case, "欣興")
    assert "RE:" not in result
    assert "FW:" not in result
    assert "加班取小值確認" in result


# ============= 星期 =============


def test_weekday_each_day() -> None:
    """2026/5/4 (一) ~ 2026/5/10 (日) 都覆蓋。"""
    expected = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    for day, weekday in enumerate(expected, start=4):
        case = _case(sent_time=f"2026/05/{day:02d} 10:00:00")
        result = format_case_header(case, "欣興")
        assert f"({weekday})" in result, f"day {day} expected {weekday} in {result}"


# ============= 上午 / 下午 =============


def test_morning() -> None:
    case = _case(sent_time="2026/05/04 09:00:00")
    assert "上午 09:00" in format_case_header(case, "欣興")


def test_noon_is_pm() -> None:
    case = _case(sent_time="2026/05/04 12:00:00")
    assert "下午 12:00" in format_case_header(case, "欣興")


def test_afternoon() -> None:
    case = _case(sent_time="2026/05/04 16:46:00")
    assert "下午 04:46" in format_case_header(case, "欣興")


def test_midnight() -> None:
    """00:30 應顯示「上午 12:30」（12h 制 0 點 = 12 點）。"""
    case = _case(sent_time="2026/05/04 00:30:00")
    assert "上午 12:30" in format_case_header(case, "欣興")


# ============= 日期 / 時間格式 =============


def test_no_leading_zero_on_month_day() -> None:
    case = _case(sent_time="2026/05/04 16:46:00")
    result = format_case_header(case, "欣興")
    assert result.startswith("2026/5/4 ")  # 5/4 不是 05/04


def test_leading_zero_on_hour() -> None:
    """16:46 → 「04:46」（hour 前導 0）。"""
    case = _case(sent_time="2026/05/04 16:46:00")
    assert "04:46" in format_case_header(case, "欣興")


def test_accepts_sent_time_with_seconds() -> None:
    case = _case(sent_time="2026/05/04 16:46:30")
    result = format_case_header(case, "欣興")
    assert "下午 04:46" in result  # 秒不顯示


def test_accepts_sent_time_without_seconds() -> None:
    case = _case(sent_time="2026/05/04 16:46")
    result = format_case_header(case, "欣興")
    assert "下午 04:46" in result


# ============= 缺漏資料 =============


def test_raises_when_sent_time_missing() -> None:
    case = _case(sent_time=None)
    with pytest.raises(ValueError, match="sent_time"):
        format_case_header(case, "欣興")


def test_raises_when_sent_time_empty() -> None:
    case = _case(sent_time="")
    with pytest.raises(ValueError, match="sent_time"):
        format_case_header(case, "欣興")


def test_raises_when_sent_time_invalid_format() -> None:
    case = _case(sent_time="not a date")
    with pytest.raises(ValueError, match="sent_time"):
        format_case_header(case, "欣興")


def test_raises_when_company_name_missing() -> None:
    case = _case()
    with pytest.raises(ValueError, match="company_name"):
        format_case_header(case, None)


def test_raises_when_company_name_empty() -> None:
    case = _case()
    with pytest.raises(ValueError, match="company_name"):
        format_case_header(case, "")


def test_raises_when_subject_missing() -> None:
    case = _case(subject=None)
    with pytest.raises(ValueError, match="subject"):
        format_case_header(case, "欣興")


def test_raises_when_subject_empty() -> None:
    case = _case(subject="")
    with pytest.raises(ValueError, match="subject"):
        format_case_header(case, "欣興")


def test_raises_when_subject_only_prefixes() -> None:
    """主旨全部是 RE:/FW: 等前綴，clean 後為空 → ValueError。"""
    case = _case(subject="RE: FW: ")
    with pytest.raises(ValueError, match="subject"):
        format_case_header(case, "欣興")
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
cd /d/CMS/.claude/worktrees/case-header-format
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_case_formatter.py -v
```

預期：FAIL（`hcp_cms.core.case_formatter` 不存在）

- [ ] **Step 3：實作 `format_case_header`**

新增 `src/hcp_cms/core/case_formatter.py`：

```python
"""案件 header 格式化工具 — 對齊客服專區提問格式。

範例：
    "2026/5/4 (週一) 下午 04:46【欣興】加班取小值確認"

使用場景：
    - MantisPushManager 推送 ticket summary
    - MantisPushManager 推送 bugnote 第一行
    - 未來桌面 App / 報表也可重用
"""
from __future__ import annotations

from datetime import datetime

from hcp_cms.core.thread_tracker import ThreadTracker
from hcp_cms.data.models import Case

_WEEKDAYS = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
_SUPPORTED_FORMATS = (
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
)


def format_case_header(case: Case, company_name: str | None) -> str:
    """格式化案件 header。

    Args:
        case: 含 sent_time + subject 的案件
        company_name: 公司名稱（caller 從 CompanyRepository 查好傳入）

    Returns:
        例如 "2026/5/4 (週一) 下午 04:46【欣興】加班取小值確認"

    Raises:
        ValueError: sent_time / company_name / subject 任一缺漏或無法解析
    """
    if not case.sent_time:
        raise ValueError("sent_time is empty")

    dt = _parse_sent_time(case.sent_time)
    if dt is None:
        raise ValueError(f"sent_time is not a parseable format: {case.sent_time!r}")

    if not company_name:
        raise ValueError("company_name is required")

    if not case.subject:
        raise ValueError("subject is empty")

    clean_subject = ThreadTracker.clean_subject(case.subject)
    if not clean_subject:
        raise ValueError("subject is empty after stripping prefixes")

    date_part = f"{dt.year}/{dt.month}/{dt.day}"
    weekday = _WEEKDAYS[dt.weekday()]
    ampm = "上午" if dt.hour < 12 else "下午"
    hour_12 = dt.hour % 12 if (dt.hour % 12) else 12
    time_part = f"{hour_12:02d}:{dt.minute:02d}"

    return f"{date_part} ({weekday}) {ampm} {time_part}【{company_name}】{clean_subject}"


def _parse_sent_time(s: str) -> datetime | None:
    """嘗試多種格式 parse sent_time，全失敗回 None。"""
    for fmt in _SUPPORTED_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None
```

- [ ] **Step 4：跑測試驗證通過**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_case_formatter.py -v
```

預期：19 個測試 PASS（16 個 spec 列的 + 3 個額外邊界補強）

- [ ] **Step 5：Lint**

```bash
/d/CMS/.venv/Scripts/ruff.exe check src/hcp_cms/core/case_formatter.py tests/unit/test_case_formatter.py
```

預期：All checks passed!

- [ ] **Step 6：Commit**

```bash
git add src/hcp_cms/core/case_formatter.py tests/unit/test_case_formatter.py
git commit -m "feat(core): format_case_header 工具函數對齊客服專區提問格式

Task 1 of 案件 Header 格式化實作計畫。

格式：「2026/5/4 (週一) 下午 04:46【欣興】加班取小值確認」

- 純函數，公司名稱由 caller 傳入
- 嚴格模式：sent_time / company_name / subject 缺漏 → ValueError
- 主旨清理沿用 ThreadTracker.clean_subject() 去 RE/FW 前綴
- 支援 sent_time 含秒 / 不含秒兩種既有格式
- 12h 制：0 點顯示 12，hour 前導 0；月日無前導 0
- 19 個單元測試覆蓋完整格式 / 各邊界 / 缺漏路徑"
```

---

## Task 2：MantisPushManager 整合 + 既有測試補 Company

**Files:**
- Modify: `src/hcp_cms/core/mantis_push.py`（`__init__` 注入 CompanyRepository、`push_case_as_new_ticket` 用新 summary、`_build_bugnote_text` 第一行替換）
- Modify: `tests/unit/test_mantis_push_manager.py`（setup fixture 補 Company + company_id；新增 3 個整合測試）

**目的：** 把 format_case_header 接到 Mantis 推送流程：建新 ticket 嚴格用新格式（失敗拒絕），bugnote 失敗時 fallback。

- [ ] **Step 1：寫失敗測試（既有 fixture 升級 + 3 個新測試）**

修改 `tests/unit/test_mantis_push_manager.py`：

**找到既有 imports 區段（line 1-15 左右），補加 Company 相關 imports：**

```python
from hcp_cms.data.models import Case, CaseMantisLink, Company, MantisTicket
from hcp_cms.data.repositories import (
    CaseMantisRepository,
    CaseRepository,
    CompanyRepository,
    MantisRepository,
)
```

**替換既有 setup fixture（line 25-39 區段）：**

```python
@pytest.fixture
def setup(tmp_path: Path):
    db = DatabaseManager(tmp_path / "t.db")
    db.initialize()
    # 補 Company（format_case_header 需要 company name）
    CompanyRepository(db.connection).insert(
        Company(company_id="CO-1", name="測試公司", domain="test.com")
    )
    CaseRepository(db.connection).insert(
        Case(
            case_id="C-1",
            subject="印表機異常",
            progress="已聯絡客戶確認",
            priority="高",
            handler="YOGA",
            company_id="CO-1",
            sent_time="2026/05/04 16:46:00",
        )
    )
    yield db
    db.close()
```

⚠ 既有測試中 `test_push_case_as_new_ticket_priority_mapping`、`test_push_cases_batch_mixed_results` 等 inline 建立 Case 也需補 `company_id="CO-1"` + `sent_time="2026/05/04 16:46:00"`，否則新整合會失敗。Step 4 跑測試時若發現失敗再回頭補。

**新增 3 個整合測試（檔末附加）：**

```python
# ============= format_case_header 整合 =============


def test_push_uses_formatted_summary(setup) -> None:
    """推送時 SOAP 收到的 summary 應為 format_case_header 的輸出，而非 case.subject。"""
    db = setup
    client = MagicMock()
    client.create_issue.return_value = "777"

    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    success, _ = mgr.push_case_as_new_ticket("C-1", "S-YOGA")
    assert success is True

    sent_summary = client.create_issue.call_args.kwargs["summary"]
    assert "2026/5/4" in sent_summary
    assert "(週一)" in sent_summary
    assert "下午 04:46" in sent_summary
    assert "【測試公司】" in sent_summary
    assert "印表機異常" in sent_summary


def test_push_fails_when_case_has_no_company_link(setup) -> None:
    """case.company_id 為 None → format_case_header 拋例外 → push 回傳 (False, '案件格式不完整：...')。"""
    db = setup
    # 建一筆無 company_id 的案件
    CaseRepository(db.connection).insert(
        Case(
            case_id="C-NO-COMPANY",
            subject="無公司案件",
            handler="YOGA",
            sent_time="2026/05/04 10:00:00",
        )
    )
    client = MagicMock()
    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    success, payload = mgr.push_case_as_new_ticket("C-NO-COMPANY", "S-YOGA")

    assert success is False
    assert "格式不完整" in payload
    client.create_issue.assert_not_called()


def test_push_fails_when_company_id_does_not_exist(setup) -> None:
    """case.company_id 指向不存在公司 → 同樣失敗（CompanyRepository.get_by_id 返回 None）。"""
    db = setup
    CaseRepository(db.connection).insert(
        Case(
            case_id="C-GHOST-COMPANY",
            subject="幽靈公司案件",
            handler="YOGA",
            company_id="CO-NONEXISTENT",
            sent_time="2026/05/04 10:00:00",
        )
    )
    client = MagicMock()
    mgr = MantisPushManager(db.connection, client=client, project_id="218")
    success, payload = mgr.push_case_as_new_ticket("C-GHOST-COMPANY", "S-YOGA")

    assert success is False
    assert "格式不完整" in payload
    client.create_issue.assert_not_called()
```

- [ ] **Step 2：跑測試驗證失敗**

```bash
cd /d/CMS/.claude/worktrees/case-header-format
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_push_manager.py -v 2>&1 | tail -30
```

預期：多筆 FAIL（既有測試因 fixture 改變失敗 + 3 個新測試也 FAIL）。重點看新測試錯誤訊息確認方向對。

- [ ] **Step 3：實作 MantisPushManager 整合**

讀 `src/hcp_cms/core/mantis_push.py` 既有結構，做 3 處修改：

**(3a) imports（檔頭）增加：**

於 `src/hcp_cms/core/mantis_push.py` imports 區段補：

```python
from hcp_cms.core.case_formatter import format_case_header
from hcp_cms.data.repositories import (
    CaseLogRepository,
    CaseMantisRepository,
    CaseRepository,
    CompanyRepository,  # 新增
    MantisRepository,
)
```

**(3b) `__init__` 新增 CompanyRepository：**

於 `self._mantis_repo = MantisRepository(conn)` 之後加：

```python
self._company_repo = CompanyRepository(conn)
```

**(3c) `push_case_as_new_ticket` 內 SOAP 呼叫前，用 format_case_header 產生 summary：**

找到方法內取得 case 後、SOAP `create_issue` 呼叫前的位置，把整段 client.create_issue 改成：

```python
        # 取公司名稱
        company = self._company_repo.get_by_id(case.company_id) if case.company_id else None
        company_name = company.name if company else None

        # 格式化 summary（缺漏會拋 ValueError）
        try:
            summary = format_case_header(case, company_name)
        except ValueError as e:
            return False, f"案件格式不完整：{e}"

        ticket_id = self._client.create_issue(
            project_id=self._project_id,
            summary=summary,
            description=self._build_description(case),
            category=self._category,
            priority=_PRIORITY_MAP.get(case.priority or "中", "normal"),
            severity="minor",
            handler=case.handler if case.handler else None,
        )
```

⚠ 注意：原本是 `summary=case.subject or f"HCP CMS 案件 {case_id}"`。新版完全用 format_case_header，不再用 case.subject fallback——因為缺漏會直接 ValueError，不會走到 SOAP 呼叫。

**(3d) `_build_bugnote_text` 第一行用 format_case_header（失敗 fallback）：**

定位既有方法（搜尋 `def _build_bugnote_text`）。將首行 `parts = [f"[HCP-CMS: {case.case_id}] 更新"]` 改為：

```python
    def _build_bugnote_text(self, case: Case) -> str:
        """組裝 bugnote 文字：當前狀態 + 進度 + 最新 case_log。"""
        # 取公司名稱
        company = self._company_repo.get_by_id(case.company_id) if case.company_id else None
        company_name = company.name if company else None

        # 嘗試新格式 header，失敗 fallback 舊格式（bugnote 容忍度高）
        try:
            header = format_case_header(case, company_name)
        except ValueError:
            header = f"[HCP-CMS: {case.case_id}] 更新"

        parts = [header]
        if case.status:
            parts.append(f"【當前狀態】{case.status}")
        if case.progress:
            parts.append(f"【最新進度】\n{case.progress}")

        # 抓最新一筆非 Mantis 推送 case_log
        logs = self._log_repo.list_by_case(case.case_id)
        non_push_logs = [log for log in logs if log.direction != "Mantis 推送"]
        if non_push_logs:
            latest = non_push_logs[0]
            parts.append(f"【最新記錄 ({latest.direction})】\n{latest.content or ''}")

        return "\n\n".join(parts)
```

- [ ] **Step 4：跑測試（mantis_push_manager） + 補既有 fixture**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest tests/unit/test_mantis_push_manager.py -v 2>&1 | tail -30
```

如果有任何 inline 建立的 Case 缺 `company_id` 或 `sent_time`（會看到 `案件格式不完整：...` 失敗），補上對應欄位。例如：

```python
# 原本
CaseRepository(db.connection).insert(Case(case_id="C-M", subject="中", priority="中", handler="YOGA"))

# 改為
CaseRepository(db.connection).insert(Case(
    case_id="C-M", subject="中", priority="中", handler="YOGA",
    company_id="CO-1", sent_time="2026/05/04 16:46:00",
))
```

重跑直到所有測試通過。

- [ ] **Step 5：跑全部 mantis 相關測試確認無回歸**

```bash
/d/CMS/.venv/Scripts/python.exe -m pytest \
  tests/unit/test_mantis_push_manager.py \
  tests/unit/test_mantis_soap_write.py \
  tests/unit/test_mantis_push_dialog.py \
  tests/integration/test_web_portal_flow.py \
  tests/unit/test_case_formatter.py \
  -q 2>&1 | tail -5
```

預期：全部 PASS

- [ ] **Step 6：Lint**

```bash
/d/CMS/.venv/Scripts/ruff.exe check src/hcp_cms/core/mantis_push.py tests/unit/test_mantis_push_manager.py
```

預期：All checks passed!

- [ ] **Step 7：Commit**

```bash
git add src/hcp_cms/core/mantis_push.py tests/unit/test_mantis_push_manager.py
git commit -m "feat(core): MantisPushManager 整合 format_case_header

Task 2 of 案件 Header 格式化實作計畫。

- __init__ 注入 CompanyRepository
- push_case_as_new_ticket: 用 format_case_header 產生 summary，
  缺資料時拒絕推送並返回 (False, '案件格式不完整：...')
- _build_bugnote_text: 第一行用 format_case_header；
  失敗 fallback 為舊格式（bugnote 容忍度高，已有 ticket）
- 既有 setup fixture 補 Company + company_id + sent_time
- 新增 3 個整合測試：格式套用 / 無 company_id / 不存在 company"
```

---

## Task 3：手動 smoke test + 最終驗收

**Files:**
- 無修改檔案，僅驗證 + 文件補充

- [ ] **Step 1：跑完整 mantis-related test suite**

```bash
cd /d/CMS/.claude/worktrees/case-header-format
/d/CMS/.venv/Scripts/python.exe -m pytest \
  tests/unit/test_mantis_push_manager.py \
  tests/unit/test_mantis_soap_write.py \
  tests/unit/test_mantis_push_dialog.py \
  tests/integration/test_web_portal_flow.py \
  tests/unit/test_case_formatter.py \
  tests/unit/test_audit_logger.py \
  tests/unit/test_case_visibility_filter.py \
  tests/unit/test_thread_tracker_closed_case.py \
  -q 2>&1 | tail -5
```

預期：全部 PASS

- [ ] **Step 2：Lint 整個 core/ 與 ui/ 受影響檔案**

```bash
/d/CMS/.venv/Scripts/ruff.exe check \
  src/hcp_cms/core/case_formatter.py \
  src/hcp_cms/core/mantis_push.py \
  tests/unit/test_case_formatter.py \
  tests/unit/test_mantis_push_manager.py
```

預期：All checks passed!

- [ ] **Step 3（選做）：Live test 推一筆案件到 Mantis**

選一筆 DB 中**含完整 company_id + sent_time + subject** 的案件，用 CLI 推送看 Mantis ticket summary 是否符合新格式：

```bash
/d/CMS/.venv/Scripts/python.exe << 'PY'
import sqlite3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from hcp_cms.services.credential import CredentialManager
from hcp_cms.services.mantis.soap import MantisSoapClient
from hcp_cms.core.mantis_push import MantisPushManager

# 用實際 DB 路徑（替換）
conn = sqlite3.connect("path/to/real/cs_tracker.db")
conn.row_factory = sqlite3.Row

# 列幾筆候選案件
rows = conn.execute("""
    SELECT c.case_id, c.subject, c.sent_time, co.name AS company_name
    FROM cs_cases c
    LEFT JOIN companies co ON c.company_id = co.company_id
    WHERE c.case_id NOT IN (SELECT case_id FROM case_mantis)
      AND c.sent_time IS NOT NULL AND c.sent_time != ''
      AND co.name IS NOT NULL
    ORDER BY c.updated_at DESC LIMIT 3
""").fetchall()
print("Top 3 候選：")
for r in rows:
    print(f"  {r['case_id']}  {r['sent_time'][:16]}  {r['company_name']}  {r['subject'][:40]}")

# 推送其中 1 筆
creds = CredentialManager()
client = MantisSoapClient(
    creds.retrieve("mantis_url"),
    creds.retrieve("mantis_user"),
    creds.retrieve("mantis_password"),
)
client.connect()
mgr = MantisPushManager(conn, client, project_id="218")
test_case_id = rows[0]["case_id"]
success, payload = mgr.push_case_as_new_ticket(test_case_id, "S-JILL")
print(f"\n推送結果：{success} / {payload}")
PY
```

到 Mantis 確認 ticket #N 的 summary 格式正確（含日期/星期/上下午/【公司】/主旨）。確認後**刪除測試 ticket**。

⚠ 此 step 為選做。Task 2 既有 11 個單元測試 + 3 個新整合測試已充分驗證邏輯。

- [ ] **Step 4：commit（若有微調）**

如 Live test 發現格式微調需求，回 Task 1 改字串模板 + 補測試，重 commit。

否則本 Task 不產生 commit。

---

## 完工檢查

- [ ] 19 個 case_formatter 測試 + 3 個新 mantis push 整合測試全 pass
- [ ] 既有 mantis push manager 11 個測試全 pass（fixture 升級後）
- [ ] 既有 web portal flow / mantis dialog / mantis soap 測試無回歸
- [ ] Ruff 全 pass
- [ ] 手動 Live test 通過（選做）

---

## 風險與處理

| 風險 | 處理 |
|------|------|
| 既有 mantis_push_manager.py 測試多處 inline Case 缺 company_id 會集體失敗 | Step 4 跑測試後逐一補 |
| Live test 在實際 DB 上跑可能誤推 ticket | 推完立刻到 Mantis 手動 close/delete |
| `sent_time` 格式跨年代不一致（例如 `"YYYY-MM-DD"`）| 目前只支援 `/` 分隔 + (H:M / H:M:S)。若實際資料有別格式，下次擴 `_SUPPORTED_FORMATS` 即可 |
| MantisPushManager 失敗訊息含「格式不完整」未被 UI 特別標示 | CaseView 既有 `setDetailedText` 已顯示，使用者可看到 |
