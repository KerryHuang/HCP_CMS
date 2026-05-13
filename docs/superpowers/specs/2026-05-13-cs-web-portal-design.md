# 客服 Web Portal 設計規格 — v2（含 Mantis 手動推送）

**日期：** 2026-05-13
**狀態：** 待確認
**取代：** `2026-05-12-cs-web-portal-design.md`（舊版，純 Companion Server）

## 與 v1 差異摘要

| 面向 | v1（2026-05-12）| v2（本版）|
|------|-------|-------|
| 主架構 | Companion Server（Jill PC + SQLite + NiceGUI Web Portal）| **完全相同** |
| Mantis 整合 | 未提，沿用既有「連結到既有 Mantis ticket」 | **新增「推到 Mantis」手動按鈕**：建新 ticket / 批次建 / 推為 bugnote |
| 自動覆寫衝突（D）| 未解決 | **新增「已結案」狀態（D-2）鎖定不重開** |
| 未指派案件（G）| 待決 | **G-3：Web Portal 不顯示，沿用桌面 App 既有流程** |
| 工程時程 | 6 天 | **8-10 天**（+1-2 天 Mantis 寫入功能）|

## 背景與目標

HCP CMS 目前是 Jill 一人使用的 PySide6 + SQLite 桌面 App，但 Jill 管 3 人客服團隊（jill / YOGA / Rebecca）。其他客服無法自行更新案件狀態、進度、處理人員等，必須透過 Jill 代操，造成瓶頸。同時，現有 Mantis SOAP 整合僅能**讀取**既有 ticket，無法從 HCP CMS 推送案件出去。

**目標**：
1. 建置 Web Portal 讓 3 位客服**透過瀏覽器**自行維護案件
2. 新增「推到 Mantis」手動按鈕，讓 Jill 可以選擇性把案件變成 Mantis ticket / bugnote
3. 解決客戶回信導致已完成案件被自動覆寫的衝突
4. **完全不影響既有 Mantis 作業**：每筆推送都需手動觸發，無自動同步

**限制條件**：

- **預算 0 元**：Companion Server 架構（Web 跑 Jill PC）
- **Jill 開機才可用**：Email Scheduler 本就只在 Jill 開機時跑，Web Portal 同步以該 PC 為基準
- **Mantis 0 自動寫入**：所有寫入 Mantis 的動作必須由使用者手動觸發
- **既有 Mantis production 完全不變動**：不新增 project / 不改 workflow / 不改 custom field

## 設計決策

### 架構（不變）

- **架構翻轉**：Web Portal 為案件維護「主場」，桌面 App 保留高級功能（報表、Patch 整理、KMS、信件處理、未指派案件處理）
- **Companion Server**：NiceGUI Web Server 在 Jill PC 上以獨立 process 開機自啟，與桌面 App 共用同一個本機 `cs_tracker.db`
- **單一 DB，免同步**：Web 與桌面 App 共用 SQLite 檔（WAL + `busy_timeout=5000ms`）
- **網路存取**：LAN 內 `http://<Jill PC IP>:8080`；遠端走 Tailscale
- **認證**：點名登入（pick from list）+ cookie 裝置綁定。3 人團隊互信
- **可視規則（B+A 聯集）**：`LOWER(handler) = LOWER(我.name) OR 我.staff_id IN companies.cs_staff_id`
- **改派規則**：任何客服都能改 handler

### Mantis 整合（新增）

- **完全手動觸發**：所有寫入 Mantis 動作（建 ticket / 加 bugnote）皆需使用者按按鈕
- **不自動同步**：HCP CMS 案件更新後**不會**自動 push 到 Mantis；Mantis ticket 更新也**不會**自動拉回 HCP CMS
- **三種推送模式並存**：
  - 模式 (a)：詳情頁按鈕「建立 Mantis ticket」→ 單筆推
  - 模式 (b)：列表多選 + 按鈕「批次建立 Mantis ticket」→ 多筆同時推
  - 模式 (c)：若案件已連結某 ticket，詳情頁按鈕變「推送更新為 bugnote」→ 將當下案件狀態與最新 case_log 變成留言
