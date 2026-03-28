# 寄件備份清單 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 EmailView 新增「寄件備份」分頁，從郵件伺服器抓取寄件資料，自動識別公司並統計各公司回覆次數。

**Architecture:** 新增 Core 層 `SentMailManager` 封裝寄件抓取、公司比對與計數邏輯；新增 UI 層 `SentMailTab` Widget 負責日期導航、彙總表與清單表呈現；修改 `EmailView` 加入 `QTabWidget` 將現有收件內容包入「收件處理」tab，並新增「寄件備份」tab。

**Tech Stack:** PySide6 6.10.2, SQLite（既有 `companies` / `cs_cases` 表）, `MailProvider` ABC（既有）, `QTabWidget`, `threading`

---

## 檔案清單

| 動作 | 路徑 | 責任 |
|------|------|------|
| 新增 | `src/hcp_cms/core/sent_mail_manager.py` | `EnrichedSentMail` dataclass、`SentMailManager`、日期解析輔助 |
| 新增 | `src/hcp_cms/ui/sent_mail_tab.py` | `SentMailTab` Widget：日期導航、彙總表、清單表、背景執行緒 |
| 修改 | `src/hcp_cms/ui/email_view.py` | 加入 `QTabWidget`，收件內容移至收件 tab，加入 `SentMailTab` |
| 新增 | `tests/unit/test_sent_mail_manager.py` | 5 個單元測試案例（TDD） |

---

## Task 1：SentMailManager 單元測試（TDD 先寫測試）

**Files:**
- Create: `tests/unit/test_sent_mail_manager.py`

- [ ] **Step 1：建立測試檔案**

```python
"""Unit tests for SentMailManager."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from hcp_cms.core.sent_mail_manager import EnrichedSentMail, SentMailManager
from hcp_cms.data.database import DatabaseManager
from hcp_cms.services.mail.base import MailProvider, RawEmail


class _MockProvider(MailProvider):
    def __init__(self, sent: list[RawEmail]) -> None:
        self._sent = sent

    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def fetch_messages(
        self, since=None, until=None, folder: str = "INBOX"
    ) -> list[RawEmail]:
        return []

    def fetch_sent_messages(self, since=None) -> list[RawEmail]:
        return self._sent

    def create_draft(
        self, to: list[str], subject: str, body: str, attachments=None
    ) -> bool:
        return False


@pytest.fixture
def db(tmp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_db_path)
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def seeded(db: DatabaseManager) -> DatabaseManager:
    conn = db.connection
    conn.execute(
        "INSERT INTO companies (company_id, name, domain) VALUES (?, ?, ?)",
        ("C1", "ABC 公司", "abc.com"),
    )
    conn.execute(
        "INSERT INTO companies (company_id, name, domain) VALUES (?, ?, ?)",
        ("C2", "XYZ 股份", "xyz.com"),
    )
    conn.execute(
        "INSERT INTO cs_cases (case_id, subject, company_id, status) VALUES (?, ?, ?, ?)",
        ("K001", "薪資異常問題", "C1", "處理中"),
    )
    conn.commit()
    return db


class TestSentMailManager:
    def test_resolve_company_by_case(self, seeded: DatabaseManager) -> None:
        mgr = SentMailManager(seeded.connection, _MockProvider([]))
        company_id, company_name = mgr._resolve_company("薪資異常問題", [])
        assert company_id == "C1"
        assert company_name == "ABC 公司"

    def test_resolve_company_by_domain(self, seeded: DatabaseManager) -> None:
        mgr = SentMailManager(seeded.connection, _MockProvider([]))
        company_id, company_name = mgr._resolve_company("無關主旨", ["user@xyz.com"])
        assert company_id == "C2"
        assert company_name == "XYZ 股份"

    def test_resolve_company_unknown(self, seeded: DatabaseManager) -> None:
        mgr = SentMailManager(seeded.connection, _MockProvider([]))
        company_id, company_name = mgr._resolve_company("不明主旨", ["nobody@unknown.com"])
        assert company_id is None
        assert company_name is None

    def test_fetch_and_enrich_counts(self, seeded: DatabaseManager) -> None:
        emails = [
            RawEmail(subject="A", to_recipients=["a@abc.com"], date="2026-03-28 10:00:00"),
            RawEmail(subject="B", to_recipients=["b@abc.com"], date="2026-03-28 11:00:00"),
            RawEmail(subject="C", to_recipients=["c@other.com"], date="2026-03-28 12:00:00"),
        ]
        mgr = SentMailManager(seeded.connection, _MockProvider(emails))
        results = mgr.fetch_and_enrich(
            since=datetime(2026, 3, 28),
            until=datetime(2026, 3, 28, 23, 59, 59),
        )
        abc_mails = [m for m in results if m.company_id == "C1"]
        assert len(abc_mails) == 2
        assert all(m.company_reply_count == 2 for m in abc_mails)
        other_mails = [m for m in results if m.company_id is None]
        assert all(m.company_reply_count == 0 for m in other_mails)

    def test_fetch_and_enrich_date_filter(self, seeded: DatabaseManager) -> None:
        emails = [
            RawEmail(subject="今日", to_recipients=[], date="2026-03-28 10:00:00"),
            RawEmail(subject="明日", to_recipients=[], date="2026-03-29 10:00:00"),
        ]
        mgr = SentMailManager(seeded.connection, _MockProvider(emails))
        results = mgr.fetch_and_enrich(
            since=datetime(2026, 3, 28),
            until=datetime(2026, 3, 28, 23, 59, 59),
        )
        assert len(results) == 1
        assert results[0].subject == "今日"
```

