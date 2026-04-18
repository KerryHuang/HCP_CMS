# 補充說明強化與人工編輯介面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 強化 PATCH 補充說明五欄位的 AI 分析準確度（整合三來源輸入 + 改善 Prompt），並新增 S2T 後的人工逐筆審閱編輯器。

**Architecture:** 四層改動（Services → Data → Core → UI）。`ClaudeContentService.extract_supplement()` 介面由單一文字改為三來源具名參數；`PatchRepository` 新增 `update_issue_supplement()` 讀改 `mantis_detail` JSON 中的 supplement；新增 `SupplementEditorWidget`（QSplitter 左右分割）嵌入 `patch_monthly_tab.py` 並新增「⑥ 補充說明」步驟。

**Tech Stack:** Python 3.14、PySide6 6.10、SQLite（`mantis_detail` JSON 欄位）、Anthropic Claude API（`claude-sonnet-4-6`）

---

## 檔案結構

| 檔案 | 動作 | 職責 |
|------|------|------|
| `src/hcp_cms/services/claude_content.py` | 修改 | `extract_supplement()` 三來源介面 + 強化 prompt |
| `src/hcp_cms/services/mantis/soap.py` | 修改 | `_parse_notes()` 上限 5→10 |
| `src/hcp_cms/data/repositories.py` | 修改 | 新增 `update_issue_supplement()` |
| `src/hcp_cms/core/monthly_patch_engine.py` | 修改 | `_fetch_supplement()` 傳入 PatchIssue；新增 `fetch_supplement_single()`；`fetch_supplements()` 新增 `skip_edited` 參數 |
| `src/hcp_cms/ui/supplement_editor_widget.py` | 新增 | 左右分割補充說明編輯器元件 |
| `src/hcp_cms/ui/patch_monthly_tab.py` | 修改 | 新增步驟 + 按鈕 + 整合編輯器 |
| `tests/unit/test_supplement_enrichment.py` | 新增 | 所有新功能單元測試 |

---

### Task 1: ClaudeContentService — 三來源 extract_supplement 介面

**Files:**
- Modify: `src/hcp_cms/services/claude_content.py`
- Test: `tests/unit/test_supplement_enrichment.py`

**背景：** 目前 `extract_supplement(mantis_text: str)` 只接受一段純文字，無欄位定義，prompt 品質低落。改為四個具名參數，分別傳入 ReleaseNote 與 Mantis 兩類資料，並重寫 prompt 加入欄位定義與業務背景。

- [ ] **Step 1: 建立測試檔並寫第一個失敗測試**

建立 `tests/unit/test_supplement_enrichment.py`：

```python
"""tests/unit/test_supplement_enrichment.py — 補充說明強化功能測試。"""
import json
import pytest
from unittest.mock import MagicMock


# ── Task 1: ClaudeContentService ──────────────────────────────────────────

def test_extract_supplement_no_client():
    """Claude client 為 None 時回傳全空 dict，不呼叫 API。"""
    from hcp_cms.services.claude_content import ClaudeContentService
    svc = ClaudeContentService.__new__(ClaudeContentService)
    svc._client = None
    result = svc.extract_supplement(
        release_note_description="有內容",
        mantis_description="有描述",
    )
    assert result == {"修改原因": "", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}
```

- [ ] **Step 2: 執行確認失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_supplement_enrichment.py::test_extract_supplement_no_client -v
```

預期：FAIL（`extract_supplement` 簽名不符）

- [ ] **Step 3: 修改 `extract_supplement()` 為新介面**

將 `src/hcp_cms/services/claude_content.py` 的 `extract_supplement` 方法完整替換為：

```python
_INSUFFICIENT = "⚠ 資料不足，請人工補充"
_SPARSE_THRESHOLD = 30  # 有效字數低於此值時加入稀疏提示

def extract_supplement(
    self,
    release_note_description: str = "",
    release_note_impact: str = "",
    mantis_description: str = "",
    mantis_notes: list[dict] | None = None,
) -> dict[str, str]:
    """分析三來源資料，回傳結構化補充說明五欄位。

    mantis_notes: list of {"reporter": str, "date": str, "text": str}
    """
    empty = {k: "" for k in _SUPPLEMENT_KEYS}
    if self._client is None:
        return empty

    notes_list = mantis_notes or []
    if notes_list:
        notes_text = "\n".join(
            f"[{n.get('date', '')}] {n.get('reporter', '')}：{n.get('text', '')}"
            for n in notes_list
        )
    else:
        notes_text = "（無活動記錄）"

    all_text = " ".join([
        release_note_description, release_note_impact,
        mantis_description, notes_text,
    ])
    effective_chars = len(all_text.replace(" ", "").replace("　", "").replace("\n", ""))
    sparse_hint = (
        "\n⚠ 注意：以上資料非常有限，若無法合理填寫請直接填入資料不足標記。"
        if effective_chars < _SPARSE_THRESHOLD else ""
    )

    prompt = (
        "你是 HCP ERP 系統的技術文件分析助理。\n"
        "請根據以下來自三個來源的資料，以繁體中文填寫五個補充說明欄位。\n\n"
        "【欄位定義】\n"
        f"- 修改原因：此次修改的業務或技術背景，解釋「為什麼要改」\n"
        f"- 原問題：修改前系統存在的問題現象，解釋「原本出了什麼問題」\n"
        f"- 範例說明：具體操作情境或資料範例（如有）\n"
        f"- 修正後：修改後的行為或效果說明\n"
        f"- 注意事項：上線後測試重點、注意事項或相依模組\n\n"
        f"【資料：ReleaseNote 說明】\n"
        f"功能說明：{release_note_description or '（無）'}\n"
        f"影響說明：{release_note_impact or '（無）'}\n\n"
        f"【資料：Mantis 問題描述】\n"
        f"{mantis_description or '（無）'}\n\n"
        f"【資料：Mantis 活動筆記（依時間排列）】\n"
        f"{notes_text}"
        f"{sparse_hint}\n\n"
        f"請以 JSON 格式回傳，key 為繁體中文欄位名稱。\n"
        f'若某欄位無對應內容且無法合理推斷，值填入「{_INSUFFICIENT}」。\n'
        f"只回傳 JSON，不要其他說明。"
    )
    raw = self._call_api(prompt, max_tokens=800)
    if not raw:
        return empty
    try:
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return empty
        data = json.loads(match.group())
        return {k: str(data.get(k) or "") for k in _SUPPLEMENT_KEYS}
    except (ValueError, KeyError):
        return empty
