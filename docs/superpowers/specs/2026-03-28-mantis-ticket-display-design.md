# Mantis Ticket 資訊呈現改善設計文件

**日期：** 2026-03-28
**作者：** Jill / Claude
**版本：** v2（修正 spec review 問題 + 新增 Bug 筆記顯示）

---

## 背景

案件詳情對話框的「🔧 Mantis 關聯」Tab 目前只從 SOAP 抓取 4 個欄位（summary、status、priority、handler），且表格呈現欄位不足，無法快速判斷 Bug 修復狀態與版本資訊。

---

## 目標

讓客服人員在查看案件時，能快速掌握：
- 這個 Bug 修好了嗎？（status + fixed_in_version）
- 什麼時候修好？（target_version）
- 誰在處理？（handler）
- 嚴重程度？（severity + priority）
- 完整問題描述（description）
- 最新進度：最後 5 條 Bug 筆記（notes）

---

## 版面配置：表格 + 詳情面板

### 上方表格（5 欄，快速掃描）

| 欄位 | 說明 |
|------|------|
| 票號 | Mantis Ticket ID |
| 狀態 | 彩色 badge（見色彩對照表） |
| 摘要 | Issue summary |
| 處理人 | handler |
| 最後同步 | synced_at |

### 下方詳情面板（常駐）

- **未選取時**：「請點選上方 Ticket 查看詳情」灰色提示
- **已選取時**：
  1. 標題列：票號 + 狀態 badge + 摘要
  2. 6 格結構化資訊（Grid 2 行 × 3 欄，由左至右由上至下）：
     - 嚴重性 / 優先 / 回報者
     - 建立時間 / 🎯 目標版本 / ✅ 修復版本
  3. 問題描述（`QTextEdit` ReadOnly，可捲動，最大高度 100px）
  4. 最後 5 條 Bug 筆記（時間降序，每條顯示：時間、回報者、內容節錄前 200 字）
  5. **若筆記總數 > 5**：面板底部顯示提示連結「📎 尚有更多筆記，點此在 Mantis 查看完整記錄」，點擊後用 `QDesktopServices.openUrl()` 開啟 `{base_url}/view.php?id={ticket_id}`

### UI Slot 命名（遵循 `_on_<widget>_<action>` 慣例）

- `_on_mantis_table_row_changed(row: int)` — 更新詳情面板
- `_refresh_detail_panel(ticket: MantisTicket | None)` — 填入詳情資料

---

## 狀態 Badge 色彩對照

| Mantis 狀態關鍵字 | 顯示文字 | 背景色 | 文字色 |
|-----------------|---------|--------|--------|
| new | 新增 | `#1e3a5f` | `#93c5fd` |
| feedback | 回饋中 | `#3730a3` | `#c7d2fe` |
| acknowledged / confirmed | 已確認 | `#78350f` | `#fde68a` |
| assigned / in progress | 處理中 | `#7c2d12` | `#fed7aa` |
| resolved | 已解決 | `#166534` | `#bbf7d0` |
| closed | 已關閉 | `#1f2937` | `#9ca3af` |

---

## 技術變更

### 1. `services/mantis/base.py` — MantisIssue

移除重複的 `created` 欄位，統一改為 `date_submitted`；新增 `notes_list` 存最後 5 條筆記：

```python
@dataclass
class MantisNote:
    """單條 Mantis Bug 筆記。"""
    note_id: str = ""
    reporter: str = ""
    text: str = ""
    date_submitted: str = ""

@dataclass
class MantisIssue:
    id: str
    summary: str
    status: str = ""
    priority: str = ""
    handler: str = ""
    severity: str = ""
    reporter: str = ""
    date_submitted: str = ""      # 原 created 欄位改名，語意統一
    target_version: str = ""
    fixed_in_version: str = ""
    description: str = ""
    notes_list: list[MantisNote] = field(default_factory=list)   # 最後 5 條
```

### 2. `services/mantis/soap.py` — MantisSoapClient

**修正 `_extract_xml` after 參數**：改用 regex 支援帶屬性標籤：

```python
if after:
    m = re.search(f"<{after}[^>]*>", text)
    if m is None:
        return None
    text = text[m.start():]
```

**新增欄位抓取**（`get_issue()` 方法）：

```python
severity         = _extract_xml(text, "name", after="severity") or ""
reporter         = _extract_xml(text, "name", after="reporter") or ""
date_submitted   = _extract_xml(text, "date_submitted") or ""
target_version   = _extract_xml(text, "target_version") or ""
fixed_in_version = _extract_xml(text, "fixed_in_version") or ""
description      = _extract_xml(text, "description") or ""
```

**解析最後 5 條 Bug 筆記**（`<notes>` → `<item>` 列表，取後 5 條）：

```python
notes_list = _parse_notes(text, max_count=5)
```

新增靜態方法 `_parse_notes(text, max_count)` 使用 `re.findall` 抓取所有 `<item>` 區段，逐一提取 id / reporter.name / text / date_submitted，取 XML 末端 max_count 條後，依 date_submitted 降序排列（最新在前）。