- [ ] **Step 2：執行測試，確認全數 FAIL**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_sent_mail_manager.py -v
```

預期：`ModuleNotFoundError: No module named 'hcp_cms.core.sent_mail_manager'`

---

## Task 2：SentMailManager 實作

**Files:**
- Create: `src/hcp_cms/core/sent_mail_manager.py`

- [ ] **Step 3：建立實作檔案**

```python
"""Sent mail enrichment manager."""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from hcp_cms.services.mail.base import MailProvider


@dataclass
class EnrichedSentMail:
    """寄件信件，附加公司與案件對應資訊。"""

    date: str
    recipients: list[str]
    subject: str
    company_id: str | None
    company_name: str | None
    linked_case_id: str | None
    company_reply_count: int = 0


class SentMailManager:
    """抓取寄件備份並補充公司/案件 metadata。"""

    def __init__(self, conn: sqlite3.Connection, provider: MailProvider) -> None:
        self._conn = conn
        self._provider = provider

    def fetch_and_enrich(
        self, since: datetime, until: datetime
    ) -> list[EnrichedSentMail]:
        """從 MailProvider 抓取寄件，過濾日期範圍，補充公司與案件資訊。"""
        raw_list = self._provider.fetch_sent_messages(since=since)
        results: list[EnrichedSentMail] = []
        for raw in raw_list:
            if raw.date and not _date_in_range(raw.date, since, until):
                continue
            company_id, company_name = self._resolve_company(
                raw.subject, raw.to_recipients
            )
            linked_case_id = self._find_linked_case(raw.subject)
            results.append(
                EnrichedSentMail(
                    date=raw.date or "",
                    recipients=raw.to_recipients,
                    subject=raw.subject,
                    company_id=company_id,
                    company_name=company_name,
                    linked_case_id=linked_case_id,
                )
            )

        counts: Counter[str] = Counter(m.company_id for m in results if m.company_id)
        for mail in results:
            if mail.company_id:
                mail.company_reply_count = counts[mail.company_id]
        return results

    def _resolve_company(
        self, subject: str, recipients: list[str]
    ) -> tuple[str | None, str | None]:
        """回傳 (company_id, company_name)。先查 cs_cases，再查 email domain。"""
        row = self._conn.execute(
            "SELECT c.company_id, co.name FROM cs_cases c "
            "LEFT JOIN companies co ON c.company_id = co.company_id "
            "WHERE c.subject = ? AND c.company_id IS NOT NULL LIMIT 1",
            (subject,),
        ).fetchone()
        if row and row[0]:
            return row[0], row[1]

        if recipients:
            domain = _extract_domain(recipients[0])
            if domain:
                row = self._conn.execute(
                    "SELECT company_id, name FROM companies WHERE domain = ? LIMIT 1",
                    (domain,),
                ).fetchone()
                if row:
                    return row[0], row[1]

        return None, None

    def _find_linked_case(self, subject: str) -> str | None:
        """若 cs_cases 有相同主旨，回傳 case_id，否則回傳 None。"""
        row = self._conn.execute(
            "SELECT case_id FROM cs_cases WHERE subject = ? LIMIT 1",
            (subject,),
        ).fetchone()
        return row[0] if row else None


