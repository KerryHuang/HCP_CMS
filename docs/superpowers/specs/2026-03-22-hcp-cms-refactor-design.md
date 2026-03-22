# HCP CMS 重構設計文件

**版本：** v1.0
**日期：** 2026-03-22
**狀態：** 待審核

## 1. 概述

### 1.1 目標

將現有 HCP 客服自動化系統從「Python 腳本 + 靜態 HTML + BAT 啟動」架構，重構為跨平台（Windows + macOS）的 PySide6 桌面應用程式。採用 TDD 開發方式，以軟體工程方式建立系統。

### 1.2 核心改進

- **手動操作自動化**：IMAP/Exchange 自動讀取信件、排程處理、回覆偵測自動更新狀態
- **KMS 知識管理系統**：FTS5 全文搜尋 + 同義詞擴展 + 多來源輸入
- **資料庫正規化**：公司獨立成表、多對多關聯表、規則資料化
- **備份機制**：自動排程備份 + 完整匯出還原 + 多人 DB 合併匯入
- **跨平台**：Windows + macOS，PyInstaller 雙平台打包
- **中英雙語**：i18n 支援繁體中文與英文切換

### 1.3 設計決策摘要

| 項目 | 決策 |
|------|------|
| UI 框架 | PySide6（LGPL，Qt 官方） |
| 架構模式 | 單體式分層架構（Monolith） |
| 信件來源 | IMAP + Exchange EWS + .msg 手動匯入 |
| KMS 搜尋 | SQLite FTS5 + jieba 中文斷詞 + 同義詞擴展 |
| Mantis 整合 | REST + SOAP 雙支援 |
| 密鑰管理 | keyring 套件（Win Credential Manager / macOS Keychain） |
| 資料庫 | SQLite WAL 模式，3 人網路磁碟共用 |
| 備份 | 用戶自訂排程 + 保留天數 |
| 匯出匯入 | 完整備份還原 + 多人合併匯入 |
| 報表寄送 | 建立郵件草稿，用戶自行發送 |
| 平台 | Windows + macOS |
| 打包 | PyInstaller 雙平台 |
| 語系 | 中英雙語 i18n（JSON 語系檔） |
| 資料遷移 | 提供遷移工具，用戶可選擇是否匯入舊資料 |
| 開發方式 | TDD（Red-Green-Refactor） |

## 2. 系統架構

### 2.1 分層架構

系統採用 6 層分離架構：

```
┌─────────────────────────────────────────────────┐
│  UI 層 — PySide6 視窗介面                        │
│  (main_window, case_view, kms_view, ...)        │
├─────────────────────────────────────────────────┤
│  Core 層 — 業務邏輯                              │
│  (CaseManager, Classifier, Anonymizer, KMS...)  │
├──────────────────────┬──────────────────────────┤
│  Services 層         │  Scheduler 層             │
│  (IMAP, Exchange,    │  (EmailJob, SyncJob,     │
│   MSG, Mantis)       │   BackupJob, ReportJob)  │
├──────────────────────┴──────────────────────────┤
│  Data 層 — 資料存取                              │
│  (Repository, FTS5, Backup, Migration, Merge)   │
├─────────────────────────────────────────────────┤
│  SQLite（WAL 模式）— 網路磁碟共用                │
└─────────────────────────────────────────────────┘
  i18n 多語系（繁中 / English）貫穿所有層
```

- **UI 層**用 PySide6 的 Signal/Slot 機制與 Core 層溝通
- **Core 層**包含所有業務邏輯，不依賴 UI 或外部服務
- **Services 層**用抽象介面封裝外部整合（MailProvider、MantisClient）
- **Scheduler 層**用 QTimer 驅動排程任務，在 QThread 中執行
- **Data 層**用 Repository 模式封裝 SQLite 存取

### 2.2 專案目錄結構

