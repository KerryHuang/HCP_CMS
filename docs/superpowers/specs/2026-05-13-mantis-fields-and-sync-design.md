# Mantis 推送欄位強化 + bugnote 雙向同步 設計規格

**日期：** 2026-05-13
**狀態：** 待確認
**子專案：** A（欄位對應強化）+ B（雙向同步）

## 背景與目標

實際 Mantis 推送上線後，Jill 發現：

1. Mantis 表單必填欄位「客戶提問人員」（custom field）目前沒被填入 → 推送可能失敗或缺欄位
2. `description` 結構化太機械（[HCP-CMS]+主旨+進度+客戶+聯絡人），不像真正的客訴內容
3. 案件後續往返的「補充記錄」（case_logs）沒被同步到 Mantis，RD 看不到後續討論
4. RD 在 Mantis 寫的 bugnote 也沒回流到 HCP CMS，CS 看不到 RD 回應

**目標**：A 補完 Mantis 推送欄位語義；B 建雙向同步讓 case_logs ↔ bugnotes 透過手動按鈕同步。

## 設計決策

- **子專案 A 先做、B 後做**（同一 session、一個 worktree、一份 spec）
- **A1: custom_fields 機制**：MantisSoapClient.create_issue 加 `custom_fields: dict[str, str] | None` 參數，未來其他自訂欄位也能用同一個機制傳送
- **A2: description = 第一筆「客戶來信」case_log 的 content**：保留 `[HCP-CMS: case_id]` header；若無客戶來信 log，fallback 為既有結構化（避免推送失敗）
- **A3: handler 沿用現狀** — `case.handler` → Mantis handler，需求 5 第一部分已達成；第二部分（後續 RD 指派）是 Mantis-side action，HCP CMS 不需動
- **B 觸發方式：手動按鈕**（user 選 γ） — 擴充既有「🔄 同步選取」按鈕，不引入背景排程
- **B 去重機制**：`case_logs.bugnote_id` 新欄位（TEXT NULL）（user 選 a）
- **B 出向範圍**：`direction IN ('內部討論', 'HCP 信件回覆', 'HCP 線上回覆')`（user 選 β）
- **B 入向**：新 direction 值 `'Mantis bugnote'`（值域擴增、schema 不變）
- **絕不出向**：`'Mantis 推送'`（既有 audit log）和 `'Mantis bugnote'`（剛拉入的 inbound）— 防同步循環

## 子專案 A：欄位對應強化

### A1: MantisSoapClient.create_issue 加 custom_fields

```python
def create_issue(
    self,
    project_id: str,
    summary: str,
    description: str,
    category: str = "",
    priority: str = "normal",
    severity: str = "minor",
    handler: str | None = None,
    custom_fields: dict[str, str] | None = None,  # ★ 新增
) -> str | None:
    ...
```

SOAP envelope 加入 `<man:custom_fields>` 區段：

```xml
<man:custom_fields>
  <man:item>
    <man:field><man:name>客戶提問人員</man:name></man:field>
    <man:value>customer@xyz.com</man:value>
  </man:item>
</man:custom_fields>
```

⚠ 兩個 keyword 的 XML escape：field name 與 value 都需經 `_escape_xml()`。
⚠ `custom_fields` 為 None / 空 dict → 不送 `<man:custom_fields>` 區段（向後相容）。

### A2: description 改為原始來信內容

`MantisPushManager._build_description` 改寫：

```python
def _build_description(self, case: Case) -> str:
    """description 用第一筆「客戶來信」case_log 內容，加 [HCP-CMS] header。

    若該案件無「客戶來信」case_log（如手動建案），fallback 為舊版結構化 description。
    """
    # 找第一筆「客戶來信」
    logs = self._log_repo.list_by_case(case.case_id)
    customer_logs = [log for log in logs if log.direction == "客戶來信"]

    if customer_logs:
        # 既有 list_by_case 為 logged_at DESC，第一筆是最新；要原始來信用最舊
        original = customer_logs[-1]
        return f"[HCP-CMS: {case.case_id}]\n\n{original.content or ''}"

    # Fallback: 舊版結構化（無客戶來信時保底）
    parts = [f"[HCP-CMS: {case.case_id}]"]
    if case.subject:
        parts.append(f"【主旨】{case.subject}")
    if case.progress:
        parts.append(f"【處理進度】\n{case.progress}")
    if case.company_id:
        parts.append(f"【客戶】{case.company_id}")
    if case.contact_person:
        parts.append(f"【聯絡人】{case.contact_person}")
    return "\n\n".join(parts)
```