- **推送結果記錄**：建新 ticket 後寫入 `case_mantis` 表（既有 schema），記錄 case_id ↔ ticket_id 對應
- **失敗處理**：SOAP 失敗時顯示錯誤訊息 + 不寫入 case_mantis，使用者可重試
- **欄位對應**（預設值，可在 spec review 時調整）：

  | HCP CMS 案件欄位 | Mantis Issue 欄位 | 備註 |
  |---|---|---|
  | subject | summary | 直接 1:1 |
  | body / progress（拼接）| description | 「【原信件】\n{body}\n\n【處理進度】\n{progress}」|
  | priority（高/中/低）| priority | 高→high, 中→normal, 低→low |
  | handler（staff.name）| handler | 需 staff ↔ Mantis user 對應（用 staff.name 比對 Mantis username）|
  | company_id | description 內附註 | MVP 不對應 category，避免動 Mantis 設定 |
  | case_id | 寫在 description 首行 `[HCP-CMS: {case_id}]` | 供反查 |
  | system_product / issue_type / error_type | 不送 | 避免依賴 Mantis custom field |

- **目標 Mantis project**：透過設定檔 `mantis_push.project_id` 指定（單一固定值），不從 UI 選擇
- **建 ticket 預設值**：severity = "minor"，category = Mantis 該 project 預設值

### 自動覆寫衝突（D-2）

- 新增 `已結案` 狀態，鎖定不自動重開
- 狀態 enum 從 3 個變 4 個：`處理中` / `已回覆` / `已完成` / `已結案`
- ThreadTracker 收到客戶回信時行為：
  - 案件為 `已結案` → **不重開**，僅新增 case_log
  - 案件為 `已完成` → 改回 `處理中`（既有行為）
  - 其他 → 既有行為
- 案件詳情頁 UI 提示：「已結案」狀態以深灰底色標示，並顯示「本案件已結案，客戶後續回信不會重新開啟」
- 報表分類：`已結案` 視同 `已完成`，但可獨立統計

### 未指派案件（G-3）

- Web Portal **完全不顯示**「handler 為空」的案件
- 「未指派」定義：`handler IS NULL OR handler = ''`（單純看 handler 欄位，不管公司歸屬）
- 即使案件所屬公司在客服管轄範圍內，只要 handler 為空就不上 Web Portal
- 處理方式：Jill 在桌面 App 看到 + 處理 + 指派 handler 後，該案件即出現在 Web Portal 對應客服的清單
- ⚠ 這代表 YOGA / Rebecca 無法主動「認領」案件，仍需 Jill 中介
- ⚠ 簡化「未指派」定義為「handler 空」單一條件，避免雙重判斷造成的視覺不一致（同一案件因公司歸屬不同決定顯示與否會混亂）

## 架構總覽

```
                  Jill 的 PC（Jill 開機時運作）
                  ┌────────────────────────────────────────┐
                  │                                        │
                  │  桌面 App (PySide6)                    │
                  │  ┌──────────────────────────────┐     │
                  │  │  Email Scheduler             │     │
                  │  │  Reports / Patch / KMS       │     │
                  │  │  未指派案件處理 (G-3 主場)    │     │
                  │  │  桌面 UI                     │     │
                  │  └──────────────────────────────┘     │
                  │              │                         │
                  │              ▼                         │
                  │  ┌──────────────────────────────┐     │
                  │  │  cs_tracker.db (SQLite WAL)  │     │
                  │  │  既有 12 表 + 2 FTS5         │     │
                  │  │  + web_audit_log (新)        │     │
                  │  └──────────────────────────────┘     │
                  │              ▲                         │
                  │              │                         │
                  │  ┌──────────────────────────────┐     │
                  │  │  NiceGUI Web Server          │     │
                  │  │  (uvicorn, port 8080)        │     │
                  │  │  NSSM/Task Scheduler 自啟    │     │
                  │  │                              │     │
                  │  │  重用既有 Core Manager       │     │
                  │  │    - CaseManager             │     │
                  │  │    - CaseMantisRepository    │     │
                  │  │    - CaseLogRepository       │     │
                  │  │    - ThreadTracker (改 D-2)  │     │
                  │  │  + MantisPushManager (新)    │     │
                  │  │  + AuditLogger (新)          │     │
                  │  │  + WebAuthManager (新)       │     │
                  │  │  + CaseVisibilityFilter (新) │     │
                  │  └──────────────────────────────┘     │
                  │              │ SOAP                    │
                  │              ▼                         │
                  └────────────────────────────────────────┘
                       ▲                ▲              ▲
                       │ HTTP           │ HTTP         │ HTTP
                       │                │              │
                  jill 瀏覽器    YOGA 瀏覽器     Rebecca 瀏覽器
                  (localhost)   (LAN/Tailscale)  (LAN/Tailscale)


                  公司 Mantis 主機（既有，0 變動）
                  ┌────────────────────────────────────────┐
                  │  Mantis 應用 + MySQL                   │
                  │  （HCP CMS 透過 SOAP 寫入新 ticket /   │
                  │   bugnote，每筆都使用者手動觸發）       │
                  └────────────────────────────────────────┘
```

