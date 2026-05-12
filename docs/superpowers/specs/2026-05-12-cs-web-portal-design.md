# 客服 Web Portal 設計規格

**日期：** 2026-05-12
**狀態：** 已確認

## 背景與目標

HCP CMS 目前是 Jill 一人使用的 PySide6 + SQLite 桌面 App，但 Jill 管 3 人客服團隊（jill / YOGA / Rebecca）。其他客服無法自行更新案件狀態、進度、處理人員等，所有維護動作必須透過 Jill 一人代操，造成瓶頸。

目標：建置一個 Web Portal 讓所有客服**透過瀏覽器**自行維護案件，包含：

- 看到自己負責或所屬公司的案件清單
- 更新核心欄位（狀態、進度、處理人員、優先度、技術負責人）
- 新增補充紀錄（case_logs）
- 加 Mantis 關聯
- 自行改派 handler 給其他客服

**限制條件**：

- **預算 0 元**：不接受月費 / 年費，採 Companion Server 架構（Web 跑在 Jill 本機 PC 上）
- **接受 Jill 開機才可用**：Email Scheduler 本來就只在 Jill 開機時跑，Web Portal 同步以該 PC 為基準
- 客服 B/C 在公司 LAN 內透過瀏覽器直接連 Jill PC；遠端使用走免費 Tailscale

## 設計決策

- **架構翻轉**：Web Portal 為案件管理「主場」，桌面 App 保留高級功能（報表、Patch 整理、KMS、信件處理）。案件「異動」走 Web，案件「來源」（信件收取）仍走桌面 App。
- **部署模式**：**Companion Server**（0 元）— NiceGUI Web Server 在 Jill PC 上以獨立 process 開機自啟，與桌面 App 共用同一個本機 `cs_tracker.db`。
- **不需同步**：Web 與桌面 App 共用同一個 SQLite 檔（WAL 模式 + `busy_timeout=5000ms` 已設定好），不會有雙 DB 同步問題。
- **不需 SyncPusher / Sync API / Token**：因單一 DB，桌面 App 的 Email Scheduler 直接寫 DB，Web Server 從同一 DB 讀，無需 HTTP 中介。
- **網路存取**：
  - 公司 LAN 內：`http://<Jill PC LAN IP>:8080`
  - 遠端（家用 / 出差）：免費 Tailscale 加入 Jill PC 同一虛擬網段後存取同 URL
  - LAN 內走 HTTP（無加密但僅內網），未來若需要加密可加 Caddy + 自簽憑證或 Tailscale 內建 MagicDNS + HTTPS
- **技術棧**：NiceGUI（Python web framework）+ FastAPI（NiceGUI 內建）+ 重用既有 Core Manager（CaseManager / MantisRepository 等）+ NSSM 或 Windows Task Scheduler 管理 Web Server 開機自啟。
- **認證**：點名登入（pick from list） + cookie 裝置綁定。無密碼，3 人團隊互信高。稽核 log 依當下 cookie 身分記錄。
- **可視規則 (B+A 聯集)**：`LOWER(handler) = LOWER(我.name) OR 我.staff_id IN companies.cs_staff_id`，handler 比對採大小寫不敏感（不動既有 ~7 筆 JILL 大寫資料）。
- **改派規則**：任何客服都能改 handler。改派後寫入 `staff.name` 標準寫法。
- **MVP 範圍**：刻意精簡至 5-6 個核心功能，砍掉新增案件、分類欄位、自訂欄位、orphan 處理。Phase 2 再補。
- **稽核 log**：精簡版（只記 staff_id / occurred_at / case_id / field_name），永久保留，僅 admin 可看。
- **未來可升級**：若 Jill 後續需要 24/7 可用（如請假時客服仍要用），同一份程式碼可搬到 Oracle Cloud Free Tier（永久免費）或付費 VPS，**無需重寫**。

## 架構總覽

```
                  Jill 的 PC（Jill 開機時運作）
                  ┌────────────────────────────────────────┐
                  │                                        │
                  │  桌面 App (PySide6)                    │
                  │  ┌──────────────────────────────┐     │
                  │  │  Email Scheduler             │     │
                  │  │  Reports / Patch / KMS       │     │
                  │  │  桌面 UI                     │     │
                  │  └──────────────────────────────┘     │
                  │              │                         │
                  │              ▼                         │
                  │  ┌──────────────────────────────┐     │
                  │  │  cs_tracker.db (SQLite WAL)  │     │ ★ 單一 DB ★
                  │  │  + 新表 web_audit_log        │     │
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
                  │  │    - MantisRepository        │     │
                  │  │    - CaseLogRepository       │     │
                  │  │  + AuditLogRepository (新增) │     │
                  │  │  + WebAuthManager (新增)     │     │
                  │  │  + CaseVisibilityFilter(新增)│     │
                  │  └──────────────────────────────┘     │
                  └────────────────────────────────────────┘
                       ▲                ▲              ▲
                       │ HTTP           │ HTTP         │ HTTP
                       │                │              │
                  jill 瀏覽器    YOGA 瀏覽器     Rebecca 瀏覽器
                  (localhost)   (LAN/Tailscale)  (LAN/Tailscale)
```

