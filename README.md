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

| 項目 | 需求 |
|------|------|
| Python | >= 3.10 |
| 作業系統 | Windows 10/11, macOS 12+ |
| 磁碟空間 | ~200MB（含依賴套件） |

## 快速開始

### 1. 安裝

```bash
# Clone 專案
git clone https://github.com/KerryHuang/HCP_CMS.git
cd HCP_CMS

# 安裝依賴（含開發工具）
pip install -e ".[dev]"
```

### 2. 啟動應用程式

```bash
py -m hcp_cms.app
```

### 3. 執行測試

```bash
# 全部測試
py -m pytest -v

# 含覆蓋率
py -m pytest --cov=hcp_cms --cov-report=term-missing

# 僅單元測試
py -m pytest tests/unit/ -v

# 僅整合測試
py -m pytest tests/integration/ -v
```

### 4. 程式碼品質

```bash
# Linter
py -m ruff check src/ tests/

# 型態檢查
py -m mypy src/hcp_cms/ --ignore-missing-imports
```

## 打包為執行檔

```bash
# Windows → HCP_CMS.exe
pyinstaller build/hcp_cms.spec

# macOS → HCP_CMS.app
pyinstaller build/hcp_cms.spec
```

產出位於 `dist/` 目錄。

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
│   ├── settings_view.py    #   系統設定
│   └── widgets/            #   共用元件
├── core/                   # 業務邏輯層
│   ├── classifier.py       #   多維分類引擎
│   ├── anonymizer.py       #   PII 匿名化（16 條規則）
│   ├── case_manager.py     #   案件管理 + 狀態流轉
│   ├── kms_engine.py       #   KMS 搜尋 + CRUD + Excel 匯入匯出
│   ├── thread_tracker.py   #   對話串追蹤
│   └── report_engine.py    #   Excel 報表產生
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
│   ├── models.py           #   資料模型（8 個 dataclass）
│   ├── repositories.py     #   Repository CRUD（8 個 Repository）
│   ├── fts.py              #   FTS5 全文搜尋
│   ├── backup.py           #   備份/還原
│   ├── merge.py            #   多人 DB 合併匯入
│   └── migration.py        #   舊 DB 遷移工具
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
| synonyms | 同義詞（搜尋擴展用） |
| db_meta | Schema 版本管理 |
| qa_fts / cases_fts | FTS5 全文搜尋虛擬表 |

## 技術棧

| 類別 | 套件 |
|------|------|
| UI | PySide6 |
| 資料庫 | SQLite3（WAL 模式） |
| Excel | openpyxl |
| 信件 | extract-msg, imaplib, exchangelib |
| Mantis | requests（REST/SOAP） |
| 密鑰 | keyring |
| 中文斷詞 | jieba |
| 測試 | pytest, pytest-qt, pytest-cov, pytest-mock |
| 品質 | ruff, mypy |
| 打包 | PyInstaller |

## 授權

內部使用專案。

## 開發團隊

- **Jill** — 客服工程師 / 系統開發
