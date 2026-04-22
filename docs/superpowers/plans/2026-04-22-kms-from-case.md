# KMS 從案件建立知識庫 + 相似問題搜尋 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在案件管理中新增「📚 加入知識庫」按鈕（從 HCP 回覆自動建立 KMS 條目），並在詳細面板加入「相似知識庫」區塊（以案件主旨即時搜尋 FTS5）。

**Architecture:** 兩個獨立 UI 功能共用同一個 Core 層入口（`KMSEngine`）。「加入知識庫」讀取案件最後一筆 HCP 回覆 CaseLog 組成 Q&A，狀態預設「待審查」。「相似搜尋」在 `_on_selection_changed` 時以主旨觸發 `KMSEngine.search()`，結果顯示在詳細面板底部的摺疊區塊。

**Tech Stack:** PySide6 6.10.2、SQLite FTS5、KMSEngine（`src/hcp_cms/core/kms_engine.py`）、CaseLogRepository（`src/hcp_cms/data/repositories.py`）

---

## 檔案改動清單

| 檔案 | 動作 | 說明 |
|------|------|------|
| `src/hcp_cms/ui/case_view.py` | Modify | 加入「📚 加入知識庫」按鈕、`_on_add_to_kms()` slot、相似搜尋區塊 `_kms_panel`、`_refresh_kms_panel()` |
| `tests/unit/test_kms_from_case.py` | Create | 新單元測試：從案件建立 KMS、搜尋相似 |

---

## 背景知識（必讀）

### KMSEngine API（`src/hcp_cms/core/kms_engine.py`）

```python
engine = KMSEngine(conn)

# 建立待審查 QA
qa = engine.create_qa(
    question="主旨或問題文字",
    answer="HCP 回覆內文",
    system_product="HCP",
    issue_type="OTH",
    error_type="人事資料管理",
    source="case",
    source_case_id="CS-2026-1133",
    status="待審查",          # 預設建立為待審查
)
# 回傳 QAKnowledge，qa.qa_id = "QA-202604-001"

# FTS5 搜尋（只返回 status='已完成' 的 QA）
results: list[QAKnowledge] = engine.search("離職申請")
# results[i].question, .answer, .qa_id
```

### CaseLogRepository API（`src/hcp_cms/data/repositories.py`）

```python
from hcp_cms.data.repositories import CaseLogRepository
logs = CaseLogRepository(conn).list_by_case("CS-2026-1133")
# 回傳 list[CaseLog]，按 logged_at ASC 排序
# log.direction: '客戶來信' | 'HCP 信件回覆' | 'HCP 線上回覆' | '內部討論'
# log.content: str  — 信件/回覆全文
```

### Case 物件欄位（`src/hcp_cms/data/models.py`）

```python
case.case_id        # "CS-2026-1133"
case.subject        # 主旨（作為 question 的依據）
case.system_product # "HCP"
case.issue_type     # "OTH"
case.error_type     # "人事資料管理"
case.company_id     # FK companies
```

### case_view.py 詳細面板現有結構（`src/hcp_cms/ui/case_view.py:156-196`）

```python
# detail panel 現有按鈕列（約 182-195 行）
btn_layout = QHBoxLayout()
self._btn_reply = QPushButton("✅ 標記已回覆")
self._btn_close  = QPushButton("🔒 結案")
self._btn_add_release = QPushButton("📋 加入待發清單")
detail_layout.addRow(btn_layout)
splitter.addWidget(detail)
```

---

## Task 1：單元測試骨架

**Files:**
- Create: `tests/unit/test_kms_from_case.py`

- [ ] **Step 1：建立測試檔案**