⚠ `list_by_case` 既有排序為 DESC（最新在前），所以「原始來信」取 `[-1]`。**若排序方向不確定，Task 1 先驗證。**

### A3: MantisPushManager.push_case_as_new_ticket 傳 custom_fields

```python
ticket_id = self._client.create_issue(
    project_id=self._project_id,
    summary=summary,
    description=self._build_description(case),
    category=self._category,
    priority=_PRIORITY_MAP.get(case.priority or "中", "normal"),
    severity="minor",
    handler=case.handler if case.handler else None,
    custom_fields={
        "客戶提問人員": case.contact_person,
    } if case.contact_person else None,
)
```

⚠ 若 `contact_person` 為空，不傳 custom_fields。Mantis 該必填欄位可能擋下 push — 屬合理錯誤回饋（「案件格式不完整：無聯絡人」由 caller 顯示，但這目前 format_case_header 已經卡這條了）。

## 子專案 B：bugnote 雙向同步

### B1: Schema migration — case_logs.bugnote_id

`src/hcp_cms/data/database.py` `_SCHEMA_SQL` 內 `case_logs` 表加欄位（新建 DB 直接含）：

```sql
CREATE TABLE IF NOT EXISTS case_logs (
    log_id      TEXT PRIMARY KEY,
    case_id     TEXT NOT NULL,
    direction   TEXT NOT NULL,
    content     TEXT,
    mantis_ref  TEXT,
    bugnote_id  TEXT,            -- ★ 新增（NULL = 尚未同步）
    logged_by   TEXT,
    logged_at   TEXT,
    reply_time  TEXT,
    ...
);
```

同時 `_apply_pending_migrations` 加冪等 ALTER（既有 DB 補欄位）：

```python
# 補 case_logs.bugnote_id（雙向同步用 dedup key）
_safe_add_column(cur, "case_logs", "bugnote_id", "TEXT")
```

⚠ 假設既有有 `_safe_add_column` helper；若無，看現有 migration 模式抄寫。

### B2: CaseLog model 新欄位

```python
@dataclass
class CaseLog:
    log_id: str
    case_id: str
    direction: str   # '客戶來信' | 'HCP 信件回覆' | 'HCP 線上回覆' | '內部討論' | 'Mantis 推送' | 'Mantis bugnote' ★
    content: str
    mantis_ref: str | None = None
    bugnote_id: str | None = None    # ★ 新增
    logged_by: str | None = None
    logged_at: str = ""
    reply_time: str | None = None
```

`CaseLogRepository` 的 `insert`、`_row_to_log` 同步加 bugnote_id 處理。

### B3: 出向 — push case_logs as bugnotes

新方法 `CaseDetailManager.sync_bugnotes_outbound`：

```python
_PUSH_DIRECTIONS = ("內部討論", "HCP 信件回覆", "HCP 線上回覆")


def sync_bugnotes_outbound(
    self,
    case_id: str,
    ticket_id: str,
    client: MantisClient,
) -> tuple[int, int]:
    """把 case_logs 推為 Mantis bugnotes。

    Returns:
        (success_count, fail_count)
    """
    logs = self._log_repo.list_by_case(case_id)
    candidates = [
        log for log in logs
        if log.direction in _PUSH_DIRECTIONS and not log.bugnote_id
    ]
    success = 0
    fail = 0
    for log in candidates:
        note_id = client.add_note(
            issue_id=ticket_id,
            text=log.content or "",
        )
        if note_id is None:
            fail += 1
            continue
        # 寫回 bugnote_id（dedup key）
        log.bugnote_id = note_id
        self._log_repo.update(log)  # 假設 CaseLogRepository 有 update
        success += 1
    return success, fail
```