```

同時在 `claude_content.py` 頂部的 `import json` 已存在，確認 `_SUPPLEMENT_KEYS` 與 `_INSUFFICIENT` 位於模組層級（`_SUPPLEMENT_KEYS` 已在第 12 行，在其下新增 `_INSUFFICIENT` 與 `_SPARSE_THRESHOLD`）。

- [ ] **Step 4: 執行確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_supplement_enrichment.py::test_extract_supplement_no_client -v
```

預期：PASS

- [ ] **Step 5: 補充兩個測試**

在 `test_supplement_enrichment.py` 追加：

```python
def test_extract_supplement_all_sources(monkeypatch):
    """三來源皆有資料時，五欄位均有輸出，prompt 包含各來源文字。"""
    from hcp_cms.services.claude_content import ClaudeContentService
    svc = ClaudeContentService.__new__(ClaudeContentService)
    svc._client = object()  # 非 None
    captured: dict = {}

    def fake_call(prompt: str, max_tokens: int) -> str:
        captured["prompt"] = prompt
        return '{"修改原因":"A","原問題":"B","範例說明":"C","修正後":"D","注意事項":"E"}'

    monkeypatch.setattr(svc, "_call_api", fake_call)
    result = svc.extract_supplement(
        release_note_description="薪資計算異常",
        release_note_impact="影響 HR 模組",
        mantis_description="員工點薪資查詢時系統報錯",
        mantis_notes=[{"reporter": "工程師A", "date": "2026-03-15", "text": "已修正第220行邏輯"}],
    )
    assert result["修改原因"] == "A"
    assert result["注意事項"] == "E"
    assert "薪資計算異常" in captured["prompt"]
    assert "員工點薪資查詢" in captured["prompt"]
    assert "工程師A" in captured["prompt"]
    assert "欄位定義" in captured["prompt"]


def test_extract_supplement_sparse_data(monkeypatch):
    """三來源合計有效字 < 30 時，prompt 包含稀疏資料提示。"""
    from hcp_cms.services.claude_content import ClaudeContentService
    svc = ClaudeContentService.__new__(ClaudeContentService)
    svc._client = object()
    captured: dict = {}

    def fake_call(prompt: str, max_tokens: int) -> str:
        captured["prompt"] = prompt
        return '{"修改原因":"⚠ 資料不足，請人工補充","原問題":"","範例說明":"","修正後":"","注意事項":""}'

    monkeypatch.setattr(svc, "_call_api", fake_call)
    svc.extract_supplement(
        release_note_description="短",
        release_note_impact="",
        mantis_description="",
        mantis_notes=[],
    )
    assert "以上資料非常有限" in captured["prompt"]
```

- [ ] **Step 6: 執行確認三個測試全過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_supplement_enrichment.py -v
```

預期：3 PASSED

- [ ] **Step 7: Lint**

```bash
.venv/Scripts/ruff.exe check src/hcp_cms/services/claude_content.py
```

預期：無錯誤

- [ ] **Step 8: Commit**

```bash
git add src/hcp_cms/services/claude_content.py tests/unit/test_supplement_enrichment.py
git commit -m "feat(services): 強化 extract_supplement 三來源介面與 prompt 定義"
```

---

### Task 2: MantisSoapClient — 筆記上限 5→10

**Files:**
- Modify: `src/hcp_cms/services/mantis/soap.py:88`
- Test: `tests/unit/test_supplement_enrichment.py`

**背景：** `get_issue()` 呼叫 `_parse_notes(text, max_count=5)`，只保留最後 5 條筆記。改為 10 條以捕捉更多工程師的分析記錄。

- [ ] **Step 1: 新增測試**

在 `test_supplement_enrichment.py` 追加：

```python
# ── Task 2: MantisSoapClient ───────────────────────────────────────────────

def test_parse_notes_limit_10():
    """_parse_notes 應保留最後 10 條筆記。"""
    from hcp_cms.services.mantis.soap import MantisSoapClient
    # 建立 12 條假筆記的 XML
    items_xml = "".join(
        f"<item><id>{i}</id><reporter><name>u{i}</name></reporter>"
        f"<text>note{i}</text><date_submitted>2026-03-{i:02d}T00:00:00Z</date_submitted></item>"
        for i in range(1, 13)
    )
    xml = f"<notes>{items_xml}</notes>"
    notes, total = MantisSoapClient._parse_notes(xml, max_count=10)
    assert total == 12
    assert len(notes) == 10
```

- [ ] **Step 2: 執行確認通過（max_count=10 已是參數，測試本身即是文件）**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_supplement_enrichment.py::test_parse_notes_limit_10 -v
```

預期：PASS（`_parse_notes` 支援任意 `max_count`，測試 10 條上限）

- [ ] **Step 3: 修改 `get_issue()` 呼叫**

在 `src/hcp_cms/services/mantis/soap.py` 第 88 行，將：

```python
notes_list, notes_count = self._parse_notes(text, max_count=5)
```

改為：

```python
notes_list, notes_count = self._parse_notes(text, max_count=10)
```

- [ ] **Step 4: Commit**

```bash
git add src/hcp_cms/services/mantis/soap.py tests/unit/test_supplement_enrichment.py
git commit -m "feat(services): Mantis 筆記上限從 5 增加至 10 條"
```

---

### Task 3: PatchRepository — update_issue_supplement

**Files:**
- Modify: `src/hcp_cms/data/repositories.py`（在 `update_issue_mantis_detail` 之後新增）
- Test: `tests/unit/test_supplement_enrichment.py`

