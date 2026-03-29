# HCP CMS — 客服自動化管理系統

HCP Customer Service Management System — 跨平台桌面應用程式，用於自動化客服案件管理、知識庫搜尋、報表產生與 Mantis 票務同步。

## 功能特色

- **信件自動處理** — 支援 IMAP、Exchange、.msg 手動匯入，自動分類建案
- **案件管理** — 完整案件生命週期（處理中 → 已回覆 → 已完成），對話串追蹤
- **KMS 知識庫** — FTS5 全文搜尋 + jieba 中文斷詞 + 同義詞擴展
- **報表產生** — 追蹤表、月報 Excel 自動產生（openpyxl）
- **Mantis 整合** — REST + SOAP 雙協定同步票務
- **排程自動化** — 信件檢查、Mantis 同步、備份、報表排程
- **資料庫備份** — 自動備份 + 匯出還原 + 多人 DB 合併匯入
- **跨平台** — Windows + macOS（PySide6 + PyInstaller）
- **中英雙語** — i18n 支援繁體中文與 English 切換

## 系統需求

| 項目 | Windows | macOS |
|------|---------|-------|
| 作業系統 | Windows 10 1709+ | macOS 12+ |
| 磁碟空間 | ~200MB（含依賴） | ~200MB（含依賴） |
| 套件管理器 | winget（內建） | [Homebrew](https://brew.sh) |

## 安裝（一般使用者）

1. 從 [Releases](https://github.com/KerryHuang/HCP_CMS/releases) 頁面下載 `HCP_CMS_Setup_x.x.x.exe`
2. 執行安裝精靈，依提示完成安裝
3. 從桌面捷徑或開始選單啟動「HCP 客服管理系統」

> 安裝包已包含所有執行時依賴，不需要額外安裝 Python。

## 安裝（開發者）

一鍵安裝腳本會自動檢查並安裝 Git、Python，建立虛擬環境，安裝所有依賴。

### Windows

在專案根目錄開啟 PowerShell，執行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-dev.ps1
```

### macOS

前置條件：先安裝 [Homebrew](https://brew.sh)。

```bash
chmod +x scripts/setup-dev.sh && ./scripts/setup-dev.sh
```

### 腳本會自動完成

- 檢查並安裝 Git（winget / brew）
- 檢查並安裝 Python >= 3.10（winget / brew）
- 建立 `.venv` 虛擬環境
- 安裝所有依賴套件（含開發工具）
- 驗證安裝結果（PySide6 / pytest / ruff）

### 手動安裝

如果你偏好手動安裝，或一鍵腳本不適用於你的環境：

```bash
git clone https://github.com/KerryHuang/HCP_CMS.git
cd HCP_CMS
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS:   source .venv/bin/activate
pip install -e ".[dev]"
```

## 啟動與開發

```bash
# 啟動應用程式
.venv/Scripts/python -m hcp_cms          # Windows
.venv/bin/python -m hcp_cms              # macOS

# 執行測試
.venv/Scripts/python -m pytest tests/ -v           # Windows
.venv/bin/python -m pytest tests/ -v               # macOS

# 含覆蓋率
.venv/Scripts/python -m pytest --cov=hcp_cms --cov-report=term-missing  # Windows
.venv/bin/python -m pytest --cov=hcp_cms --cov-report=term-missing      # macOS

# 程式碼品質
.venv/Scripts/ruff check src/ tests/               # Windows
.venv/bin/ruff check src/ tests/                    # macOS

# 型態檢查
.venv/Scripts/python -m mypy src/hcp_cms/ --ignore-missing-imports  # Windows
.venv/bin/python -m mypy src/hcp_cms/ --ignore-missing-imports      # macOS
```

## 打包與發佈

```bash
# 打包為執行檔（PyInstaller）
python scripts/build.py
# 產出位於 dist/HCP_CMS/，主程式為 HCP_CMS.exe

# 產生安裝精靈（需安裝 Inno Setup 6）
iscc scripts/installer.iss
# 產出位於 dist/HCP_CMS_Setup_x.x.x.exe
```

## 專案架構

```
src/hcp_cms/
├── app.py                  # 應用程式進入點
├── ui/                     # UI 層（PySide6）
│   ├── main_window.py      #   主視窗（側邊導覽 + 深色主題）
│   ├── dashboard_view.py   #   儀表板（KPI 卡片）
│   ├── case_view.py        #   案件管理
│   ├── kms_view.py         #   KMS 知識庫
│   ├── email_view.py       #   信件處理
│   ├── mantis_view.py      #   Mantis 同步
│   ├── report_view.py      #   報表中心
│   ├── rules_view.py       #   規則設定
│   ├── case_detail_dialog.py #  案件詳情對話框
│   ├── csv_import_dialog.py #  CSV 匯入精靈
│   ├── delete_cases_dialog.py # 批次刪除案件對話框
│   ├── sent_mail_tab.py    #   寄件清單
│   ├── settings_view.py    #   系統設定
│   └── widgets/            #   共用元件
├── core/                   # 業務邏輯層
│   ├── anonymizer.py       #   PII 匿名化（16 條規則）
│   ├── case_detail_manager.py #  案件詳情管理
│   ├── case_manager.py     #   案件管理 + 狀態流轉
│   ├── classifier.py       #   多維分類引擎
│   ├── csv_import_engine.py #  CSV 匯入引擎
│   ├── custom_column_manager.py # 自定義欄位管理
│   ├── kms_engine.py       #   KMS 搜尋 + CRUD + Excel 匯入匯出
│   ├── report_engine.py    #   Excel 報表產生
│   ├── report_writer.py    #   報表 Excel 寫入
│   ├── sent_mail_manager.py #  寄件清單管理
│   └── thread_tracker.py   #   對話串追蹤
├── services/               # 外部整合層
│   ├── mail/               #   信件提供者（IMAP/Exchange/MSG）
│   ├── mantis/             #   Mantis 客戶端（REST/SOAP）
│   └── credential.py       #   密鑰管理（keyring）
├── scheduler/              # 排程自動化層
│   ├── scheduler.py        #   排程管理員
│   ├── email_job.py        #   信件定時處理
│   ├── sync_job.py         #   Mantis 定時同步
│   ├── backup_job.py       #   DB 定時備份
│   └── report_job.py       #   報表定時產生
├── data/                   # 資料存取層
│   ├── database.py         #   SQLite 連線管理（WAL 模式）
│   ├── models.py           #   資料模型（10 個 dataclass）
│   ├── repositories.py     #   Repository CRUD（10 個 Repository）
│   ├── fts.py              #   FTS5 全文搜尋
│   ├── backup.py           #   備份/還原
│   ├── merge.py            #   多人 DB 合併匯入
│   ├── migration.py        #   舊 DB 遷移工具
│   └── seed_rules.py       #   預設分類規則種子資料
└── i18n/                   # 多語系
    ├── translator.py       #   翻譯引擎
    ├── zh_TW.json          #   繁體中文
    └── en.json             #   English
```

## 資料庫

SQLite WAL 模式，支援 3 人透過網路磁碟共用。

| 資料表 | 說明 |
|--------|------|
| cs_cases | 客服案件（22 欄） |
| qa_knowledge | QA 知識庫（17 欄） |
| mantis_tickets | Mantis 票務（14 欄） |
| companies | 客戶公司 |
| case_mantis | 案件-Mantis 多對多關聯 |
| processed_files | 已處理信件（SHA256 防重複） |
| classification_rules | 分類規則（DB 驅動） |
| case_logs | 案件操作日誌 |
| custom_columns | 自定義欄位定義 |
| synonyms | 同義詞（搜尋擴展用） |
| db_meta | Schema 版本管理 |
| qa_fts / cases_fts | FTS5 全文搜尋虛擬表 |

## 技術棧

| 類別 | 套件 |
|------|------|
| UI | PySide6 |
| 資料庫 | SQLite3（WAL 模式） |
| Excel | openpyxl |
| Word | python-docx |
| 信件 | extract-msg, imaplib, exchangelib |
| Mantis | requests（REST/SOAP） |
| 密鑰 | keyring |
| 中文斷詞 | jieba |
| 測試 | pytest, pytest-qt, pytest-cov, pytest-mock |
| 品質 | ruff, mypy |
| 打包 | PyInstaller |

## Claude Code 代理系統

本專案內建 Claude Code 代理系統（`.claude/`），並搭配 **superpowers plugin** 進行規劃與實作。

### Superpowers Plugin

本專案的功能規劃與實作流程由 [superpowers](https://github.com/anthropics/superpowers) plugin 驅動，提供結構化的開發工作流：

| 工作流 | 用途 |
|--------|------|
| **brainstorming** | 功能開發前探索需求、釐清意圖與設計方向 |
| **writing-plans** | 產出多步驟實作計畫，含 POC 風險標記 |
| **executing-plans** | 依計畫逐步執行，含審查檢查點 |
| **test-driven-development** | TDD 流程：先寫測試再寫實作 |
| **systematic-debugging** | 結構化除錯，先診斷再修復 |
| **dispatching-parallel-agents** | 獨立任務平行派發 subagent 執行 |
| **subagent-driven-development** | 計畫內獨立 task 平行實作 |
| **requesting-code-review** | 完成實作後請求程式碼審查 |
| **verification-before-completion** | 宣告完成前強制驗證 |
| **finishing-a-development-branch** | 分支完成後引導合併/PR/清理 |

典型開發流程：`brainstorming → writing-plans → executing-plans（內含 TDD + debugging）→ code-review → verification → finish`

### 專案自訂技能

內建 11 個開發技能，輸入 `/指令` 即可使用：

| 指令 | 用途 |
|------|------|
| `/commit` | 提交變更（繁體中文訊息） |
| `/push` `/pull` | 推送 / 拉取 |
| `/reflect` | Session 回顧 |
| `/test` | 執行測試 |
| `/run` | 啟動應用程式 |
| `/build` | 打包執行檔 |
| `/poc` | POC 驗證 |
| `/release` | 發行新版本 |
| `/publish` | 本地發行驗證 |
| `/update-docs` | 更新專案文件 |

詳見 `.claude/skills/README.md`。

### 其他代理元件

- **Rules** — 各層程式碼慣例自動注入（data / core / ui / services / tests）
- **Hooks** — Write/Edit 後自動執行 ruff format + lint 檢查

## 授權

內部使用專案。

## 開發團隊

- **Jill** — 客服工程師 / 系統開發