⚠ 假設 `CaseLogRepository` 有 `update(log)` 方法；若無，加。

### B4: 入向 — pull bugnotes as case_logs

新方法 `CaseDetailManager.sync_bugnotes_inbound`：

```python
def sync_bugnotes_inbound(
    self,
    case_id: str,
    ticket_id: str,
    client: MantisClient,
) -> tuple[int, int]:
    """從 Mantis 拉新 bugnotes 為 case_logs。

    Returns:
        (pulled_count, fail_count)
    """
    issue = client.get_issue(ticket_id)
    if issue is None:
        return 0, 1

    # 已存在的 bugnote_id（避免重複插入）
    existing_logs = self._log_repo.list_by_case(case_id)
    existing_ids = {log.bugnote_id for log in existing_logs if log.bugnote_id}

    pulled = 0
    for note in issue.notes_list:
        if note.note_id in existing_ids:
            continue
        new_log = CaseLog(
            log_id=self._log_repo.next_log_id(),
            case_id=case_id,
            direction="Mantis bugnote",
            content=note.text,
            bugnote_id=note.note_id,
            logged_by=note.reporter,
            logged_at=note.date_submitted or datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
        )
        self._log_repo.insert(new_log)
        pulled += 1
    return pulled, 0
```

⚠ `MantisIssue.notes_list` 既有最多 10 筆（`_parse_notes(text, max_count=10)`）。若 Mantis ticket 有 > 10 筆 bugnote，只拉最新 10。**Phase 2 可擴充 max_count，MVP 接受**。

### B5: 整合 sync_bugnotes_bidirectional

```python
def sync_bugnotes_bidirectional(
    self,
    case_id: str,
    ticket_id: str,
    client: MantisClient,
) -> dict:
    """雙向同步 case_logs ↔ Mantis bugnotes。

    Returns:
        {"pushed": int, "pulled": int, "fail": int}
    """
    push_success, push_fail = self.sync_bugnotes_outbound(case_id, ticket_id, client)
    pull_success, pull_fail = self.sync_bugnotes_inbound(case_id, ticket_id, client)
    return {
        "pushed": push_success,
        "pulled": pull_success,
        "fail": push_fail + pull_fail,
    }
```

### B6: UI 擴充 _on_sync_mantis

既有 `_on_sync_mantis` 流程（剛剛 mantis-detect-deleted 做的）後面接 bugnote 同步：

```python
def _on_sync_mantis(self) -> None:
    from hcp_cms.core.case_detail_manager import SyncResult

    rows = self._mantis_table.selectionModel().selectedRows()
    if not rows:
        QMessageBox.information(self, "提示", "請先選取要同步的 Ticket。")
        return
    ticket_id = self._mantis_table.item(rows[0].row(), 0).text()
    client = self._build_mantis_client()

    # 1. 同步 metadata（既有，含 NOT_FOUND 處理）
    result, _ticket = self._manager.sync_mantis_ticket(ticket_id, client=client)

    if result == SyncResult.NOT_FOUND:
        # 既有「ticket 已不存在」對話框 + unlink 流程
        ...（既有不動）
        return
    elif result == SyncResult.ERROR:
        QMessageBox.warning(self, "同步失敗", "無法連線至 Mantis，或 Mantis 設定未完成。")
        return

    # 2. SUCCESS — 接著雙向同步 bugnotes
    if client is None:
        # 不應該發生（既有 sync 已過），保險起見
        self._refresh_mantis_table()
        return

    summary_dict = self._manager.sync_bugnotes_bidirectional(
        case_id=self._case_id,
        ticket_id=ticket_id,
        client=client,
    )
    self._refresh_mantis_table()
    self._refresh_log_table()  # 假設既有有此方法或同名

    # 結果摘要
    QMessageBox.information(
        self,
        "同步完成",
        f"Ticket metadata 已更新。\n\n"
        f"補充記錄同步：\n"
        f"  推出 {summary_dict['pushed']} 筆\n"
        f"  拉入 {summary_dict['pulled']} 筆\n"
        f"  失敗 {summary_dict['fail']} 筆",
    )
```