**背景：** 目前 `fetch_supplements` 直接操作 `mantis_detail` JSON 字串。新增 `update_issue_supplement()` 方法，讀取現有 JSON、更新 supplement 欄位、寫回，支援 `manual=True` 旗標（`supplement_edited=True`）。

- [ ] **Step 1: 新增失敗測試**

在 `test_supplement_enrichment.py` 追加：

```python
# ── Task 3: PatchRepository ────────────────────────────────────────────────

@pytest.fixture
def db_conn(tmp_path):
    from hcp_cms.data.database import DatabaseManager
    db = DatabaseManager(str(tmp_path / "test.db"))
    db.initialize()
    yield db._conn
    db.close()


def test_update_issue_supplement_auto(db_conn):
    """auto 模式（manual=False）儲存 supplement，supplement_edited 保持 False。"""
    import json
    from hcp_cms.data.models import PatchIssue, PatchRecord
    from hcp_cms.data.repositories import PatchRepository
    repo = PatchRepository(db_conn)
    patch_id = repo.insert_patch(PatchRecord(type="monthly", month_str="202604"))
    issue_id = repo.insert_issue(PatchIssue(patch_id=patch_id, issue_no="0017023"))

    supplement = {"修改原因": "自動填入", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}
    repo.update_issue_supplement(issue_id, supplement, manual=False)

    updated = repo.get_issue_by_id(issue_id)
    detail = json.loads(updated.mantis_detail)
    assert detail["supplement"]["修改原因"] == "自動填入"
    assert detail.get("supplement_edited", False) is False


def test_update_issue_supplement_manual(db_conn):
    """manual=True 時 supplement_edited 旗標設為 True。"""
    import json
    from hcp_cms.data.models import PatchIssue, PatchRecord
    from hcp_cms.data.repositories import PatchRepository
    repo = PatchRepository(db_conn)
    patch_id = repo.insert_patch(PatchRecord(type="monthly", month_str="202604"))
    issue_id = repo.insert_issue(PatchIssue(patch_id=patch_id, issue_no="0017023"))

    supplement = {"修改原因": "人工修改", "原問題": "B", "範例說明": "C", "修正後": "D", "注意事項": "E"}
    repo.update_issue_supplement(issue_id, supplement, manual=True)

    updated = repo.get_issue_by_id(issue_id)
    detail = json.loads(updated.mantis_detail)
    assert detail["supplement"]["修改原因"] == "人工修改"
    assert detail["supplement_edited"] is True


def test_update_issue_supplement_preserves_existing_fields(db_conn):
    """update_issue_supplement 保留既有 mantis_detail 其他欄位（如 form_files）。"""
    import json
    from hcp_cms.data.models import PatchIssue, PatchRecord
    from hcp_cms.data.repositories import PatchRepository
    repo = PatchRepository(db_conn)
    patch_id = repo.insert_patch(PatchRecord(type="monthly", month_str="202604"))
    existing_detail = json.dumps({"form_files": ["HRWF304"], "archive_name": "01.IP_11G.7z"})
    issue_id = repo.insert_issue(PatchIssue(
        patch_id=patch_id, issue_no="0017023", mantis_detail=existing_detail
    ))

    supplement = {"修改原因": "測試", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}
    repo.update_issue_supplement(issue_id, supplement, manual=False)

    updated = repo.get_issue_by_id(issue_id)
    detail = json.loads(updated.mantis_detail)
    assert detail["form_files"] == ["HRWF304"]        # 原有欄位保留
    assert detail["supplement"]["修改原因"] == "測試"  # 新欄位寫入
```

- [ ] **Step 2: 執行確認失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_supplement_enrichment.py -k "supplement_auto or supplement_manual or preserves_existing" -v
```

預期：FAIL（`update_issue_supplement` 不存在）

- [ ] **Step 3: 在 `repositories.py` 第 1255 行後新增方法**

在 `update_issue_mantis_detail` 方法之後插入：

```python
def update_issue_supplement(
    self, issue_id: int, supplement: dict, manual: bool = False
) -> None:
    """更新 mantis_detail JSON 中的 supplement 欄位。

    保留其他既有欄位（form_files、archive_name 等）。
    manual=True 時一併設定 supplement_edited=True。
    """
    iss = self.get_issue_by_id(issue_id)
    if iss is None:
        return
    try:
        detail: dict = json.loads(iss.mantis_detail) if iss.mantis_detail else {}
    except (json.JSONDecodeError, TypeError):
        detail = {}
    detail["supplement"] = supplement
    if manual:
        detail["supplement_edited"] = True
    self.update_issue_mantis_detail(issue_id, json.dumps(detail, ensure_ascii=False))
```

確認 `import json` 已在檔案頂部（`repositories.py` 已有）。

- [ ] **Step 4: 執行確認三個測試通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_supplement_enrichment.py -k "supplement_auto or supplement_manual or preserves_existing" -v
```

預期：3 PASSED

- [ ] **Step 5: Lint**

```bash
.venv/Scripts/ruff.exe check src/hcp_cms/data/repositories.py
```

預期：無錯誤

- [ ] **Step 6: Commit**

```bash
git add src/hcp_cms/data/repositories.py tests/unit/test_supplement_enrichment.py
git commit -m "feat(data): 新增 PatchRepository.update_issue_supplement() 含 manual 旗標"
```

---

### Task 4: MonthlyPatchEngine — 三來源資料整合 + fetch_supplement_single

**Files:**
- Modify: `src/hcp_cms/core/monthly_patch_engine.py`
- Test: `tests/unit/test_supplement_enrichment.py`

**背景：** `_fetch_supplement(issue_no, client, svc)` 只傳 Mantis 資料給 Claude；改為接受完整 `PatchIssue`，同時傳入 ReleaseNote 解析欄位。新增 `fetch_supplement_single(issue_id)` 供 UI 單筆重新分析。`fetch_supplements()` 新增 `skip_edited` 參數供「重新分析全部但跳過已手動編輯」使用。