## Data 層

### 既有資料表（不改 schema）

- `cs_cases` — 案件主表（**狀態 enum 由 3 變 4**，加入「已結案」，無 schema 變動，僅值域擴增）
- `staff` — 客服身分來源
- `case_logs` — 補充紀錄
- `case_mantis` — Mantis 連結（**直接擴用**，記錄推送結果）
- `companies` — 公司主表（取 cs_staff_id 做可視過濾）
- 其他既有表照舊

### 新增資料表

**web_audit_log**

| 欄位 | 型別 | 說明 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | |
| staff_id | TEXT NOT NULL | 引用 staff.staff_id |
| occurred_at | TEXT NOT NULL | `YYYY/MM/DD HH:MM:SS` |
| case_id | TEXT NOT NULL | 引用 cs_cases.case_id |
| field_name | TEXT NOT NULL | 例：`status`, `handler`, `progress`, `mantis_push` |

索引：
- `idx_audit_case (case_id, occurred_at)`
- `idx_audit_staff (staff_id, occurred_at)`

⚠ 推送 Mantis 也記在這個表，`field_name='mantis_push'`，可在稽核頁追蹤誰何時推了哪筆。

### Migration 規劃

1. **狀態 enum 擴增**：無 schema 變動，僅 Python 端 enum / 驗證邏輯增加 `已結案`
2. **新增 web_audit_log**：透過既有 `_apply_pending_migrations()` 機制冪等執行
3. **既有資料**：所有現有「已完成」案件**保持「已完成」**，不批次轉「已結案」（保留現有行為）

## Services 層

### 既有（不變）

- MailProvider ABC + 各實作（IMAP / Exchange）
- 各 Core Manager 不動

### 擴充 MantisClient ABC

新增 2 個寫入方法到 `services/mantis/base.py::MantisClient`：

```python
class MantisClient(ABC):
    # 既有方法
    @abstractmethod
    def connect(self) -> bool: ...
    @abstractmethod
    def get_issue(self, issue_id: str) -> MantisIssue | None: ...
    @abstractmethod
    def get_issues(self, project_id: str | None = None) -> list[MantisIssue]: ...

    # 新增：寫入方法
    @abstractmethod
    def create_issue(
        self,
        project_id: str,
        summary: str,
        description: str,
        category: str = "",
        priority: str = "normal",
        severity: str = "minor",
        handler: str | None = None,
    ) -> str | None:
        """建立新 issue，成功回傳 ticket_id，失敗回 None（self.last_error 含原因）。"""

    @abstractmethod
    def add_note(
        self,
        issue_id: str,
        text: str,
        view_state: str = "public",
    ) -> str | None:
        """加 bugnote，成功回傳 note_id，失敗回 None。"""
```

### MantisSoapClient 擴充

實作上述 2 方法，透過 SOAP `mc_issue_add` 與 `mc_issue_note_add`。SOAP envelope 範例：