```
hcp_cms/
├── src/hcp_cms/
│   ├── __init__.py
│   ├── app.py                 # 應用程式進入點
│   ├── ui/                    # UI 層
│   │   ├── main_window.py     # 主視窗（左側導覽 + 右側內容區）
│   │   ├── dashboard_view.py  # 儀表板（KPI 卡片 + 最近案件 + 提醒）
│   │   ├── case_view.py       # 案件管理頁面
│   │   ├── kms_view.py        # KMS 知識庫頁面
│   │   ├── email_view.py      # 信件處理頁面
│   │   ├── mantis_view.py     # Mantis 同步頁面
│   │   ├── report_view.py     # 報表中心頁面
│   │   ├── rules_view.py      # 規則設定頁面
│   │   ├── settings_view.py   # 系統設定頁面
│   │   └── widgets/           # 共用元件
│   ├── core/                  # 業務邏輯層
│   │   ├── case_manager.py    # 案件 CRUD + 狀態流轉
│   │   ├── classifier.py      # 多維分類引擎
│   │   ├── anonymizer.py      # PII 匿名化（16 條規則）
│   │   ├── kms_engine.py      # KMS 搜尋 + 同義詞擴展
│   │   ├── report_engine.py   # Excel 報表產生
│   │   └── thread_tracker.py  # 對話串追蹤
│   ├── services/              # 外部整合層
│   │   ├── mail/
│   │   │   ├── base.py        # MailProvider 抽象介面
│   │   │   ├── imap.py        # IMAP 實作
│   │   │   ├── exchange.py    # Exchange EWS 實作
│   │   │   └── msg_reader.py  # .msg 檔案讀取
│   │   ├── mantis/
│   │   │   ├── base.py        # MantisClient 抽象介面
│   │   │   ├── rest.py        # REST API 實作
│   │   │   └── soap.py        # SOAP API 實作
│   │   └── credential.py      # keyring 密鑰管理
│   ├── scheduler/             # 排程自動化層
│   │   ├── scheduler.py       # 排程管理員（QTimer）
│   │   ├── email_job.py       # 信件定時處理
│   │   ├── sync_job.py        # Mantis 定時同步
│   │   ├── backup_job.py      # DB 定時備份
│   │   └── report_job.py      # 報表定時產生 + 草稿
│   ├── data/                  # 資料存取層
│   │   ├── database.py        # SQLite 連線管理（WAL）
│   │   ├── models.py          # 資料模型（dataclass）
│   │   ├── repositories.py    # Repository 模式 CRUD
│   │   ├── fts.py             # FTS5 全文搜尋索引
│   │   ├── backup.py          # 備份/還原/保留策略
│   │   ├── migration.py       # 舊 DB 遷移工具
│   │   └── merge.py           # 多人 DB 合併匯入
│   └── i18n/                  # 多語系
│       ├── zh_TW.json         # 繁體中文
│       └── en.json            # English
├── tests/                     # TDD 測試
│   ├── unit/                  # 單元測試（core/data）
│   ├── integration/           # 整合測試（services）
│   └── e2e/                   # 端對端測試（UI flow）
├── resources/                 # 靜態資源（圖示、範本）
├── docs/                      # 文件
├── pyproject.toml             # 專案設定
└── build/                     # PyInstaller 打包設定
```

## 3. 資料庫設計

### 3.1 資料表概覽

SQLite WAL 模式，7 張主表 + 2 張 FTS5 虛擬表 + 1 張同義詞表。

### 3.2 cs_cases（客服案件）

| 欄位 | 型態 | 說明 |
|------|------|------|
| case_id | TEXT PK | CS-YYYY-NNN，每年流水號重置 |
| contact_method | TEXT | Email / Phone / 其他 |
| status | TEXT | 處理中 / 已回覆 / 已完成 / Closed |
| priority | TEXT | 高 / 中 / 低 |
| replied | TEXT | 是 / 否 |
| sent_time | TEXT | 信件寄出時間 |
| company_id | TEXT FK | → companies.company_id |
| contact_person | TEXT | 客戶聯絡人姓名 |
| subject | TEXT | 信件主旨 |
| system_product | TEXT | HCP / WebLogic / ERP |
| issue_type | TEXT | 問題類型（7+1 類） |
| error_type | TEXT | 錯誤類型（功能模組） |
| impact_period | TEXT | 影響期間 |
| progress | TEXT | 處理進度 |
| actual_reply | TEXT | 實際首次回覆時間 |
| notes | TEXT | 備注 |
| rd_assignee | TEXT | 指派技術人員 |
| handler | TEXT | 負責客服人員 |
| reply_count | INTEGER | 來回次數 |
| linked_case_id | TEXT FK | → cs_cases.case_id（對話串根案件） |
| source | TEXT | 來源：email / phone / manual |
| created_at | TEXT | 建立時間 |
| updated_at | TEXT | 更新時間 |