- [ ] **Step 1: 新增失敗測試**

在 `test_supplement_enrichment.py` 追加：

```python
# ── Task 4: MonthlyPatchEngine ─────────────────────────────────────────────

def test_fetch_supplement_passes_release_note():
    """_fetch_supplement 應將 iss.description 與 iss.impact 傳給 Claude。"""
    from unittest.mock import MagicMock
    from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
    from hcp_cms.data.models import PatchIssue
    from hcp_cms.services.mantis.base import MantisIssue, MantisNote

    eng = MonthlyPatchEngine.__new__(MonthlyPatchEngine)
    captured: dict = {}

    def fake_extract(**kwargs):
        captured.update(kwargs)
        return {"修改原因": "", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}

    svc = MagicMock()
    svc.extract_supplement = fake_extract

    client = MagicMock()
    client.get_issue.return_value = MantisIssue(
        id="17023", summary="Test",
        description="Mantis 原始描述",
        notes_list=[MantisNote(reporter="工程師", date_submitted="2026-03-15T00:00:00Z", text="note")],
    )

    iss = PatchIssue(
        issue_no="0017023",
        description="ReleaseNote 功能說明",
        impact="影響說明文字",
    )
    eng._fetch_supplement(iss, client, svc)

    assert captured["release_note_description"] == "ReleaseNote 功能說明"
    assert captured["release_note_impact"] == "影響說明文字"
    assert captured["mantis_description"] == "Mantis 原始描述"
    assert len(captured["mantis_notes"]) == 1
    assert captured["mantis_notes"][0]["reporter"] == "工程師"


def test_fetch_supplements_skip_edited(db_conn):
    """fetch_supplements(skip_edited=True) 跳過 supplement_edited=True 的 Issue。"""
    import json
    from unittest.mock import MagicMock, patch
    from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
    from hcp_cms.data.models import PatchIssue, PatchRecord
    from hcp_cms.data.repositories import PatchRepository

    repo = PatchRepository(db_conn)
    patch_id = repo.insert_patch(PatchRecord(type="monthly", month_str="202604"))
    # Issue A：已人工編輯
    edited_detail = json.dumps({"supplement": {"修改原因": "手動"}, "supplement_edited": True})
    id_a = repo.insert_issue(PatchIssue(patch_id=patch_id, issue_no="0001", mantis_detail=edited_detail))
    # Issue B：未編輯
    id_b = repo.insert_issue(PatchIssue(patch_id=patch_id, issue_no="0002"))

    eng = MonthlyPatchEngine(db_conn)
    processed_nos = []

    def fake_fetch(iss, client, svc):
        processed_nos.append(iss.issue_no)
        return {"修改原因": "AI", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}

    with patch.object(eng, "_fetch_supplement", side_effect=fake_fetch), \
         patch.object(eng, "_build_mantis_client", return_value=MagicMock()):
        eng.fetch_supplements(patch_id, skip_edited=True)

    assert "0001" not in processed_nos   # 跳過已編輯
    assert "0002" in processed_nos       # 處理未編輯


def test_fetch_supplement_single_not_found(db_conn):
    """fetch_supplement_single 當 issue_id 不存在時回傳空 dict。"""
    from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
    eng = MonthlyPatchEngine(db_conn)
    result = eng.fetch_supplement_single(999999)
    assert result == {"修改原因": "", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}
```

- [ ] **Step 2: 執行確認失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_supplement_enrichment.py -k "fetch_supplement" -v
```

預期：3 FAIL

- [ ] **Step 3: 修改 `_fetch_supplement()` 簽名與實作**

在 `src/hcp_cms/core/monthly_patch_engine.py` 找到 `_fetch_supplement` 方法（約第 410 行），完整替換為：

```python
def _fetch_supplement(
    self, iss: "PatchIssue", client: "MantisSoapClient", svc: "ClaudeContentService"
) -> dict[str, str]:
    """呼叫 Mantis + Claude（三來源），回傳補充說明五欄位 dict。"""
    empty = {"修改原因": "", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}
    try:
        issue = client.get_issue(iss.issue_no.lstrip("0") or "0")
        if issue is None:
            logging.warning(
                "fetch_supplement: Mantis 找不到 issue_no=%s: %s",
                iss.issue_no, client.last_error,
            )
            mantis_desc = ""
            notes = []
        else:
            mantis_desc = issue.description or ""
            notes = [
                {
                    "reporter": n.reporter,
                    "date": n.date_submitted[:10] if n.date_submitted else "",
                    "text": n.text,
                }
                for n in (issue.notes_list or [])
            ]
        return svc.extract_supplement(
            release_note_description=iss.description or "",
            release_note_impact=iss.impact or "",
            mantis_description=mantis_desc,
            mantis_notes=notes,
        )
    except Exception as e:
        logging.warning("fetch_supplement 失敗 [%s]: %s", iss.issue_no, e)
        return empty
```

- [ ] **Step 4: 更新 `fetch_supplements()` 的呼叫點與新增 `skip_edited` 參數**

找到 `fetch_supplements` 方法定義（約第 372 行），更新簽名與迴圈內邏輯：

```python
def fetch_supplements(
    self,
    patch_id: int,
    progress: Callable[[str], None] | None = None,
    skip_edited: bool = False,
) -> int:
    """從 Mantis 取得各 Issue 說明，以 Claude 整理補充說明五欄位。

    skip_edited=True 時跳過已人工編輯（supplement_edited=True）的 Issue。
    回傳值：
        >= 0  → 成功更新筆數
        -1    → Mantis 連線失敗
        -2    → 該 Patch 無 Issue
    """
    def _log(msg: str) -> None:
        if progress:
            progress(msg)

    client = self._build_mantis_client()
    if client is None:
        return self._FETCH_NO_CONN
    svc = ClaudeContentService()
    issues = self._repo.list_issues_by_patch(patch_id)
    if not issues:
        return self._FETCH_NO_ISSUE
    count = 0
    for iss in issues:
        if skip_edited:
            existing = self._parse_scan_meta(iss)
            if existing.get("supplement_edited", False):
                _log(f"  ⏭ Issue {iss.issue_no}：已人工編輯，略過")
                continue
        mantis_id = iss.issue_no.lstrip("0") or "0"
        _log(f"  🔍 查詢 Issue {iss.issue_no} (Mantis id={mantis_id})…")
        supplement = self._fetch_supplement(iss, client, svc)
        if not any(supplement.values()):
            _log(f"  ⚠️ Issue {iss.issue_no}：Mantis 無資料（{client.last_error or '補充欄位為空'}）")
            continue
        self._repo.update_issue_supplement(iss.issue_id, supplement, manual=False)
        _log(f"  ✅ Issue {iss.issue_no}：補充說明已更新")
        count += 1
    return count
