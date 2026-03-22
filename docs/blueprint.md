# HCP CMS 專案藍圖

## 技術棧

- **語言**：Python 3.12+
- **GUI 框架**：PySide6 6.10.2
- **資料庫**：SQLite3（內建）+ FTS5
- **中文斷詞**：jieba 0.42.1
- **套件管理**：pip + pyproject.toml
- **打包**：PyInstaller

## 核心依賴

```
PySide6 >= 6.10.0
openpyxl >= 3.1.0
extract-msg >= 0.50.0
exchangelib >= 5.0.0
requests >= 2.31.0
keyring >= 25.0.0
jieba >= 0.42.1
```

## 開發依賴

```
pytest >= 8.0.0
pytest-qt >= 4.4.0
ruff >= 0.9.0
mypy >= 1.13.0
PyInstaller >= 6.0.0
pre-commit >= 4.0.0
```

## 專案結構

```
D:\cms\
├── pyproject.toml              # 專案配置（含 ruff/mypy/pytest）
├── CLAUDE.md                   # Claude Code 規則
├── README.md
├── docs/
│   └── blueprint.md
├── src/
│   └── hcp_cms/
│       ├── __init__.py
│       ├── __main__.py         # 進入點
│       ├── app.py              # QApplication 初始化
│       │
│       ├── ui/                 # UI 層 — PySide6 介面
│       │   ├── __init__.py
│       │   ├── main_window.py  # 主視窗（左側導覽 + 右側內容區）
│       │   ├── pages/          # 7 個主頁面
│       │   │   ├── __init__.py
│       │   │   ├── dashboard.py
│       │   │   ├── cases.py
│       │   │   ├── kms.py
│       │   │   ├── mail.py
│       │   │   ├── mantis.py
│       │   │   ├── reports.py
│       │   │   └── settings.py
│       │   ├── widgets/        # 共用元件
│       │   │   ├── __init__.py
│       │   │   ├── global_search.py   # Ctrl+K 全域搜尋
│       │   │   ├── notification.py    # 通知中心
│       │   │   └── kpi_card.py
│       │   └── resources/      # 圖示、樣式
│       │
│       ├── core/               # Core 層 — 業務邏輯
│       │   ├── __init__.py
│       │   ├── case_manager.py
│       │   ├── kms_manager.py
│       │   ├── mail_processor.py      # 7 步處理管線
│       │   ├── report_generator.py
│       │   ├── backup_manager.py
│       │   ├── reply_detector.py      # 回覆偵測
│       │   └── search_engine.py       # jieba + 同義詞 + FTS5
│       │
│       ├── services/           # Services 層 — 外部服務介面
│       │   ├── __init__.py
│       │   ├── mail_provider.py       # MailProvider ABC
│       │   ├── imap_provider.py
│       │   ├── exchange_provider.py
│       │   ├── msg_provider.py
│       │   ├── mantis_client.py       # MantisClient ABC
│       │   └── mantis_rest.py
│       │
│       ├── scheduler/          # Scheduler 層 — 排程
│       │   ├── __init__.py
│       │   ├── scheduler.py           # QTimer + QThread 排程引擎
│       │   ├── tasks/
│       │   │   ├── __init__.py
│       │   │   ├── mail_task.py
│       │   │   ├── mantis_task.py
│       │   │   ├── report_task.py
│       │   │   └── backup_task.py
│       │   └── workers.py             # QThread workers
│       │
│       ├── data/               # Data 層 — 資料存取
│       │   ├── __init__.py
│       │   ├── database.py            # 連線管理 + 遷移
│       │   ├── repositories/
│       │   │   ├── __init__.py
│       │   │   ├── case_repo.py
│       │   │   ├── kms_repo.py
│       │   │   ├── mantis_repo.py
│       │   │   ├── company_repo.py
│       │   │   ├── rule_repo.py
│       │   │   └── file_repo.py
│       │   ├── fts/                   # FTS5 全文搜尋
│       │   │   ├── __init__.py
│       │   │   ├── fts_manager.py
│       │   │   └── synonym_manager.py
│       │   └── migration.py           # 舊 DB 遷移
│       │
│       └── i18n/               # 國際化
│           ├── __init__.py
│           ├── zh_TW.json
│           └── en_US.json
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # 共用 fixtures
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── data/               # Repository 單元測試
│   │   └── core/               # 業務邏輯單元測試
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_mail_pipeline.py
│   │   ├── test_kms_search.py
│   │   ├── test_report_gen.py
│   │   └── test_backup.py
│   └── e2e/
│       ├── __init__.py
│       └── test_scenarios.py   # pytest-qt E2E
│
├── scripts/
│   └── build.py                # PyInstaller 打包腳本
│
└── resources/
    ├── synonyms_default.json   # HCP 領域預設同義詞庫
    └── jieba_userdict.txt      # jieba 自訂詞庫（HCP 專有名詞）
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
| qa_knowledge | QA 知識庫 |
| mantis_tickets | Mantis 工單 |
| companies | 公司（正規化） |
| case_mantis | 案件-Mantis 多對多關聯 |
| processed_files | 已處理檔案（SHA256 去重） |
| rules | 分類規則 |

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