### 3.3 qa_knowledge（QA 知識庫 / KMS）

| 欄位 | 型態 | 說明 |
|------|------|------|
| qa_id | TEXT PK | QA-YYYYMM-NNN，每月流水號重置 |
| system_product | TEXT | 系統產品 |
| issue_type | TEXT | 問題類型 |
| error_type | TEXT | 錯誤類型 |
| question | TEXT | 問題描述（已匿名化） |
| answer | TEXT | 回覆內容（已匿名化） |
| solution | TEXT | 解決方案（獨立於 answer） |
| keywords | TEXT | 同義詞標籤（提升搜尋命中率） |
| has_image | TEXT | 是否有附圖 |
| doc_name | TEXT | 關聯文件名稱 |
| company_id | TEXT FK | → companies.company_id |
| source_case_id | TEXT FK | → cs_cases.case_id |
| source | TEXT | 來源：email / manual / import |
| created_by | TEXT | 建立者 |
| created_at | TEXT | 建立時間 |
| updated_at | TEXT | 更新時間 |
| notes | TEXT | 備注 |

### 3.4 mantis_tickets（Mantis 票務）

| 欄位 | 型態 | 說明 |
|------|------|------|
| ticket_id | TEXT PK | Mantis 票號 |
| created_time | TEXT | 建立時間 |
| company_id | TEXT FK | → companies.company_id |
| summary | TEXT | 票務摘要 |
| priority | TEXT | 優先等級 |
| status | TEXT | 狀態 |
| issue_type | TEXT | 問題類型 |
| module | TEXT | 功能模組 |
| handler | TEXT | 負責工程師 |
| planned_fix | TEXT | 預計修復版本/時間 |
| actual_fix | TEXT | 實際修復版本/時間 |
| progress | TEXT | 處理進度 |
| notes | TEXT | 備注 |
| synced_at | TEXT | 最後同步時間 |

### 3.5 companies（客戶公司）— 新增

| 欄位 | 型態 | 說明 |
|------|------|------|
| company_id | TEXT PK | 自動產生的唯一 ID |
| name | TEXT | 中文公司名稱 |
| domain | TEXT UNIQUE | Email 域名 |
| alias | TEXT | 別名 |
| contact_info | TEXT | 聯絡資訊 |
| created_at | TEXT | 建立時間 |

### 3.6 case_mantis（案件-Mantis 關聯）— 新增

| 欄位 | 型態 | 說明 |
|------|------|------|
| case_id | TEXT FK | → cs_cases.case_id |
| ticket_id | TEXT FK | → mantis_tickets.ticket_id |
| | PK | (case_id, ticket_id) 複合主鍵 |

### 3.7 processed_files（已處理信件）

| 欄位 | 型態 | 說明 |
|------|------|------|
| file_hash | TEXT PK | 檔案 SHA256 hash |
| filename | TEXT | 原始檔名 |
| message_id | TEXT | Email Message-ID header |
| processed_at | TEXT | 處理時間 |

### 3.8 classification_rules（分類規則）— 新增

| 欄位 | 型態 | 說明 |
|------|------|------|
| rule_id | INTEGER PK | 自動遞增 |
| rule_type | TEXT | 類型：product / issue / error / priority / broadcast |
| pattern | TEXT | 正則表達式 |
| value | TEXT | 匹配值 |
| priority | INTEGER | 排序優先級（數字小的先比對） |
| enabled | INTEGER | 是否啟用（0/1） |
| created_at | TEXT | 建立時間 |

### 3.9 FTS5 虛擬表

**qa_fts**：qa_id, question, answer, solution, keywords — 對 qa_knowledge 全文索引

**cases_fts**：case_id, subject, progress, notes — 對 cs_cases 全文索引

### 3.10 synonyms（同義詞表）— 新增

| 欄位 | 型態 | 說明 |
|------|------|------|
| id | INTEGER PK | 自動遞增 |
| word | TEXT | 詞彙 |
| synonym | TEXT | 同義詞 |
| group_name | TEXT | 詞組名稱（同組互為同義詞） |

### 3.11 與原系統的主要差異