```

注意：`update_issue_supplement` 取代舊的 `_parse_scan_meta` + `update_issue_mantis_detail` 組合。

- [ ] **Step 5: 新增 `fetch_supplement_single()` 方法**

在 `fetch_supplements` 方法之後新增：

```python
def fetch_supplement_single(self, issue_id: int) -> dict[str, str]:
    """取得單筆 Issue 的補充說明（不寫回 DB，供 UI 呼叫後自行儲存）。"""
    empty = {"修改原因": "", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}
    iss = self._repo.get_issue_by_id(issue_id)
    if iss is None:
        return empty
    client = self._build_mantis_client()
    if client is None:
        return empty
    svc = ClaudeContentService()
    return self._fetch_supplement(iss, client, svc)
```

- [ ] **Step 6: 執行測試確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_supplement_enrichment.py -k "fetch_supplement" -v
```

預期：3 PASSED

- [ ] **Step 7: 執行全部測試確認無回退**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_monthly_patch_engine.py tests/unit/test_supplement_enrichment.py -v
```

預期：全部 PASSED

- [ ] **Step 8: Lint**

```bash
.venv/Scripts/ruff.exe check src/hcp_cms/core/monthly_patch_engine.py
```

預期：無錯誤

- [ ] **Step 9: Commit**

```bash
git add src/hcp_cms/core/monthly_patch_engine.py tests/unit/test_supplement_enrichment.py
git commit -m "feat(core): _fetch_supplement 整合三來源資料，新增 fetch_supplement_single 與 skip_edited"
```

---

### Task 5: SupplementEditorWidget — 左右分割編輯器 [POC: 首次使用 QSplitter + 複雜 Signal 互動]

**Files:**
- Create: `src/hcp_cms/ui/supplement_editor_widget.py`
- Test: `tests/unit/test_supplement_enrichment.py`

**背景：** 全新 PySide6 Widget，使用 QSplitter 左右分割：左側 QListWidget 顯示 Issue 清單（含狀態圖示），右側 QScrollArea 包含五個 QTextEdit 欄位與操作按鈕。

- [ ] **Step 1: 新增 supplement_status 靜態方法測試**

在 `test_supplement_enrichment.py` 追加：

```python
# ── Task 5: SupplementEditorWidget ────────────────────────────────────────

def test_supplement_status_empty():
    from hcp_cms.ui.supplement_editor_widget import SupplementEditorWidget
    assert SupplementEditorWidget.supplement_status({}, False) == "empty"
    assert SupplementEditorWidget.supplement_status(None, False) == "empty"  # type: ignore


def test_supplement_status_complete():
    from hcp_cms.ui.supplement_editor_widget import SupplementEditorWidget
    full = {"修改原因": "A", "原問題": "B", "範例說明": "C", "修正後": "D", "注意事項": "E"}
    assert SupplementEditorWidget.supplement_status(full, False) == "complete"


def test_supplement_status_insufficient():
    from hcp_cms.ui.supplement_editor_widget import SupplementEditorWidget
    insuff = {"修改原因": "⚠ 資料不足，請人工補充", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}
    assert SupplementEditorWidget.supplement_status(insuff, False) == "insufficient"


def test_supplement_status_edited_overrides():
    from hcp_cms.ui.supplement_editor_widget import SupplementEditorWidget
    full = {"修改原因": "A", "原問題": "B", "範例說明": "C", "修正後": "D", "注意事項": "E"}
    assert SupplementEditorWidget.supplement_status(full, True) == "edited"
    assert SupplementEditorWidget.supplement_status({}, True) == "edited"
```

- [ ] **Step 2: 執行確認失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_supplement_enrichment.py -k "supplement_status" -v
```

預期：4 FAIL（模組不存在）

- [ ] **Step 3: 建立 `supplement_editor_widget.py`**

建立 `src/hcp_cms/ui/supplement_editor_widget.py`，完整內容如下：