```xml
<!-- 建 issue -->
<man:mc_issue_add>
    <man:username>{user}</man:username>
    <man:password>{pass}</man:password>
    <man:issue>
        <man:project><man:id>{project_id}</man:id></man:project>
        <man:summary>{summary}</man:summary>
        <man:description>{description}</man:description>
        <man:priority><man:name>{priority}</man:name></man:priority>
        <man:severity><man:name>{severity}</man:name></man:severity>
        <man:handler><man:name>{handler}</man:name></man:handler>
        <man:category>{category}</man:category>
    </man:issue>
</man:mc_issue_add>

<!-- 加 bugnote -->
<man:mc_issue_note_add>
    <man:username>{user}</man:username>
    <man:password>{pass}</man:password>
    <man:issue_id>{issue_id}</man:issue_id>
    <man:note>
        <man:text>{text}</man:text>
        <man:view_state><man:name>{view_state}</man:name></man:view_state>
    </man:note>
</man:mc_issue_note_add>
```

回應解析新 ticket id / note id 用既有 `_extract_xml()` 輔助函數。

### MantisRESTClient 擴充

實作對應 REST 端點：
- `POST /api/rest/issues` 建 issue
- `POST /api/rest/issues/{id}/notes` 加 bugnote

⚠ 兩個 client 各自獨立實作，符合既有架構。MVP 預設用 SOAP（既有設定）。

## Core 層

### 新增

**WebAuthManager**（NiceGUI 端）
- `list_cs_staff() -> list[Staff]` 回傳 role='cs' 的 staff
- `set_session_staff(response, staff_id)` 設 cookie
- `get_session_staff(request) -> Staff | None` 解 cookie 取 staff
- 不需密碼

**CaseVisibilityFilter**（依 B+A 規則 + G-3 排除未指派）
- `visible_cases(staff: Staff) -> list[Case]`
- SQL:
  ```sql
  SELECT c.* FROM cs_cases c
  WHERE (
    LOWER(c.handler) = LOWER(?)
    OR c.company_id IN (
       SELECT company_id FROM companies WHERE cs_staff_id = ?
    )
  )
  AND c.handler IS NOT NULL
  AND c.handler != ''
  ORDER BY c.updated_at DESC
  ```
  ⚠ G-3：強制要求 `handler` 不為空，未指派案件即使來自客服管轄公司也不顯示。

**AuditLogger**
- 每次欄位變更前比對 before/after，僅記錄 `field_name`
- `log_field_change(staff_id, case_id, field_name)` → INSERT 一筆到 `web_audit_log`
- `log_mantis_push(staff_id, case_id, ticket_id, mode)` 雙寫：
  1. INSERT 一筆到 `web_audit_log`：field_name='mantis_push'（追蹤誰何時推了哪筆案件）
  2. INSERT 一筆到 `case_logs`：direction='Mantis 推送'，mantis_ref=ticket_id，content=「{operator} 於 {time} 推送為 {mode}: ticket #{ticket_id}」（記錄詳細 ticket_id 與內容）

⚠ 不擴 `web_audit_log` schema（保持精簡）。ticket_id 的詳細對應記在 case_logs，符合既有「案件相關時序紀錄」的精神。

**MantisPushManager**（新核心類別）

```python
class MantisPushManager:
    def __init__(self, conn: sqlite3.Connection, client: MantisClient, project_id: str) -> None:
        self._conn = conn
        self._client = client
        self._project_id = project_id
        self._case_repo = CaseRepository(conn)
        self._mantis_link_repo = CaseMantisRepository(conn)
        self._case_log_repo = CaseLogRepository(conn)

    def push_case_as_new_ticket(self, case_id: str, operator_staff_id: str) -> tuple[bool, str]:
        """模式 (a)(b)：建新 Mantis ticket。回傳 (success, ticket_id_or_error)。
        若案件已連結 ticket，回傳 (False, '案件已有連結，請改用 push_as_bugnote')。
        """

    def push_case_as_bugnote(self, case_id: str, operator_staff_id: str) -> tuple[bool, str]:
        """模式 (c)：將案件最新內容推為已連結 ticket 的 bugnote。
        若案件未連結，回傳 (False, '案件尚未連結 Mantis ticket，請改用 push_as_new_ticket')。
        """

    def push_cases_batch(
        self,
        case_ids: list[str],
        operator_staff_id: str,
    ) -> list[tuple[str, bool, str]]:
        """模式 (b)：批次推。每筆獨立成功/失敗，返回逐筆結果列表。
        已連結 ticket 的案件自動 skip 並標記為 skipped。
        """

    def _build_description(self, case: Case) -> str:
        """組裝 Mantis description：含 [HCP-CMS: case_id] + 主旨 + 本文 + 進度。"""

    def _build_bugnote_text(self, case: Case) -> str:
        """組裝 bugnote 文字：含當前狀態 + 進度 + 最新 case_log。"""

    def _map_priority(self, hcp_priority: str) -> str:
        """高 → high, 中 → normal, 低 → low。"""
```

