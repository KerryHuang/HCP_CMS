# HCP CMS 專案藍圖

## 技術棧

- **語言**：Python >= 3.10（目前使用 3.14.3）
- **GUI 框架**：PySide6 6.10.2
- **資料庫**：SQLite3（內建）+ FTS5
- **中文斷詞**：jieba 0.42.1
- **套件管理**：pip + pyproject.toml
- **打包**：PyInstaller

## 核心依賴

```
PySide6 >= 6.6
openpyxl >= 3.1
extract-msg >= 0.48
exchangelib >= 5.1
requests >= 2.31
keyring >= 25.0
jieba >= 0.42
```

## 開發依賴

```
pytest >= 8.0
pytest-qt >= 4.3
pytest-cov >= 4.1
pytest-mock >= 3.12
ruff >= 0.3
mypy >= 1.8
PyInstaller >= 6.3
pre-commit >= 3.6
```

## 專案結構

```
D:\cms\
├── pyproject.toml              # 專案配置（含 ruff/mypy/pytest）
├── CLAUDE.md                   # Claude Code 開發法則
├── README.md
├── docs/
│   ├── blueprint.md            # 本文件
│   ├── operation-manual.md     # 操作手冊
│   └── getting-started-checklist.md  # 新手教學
├── .claude/
│   ├── settings.json           # Hook 設定
│   ├── rules/                  # 各層程式碼慣例
│   ├── hooks/                  # ruff 自動檢查
│   └── skills/                 # 9 個開發技能
├── src/
│   └── hcp_cms/
│       ├── __init__.py
│       ├── app.py              # QApplication 進入點
│       │
│       ├── ui/                 # UI 層 — PySide6 介面
│       │   ├── main_window.py  #   主視窗（左側導覽 + 深色主題）
│       │   ├── dashboard_view.py
│       │   ├── case_view.py
│       │   ├── kms_view.py
│       │   ├── email_view.py
│       │   ├── mantis_view.py
│       │   ├── report_view.py
│       │   ├── rules_view.py
│       │   ├── settings_view.py
│       │   └── widgets/        #   共用元件（status_bar）
│       │
│       ├── core/               # Core 層 — 業務邏輯
│       │   ├── case_manager.py #   案件管理 + 狀態流轉
│       │   ├── kms_engine.py   #   KMS 搜尋 + CRUD + Excel
│       │   ├── classifier.py   #   多維分類引擎
│       │   ├── anonymizer.py   #   PII 匿名化
│       │   ├── thread_tracker.py #  對話串追蹤
│       │   └── report_engine.py #  Excel 報表產生
│       │
│       ├── services/           # Services 層 — 外部服務介面
│       │   ├── credential.py   #   密鑰管理（keyring）
│       │   ├── mail/           #   MailProvider ABC + IMAP/Exchange/MSG
│       │   └── mantis/         #   MantisClient ABC + REST/SOAP
│       │
│       ├── scheduler/          # Scheduler 層 — 排程
│       │   ├── scheduler.py    #   排程管理員
│       │   ├── email_job.py    #   信件定時處理
│       │   ├── sync_job.py     #   Mantis 定時同步
│       │   ├── backup_job.py   #   DB 定時備份
│       │   └── report_job.py   #   報表定時產生
│       │
│       ├── data/               # Data 層 — 資料存取
│       │   ├── database.py     #   SQLite 連線管理（WAL 模式）
│       │   ├── models.py       #   資料模型（dataclass）
│       │   ├── repositories.py #   Repository CRUD
│       │   ├── fts.py          #   FTS5 全文搜尋 + jieba
│       │   ├── backup.py       #   備份/還原
│       │   ├── merge.py        #   多人 DB 合併匯入
│       │   └── migration.py    #   舊 DB 遷移工具
│       │
│       └── i18n/               # 國際化
│           ├── translator.py
│           ├── zh_TW.json
│           └── en.json
│
├── tests/
│   ├── conftest.py             # 共用 fixtures
│   ├── unit/                   # 單元測試（test_rules_csv 等）
│   └── integration/            # 整合測試
│
└── scripts/
    └── build.py                # PyInstaller 打包腳本
```

## 架構（6 層分離）

```
UI（PySide6 Signal/Slot）
  ↕
Core（業務邏輯）
  ↕
Services（MailProvider/MantisClient ABC）  |  Scheduler（QTimer + QThread）
  ↕                                        ↕
Data（Repository 模式 + FTS5）
  ↕
SQLite
```

## 資料庫 Schema

### 主表（7 張）
| 表名 | 用途 |
|------|------|
| cs_cases | 客服案件 |
| qa_knowledge | QA 知識庫（含 status 欄位：待審核 / 已完成） |
| mantis_tickets | Mantis 工單 |
| companies | 公司（正規化） |
| case_mantis | 案件-Mantis 多對多關聯 |
| processed_files | 已處理檔案（SHA256 去重） |
| classification_rules | 分類規則（DB 驅動，支援 handler/progress） |

### 虛擬表（2 張 FTS5 + 1 張同義詞）
| 表名 | 用途 |
|------|------|
| cases_fts | 案件全文搜尋 |
| qa_fts | QA 知識庫全文搜尋 |
| synonyms | 同義詞擴展 |

## 初始化指令

```bash
# 建立虛擬環境
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS

# 安裝依賴
pip install -e ".[dev]"

# 驗證安裝
python -m pytest --co
python -m hcp_cms
```

## 開發順序（TDD）

1. **data/** — Repository + FTS5 + 遷移
2. **core/** — 業務邏輯（信件管線、KMS 搜尋、報表、備份）
3. **services/** — MailProvider/MantisClient 實作
4. **scheduler/** — QTimer + QThread 排程
5. **ui/** — PySide6 介面

## Agent 系統規劃

- **CLAUDE.md**：繁體中文 law、6 層架構規則、TDD 開發規範
- **Rules**：Python 程式碼風格、PySide6 Signal/Slot 規範
- **Hooks**：ruff 自動格式化（PostToolUse）

## 打包部署

- Windows：`PyInstaller → HCP_CMS.exe`
- macOS：`PyInstaller → HCP_CMS.app`
- 可選：GitHub Actions CI/CD