1. **companies 獨立成表** — 原系統的公司名散在 cs_cases.company 文字欄位，現正規化為獨立表
2. **case_mantis 多對多關聯表** — 原系統用分號分隔文字存關聯，改為正規關聯表
3. **classification_rules 資料化** — 原系統規則硬寫在 rules_config.py，改存 DB 透過 GUI 管理
4. **FTS5 全文搜尋** — 新增 qa_fts / cases_fts 虛擬表支援中文全文搜尋
5. **processed_files 改用 file_hash** — 原系統用檔名防重複，改用 SHA256 hash + message_id 雙重防重
6. **KMS 擴充** — qa_knowledge 新增 solution、keywords、source 欄位

## 4. UI 介面設計

### 4.1 主視窗佈局

左側導覽固定 + 右側內容區的佈局，取代原系統的 Tab 切換。

### 4.2 頁面清單

| 頁面 | 功能 |
|------|------|
| 儀表板 | KPI 卡片（案件數、回覆率、待處理、FRT）、最近案件列表、提醒通知 |
| 案件管理 | 案件列表（篩選/排序/分頁/全文搜尋）、案件詳情、對話串檢視、手動建案、批次操作、SLA 警示 |
| KMS 知識庫 | 智慧搜尋、QA 新增/編輯、從案件建立 QA、Excel 匯入匯出、同義詞管理 |
| 信件處理 | IMAP/Exchange 連線設定、信件列表預覽、時間區間篩選、.msg 拖放匯入、處理進度、排程設定 |
| Mantis 同步 | REST/SOAP 連線設定、手動/自動同步、同步歷史、票務列表 |
| 報表中心 | 追蹤表/月報產生、APP 內預覽、排程設定、草稿管理、歷史紀錄 |
| 規則設定 | 分類規則 GUI 管理（產品/問題類型/錯誤類型/優先級/廣播）、同義詞管理 |
| 系統設定 | 使用者/語系、信件帳號、Mantis 帳號、DB 路徑、備份排程、匯出匯入合併、舊 DB 遷移 |

### 4.3 UI 設計原則

- **全域搜尋**：Ctrl+K 快捷鍵，同時搜尋案件和 KMS
- **通知中心**：SLA 逾期、新信件、同步完成等推播提醒
- **深色主題**：預設深色，可切換淺色
- **狀態列**：底部顯示 DB 連線狀態、排程狀態、最後同步時間

## 5. 信件處理與自動化

### 5.1 MailProvider 抽象介面

```
class MailProvider(ABC):
    def connect(self) -> bool
    def fetch_messages(self, since, until, folder) -> List[RawEmail]
    def fetch_sent_messages(self, since) -> List[RawEmail]
    def create_draft(self, to, subject, body, attachments) -> bool
    def disconnect(self) -> None
```

三種實作：IMAPProvider、ExchangeProvider、MSGReader。

### 5.2 處理管線（Pipeline）

7 步驟依序執行：

1. **重複檢查** — SHA256 hash + message_id 雙重防重
2. **廣播信過濾** — BROADCAST_KEYWORDS 比對，廣播信不建案
3. **欄位解析** — sender、subject、body、date、attachments
4. **自動分類** — Classifier 引擎依 classification_rules 表比對
5. **對話串比對** — ThreadTracker 識別根案件，設定 linked_case_id
6. **建案/更新** — CaseManager 建立新案件或更新既有案件
7. **QA 抽取** — 偵測詢問句型，匿名化後建立 KMS 條目（待審核）

### 5.3 回覆偵測自動更新

- **偵測我方回覆**：掃描已寄送信件夾，比對 In-Reply-To / References header 或 subject + 收件人 domain
- **自動更新狀態**：案件狀態 → 已回覆，記錄 actual_reply，replied = 是
- **偵測客戶再次來信**：已回覆案件有新信 → 重開為「處理中」，reply_count + 1

### 5.4 三種操作模式

- **全自動**：排程自動抓取並處理所有新信
- **半自動**：抓取後列出清單，用戶勾選後匯入
- **手動**：拖放 .msg 或選擇檔案匯入

### 5.5 排程引擎

基於 QTimer + QThread，4 種排程任務：