```python
# tests/unit/test_kms_from_case.py
"""測試從案件建立 KMS 條目與相似搜尋輔助函式。"""
import pytest
import sqlite3
from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import Case, CaseLog
from hcp_cms.data.repositories import CaseRepository, CaseLogRepository
from hcp_cms.core.kms_engine import KMSEngine


@pytest.fixture
def db():
    mgr = DatabaseManager(":memory:")
    mgr.initialize()
    yield mgr.connection
    mgr.connection.close()


@pytest.fixture
def case_with_logs(db):
    """建立一個含客戶來信 + HCP 回覆的測試案件。"""
    case = Case(
        case_id="CS-TEST-001",
        subject="離職申請流程如何操作？",
        system_product="HCP",
        issue_type="OTH",
        error_type="人事資料管理",
        status="已回覆",
        sent_time="2026/04/01 09:00",
    )
    CaseRepository(db).insert(case)

    log_customer = CaseLog(
        log_id="LOG-20260401-001",
        case_id="CS-TEST-001",
        direction="客戶來信",
        content="請問離職申請的操作步驟為何？",
        logged_at="2026/04/01 09:00:00",
    )
    log_hcp = CaseLog(
        log_id="LOG-20260401-002",
        case_id="CS-TEST-001",
        direction="HCP 信件回覆",
        content="您好，離職申請請至人事管理 → 離職申請，填寫離職日期後送出即可。",
        logged_at="2026/04/01 10:00:00",
    )
    CaseLogRepository(db).insert(log_customer)
    CaseLogRepository(db).insert(log_hcp)
    return case


def test_build_qa_from_case_creates_pending(db, case_with_logs):
    """從案件建立 KMS 條目，預設狀態應為待審查。"""
    case = case_with_logs
    logs = CaseLogRepository(db).list_by_case(case.case_id)
    hcp_logs = [l for l in logs if l.direction in ("HCP 信件回覆", "HCP 線上回覆")]
    assert hcp_logs, "應有 HCP 回覆記錄"

    engine = KMSEngine(db)
    qa = engine.create_qa(
        question=case.subject,
        answer=hcp_logs[-1].content,
        system_product=case.system_product,
        issue_type=case.issue_type,
        error_type=case.error_type,
        source="case",
        source_case_id=case.case_id,
        status="待審查",
    )
    assert qa.qa_id.startswith("QA-")
    assert qa.status == "待審查"
    assert qa.source_case_id == "CS-TEST-001"
    assert qa.question == "離職申請流程如何操作？"
    assert "離職申請" in qa.answer


def test_search_similar_returns_empty_for_pending(db, case_with_logs):
    """待審查的 QA 不應出現在搜尋結果中。"""
    case = case_with_logs
    logs = CaseLogRepository(db).list_by_case(case.case_id)
    hcp_logs = [l for l in logs if l.direction in ("HCP 信件回覆", "HCP 線上回覆")]

    engine = KMSEngine(db)
    engine.create_qa(
        question=case.subject,
        answer=hcp_logs[-1].content,
        source="case",
        source_case_id=case.case_id,
        status="待審查",
    )
    results = engine.search("離職申請")
    assert results == [], "待審查 QA 不應出現在搜尋結果"


def test_search_similar_returns_approved(db, case_with_logs):
    """已完成的 QA 應可被搜尋到。"""
    engine = KMSEngine(db)
    qa = engine.create_qa(
        question="離職申請流程如何操作？",
        answer="人事管理 → 離職申請，填寫離職日期後送出。",
        source="case",
        source_case_id="CS-TEST-001",
        status="已完成",
    )
    results = engine.search("離職申請")
    assert any(r.qa_id == qa.qa_id for r in results)
```

- [ ] **Step 2：確認測試失敗（目前功能尚未存在，但 import 應成功）**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_kms_from_case.py -v
```

預期：全部 3 個測試 PASS（因為只測試已有的 KMSEngine API）

- [ ] **Step 3：提交測試**

```bash
git add tests/unit/test_kms_from_case.py
git commit -m "test: 新增從案件建立 KMS 與相似搜尋單元測試"
```

---

## Task 2：「加入知識庫」按鈕與 slot [POC: 需確認 QAReviewDialog 接收 source_case_id 的介面]

**Files:**
- Modify: `src/hcp_cms/ui/case_view.py`

- [ ] **Step 1：在 `_setup_ui()` 按鈕列加入「📚 加入知識庫」按鈕**

在 `case_view.py` 的 `_setup_ui()` 方法（約第 191-195 行），找到：

```python
        self._btn_add_release = QPushButton("📋 加入待發清單")
        self._btn_add_release.clicked.connect(self._on_add_to_release)
        btn_layout.addWidget(self._btn_add_release)

        detail_layout.addRow(btn_layout)
```

改為：

```python
        self._btn_add_release = QPushButton("📋 加入待發清單")
        self._btn_add_release.clicked.connect(self._on_add_to_release)
        btn_layout.addWidget(self._btn_add_release)

        self._btn_add_kms = QPushButton("📚 加入知識庫")
        self._btn_add_kms.setToolTip("將此案件的客戶問題與 HCP 回覆加入知識庫（建為待審查）")
        self._btn_add_kms.clicked.connect(self._on_add_to_kms)
        btn_layout.addWidget(self._btn_add_kms)

        detail_layout.addRow(btn_layout)
