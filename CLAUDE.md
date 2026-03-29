# HCP 客服管理系統 (HCP CMS)

PySide6 + SQLite 桌面應用，管理客服信件、案件追蹤、知識庫搜尋。

<law>
**Law 1: 繁體中文** — 一律使用繁體中文回覆。所有對話、註解、commit 訊息、文件皆使用繁體中文。

**Law 2: 6 層架構分離** — UI → Core → Services / Scheduler → Data → SQLite。不可跨層直接存取。UI 層透過 Signal/Slot 與 Core 層溝通。Data 層透過 Repository 模式封裝 SQLite 存取。

**Law 3: TDD 開發** — 先寫測試再寫實作。開發順序：data → core → services → scheduler → ui。

**Law 4: 搜尋管線** — 搜尋功能必須經過完整管線：jieba 斷詞 → 同義詞擴展 → FTS5 MATCH。不可直接 LIKE 查詢。

**Law 5: 信件處理** — 新增信件來源時必須實作 MailProvider ABC。信件處理管線 7 步不可跳過或重排：①重複檢查 →②廣播信過濾 →③欄位解析 →④自動分類 →⑤對話串比對 →⑥建案/更新 →⑦QA 抽取。

</law>

# 常用指令

```bash
.venv/Scripts/python.exe -m pytest tests/ -v                    # 全部測試
.venv/Scripts/python.exe -m pytest tests/unit/test_xxx.py -v    # 單一檔案
.venv/Scripts/python.exe -m pytest tests/unit/test_xxx.py::TestClass::test_method -v
.venv/Scripts/ruff.exe check src/ tests/                        # Lint
.venv/Scripts/ruff.exe format src/ tests/                       # 格式化
.venv/Scripts/python.exe -m hcp_cms                             # 執行
```

- **Python**: 3.14.3 | **PySide6**: 6.10.2 | **SQLite**: 內建 FTS5

# 專案結構

```
src/hcp_cms/
├── ui/          # UI 層 — PySide6 (Signal/Slot)
├── core/        # Core 層 — 業務邏輯 (XxxManager / XxxEngine)
├── services/    # Services 層 — MailProvider / MantisClient ABC
├── scheduler/   # Scheduler 層 — threading.Timer 背景排程
├── data/        # Data 層 — Repository + FTS5 + Migration
└── i18n/        # 國際化 JSON 語系檔

tests/
├── unit/        # 單元測試
└── integration/ # 整合測試
```

# 跨層架構

## 依賴注入：共用 sqlite3.Connection

`app.py::main()` 建立 `DatabaseManager`，取得單一 `conn`，向下傳遞給 `MainWindow` → 各 View → 各 Core Manager → 各 Repository。所有層共用同一條連線。

```
app.main()
  └─ DatabaseManager(db_path).initialize()
       ├─ PRAGMA: busy_timeout=5000, journal_mode=WAL, foreign_keys=ON
       ├─ executescript(_SCHEMA_SQL) — 12 表 + 2 FTS5 虛擬表
       └─ _apply_pending_migrations() — 冪等 ALTER TABLE
  └─ MainWindow(conn, db_dir)
       └─ 各 View(conn) → Core Manager(conn) → Repository(conn)
```

## UI → Core → Data 呼叫鏈

UI View 在方法內建立 Core Manager 實例（非持有），Core Manager 在 `__init__` 內建立 Repository 實例：

```python
# UI 層（CaseView）
mgr = CaseManager(self._conn)
case = mgr.create_case(subject=..., body=...)

# Core 層（CaseManager.__init__）
self._repo = CaseRepository(conn)
self._fts = FTSManager(conn)
self._classifier = Classifier(conn)
```

## 執行緒安全

- `check_same_thread=False` — UI 主線程與 Scheduler 背景線程共用連線
- WAL 模式 + `busy_timeout=5000ms` 處理並發寫入
- Scheduler 使用 `threading.Timer` 遞迴排程，不可在背景線程直接操作 UI

## 案件狀態機

有效狀態：`"處理中"` → `"已回覆"` → `"已完成"`。客戶再次回信時重新開啟（→ `"處理中"`）。`ThreadTracker` 透過 subject / message_id / in_reply_to 串接信件串。

## 自訂欄位系統

`cs_cases` 表內 `cx_1` ~ `cx_N` 欄位 + `custom_columns` 表存後設資料。`Case.extra_fields: dict` 在執行期對映動態欄位值。