### 3. `data/models.py` — MantisTicket

新增欄位：

```python
severity: str | None = None
reporter: str | None = None
description: str | None = None
notes_json: str | None = None   # JSON 序列化的 list[dict]，存最後 5 條筆記
```

`notes` 欄位語意澄清：**保留 `notes` 欄位但不再從 SOAP 寫入**（舊版相容），Bug 筆記改存至 `notes_json`（新欄位）。

新增 `notes_count: int | None = None` 欄位：記錄 SOAP 回傳的筆記總數（不受 max_count=5 限制），UI 依此判斷是否顯示「查看完整記錄」提示連結。

### 4. `data/database.py` — Migration

在 `_MIGRATIONS` list 末尾新增（使用 try/except 防呆，相容 SQLite 3.37 之前版本）：

```python
# 每條 migration 為一個 callable 或 SQL 字串
# 既有慣例使用 SQL 字串，但 ALTER TABLE 需防呆，改為 callable：
lambda conn: _safe_add_column(conn, "mantis_tickets", "severity", "TEXT"),
lambda conn: _safe_add_column(conn, "mantis_tickets", "reporter", "TEXT"),
lambda conn: _safe_add_column(conn, "mantis_tickets", "description", "TEXT"),
lambda conn: _safe_add_column(conn, "mantis_tickets", "notes_json", "TEXT"),
lambda conn: _safe_add_column(conn, "mantis_tickets", "notes_count", "INTEGER"),
```

新增輔助函數 `_safe_add_column(conn, table, column, col_type)`：
```python
def _safe_add_column(conn, table, column, col_type):
    existing = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
```

`_apply_pending_migrations()` 執行迴圈需支援 callable：
```python
for migration in pending:
    if callable(migration):
        migration(conn)
    else:
        conn.execute(migration)
```

觸發時機：與現有 migration 相同，在應用啟動時 `init_db()` 內執行。

### 5. `data/repositories.py` — MantisTicketRepository

`upsert()` 新增欄位：severity、reporter、description、notes_json
`get_by_id()` / `list_all()` 透過 `SELECT *` 自動取得新欄位（已使用 `dict(row)` 展開）。

### 6. `core/case_detail_manager.py` — sync_mantis_ticket

```python
import json

ticket = MantisTicket(
    ticket_id=issue.id,
    summary=issue.summary,
    status=issue.status,
    priority=issue.priority,
    handler=issue.handler,
    severity=issue.severity,
    reporter=issue.reporter,
    created_time=issue.date_submitted,
    planned_fix=issue.target_version,
    actual_fix=issue.fixed_in_version,
    description=issue.description,
    notes_json=json.dumps(
        [{"reporter": n.reporter, "text": n.text, "date_submitted": n.date_submitted}
         for n in issue.notes_list],
        ensure_ascii=False,
    ),
    synced_at=_now(),
)
```

### 7. `ui/case_detail_dialog.py` — _build_tab3

**表格**：5 欄（票號、狀態、摘要、處理人、最後同步）
**狀態 badge**：`QTableWidgetItem` + `setBackground(QColor(...))` + `setForeground(QColor(...))`

**詳情面板**（`QFrame`，常駐顯示）：
- `_detail_title: QLabel` — 票號 + 狀態 + 摘要
- `_detail_grid: QGridLayout` (2×3) — 6 個 `(label, value)` QLabel 對
- `_detail_desc: QTextEdit` (ReadOnly, max-height 100px) — 問題描述
- `_detail_notes: QTextEdit` (ReadOnly, max-height 120px) — Bug 筆記列表

Signal 連線：
```python
self._mantis_table.currentRowChanged.connect(self._on_mantis_table_row_changed)
```

---

## 不在本次範圍

- `scheduler/sync_job.py` SyncJob：批次背景同步暫不更新新欄位（記錄為後續 issue）
- `ui/mantis_view.py` Worker：同上，留待後續
- 主動在 Mantis 主頁面新增超連結按鈕（筆記超過 5 條時的提示連結不在此限，已納入本次範圍）
- 修改 case_mantis 關聯表結構

---

## 測試計畫

1. **`tests/unit/test_mantis_soap_fields.py`**
   - `test_extract_xml_with_attributes` — 驗證帶 xsi:type 屬性的標籤可正確解析
   - `test_get_issue_new_fields` — mock HTTP response，驗證 severity/reporter/date_submitted/versions/description 正確填入
   - `test_parse_notes_returns_last_5` — 驗證超過 5 條時只取最後 5 條

2. **`tests/unit/test_mantis_ticket_repository.py`**
   - `test_upsert_with_new_fields` — 儲存含新欄位的 MantisTicket 並 get_by_id 取回驗證
   - `test_safe_add_column_idempotent` — 重複執行 migration 不報錯

3. **`tests/unit/test_case_detail_manager_sync.py`**
   - `test_sync_maps_notes_json` — 驗證 notes_list 正確序列化為 JSON 儲存