### 修改既有 ThreadTracker（D-2 規則）

於 `core/thread_tracker.py` 客戶回信處理路徑：

```python
def handle_customer_reply(self, case: Case, new_log: CaseLog) -> None:
    # 加 case_log（既有行為）
    self._case_log_repo.insert(new_log)
    # 狀態判斷
    if case.status == "已結案":
        # D-2 新規則：不重開
        return
    if case.status in ("已完成", "已回覆"):
        # 既有行為：改回處理中
        self._case_repo.update_status(case.case_id, "處理中")
```

### 重用既有

- CaseManager / FTSManager / Classifier / CaseRepository / CaseMantisRepository / CaseLogRepository

## UI 層

NiceGUI（Python web framework）開發，深色主題與桌面 App 對齊。

### 頁面結構

| 路徑 | 功能 | 權限 |
|------|------|------|
| `GET /` | 首頁，未登入導 /login，已登入導 /cases | — |
| `GET /login` | 點名清單頁（role='cs'）| — |
| `POST /login` | 設 cookie，導 /cases | — |
| `POST /logout` | 清 cookie | 任何登入者 |
| `GET /cases` | 「我的案件」清單頁，依 B+A + G-3 過濾 | cs |
| `POST /cases/push-batch` | **批次推送 Mantis**（模式 b）| cs |
| `GET /cases/{case_id}` | 案件編輯頁 | cs（需可視）|
| `POST /cases/{case_id}` | 儲存 status/progress/handler/priority/rd_assignee | cs（需可視）|
| `POST /cases/{case_id}/push-mantis` | **推到 Mantis**（自動判斷模式 a 或 c）| cs（需可視）|
| `POST /cases/{case_id}/logs` | 新增補充紀錄 | cs（需可視）|
| `POST /cases/{case_id}/mantis-link` | 加既有 Mantis 連結（既有功能，輸入 ticket_id）| cs（需可視）|
| `GET /audit` | 看稽核 log | admin |

### MVP 可編輯欄位（同 v1）