def _extract_domain(email: str) -> str | None:
    if "@" in email:
        return email.split("@", 1)[1].lower().strip()
    return None


def _date_in_range(date_str: str, since: datetime, until: datetime) -> bool:
    """回傳 True 若 date_str 落在 [since, until]（以日期比較，忽略時區）。"""
    match = re.search(r"\d{4}[-/]\d{2}[-/]\d{2}", str(date_str))
    if not match:
        return True  # 無法解析則保留
    parts = re.split(r"[-/]", match.group())
    try:
        msg_date = datetime(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return True
    return since <= msg_date <= until
```

- [ ] **Step 4：執行測試，確認全數 PASS**

```
.venv/Scripts/python.exe -m pytest tests/unit/test_sent_mail_manager.py -v
```

預期：5 個測試全部 PASS

- [ ] **Step 5：Commit**

```bash
git add tests/unit/test_sent_mail_manager.py src/hcp_cms/core/sent_mail_manager.py
git commit -m "feat(core): 新增 SentMailManager 寄件備份比對與統計"
```

---

## Task 3：SentMailTab UI Widget

**Files:**
- Create: `src/hcp_cms/ui/sent_mail_tab.py`

- [ ] **Step 6：建立 `sent_mail_tab.py`**

```python
"""Sent mail backup tab widget."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.services.mail.base import MailProvider


class SentMailTab(QWidget):
    """寄件備份分頁：顯示寄件清單與公司彙總統計。"""

    _worker_done = Signal(object)
    _worker_error = Signal(str)

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._provider: MailProvider | None = None
        self._setup_ui()

    def set_provider(self, provider: MailProvider | None) -> None:
        """由 EmailView 在連線成功後呼叫。"""
        self._provider = provider

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        # --- 日期導航列（同收件分頁） ---
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("日期:"))

        prev_week_btn = QPushButton("◀◀")
        prev_week_btn.setFixedWidth(42)
        prev_week_btn.setToolTip("前七天")
        prev_week_btn.clicked.connect(self._on_prev_week)
        filter_layout.addWidget(prev_week_btn)

        prev_btn = QPushButton("◀")
        prev_btn.setFixedWidth(36)
        prev_btn.setToolTip("前一天")
        prev_btn.clicked.connect(self._on_prev_day)
        filter_layout.addWidget(prev_btn)

        self._date_edit = QDateEdit(QDate.currentDate())
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy/MM/dd")
        filter_layout.addWidget(self._date_edit)

        next_btn = QPushButton("▶")
        next_btn.setFixedWidth(36)
        next_btn.setToolTip("後一天")
        next_btn.clicked.connect(self._on_next_day)
        filter_layout.addWidget(next_btn)

        next_week_btn = QPushButton("▶▶")
        next_week_btn.setFixedWidth(42)
        next_week_btn.setToolTip("後七天")
        next_week_btn.clicked.connect(self._on_next_week)
        filter_layout.addWidget(next_week_btn)

        today_btn = QPushButton("今天")
        today_btn.setFixedWidth(50)
        today_btn.clicked.connect(self._on_today)
        filter_layout.addWidget(today_btn)

        self._refresh_btn = QPushButton("🔄 重新整理")
        self._refresh_btn.clicked.connect(self._on_refresh)
        filter_layout.addWidget(self._refresh_btn)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # --- 公司彙總表 ---
        summary_label = QLabel("公司彙總")
        summary_label.setStyleSheet("font-weight: bold; color: #f1f5f9;")
        layout.addWidget(summary_label)

        self._summary_table = QTableWidget(0, 2)
        self._summary_table.setHorizontalHeaderLabels(["公司名稱", "次數"])
        self._summary_table.setFixedHeight(120)
        self._summary_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._summary_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._summary_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Fixed
        )
        self._summary_table.horizontalHeader().resizeSection(1, 60)
        layout.addWidget(self._summary_table)

        # --- 寄件清單 ---
        list_label = QLabel("寄件清單")
        list_label.setStyleSheet("font-weight: bold; color: #f1f5f9;")
        layout.addWidget(list_label)

        self._list_table = QTableWidget(0, 6)
        self._list_table.setHorizontalHeaderLabels(
            ["日期", "收件人", "主旨", "公司", "案件", "次數"]
        )
        self._list_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self._list_table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for col in [0, 1, 3, 4, 5]:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        self._list_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self._list_table, stretch=1)

        # --- 日誌 ---
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(80)
        self._log.setPlaceholderText("處理日誌...")
        layout.addWidget(self._log)

        self._worker_done.connect(self._on_worker_done, Qt.ConnectionType.QueuedConnection)
        self._worker_error.connect(self._on_worker_error, Qt.ConnectionType.QueuedConnection)

    # --- 日期導航 ---

    def _on_prev_week(self) -> None:
        d = self._date_edit.date()
        start = d.addDays(-6)
        until = datetime(d.year(), d.month(), d.day(), 23, 59, 59)
        since = datetime(start.year(), start.month(), start.day())
        self._date_edit.setDate(start)
        self._fetch(since=since, until=until)

    def _on_prev_day(self) -> None:
        self._date_edit.setDate(self._date_edit.date().addDays(-1))
        self._on_refresh()

    def _on_next_day(self) -> None:
        self._date_edit.setDate(self._date_edit.date().addDays(1))
        self._on_refresh()

    def _on_next_week(self) -> None:
        d = self._date_edit.date()
        end = d.addDays(6)
        since = datetime(d.year(), d.month(), d.day())
        until = datetime(end.year(), end.month(), end.day(), 23, 59, 59)
        self._date_edit.setDate(end)
        self._fetch(since=since, until=until)

    def _on_today(self) -> None:
        self._date_edit.setDate(QDate.currentDate())
        self._on_refresh()

    def _on_refresh(self) -> None:
        d = self._date_edit.date()
        self._fetch(
            since=datetime(d.year(), d.month(), d.day()),
            until=datetime(d.year(), d.month(), d.day(), 23, 59, 59),
        )

    # --- 背景抓取 ---

    def _fetch(self, since: datetime, until: datetime) -> None:
        if not self._provider or not self._conn:
            self._log.append("⚠️ 請先連線信箱。")
            return
        self._refresh_btn.setEnabled(False)
        if since.date() == until.date():
            self._log.append(f"正在取得 {since.strftime('%Y/%m/%d')} 的寄件備份...")
        else:
            self._log.append(
                f"正在取得 {since.strftime('%Y/%m/%d')} ~ {until.strftime('%Y/%m/%d')} 的寄件備份..."
            )

        conn = self._conn
        provider = self._provider

        def _work() -> object:
            from hcp_cms.core.sent_mail_manager import SentMailManager

            return SentMailManager(conn, provider).fetch_and_enrich(since, until)

        def _thread() -> None:
            try:
                self._worker_done.emit(_work())
            except Exception as e:
                self._worker_error.emit(str(e))

        threading.Thread(target=_thread, daemon=True).start()

    def _on_worker_done(self, results: object) -> None:
        from hcp_cms.core.sent_mail_manager import EnrichedSentMail

        mails: list[EnrichedSentMail] = results  # type: ignore[assignment]
        self._refresh_btn.setEnabled(True)
        self._log.append(f"✅ 取得 {len(mails)} 封寄件備份。")
        self._populate_tables(mails)

    def _on_worker_error(self, msg: str) -> None:
        self._refresh_btn.setEnabled(True)
        self._log.append(f"❌ 錯誤：{msg}")

    # --- 渲染 ---

    def _populate_tables(self, mails: list) -> None:
        # 彙總表（去重後依次數降冪）
        seen: dict[str, tuple[str, int]] = {}
        for m in mails:
            if m.company_id and m.company_id not in seen:
                seen[m.company_id] = (m.company_name or m.company_id, m.company_reply_count)
        ranked = sorted(seen.values(), key=lambda x: x[1], reverse=True)
        self._summary_table.setRowCount(len(ranked))
        for row, (name, count) in enumerate(ranked):
            self._summary_table.setItem(row, 0, QTableWidgetItem(name))
            self._summary_table.setItem(row, 1, QTableWidgetItem(str(count)))

        # 寄件清單
        self._list_table.setRowCount(len(mails))
        for row, m in enumerate(mails):
            self._list_table.setItem(row, 0, QTableWidgetItem(m.date[:10] if m.date else ""))
            self._list_table.setItem(row, 1, QTableWidgetItem(", ".join(m.recipients)))
            self._list_table.setItem(row, 2, QTableWidgetItem(m.subject))
            self._list_table.setItem(row, 3, QTableWidgetItem(m.company_name or "未知"))
            case_text = m.linked_case_id or "—"
            case_item = QTableWidgetItem(case_text)
            if m.linked_case_id:
                case_item.setToolTip("雙擊複製案件編號")
            self._list_table.setItem(row, 4, case_item)
            count_text = str(m.company_reply_count) if m.company_id else "—"
            self._list_table.setItem(row, 5, QTableWidgetItem(count_text))

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        if col == 4:
            item = self._list_table.item(row, col)
            if item and item.text() != "—":
                from PySide6.QtWidgets import QApplication

                QApplication.clipboard().setText(item.text())
                self._log.append(f"📋 已複製案件編號：{item.text()}")
```

- [ ] **Step 7：Commit**

```bash
git add src/hcp_cms/ui/sent_mail_tab.py
git commit -m "feat(ui): 新增 SentMailTab 寄件備份分頁 Widget"
```

---

## Task 4：修改 EmailView 加入 QTabWidget

**Files:**
- Modify: `src/hcp_cms/ui/email_view.py`

- [ ] **Step 8：在 `email_view.py` import 區塊末尾（約第 38 行後）加入兩行 import**

在 `from hcp_cms.services.mail.msg_reader import MSGReader` 之後加入：

```python
from PySide6.QtWidgets import QTabWidget
from hcp_cms.ui.sent_mail_tab import SentMailTab
```

- [ ] **Step 9：修改 `_setup_ui` 方法，將收件內容移入 QTabWidget 的「收件處理」tab**

找到（約第 113 行）：
```python
        layout.addWidget(conn_group)

        # Date navigator — ← [日期] →
        filter_layout = QHBoxLayout()
```

改為：
```python
        layout.addWidget(conn_group)

        # Tab widget：收件處理 / 寄件備份
        self._tab_widget = QTabWidget()
        inbox_widget = QWidget()
        inbox_layout = QVBoxLayout(inbox_widget)
        inbox_layout.setContentsMargins(0, 8, 0, 0)

        # Date navigator — ← [日期] →
        filter_layout = QHBoxLayout()
```

然後找到 `_setup_ui` 中原本將各區塊加入主 `layout` 的這幾行（約第 160–224 行）：
```python
        layout.addLayout(filter_layout)

        # Email list — 5 columns: ...
        ...
        layout.addLayout(select_row)
        ...
        layout.addWidget(self._splitter, stretch=1)
        ...
        layout.addLayout(action_layout)

        # Progress
        ...
        layout.addWidget(self._progress)

        # Log
        ...
        layout.addWidget(self._log)
```

全部改為（將 `layout.add...` 換成 `inbox_layout.add...`）：
```python
        inbox_layout.addLayout(filter_layout)

        # Email list — 5 columns: ...
        ...
        inbox_layout.addLayout(select_row)
        ...
        inbox_layout.addWidget(self._splitter, stretch=1)
        ...
        inbox_layout.addLayout(action_layout)

        # Progress
        ...
        inbox_layout.addWidget(self._progress)

        # Log
        ...
        inbox_layout.addWidget(self._log)

        self._tab_widget.addTab(inbox_widget, "📥 收件處理")

        # 寄件備份 tab
        self._sent_tab = SentMailTab(conn=self._conn)
        self._tab_widget.addTab(self._sent_tab, "📤 寄件備份")

        layout.addWidget(self._tab_widget, stretch=1)
```

> 注意：`schedule_group` 保持使用 `layout.addWidget(schedule_group)`，在 tab widget 之後加入。

- [ ] **Step 10：在 `_on_connect` 的 `on_done` 中傳遞 provider 給 SentMailTab**

找到（約第 331 行）：
```python
                self._provider = result["provider"]
                self._log.append(f"✅ {proto} 連線成功！")
```

在其後加入一行：
```python
                self._sent_tab.set_provider(self._provider)
```

- [ ] **Step 11：執行應用程式確認啟動正常**

```
.venv/Scripts/python.exe -m hcp_cms
```

預期：應用程式正常啟動，信件頁面頂部出現「📥 收件處理」與「📤 寄件備份」兩個 tab，切換後版面正確。

- [ ] **Step 12：執行全部測試確認無回歸**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

預期：所有測試 PASS（包含 5 個新增的 `test_sent_mail_manager` 測試）

- [ ] **Step 13：Commit**

```bash
git add src/hcp_cms/ui/email_view.py
git commit -m "feat(ui): EmailView 新增寄件備份分頁（QTabWidget）"
```