## Data 層

### 新增資料表

**web_audit_log**

| 欄位 | 型別 | 說明 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | |
| staff_id | TEXT NOT NULL | 引用 staff.staff_id |
| occurred_at | TEXT NOT NULL | `YYYY/MM/DD HH:MM:SS` |
| case_id | TEXT NOT NULL | 引用 cs_cases.case_id |
| field_name | TEXT NOT NULL | 例：`status`, `handler`, `progress` |

索引：
- `idx_audit_case (case_id, occurred_at)`
- `idx_audit_staff (staff_id, occurred_at)`

### 重用既有資料表（不改 schema）

- `staff` — 客服身分來源（jill / YOGA / Rebecca）
- `cs_cases` — 案件主表
- `case_logs` — 補充紀錄
- `case_mantis` — Mantis 連結
- `companies` — 公司主表（取 cs_staff_id 做可視過濾）

### 並發寫入處理

桌面 App（Email Scheduler）與 Web Server 兩個 process 同時讀寫同一個 SQLite 檔：

- SQLite WAL 模式（既有設定）允許多讀者 + 單寫者
- `busy_timeout=5000ms` 處理短暫寫入競爭（既有設定）
- 寫入操作極短（INSERT/UPDATE 單筆案件），實務上不會有競爭
- 3 個 Web 使用者 + 1 個 Email Scheduler，遠未達 SQLite 上限

## Services 層

### 重用既有

- 全部 Core Manager（CaseManager / FTSManager / Classifier / ThreadTracker）
- MantisRepository / CaseMantisRepository

### 不需要新增

- ~~SyncPusher~~：單一 DB 不需要
- ~~Sync API endpoints~~：不需要
- ~~API Token 機制~~：不需要

## Core 層

### 新增

**WebAuthManager**（NiceGUI 端）
- `list_cs_staff() -> list[Staff]` 回傳 role='cs' 的 staff
- `set_session_staff(response, staff_id)` 設 cookie
- `get_session_staff(request) -> Staff | None` 解 cookie 取 staff
- 不需要密碼驗證（pick-from-list）

**CaseVisibilityFilter**（新增，依 B+A 規則）
- `visible_cases(staff: Staff) -> list[Case]`
- SQL:
  ```sql
  SELECT * FROM cs_cases
  WHERE LOWER(handler) = LOWER(?)
     OR company_id IN (
        SELECT company_id FROM companies WHERE cs_staff_id = ?
     )
  ORDER BY updated_at DESC
  ```

**AuditLogger**
- 每次欄位變更前比對 before/after，僅記錄 `field_name`
- 使用 `sqlite3.Connection` 寫入 `web_audit_log`

### 重用既有

- CaseManager（更新案件）
- 改派 handler 時用 staff.name 標準寫法（已有 staff repo）

## UI 層

NiceGUI（Python web framework）開發，深色主題與桌面 App 對齊。

### 頁面結構

| 路徑 | 功能 | 權限 |
|------|------|------|
| `GET /` | 首頁，未登入導 /login，已登入導 /cases | — |
| `GET /login` | 點名清單頁（role='cs'）| — |
| `POST /login` | 設 cookie，導 /cases | — |
| `POST /logout` | 清 cookie | 任何登入者 |
| `GET /cases` | 「我的案件」清單頁，依 B+A 過濾 | cs |
| `GET /cases/{case_id}` | 案件編輯頁 | cs（需可視）|
| `POST /cases/{case_id}` | 儲存 status/progress/handler/priority/rd_assignee | cs（需可視）|
| `POST /cases/{case_id}/logs` | 新增補充紀錄 | cs（需可視）|
| `POST /cases/{case_id}/mantis` | 加 Mantis 關聯 | cs（需可視）|
| `GET /audit` | 看稽核 log | admin |

### MVP 可編輯欄位

- `status`（下拉：處理中/已回覆/已完成）
- `progress`（多行文字）
- `handler`（下拉：staff role='cs'）
- `priority`（下拉：高/中/低）
- `rd_assignee`（自由輸入文字 + 過往值自動建議）
- 新增 case_log（補充紀錄）
- 加 Mantis 連結（輸入 ticket_id）

### Phase 2 待補

- 新增整筆案件（d1）
- 分類欄位（a5: system_product / issue_type / error_type）
- 問題/原因/解法 3 欄（a6）
- 自訂欄位 cx_1~N（e1）
- 移除 Mantis 連結（c2）
- 在 Web 直接寄回信（b2）
- 在 Web 開 Mantis ticket（c3）
- 未指派案件「孤兒」認領頁（需先補 source mailbox 追蹤）
- 研發人員 staff 管理 tab（桌面 App）
- 升級到 Oracle Cloud Free Tier 或 VPS（如果 Jill 24/7 可用需求出現）

## 認證設計

### Web 端：點名 + cookie