| 排程 | 預設間隔 | 說明 |
|------|---------|------|
| 信件自動檢查 | 每 15 分鐘 | 自動抓取新信並處理 |
| Mantis 自動同步 | 每 1 小時 | 批次同步所有未結案票務 |
| 報表自動產生 | 用戶自訂 | 產生 Excel → 建立郵件草稿 |
| DB 自動備份 | 用戶自訂 | 備份 DB → 清理過期備份 |

## 6. KMS 知識管理系統

### 6.1 搜尋管線

1. **使用者輸入** — 自然語言查詢
2. **jieba 中文斷詞** — 將查詢拆解為詞彙
3. **同義詞擴展** — 查詢 synonyms 表，擴展為同義詞群組
4. **FTS5 查詢** — 組合 MATCH 語句，OR 連接所有擴展詞
5. **BM25 排序 + 高亮** — 依相關度排序，關鍵字高亮顯示

### 6.2 四種輸入來源

| 來源 | source 值 | 說明 |
|------|----------|------|
| 信件自動抽取 | email | 偵測詢問句型自動建立，標記「待審核」需人工確認 |
| 人工手動輸入 | manual | KMS 頁面新增，支援富文字 |
| Excel 匯入 | import | 批次匯入，匯入前預覽 + 驗證 + 重複偵測 |
| Excel 匯出 | — | 全部或篩選後匯出，格式與匯入範本一致 |

### 6.3 同義詞管理

- 內建 HCP 領域預設詞庫（薪水↔薪資↔工資、請假↔休假↔假單 等）
- 用戶可在規則設定頁面自行擴充
- 搜尋時自動擴展查詢詞

### 6.4 中文斷詞

- 使用 jieba 套件，純 Python，離線可用，跨平台
- 支援自訂詞庫（HCP 專有名詞：法院扣薪、留停復職 等）

## 7. 報表引擎

### 7.1 報表類型

**追蹤表 Excel：**
1. 客戶索引（超連結跳轉）
2. 問題追蹤總表（26 欄完整資料）
3. QA 知識庫（11 欄）
4. 各客戶分頁（按案件數排序）
5. 客制需求（獨立頁籤）

**月報 Excel：**
1. 月報摘要（KPI + 統計）
2. 案件明細
3. 各客戶頁籤
4. 未結案清單（老化天數）
5. Mantis 進度

### 7.2 新增能力

- **APP 內預覽**：QTableView 顯示報表資料，確認後再下載
- **排程自動產生**：每月 N 號 / 每週 N 自動產生
- **草稿管理**：產生後自動建立郵件草稿，收件人清單在設定中維護
- **Excel 樣式**：延續原系統樣式規範（微軟正黑體、深藍標題、交替行色），openpyxl 跨平台產生

### 7.3 月報 KPI 定義

| KPI | 計算方式 |
|-----|---------|
| 案件總數 | 查詢期間所有案件數 |
| 已回覆 | replied = 是 的案件數 |
| 待處理 | 狀態非已完成/Closed 的案件數 |
| 回覆率 | 已回覆 ÷ 總數 × 100% |
| 平均 FRT | avg(actual_reply - sent_time)，排除 > 720h |

## 8. 備份機制

### 8.1 自動備份

- **排程**：用戶自訂頻率（每日/每週/自訂）與時間
- **保留策略**：用戶設定保留天數，超過自動清理
- **實作**：使用 sqlite3 backup API，備份中不阻塞讀寫
- **檔案命名**：`cs_tracker_YYYYMMDD_HHMMSS.db`
- **儲存位置**：
  - Windows: `%APPDATA%/HCP_CMS/backups/`
  - macOS: `~/Library/Application Support/HCP_CMS/backups/`

### 8.2 完整匯出/還原

- **匯出**：.db 檔或 .zip（DB + 設定檔），含 schema 版本標記
- **還原**：選擇檔案 → 驗證 schema 相容性 → 自動備份當前 DB → 還原
- **使用情境**：換電腦遷移、災難復原

### 8.3 合併匯入

- **來源**：另一台電腦的 .db 或 .zip 備份
- **比對**：以 case_id / qa_id 為主鍵
- **衝突處理**：保留本機（略過）/ 保留匯入（覆蓋）/ 逐筆確認（顯示差異）
- **預覽**：合併前顯示新增 N 筆、衝突 N 筆、略過 N 筆
- **安全**：合併前自動備份，合併記錄寫入 log