- `status`（下拉：處理中/已回覆/已完成/**已結案**）⚠ 「已結案」需 confirm dialog
- `progress`（多行文字）
- `handler`（下拉：staff role='cs'）
- `priority`（下拉：高/中/低）
- `rd_assignee`（自由輸入 + 過往值建議）
- 新增 case_log（補充紀錄）
- 加既有 Mantis 連結（手動輸入 ticket_id，既有功能）

### Mantis 推送 UI

**案件詳情頁 — 「推到 Mantis」按鈕**

依案件是否已連結 ticket 動態變化：

```
情境 1（無連結）：
  ┌──────────────────────────────────┐
  │  本案件尚未連結 Mantis ticket    │
  │  [建立新 Mantis ticket]          │
  └──────────────────────────────────┘
  按下 → confirm dialog「將案件 #C-20260513-001 建為新 Mantis ticket？」
  → 成功：頁面 reload，顯示「已建立 Mantis ticket #1234」+ 連結
  → 失敗：顯示錯誤訊息，紅色 banner

情境 2（已連結）：
  ┌──────────────────────────────────┐
  │  已連結 Mantis ticket #1234      │
  │  [推送更新為 bugnote]            │
  │  [連結到另一個 ticket]           │
  └──────────────────────────────────┘
  按下「推送更新為 bugnote」→ confirm「將當前進度推為 #1234 的留言？」
  → 成功：頁面 reload，case_log 多一筆「[Mantis 推送] note_id=N123 by YOGA」
```

**案件清單頁 — 批次推送**

```
☐ [全選] 主旨           客戶    狀態      handler   [推到 Mantis]
☐       印表機異常       ABC     處理中    YOGA
☑       排程失敗         XYZ     已回覆    Rebecca
☑       錯誤 0x123       DEF     處理中    YOGA

選 N 筆，按「推到 Mantis」→ confirm dialog 列出明細：
  將推送以下 2 筆案件為新 Mantis ticket：
    ☐ C-20260513-002 排程失敗（客戶: XYZ）
    ☐ C-20260513-003 錯誤 0x123（客戶: DEF）
  （已連結 ticket 的案件不會出現在這個清單）
  [取消]  [確認推送]
  確認 → 顯示進度條 + 結果摘要：「成功 2 筆 / 失敗 0 筆 / 略過 0 筆」
  失敗筆數可展開看錯誤訊息
```

⚠ 批次操作中每筆呼叫 SOAP，UI 顯示進度條避免使用者誤以為當機。
⚠ confirm dialog 列出案件 ID + 主旨 + 客戶，讓使用者最後確認，避免誤推大批案件。

### Phase 2 待補（同 v1，未變）

- 新增整筆案件（d1）
- 分類欄位（a5）/ 問題原因解法（a6）/ 自訂欄位（e1）
- 移除 Mantis 連結（c2）/ 在 Web 直接寄回信（b2）
- 未指派案件「孤兒」認領頁（G-1 / G-2 升級）
- 升級到 Oracle Cloud Free Tier
- **Mantis 雙向同步**：拉回 ticket 狀態變更到 HCP CMS

## 認證設計

完全同 v1：點名 + cookie，無密碼，LAN/Tailscale 內 HTTP。

## 部署

完全同 v1：Jill PC + NSSM + 既有 .venv + port 8080。

新增需求：
- **設定檔 `mantis_push.project_id`**：指定目標 Mantis project ID（單一值）
- 既有 Mantis 連線設定（base_url / username / password）已存在，重用

## 測試策略

依 Law 3（TDD）+ 6 層架構：

| 層 | 測試類型 | 重點 |
|----|---------|------|
| Data | Unit | `web_audit_log` CRUD；case 狀態值域擴增至 4 個 |
| Services | Unit | `MantisSoapClient.create_issue()` / `add_note()`（mock requests）|
| Core | Unit | `MantisPushManager` 三種模式 + 邊界（已連結時建新、未連結時推 bugnote 都要回錯誤）<br>`CaseVisibilityFilter` G-3 過濾<br>`ThreadTracker` 已結案不重開<br>`WebAuthManager` cookie 流程 |
| UI (NiceGUI) | Integration | NiceGUI testing client 測 5 頁渲染與互動<br>批次推送進度條顯示 |
| 整合 | Integration | 模擬 SOAP 失敗時 case_mantis 不寫入<br>並發：Email Scheduler 寫入時 Web 同時讀 |

每段功能先寫紅燈測試（Law 3）。

## 8-10 天時程

| 天 | 內容 |
|----|------|
| Day 1 | NiceGUI 環境建立 + 登入頁（pick from list + cookie）+ WebAuthManager |
| Day 2 | `/cases` 清單頁 + `CaseVisibilityFilter`（B+A + G-3）|
| Day 3 | `/cases/{case_id}` 詳情頁 + 5 欄位編輯 + AuditLogger 整合 + **「已結案」狀態 UI + ThreadTracker D-2 邏輯** |
| Day 4 | case_logs 新增 + 既有 Mantis 連結 + 改派 handler 細節 |
| Day 5 | **MantisClient ABC 寫入方法 + SOAP 實作 + 單元測試** |
| Day 6 | **MantisPushManager 三模式 + 單元測試 + AuditLog 整合** |
| Day 7 | **詳情頁「推到 Mantis」按鈕 + 確認 dialog + 連結後變 bugnote 模式** |
| Day 8 | **清單頁批次推送 + 進度條 + 失敗摘要** |
| Day 9 | `/audit` 稽核頁 + 整體 UI 打磨 + NSSM 部署設定 |
| Day 10 | 整合測試 + Tailscale 設定指引 + 使用文件 + buffer |

⚠ 若 Day 5-6 SOAP 寫入遇到 Mantis 版本相容問題（不同 Mantis 版本 SOAP schema 略異），可能需 0.5-1 天 buffer 做 POC，影響整體 +1 天。

## 風險與緩解

| 風險 | 機率 | 緩解 |
|------|------|------|
| Jill PC 當機 / 重開 | 中 | NSSM 自動重啟 Web Server |
| Jill 請假 / 出差關機 | 中 | MVP 階段客服 B/C 該時段不可用（既定取捨）|
| Mantis SOAP `mc_issue_add` 在公司 Mantis 版本不支援 | **中** | **Day 5 開頭先做 5 分鐘 POC（用 curl 試打）**確認可行；若不行改 REST API 或 Phase 2 處理 |
| Mantis SOAP 寫入回應格式跨版本差異 | 低-中 | 寫入後立即 `get_issue` 驗證 + 解析多種回應格式 |
| 批次推送中途失敗 | 中 | 每筆獨立交易（不 rollback 其他筆）+ UI 顯示逐筆結果 |
| Mantis handler 名稱與 staff.name 對不上 | 中 | 若對應失敗則建 ticket 時 handler 留空，UI 顯示警告 |
| 客服誤推大量案件到 Mantis | 低-中 | 批次推送 confirm dialog 顯示筆數 + 列出案件 ID |
| 「已結案」誤用變黑洞 | 低 | UI 顯著色標 + 詳情頁文字提示 + 報表獨立統計 |
| 既有 ~30% 案件無 cs_staff_id 變黑洞 | 中 | G-3：Web 不顯示，桌面 App 既有流程處理 |
| LAN 連線中斷 | 低 | IT 環境問題 |
| cookie 被竊 | 低 | LAN 封閉環境風險低 |
| Email Scheduler 與 Web 同時寫 DB | 低 | WAL + busy_timeout 足夠 |

## 後續事項

- **Phase 2（MVP 上線 1 個月後）**：
  - 補 a5/a6/d1/e1
  - Mantis 連結移除
  - 未指派案件 G-1/G-2 升級（看實際使用後決定要不要做認領池）
  - 自動推送 Mantis（觀察手動使用習慣後決定）
  - Mantis 雙向同步（ticket 更新拉回 HCP CMS）
- **Phase 3**：報表 Web 化、寄回信功能、研發人員 staff tab
- **升級路徑**：若 Jill 需要 24/7 → 搬到 Oracle Cloud Free Tier 或 Linode VPS（同份 code）
- **觀察決定**：權限角色更細、行動裝置最佳化、Excel 匯入匯出

## 設計取捨記錄

依 `spec-writing.md` 慣例記錄：

- **選擇方案 IV-b 物理完全隔離 Mantis**；排除 (IV-a) 邏輯隔離（共用 MySQL）：使用者偏好「完全不沾 Mantis 主機」，避免任何潛在影響
- **選擇手動推送 Mantis 按鈕**；排除 B 路線（案件直接變 Mantis ticket）：Mantis 雙向自動同步複雜度過高，且使用者要求「完全隔離」
- **選擇 D-2 新增已結案狀態**；排除 D-1（僅 UI 提示）：3 人協作下「鬼改」案件會頻繁發生，需要明確的鎖定機制
- **選擇 G-3 未指派案件不上 Web**；排除 G-2（未指派池）：MVP 階段不需擴展未指派處理流程，沿用桌面 App 既有方式
- ⚠ **Mantis SOAP 寫入跨版本相容**：使用者公司 Mantis 版本未知，Day 5 開頭需 POC 驗證；若 `mc_issue_add` 不支援，需臨時切換 REST 或延後 Mantis 推送功能