```

- [ ] **Step 2：實作 `_on_add_to_kms()` slot**

在 `case_view.py` 中，在 `_on_add_to_release` 方法之後新增：

```python
    def _on_add_to_kms(self) -> None:
        """從目前案件的 HCP 回覆建立 KMS 待審查條目。"""
        if not self._conn or not self._detail_id.text():
            return
        case_id = self._detail_id.text()
        case = next(
            (c for c in self._cases if c.case_id == case_id),
            None,
        ) if hasattr(self, "_cases") else None
        if not case:
            return

        # 找最後一筆 HCP 回覆作為 answer
        from hcp_cms.data.repositories import CaseLogRepository
        logs = CaseLogRepository(self._conn).list_by_case(case_id)
        hcp_logs = [
            lg for lg in logs
            if lg.direction in ("HCP 信件回覆", "HCP 線上回覆")
        ]

        if not hcp_logs:
            QMessageBox.warning(
                self, "無回覆記錄",
                "此案件尚無 HCP 回覆記錄，無法自動建立知識庫條目。\n"
                "請先回覆案件，或至 KMS 知識庫手動新增。"
            )
            return

        answer = hcp_logs[-1].content or ""
        question = case.subject or ""

        # 彈出確認視窗，讓使用者確認問題與回覆內容
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QTextEdit as _QTE
        dlg = QDialog(self)
        dlg.setWindowTitle("加入知識庫")
        dlg.setMinimumWidth(520)
        layout = QFormLayout(dlg)

        q_edit = _QTE()
        q_edit.setPlainText(question)
        q_edit.setMinimumHeight(60)
        layout.addRow("問題（Q）：", q_edit)

        a_edit = _QTE()
        a_edit.setPlainText(answer)
        a_edit.setMinimumHeight(120)
        layout.addRow("回覆（A）：", a_edit)

        info = QLabel(f"系統產品：{case.system_product or ''}　"
                      f"問題類型：{case.issue_type or ''}　"
                      f"功能模組：{case.error_type or ''}")
        info.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addRow("", info)

        hint = QLabel("⚠ 建立後狀態為「待審查」，請至 KMS 知識庫確認完成後才會納入搜尋。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #f59e0b; font-size: 11px;")
        layout.addRow("", hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        final_q = q_edit.toPlainText().strip()
        final_a = a_edit.toPlainText().strip()
        if not final_q or not final_a:
            QMessageBox.warning(self, "欄位不完整", "問題與回覆均不可為空。")
            return

        from hcp_cms.core.kms_engine import KMSEngine
        qa = KMSEngine(self._conn).create_qa(
            question=final_q,
            answer=final_a,
            system_product=case.system_product,
            issue_type=case.issue_type,
            error_type=case.error_type,
            source="case",
            source_case_id=case_id,
            status="待審查",
        )
        QMessageBox.information(
            self, "完成",
            f"已建立知識庫條目 {qa.qa_id}（待審查）。\n"
            "請至「KMS 知識庫 → 待審核」確認後發布。"
        )
```

- [ ] **Step 3：執行全部測試確認未破壞現有功能**

```
.venv/Scripts/python.exe -m pytest tests/unit/ -q
```

預期：全部 PASS

- [ ] **Step 4：提交**

```bash
git add src/hcp_cms/ui/case_view.py
git commit -m "feat: 案件管理加入「加入知識庫」按鈕，從 HCP 回覆建立 KMS 待審查條目"
```

---

## Task 3：相似知識庫搜尋面板

**Files:**
- Modify: `src/hcp_cms/ui/case_view.py`

- [ ] **Step 1：在 `_setup_ui()` 詳細面板加入 KMS 相似結果區塊**

在 `case_view.py` 的 `_setup_ui()` 中，找到：

```python
        detail_layout.addRow(btn_layout)
        splitter.addWidget(detail)
```

在 `detail_layout.addRow(btn_layout)` 之後、`splitter.addWidget(detail)` 之前插入：

```python
        # 相似知識庫面板
        from PySide6.QtWidgets import QGroupBox
        kms_group = QGroupBox("🔍 相似知識庫")
        kms_group.setStyleSheet(
            "QGroupBox { color: #94a3b8; font-size: 11px; border: 1px solid #334155;"
            " border-radius:4px; margin-top:6px; padding-top:8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
        )
        kms_inner = QVBoxLayout(kms_group)
        kms_inner.setContentsMargins(4, 4, 4, 4)
        self._kms_panel = QTextEdit()
        self._kms_panel.setReadOnly(True)
        self._kms_panel.setMinimumHeight(80)
        self._kms_panel.setMaximumHeight(160)
        self._kms_panel.setHtml("<i style='color:#6b7280'>（選取案件後自動搜尋）</i>")
        kms_inner.addWidget(self._kms_panel)
        detail_layout.addRow(kms_group)
```

- [ ] **Step 2：實作 `_refresh_kms_panel()` 方法**

在 `case_view.py` 中，在 `_build_log_html` 方法之後新增：

```python
    def _refresh_kms_panel(self, subject: str) -> None:
        """以案件主旨搜尋相似 KMS 條目，更新面板顯示（最多 3 筆）。"""
        if not self._conn or not subject.strip():
            self._kms_panel.setHtml("<i style='color:#6b7280'>（無主旨，無法搜尋）</i>")
            return
        try:
            from hcp_cms.core.kms_engine import KMSEngine
            results = KMSEngine(self._conn).search(subject.strip())[:3]
        except Exception:
            self._kms_panel.setHtml("<i style='color:#6b7280'>（搜尋失敗）</i>")
            return

        if not results:
            self._kms_panel.setHtml(
                "<i style='color:#6b7280'>（無相似知識庫條目）</i>"
            )
            return

        parts: list[str] = []
        for qa in results:
            q = _html_escape((qa.question or "")[:80])
            a = _html_escape((qa.answer or "")[:120])
            qid = _html_escape(qa.qa_id)
            parts.append(
                f"<div style='border-left:3px solid #3b82f6;padding:4px 6px;"
                f"margin-bottom:4px;background:#1e293b;border-radius:2px;'>"
                f"<span style='color:#60a5fa;font-size:11px;font-weight:bold;'>{qid}</span><br>"
                f"<span style='color:#e2e8f0;font-size:11px;'>Q: {q}</span><br>"
                f"<span style='color:#94a3b8;font-size:11px;'>A: {a}…</span>"
                f"</div>"
            )
        self._kms_panel.setHtml("".join(parts))
```

- [ ] **Step 3：在 `_on_selection_changed` 末尾呼叫 `_refresh_kms_panel`**

在 `case_view.py` 的 `_on_selection_changed` 方法，找到：

```python
        self._detail_progress.setHtml(self._build_log_html(case))
```

在其後加入：

```python
        self._refresh_kms_panel(case.subject or "")
```

- [ ] **Step 4：`_clear_detail` 方法也清空 KMS 面板**

找到 `_clear_detail` 方法（搜尋 `def _clear_detail`），在其方法體末尾加入：

```python
        if hasattr(self, "_kms_panel"):
            self._kms_panel.setHtml("<i style='color:#6b7280'>（選取案件後自動搜尋）</i>")
```

- [ ] **Step 5：執行全部測試**

```
.venv/Scripts/python.exe -m pytest tests/unit/ -q
```

預期：全部 PASS

- [ ] **Step 6：提交**

```bash
git add src/hcp_cms/ui/case_view.py
git commit -m "feat: 案件詳細面板加入相似知識庫搜尋區塊"
```

---

## Task 4：端對端手動驗證

- [ ] **Step 1：啟動應用程式**

```
.venv/Scripts/python.exe -m hcp_cms
```

- [ ] **Step 2：驗證「加入知識庫」流程**

1. 進入「案件管理」
2. 選取任一「已回覆」案件
3. 點「📚 加入知識庫」
4. 確認對話框顯示主旨（Q）與最後一筆 HCP 回覆（A）
5. 點確認 → 顯示「已建立 QA-XXXXXX（待審查）」提示
6. 切換至「KMS 知識庫 → 待審核」，確認新條目出現，`source_case_id` 正確

- [ ] **Step 3：驗證相似搜尋流程**

1. 先在 KMS 手動新增一筆「已完成」條目，問題包含「離職」關鍵字
2. 回到「案件管理」，選取主旨含「離職」的案件
3. 確認詳細面板底部「🔍 相似知識庫」區塊出現該條目
4. 選取與離職無關的案件，確認顯示「無相似知識庫條目」

- [ ] **Step 4：驗證無 HCP 回覆時的警告**

1. 選取一筆只有客戶來信、無 HCP 回覆的案件
2. 點「📚 加入知識庫」
3. 確認彈出警告：「此案件尚無 HCP 回覆記錄…」

---

## Self-Review Checklist

### Spec coverage
- ✅ 從案件 HCP 回覆建立 KMS 條目（Task 2）
- ✅ 預設狀態「待審查」，需至 KMS 確認（Task 2）
- ✅ 可修改 Q/A 再確認（Task 2 對話框）
- ✅ 相似問題搜尋區塊（Task 3）
- ✅ 無回覆記錄的錯誤處理（Task 2）
- ✅ 搜尋結果限制 3 筆避免面板過大（Task 3）

### Placeholder scan
無 TBD / TODO / 模糊指示。

### Type consistency
- `KMSEngine.create_qa()` 簽名在 Task 1 測試與 Task 2 實作均一致
- `_refresh_kms_panel(subject: str)` 在 Task 3 定義，Task 3 Step 3 呼叫一致
- `_html_escape()` 在 `case_view.py` 頂部已定義（第 36-37 行）