```python
"""補充說明編輯器 — 左右分割逐筆維護 Issue 補充欄位。"""

from __future__ import annotations

import json
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.data.models import PatchIssue

_SUPPLEMENT_KEYS = ("修改原因", "原問題", "範例說明", "修正後", "注意事項")

_CLR_COMPLETE = QColor("#22c55e")
_CLR_INSUFFICIENT = QColor("#f97316")
_CLR_EMPTY = QColor("#94a3b8")
_CLR_EDITED = QColor("#3b82f6")


class SupplementEditorWidget(QWidget):
    supplement_saved = Signal(int, dict)   # (issue_id, supplement)
    reanalyze_requested = Signal(int)      # issue_id
    reanalyze_all_requested = Signal()

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._issues: list[PatchIssue] = []
        self._current_issue_id: int | None = None
        self._edits: dict[str, QTextEdit] = {}
        self._dirty = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        top_bar = QHBoxLayout()
        self._reanalyze_all_btn = QPushButton("🔄 重新從 Mantis 分析全部")
        top_bar.addWidget(self._reanalyze_all_btn)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._list = QListWidget()
        self._list.setMaximumWidth(220)
        splitter.addWidget(self._list)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 8, 8, 8)

        self._title_label = QLabel("請從左側選擇 Issue")
        self._title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        right_layout.addWidget(self._title_label)

        for key in _SUPPLEMENT_KEYS:
            right_layout.addWidget(QLabel(key))
            edit = QTextEdit()
            edit.setFixedHeight(80)
            self._edits[key] = edit
            right_layout.addWidget(edit)
            edit.textChanged.connect(self._on_text_changed)

        btn_row = QHBoxLayout()
        self._reanalyze_btn = QPushButton("🔄 重新分析此 Issue")
        self._save_btn = QPushButton("💾 儲存")
        btn_row.addWidget(self._reanalyze_btn)
        btn_row.addWidget(self._save_btn)
        btn_row.addStretch()
        right_layout.addLayout(btn_row)
        right_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(right_widget)
        scroll.setWidgetResizable(True)
        splitter.addWidget(scroll)
        splitter.setSizes([200, 600])

        layout.addWidget(splitter, stretch=1)

        self._list.currentRowChanged.connect(self._on_issue_selected)
        self._reanalyze_all_btn.clicked.connect(self.reanalyze_all_requested)
        self._reanalyze_btn.clicked.connect(self._on_reanalyze_clicked)
        self._save_btn.clicked.connect(self._on_save_clicked)

        self._set_right_enabled(False)

    def load_issues(self, issues: list[PatchIssue]) -> None:
        """載入 Issue 清單，更新左側列表。"""
        self._issues = issues
        self._list.clear()
        for iss in issues:
            detail = self._parse_detail(iss)
            supplement = detail.get("supplement") or {}
            edited = detail.get("supplement_edited", False)
            status = self.supplement_status(supplement, edited)
            item = QListWidgetItem(f"{self._status_icon(status)} {iss.issue_no}")
            item.setForeground(self._status_color(status))
            item.setData(Qt.ItemDataRole.UserRole, iss.issue_id)
            self._list.addItem(item)

    def update_issue_display(
        self, issue_id: int, supplement: dict, edited: bool = False
    ) -> None:
        """外部（Mantis 分析完成後）更新指定 Issue 的清單圖示與右側欄位。"""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == issue_id:
                if i < len(self._issues):
                    status = self.supplement_status(supplement, edited)
                    item.setText(f"{self._status_icon(status)} {self._issues[i].issue_no}")
                    item.setForeground(self._status_color(status))
                break
        if self._current_issue_id == issue_id:
            self._load_supplement(supplement)

    @staticmethod
    def supplement_status(supplement: dict | None, edited: bool) -> str:
        """回傳 'edited' | 'complete' | 'insufficient' | 'empty'。"""
        if edited:
            return "edited"
        if not supplement:
            return "empty"
        if any("⚠" in str(v) for v in supplement.values()):
            return "insufficient"
        if all(supplement.get(k, "").strip() for k in _SUPPLEMENT_KEYS):
            return "complete"
        return "insufficient"

    @staticmethod
    def _status_icon(status: str) -> str:
        return {"edited": "✏", "complete": "✅", "insufficient": "⚠", "empty": "○"}.get(status, "○")

    @staticmethod
    def _status_color(status: str) -> QColor:
        return {
            "edited": _CLR_EDITED,
            "complete": _CLR_COMPLETE,
            "insufficient": _CLR_INSUFFICIENT,
            "empty": _CLR_EMPTY,
        }.get(status, _CLR_EMPTY)

    def _on_issue_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._issues):
            self._set_right_enabled(False)
            return
        if self._dirty:
            reply = QMessageBox.question(
                self, "未儲存的變更", "目前有未儲存的變更，是否放棄？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return
        iss = self._issues[row]
        self._current_issue_id = iss.issue_id
        detail = self._parse_detail(iss)
        supplement = detail.get("supplement") or {}
        self._title_label.setText(f"Issue {iss.issue_no} — {iss.description or ''}")
        self._load_supplement(supplement)
        self._set_right_enabled(True)
        self._dirty = False

    def _load_supplement(self, supplement: dict) -> None:
        for key, edit in self._edits.items():
            edit.blockSignals(True)
            edit.setPlainText(supplement.get(key, ""))
            edit.blockSignals(False)
        self._dirty = False

    def _on_text_changed(self) -> None:
        self._dirty = True

    def _on_save_clicked(self) -> None:
        if self._current_issue_id is None:
            return
        supplement = {k: self._edits[k].toPlainText() for k in _SUPPLEMENT_KEYS}
        self.supplement_saved.emit(self._current_issue_id, supplement)
        self._dirty = False

    def _on_reanalyze_clicked(self) -> None:
        if self._current_issue_id is not None:
            self.reanalyze_requested.emit(self._current_issue_id)

    def _set_right_enabled(self, enabled: bool) -> None:
        for edit in self._edits.values():
            edit.setEnabled(enabled)
        self._save_btn.setEnabled(enabled)
        self._reanalyze_btn.setEnabled(enabled)

    @staticmethod
    def _parse_detail(iss: PatchIssue) -> dict:
        if not iss.mantis_detail:
            return {}
        try:
            return json.loads(iss.mantis_detail)
        except (json.JSONDecodeError, TypeError):
            return {}
```

- [ ] **Step 4: 執行確認 4 個 status 測試通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_supplement_enrichment.py -k "supplement_status" -v
```

預期：4 PASSED

- [ ] **Step 5: Lint**

```bash
.venv/Scripts/ruff.exe check src/hcp_cms/ui/supplement_editor_widget.py
```

預期：無錯誤

- [ ] **Step 6: Commit**

```bash
git add src/hcp_cms/ui/supplement_editor_widget.py tests/unit/test_supplement_enrichment.py
git commit -m "feat(ui): 新增 SupplementEditorWidget 左右分割補充說明編輯器"
```

---

### Task 6: patch_monthly_tab.py — 新增步驟與整合編輯器

**Files:**
- Modify: `src/hcp_cms/ui/patch_monthly_tab.py`

**背景：** 在 `_STEPS` 插入「⑥ 補充說明」，同時新增「📋 補充說明」按鈕與 `SupplementEditorWidget`。處理補充說明儲存、單筆重分析、全部重分析三個事件。調整所有 `_set_step()` 呼叫以符合新編號。

- [ ] **Step 1: 修改 `_STEPS` 清單（第 30-31 行）**

將：

```python
_STEPS = ["① 選月份", "② 選來源", "③ 匯入", "④ 編輯", "⑤ S2T",
          "⑥ Excel", "⑦ 驗證", "⑧ 通知信", "⑨ 完成"]