⚠ `_refresh_log_table` 名稱待 Task 6 驗證。若名稱不同（如 `_load_logs`），對齊既有。

## 測試策略

### 子專案 A

| 層 | 測試 |
|----|------|
| Services | `test_mantis_soap_write.py` 新增：`test_create_issue_includes_custom_fields_when_provided` / `test_create_issue_omits_custom_fields_when_none` / `test_custom_field_xml_escapes` |
| Core | `test_mantis_push_manager.py` 新增：`test_push_uses_customer_email_as_description`（無客戶來信 → fallback 既有格式）/ `test_push_sends_contact_person_as_custom_field`（含 contact_person → SOAP 帶 custom_fields）|

### 子專案 B

| 層 | 測試 |
|----|------|
| Data | `test_case_log_repository.py`（既有 / 新）：`test_insert_with_bugnote_id` / `test_update_bugnote_id` |
| Core | `test_case_detail_manager_sync.py` 新增：<br>- `test_sync_outbound_pushes_non_synced_logs`<br>- `test_sync_outbound_skips_already_synced` (bugnote_id 已寫)<br>- `test_sync_outbound_skips_non_pushable_directions`（客戶來信 / Mantis 推送 / Mantis bugnote 都 skip）<br>- `test_sync_inbound_pulls_new_bugnotes`<br>- `test_sync_inbound_skips_existing_bugnote_id`<br>- `test_sync_bidirectional_returns_summary` |
| UI | 手動 smoke test：點同步按鈕看結果 dialog |

## 風險與緩解

| 風險 | 緩解 |
|------|------|
| Mantis SOAP `mc_issue_add` 對 custom_fields 區段格式與我們組裝的不一致 | Task 1 完成後立刻用 Live POC 推一筆驗證（測試用 ticket，事後刪除）|
| 「客戶提問人員」實際 Mantis 欄位名稱可能含空格或大小寫差異 | Live POC 用 mc_issue_get 反查既有 ticket 的 custom_fields 確認真實 name |
| `CaseLogRepository.update` 可能不存在 | Task 3 寫測試時若失敗，先在 Repository 加最小實作 |
| `case_logs` 既有資料的 `bugnote_id` 都是 NULL — 首次同步會把全部 case_logs 都 push | **這是預期行為**（之前沒同步過，第一次補齊）。Task 6 提示對話框：「本案件首次同步 → 推出 N 筆既有 case_log」|
| Mantis 端被人手動清掉 bugnote → 下次同步入向不會拉回該筆（已有 bugnote_id 對應的 case_log） | 視為 Mantis-side action，HCP CMS 保留 case_log 紀錄（與 ticket 刪除的處理一致 — 已在前個 worktree 處理）|
| 入向只拉 max 10 筆 | 既有 SOAP 解析限制；Phase 2 擴充 max_count 即可 |

## 工程量

**~4-5 小時，6 個 Tasks：**

1. **A1**: `MantisSoapClient.create_issue` 加 custom_fields 參數 + 3 測試（40 分鐘）
2. **A2 + A3**: `MantisPushManager._build_description` 改用客戶來信 + `push_case_as_new_ticket` 傳 custom_fields + 2 測試（40 分鐘）
3. **B1 + B2**: schema migration + CaseLog model 加 bugnote_id + CaseLogRepository 加 update 方法（40 分鐘）
4. **B3**: `sync_bugnotes_outbound` + 3 測試（40 分鐘）
5. **B4**: `sync_bugnotes_inbound` + 2 測試（40 分鐘）
6. **B5 + B6**: `sync_bugnotes_bidirectional` 整合 + UI _on_sync_mantis 擴充 + smoke test（40 分鐘）

## 後續事項

- Mantis bugnote 內容超過 10 筆時拉不全：擴充 `MantisSoapClient._parse_notes` 的 max_count（Phase 2）
- 既有手動「🗑 取消連結」改為走 `unlink_mantis_with_audit`（與同步失敗 unlink 統一格式）
- Web Portal 端的 sync 也加 bugnote 雙向同步（Phase 2）
- bugnote 內容含 Mantis 內部超連結 / 圖片附件時 plain text 抓不全（Phase 2 考慮 markdown / 附件處理）
