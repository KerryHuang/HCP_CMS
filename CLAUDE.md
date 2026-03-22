<law>
一律使用繁體中文回覆。所有對話、註解、commit 訊息、文件皆使用繁體中文。
</law>

<law>
遵循 6 層架構分離：UI → Core → Services / Scheduler → Data → SQLite。不可跨層直接存取。UI 層透過 Signal/Slot 與 Core 層溝通。Data 層透過 Repository 模式封裝 SQLite 存取。
</law>

<law>
TDD 開發：先寫測試再寫實作。開發順序：data → core → services → scheduler → ui。
</law>

<law>
搜尋功能必須經過完整管線：jieba 斷詞 → 同義詞擴展 → FTS5 MATCH。不可直接 LIKE 查詢。
</law>

<law>
新增信件來源時必須實作 MailProvider ABC。信件處理管線 7 步不可跳過或重排。
</law>

# 專案結構

```
src/hcp_cms/
├── ui/          # UI 層 — PySide6 (Signal/Slot)
├── core/        # Core 層 — 業務邏輯
├── services/    # Services 層 — MailProvider/MantisClient ABC
├── scheduler/   # Scheduler 層 — QTimer + QThread
├── data/        # Data 層 — Repository + FTS5
└── i18n/        # 國際化 JSON 語系檔
```

# 快速參考

- **測試**: `.venv/Scripts/python.exe -m pytest tests/ -v`
- **Lint**: `.venv/Scripts/ruff.exe check src/ tests/`
- **格式化**: `.venv/Scripts/ruff.exe format src/ tests/`
- **執行**: `.venv/Scripts/python.exe -m hcp_cms`
- **Python**: 3.14.3 | **PySide6**: 6.10.2 | **SQLite**: 內建 FTS5