```

改為：

```python
_STEPS = ["① 選月份", "② 選來源", "③ 匯入", "④ 編輯", "⑤ S2T",
          "⑥ 補充說明", "⑦ Excel", "⑧ 驗證", "⑨ 通知信", "⑩ 完成"]
```

- [ ] **Step 2: 新增 import**

在檔案頂部 import 區段（現有 `from hcp_cms.ui.widgets.issue_table_widget import IssueTableWidget` 之後）新增：

```python
from hcp_cms.ui.supplement_editor_widget import SupplementEditorWidget
```

- [ ] **Step 3: 在 action_row 新增「📋 補充說明」按鈕（第 139-150 行區域）**

將：

```python
        self._import_btn = QPushButton("📥 匯入 Issue")
        self._s2t_btn = QPushButton("🔤 S2T 轉換")
        self._generate_excel_btn = QPushButton("📊 產生 Excel")
        self._verify_btn = QPushButton("🔗 驗證超連結")
        self._generate_html_btn = QPushButton("✉️ 產生通知信")
        self._regenerate_btn = QPushButton("🔄 重新產出")
        for btn in [self._import_btn, self._s2t_btn, self._generate_excel_btn,
                    self._verify_btn, self._generate_html_btn, self._regenerate_btn]:
            action_row.addWidget(btn)
```

改為：

```python
        self._import_btn = QPushButton("📥 匯入 Issue")
        self._s2t_btn = QPushButton("🔤 S2T 轉換")
        self._supplement_editor_btn = QPushButton("📋 補充說明")
        self._generate_excel_btn = QPushButton("📊 產生 Excel")
        self._verify_btn = QPushButton("🔗 驗證超連結")
        self._generate_html_btn = QPushButton("✉️ 產生通知信")
        self._regenerate_btn = QPushButton("🔄 重新產出")
        for btn in [self._import_btn, self._s2t_btn, self._supplement_editor_btn,
                    self._generate_excel_btn, self._verify_btn,
                    self._generate_html_btn, self._regenerate_btn]:
            action_row.addWidget(btn)
```

- [ ] **Step 4: 在 Issue 表格後新增 SupplementEditorWidget（第 171-173 行區域）**

將：

```python
        # Issue 表格
        self._issue_table = IssueTableWidget(conn=self._conn)
        layout.addWidget(self._issue_table, stretch=2)
```

改為：

```python
        # Issue 表格（與補充說明編輯器互斥顯示）
        self._issue_table = IssueTableWidget(conn=self._conn)
        layout.addWidget(self._issue_table, stretch=2)

        # 補充說明編輯器（預設隱藏）
        self._supplement_editor = SupplementEditorWidget(conn=self._conn)
        self._supplement_editor.setVisible(False)
        layout.addWidget(self._supplement_editor, stretch=2)
```

- [ ] **Step 5: 在 Signal/Slot 連線區段新增連線（第 186-207 行之後）**

在 `self._supplement_done.connect(self._on_supplement_result)` 之後新增：

```python
        self._supplement_editor_btn.clicked.connect(self._on_supplement_editor_clicked)
        self._supplement_editor.supplement_saved.connect(self._on_supplement_saved)
        self._supplement_editor.reanalyze_requested.connect(self._on_reanalyze_single)
        self._supplement_editor.reanalyze_all_requested.connect(self._on_reanalyze_all)
```

- [ ] **Step 6: 更新 `_enable_operation_buttons()`**

將：

```python
        for btn in [self._generate_excel_btn, self._generate_html_btn,
                    self._s2t_btn, self._verify_btn, self._regenerate_btn]:
```

改為：

```python
        for btn in [self._generate_excel_btn, self._generate_html_btn,
                    self._s2t_btn, self._supplement_editor_btn,
                    self._verify_btn, self._regenerate_btn]:
```

- [ ] **Step 7: 更新 `_on_generate_result()` 的步驟編號（第 465 行）**

將：

```python
        step = 6 if result.get("type") == "excel" else 8
```

改為：

```python
        step = 7 if result.get("type") == "excel" else 9
```

- [ ] **Step 8: 更新 `_on_supplement_result()` — 新增 `_set_step(6)` 與載入編輯器**

找到 `_on_supplement_result` 方法，在最後的回傳前（方法結尾處）追加：

```python
        self._set_step(6)
        # 載入補充說明編輯器（若已有 patch_id）
        self._reload_supplement_editor()