1. 使用者開啟 `http://<Jill PC IP>:8080` → 無 cookie → 導 `/login`
2. 列出 staff 表 `role='cs'` 的 3 人（jill / YOGA / Rebecca）
3. 點一下 → POST `/login` 帶 staff_id → 後端 set-cookie `cms_staff=<staff_id>` (HttpOnly, SameSite=Lax, Max-Age=365 天)
4. 下次自動登入；頂部顯示「身分：jill ▼ 切換」
5. 切換按鈕 → POST `/logout` → 回 `/login`

### 為什麼不用 HTTPS / Secure cookie？

MVP 在 LAN 內 HTTP 部署，cookie 不設 `Secure` flag：

- LAN 內封閉環境、互信，無中間人攻擊風險
- 加 HTTPS 需要：(a) 自簽憑證（瀏覽器警告麻煩）或 (b) Tailscale 內建 HTTPS（需所有使用者裝 Tailscale）
- 若客服習慣用 Tailscale，可後續啟用 Tailscale HTTPS，cookie 加上 Secure flag

## 部署

| 項目 | 選擇 |
|------|------|
| 主機 | Jill 的工作 PC（既有，無額外硬體）|
| OS | Windows 11（既有）|
| Python 環境 | Jill PC 既有 `.venv`（共用）|
| Web Server | NiceGUI + uvicorn（port 8080）|
| 開機自啟 | NSSM（推薦）或 Windows Task Scheduler |
| LAN 存取 | 設定 Windows 防火牆允許 8080 inbound |
| 遠端存取 | Tailscale（免費版 3 人團隊夠用），加入後可用同一 IP |
| 備份 | 桌面 App 既有備份機制（無需改）|
| 監控 | NSSM 自動重啟；Phase 2 可加簡易 healthcheck |

### NSSM 設定（部署時操作）

```
nssm install HCP_CMS_Web "D:\CMS\.venv\Scripts\python.exe" -m hcp_cms.web
nssm set HCP_CMS_Web AppDirectory "D:\CMS"
nssm set HCP_CMS_Web Start SERVICE_AUTO_START
nssm start HCP_CMS_Web
```

## 測試策略

依 Law 3（TDD）+ 6 層架構：

| 層 | 測試類型 | 重點 |
|----|---------|------|
| Data | Unit | `web_audit_log` CRUD |
| Core | Unit | `CaseVisibilityFilter` B+A 規則、`WebAuthManager` cookie 流程、handler 大小寫不敏感比對、改派寫回 staff.name、`AuditLogger` 寫入欄位變更 |
| UI (NiceGUI) | Integration | NiceGUI testing client 測 4 頁的渲染與互動 |
| 並發 | Integration | 模擬 Email Scheduler 寫入時 Web 同時讀，確認 WAL 模式無 lock 錯誤 |

每段功能先寫紅燈測試。

## 6 天時程

| 天 | 內容 |
|----|------|
| Day 1 | NiceGUI 環境建立 + 登入頁（pick from list + cookie） + WebAuthManager |
| Day 2 | `/cases` 清單頁 + `CaseVisibilityFilter` B+A 權限過濾 |
| Day 3 | `/cases/{case_id}` 詳情頁 + 5 欄位編輯 + `AuditLogger` 整合 |
| Day 4 | case_logs 新增 + Mantis 連結新增 + 改派 handler 細節 |
| Day 5 | `/audit` 稽核頁 + 整體 UI 打磨 + NSSM 部署設定 |
| Day 6 | 整合測試 + Tailscale 設定指引 + 使用文件 + buffer |

## 風險與緩解

| 風險 | 機率 | 緩解 |
|------|------|------|
| Jill PC 當機 / 重開 | 中 | NSSM 自動重啟 Web Server；桌面 App 既有重啟流程 |
| Jill 請假 / 出差關機 | 中 | **MVP 階段：客服 B/C 該時段不可用**（既定取捨）；Phase 2 可升級到雲端 |
| LAN 連線中斷 | 低 | 屬 IT 環境問題，與本系統無關 |
| cookie 被竊（裝置遺失）| 低 | LAN 內封閉環境風險低；遺失時可 SQL 改 staff.staff_id 強制重新登入 |
| Email Scheduler 與 Web 同時寫 DB | 低 | SQLite WAL + busy_timeout 既有設定足夠處理 |
| 既有 ~30% 案件無 cs_staff_id 變黑洞 | 中 | MVP 不解決，桌面 App 照舊處理；Phase 2 補 orphan 頁 |
| 客服遠端使用需學 Tailscale | 低 | 一頁教學文件，5 分鐘設定完成 |

## 後續事項

- Phase 2（MVP 上線 1 個月後）：補 a5/a6/d1/e1、Mantis 連結移除、孤兒案件認領、source mailbox 追蹤
- Phase 3：報表也 Web 化、寄回信功能、研發人員 staff tab
- 升級路徑（如 Jill 需要 24/7）：搬到 Oracle Cloud Free Tier（**永久免費**）或 Linode VPS（$5/月）— 同一份程式碼可直接部署
- 觀察使用情況決定要不要做：權限角色更細、行動裝置最佳化（RWD）、Excel 案件匯入匯出補完