### 8.4 舊 DB 遷移工具

1. 選擇舊版 cs_tracker.db
2. 自動偵測舊版 schema
3. 預覽可遷移資料筆數
4. 資料轉換（company 文字 → company_id FK、related_cs_case 文字 → case_mantis 關聯表）
5. 遷移前自動備份
6. 執行遷移並顯示結果報告

## 9. 技術規格

### 9.1 核心依賴

| 套件 | 用途 |
|------|------|
| PySide6 | UI 框架 |
| sqlite3 | 資料庫（Python 內建） |
| openpyxl | Excel 讀寫 |
| extract-msg | .msg 信件解析 |
| exchangelib | Exchange EWS 連線 |
| requests | Mantis REST/SOAP API |
| keyring | 跨平台密鑰管理 |
| jieba | 中文斷詞 |

### 9.2 開發依賴

| 套件 | 用途 |
|------|------|
| pytest | 測試框架 |
| pytest-qt | PySide6 UI 測試 |
| pytest-cov | 測試覆蓋率 |
| pytest-mock | Mock 工具 |
| ruff | Linter + Formatter |
| mypy | 靜態型態檢查 |
| PyInstaller | 打包為 exe / .app |
| pre-commit | Git hook（ruff + mypy） |

### 9.3 Python 版本

Python >= 3.10（型態提示 `str | None` 語法）

### 9.4 i18n 多語系

- JSON 語系檔：`i18n/zh_TW.json` + `i18n/en.json`
- 格式：`{"dashboard.title": "儀表板", ...}`
- `tr("key")` 函式取得翻譯文字
- 切換語系後 Signal 通知所有 UI 即時更新
- 報表語系跟隨 APP 設定

## 10. 測試策略

### 10.1 TDD 開發循環

Red（寫失敗的測試）→ Green（寫最少程式碼通過）→ Refactor（重構，保持測試通過）→ 重複

開發順序：data → core → services → scheduler → ui

### 10.2 測試金字塔

**單元測試（大量）：**
- core/：Classifier、Anonymizer、CaseManager、KMSEngine、ThreadTracker、ReportEngine
- data/：Repository CRUD、FTS 索引/查詢、Backup 備份/清理、Merge 衝突偵測

**整合測試（中量）：**
- 信件處理管線：模擬 .msg → 完整管線 → DB 驗證
- KMS 搜尋完整流程：建立 QA → 建立索引 → 搜尋驗證
- 報表產生：模擬資料 → Excel 產生 → 驗證內容
- 備份/還原/合併：備份 → 修改 → 還原 → 驗證

**E2E 測試（少量，10-15 個場景）：**
- pytest-qt + QTest 模擬使用者操作
- 關鍵流程：匯入信件→建案→檢視、搜尋 KMS→結果、產生報表→下載

## 11. 打包與部署

### 11.1 PyInstaller 打包

- **Windows**：HCP_CMS.exe（含 jieba 詞庫、i18n JSON、圖示）
- **macOS**：HCP_CMS.app（應用程式包，Info.plist 設定）
- **.spec 檔**設定 hidden imports 和 data files

### 11.2 CI/CD（可選）

GitHub Actions 雙平台自動打包，Release 時自動產出安裝檔。

## 12. 實作注意事項

### 12.1 SQLite WAL 並發策略

SQLite 透過網路磁碟共用存在已知限制，需特別處理：
- 設定 `busy_timeout`（建議 5000ms），寫入鎖定時自動重試
- 應用層加入重試機制（最多 3 次，指數退避）
- 寫入失敗時顯示明確錯誤訊息（「資料庫忙碌，請稍後重試」）

### 12.2 FTS5 中文斷詞整合

jieba 斷詞結果以空格分隔後存入 FTS5（pre-tokenized content insertion），搜尋時同樣先斷詞再組合 MATCH 語句。不使用自訂 tokenizer，降低複雜度。

### 12.3 Schema 版本管理

新增 `db_meta` 表記錄 schema 版本號：

| 欄位 | 型態 | 說明 |
|------|------|------|
| key | TEXT PK | 設定鍵（如 "schema_version"） |
| value | TEXT | 設定值（如 "2.0.0"） |

未來 schema 變更時透過版本號判斷是否需要遷移。匯出/匯入時驗證版本相容性。