```

同時，若方法內有 `_set_step` 呼叫（目前無），確認補充說明步驟標記正確。

- [ ] **Step 9: 新增四個 Slot 方法**

在 `patch_monthly_tab.py` 末尾（或 `_fetch_supplements_async` 之後）新增以下四個方法：

```python
    def _reload_supplement_editor(self) -> None:
        """從 DB 重新載入 Issue 清單至補充說明編輯器。"""
        if not self._conn:
            return
        patch_ids = list(self._scan_patch_ids.values()) if self._scan_patch_ids else []
        if self._patch_id:
            patch_ids = [self._patch_id]
        if not patch_ids:
            return
        from hcp_cms.data.repositories import PatchRepository
        repo = PatchRepository(self._conn)
        issues: list = []
        for pid in patch_ids:
            issues.extend(repo.list_issues_by_patch(pid))
        self._supplement_editor.load_issues(issues)

    def _on_supplement_editor_clicked(self) -> None:
        """切換補充說明編輯器顯示／隱藏。"""
        visible = not self._supplement_editor.isVisible()
        self._supplement_editor.setVisible(visible)
        self._issue_table.setVisible(not visible)
        if visible:
            self._reload_supplement_editor()

    def _on_supplement_saved(self, issue_id: int, supplement: dict) -> None:
        """儲存人工編輯的補充說明至 DB。"""
        if not self._conn:
            return
        from hcp_cms.data.repositories import PatchRepository
        repo = PatchRepository(self._conn)
        repo.update_issue_supplement(issue_id, supplement, manual=True)
        self._append_log(f"💾 Issue 補充說明已儲存（人工）")
        self._supplement_editor.update_issue_display(issue_id, supplement, edited=True)

    def _on_reanalyze_single(self, issue_id: int) -> None:
        """單筆 Issue 重新從 Mantis 分析補充說明。"""
        if not self._conn:
            return
        conn = self._conn
        # 檢查是否已人工編輯，若是則詢問確認
        import json
        from hcp_cms.data.repositories import PatchRepository
        repo = PatchRepository(conn)
        iss = repo.get_issue_by_id(issue_id)
        if iss and iss.mantis_detail:
            try:
                detail = json.loads(iss.mantis_detail)
                if detail.get("supplement_edited", False):
                    from PySide6.QtWidgets import QMessageBox
                    reply = QMessageBox.question(
                        self, "覆蓋人工編輯", "此 Issue 已人工編輯過，確定要用 AI 重新分析並覆蓋？",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    )
                    if reply == QMessageBox.StandardButton.No:
                        return
            except (json.JSONDecodeError, TypeError):
                pass

        self._append_log(f"🔄 重新分析 Issue（id={issue_id}）…")

        def work() -> tuple[int, dict]:
            from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
            eng = MonthlyPatchEngine(conn)
            supplement = eng.fetch_supplement_single(issue_id)
            return issue_id, supplement

        def on_done(result: tuple[int, dict]) -> None:
            iid, supplement = result
            repo2 = PatchRepository(conn)
            repo2.update_issue_supplement(iid, supplement, manual=False)
            self._supplement_editor.update_issue_display(iid, supplement, edited=False)
            self._append_log(f"✅ Issue（id={iid}）補充說明已重新分析")

        import threading
        threading.Thread(
            target=lambda: on_done(work()), daemon=True
        ).start()

    def _on_reanalyze_all(self) -> None:
        """批次重新分析所有未手動編輯的 Issue。"""
        if not self._conn:
            return
        if not self._patch_id and not self._scan_patch_ids:
            return
        conn = self._conn
        patch_ids_list = (
            list(self._scan_patch_ids.values()) if self._scan_patch_ids
            else ([self._patch_id] if self._patch_id else [])
        )
        self._append_log("🔄 批次重新分析補充說明（跳過已人工編輯）…")

        def work() -> int:
            from hcp_cms.core.monthly_patch_engine import MonthlyPatchEngine
            eng = MonthlyPatchEngine(conn)
            total = 0
            for pid in patch_ids_list:
                if pid is not None:
                    total += eng.fetch_supplements(
                        pid,
                        progress=lambda msg: self._import_log.emit(msg),
                        skip_edited=True,
                    )
            return total

        def on_done(count: int) -> None:
            self._append_log(f"✅ 批次分析完成：{count} 筆已更新")
            self._reload_supplement_editor()

        import threading
        threading.Thread(target=lambda: on_done(work()), daemon=True).start()
```

- [ ] **Step 10: 執行程式確認 UI 正常**

```bash
.venv/Scripts/python.exe -m hcp_cms
```

確認：
1. 步驟列顯示 ① → ② → ③ → ④ → ⑤ → **⑥ 補充說明** → ⑦ → ⑧ → ⑨ → ⑩
2. 「📋 補充說明」按鈕出現在操作列
3. 點擊「📋 補充說明」切換顯示左右分割編輯器
4. 產生 Excel 後步驟進到 ⑦（而非 ⑥）

- [ ] **Step 11: Lint + 全部測試**

```bash
.venv/Scripts/ruff.exe check src/hcp_cms/ui/patch_monthly_tab.py
.venv/Scripts/python.exe -m pytest tests/unit/test_supplement_enrichment.py tests/unit/test_monthly_patch_engine.py -v
```

預期：Lint 無錯誤，所有測試 PASSED

- [ ] **Step 12: Commit**

```bash
git add src/hcp_cms/ui/patch_monthly_tab.py
git commit -m "feat(ui): 新增補充說明步驟與 SupplementEditorWidget 整合"
```

---

## 自我審查

**Spec 覆蓋檢查：**
- ✅ ClaudeContentService 三來源介面 → Task 1
- ✅ Prompt 強化（欄位定義、業務背景、稀疏提示）→ Task 1
- ✅ Mantis 筆記上限 5→10 → Task 2
- ✅ PatchRepository.update_issue_supplement() + manual 旗標 → Task 3
- ✅ _fetch_supplement 傳入 PatchIssue 整合三來源 → Task 4
- ✅ fetch_supplement_single → Task 4 Step 5
- ✅ fetch_supplements skip_edited → Task 4 Step 4
- ✅ SupplementEditorWidget + supplement_status → Task 5
- ✅ 步驟 ⑥ 補充說明 + 按鈕 + 切換顯示 → Task 6 Step 1-4
- ✅ 儲存人工編輯 → Task 6 Step 9 (_on_supplement_saved)
- ✅ 單筆重分析（確認已編輯再覆蓋）→ Task 6 Step 9 (_on_reanalyze_single)
- ✅ 全部重分析跳過已編輯 → Task 6 Step 9 (_on_reanalyze_all)

**型別一致性：**
- `extract_supplement()` 四具名參數在 Task 1 定義，Task 4 呼叫一致 ✅
- `update_issue_supplement(issue_id, supplement, manual)` Task 3 定義，Task 4/6 呼叫一致 ✅
- `_fetch_supplement(iss: PatchIssue, client, svc)` Task 4 定義，`fetch_supplements` 呼叫更新一致 ✅
- `supplement_status(supplement, edited)` Task 5 定義，Task 6 使用 `update_issue_display` 間接調用 ✅
