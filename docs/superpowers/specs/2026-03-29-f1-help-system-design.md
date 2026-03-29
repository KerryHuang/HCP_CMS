# F1 上下文說明系統

**日期：** 2026-03-29
**狀態：** 已核准

---

## 概述

按 F1 鍵開啟上下文說明對話框，根據當前所在頁面自動顯示 `operation-manual.md` 對應章節內容。Markdown 渲染為 HTML 後以深色主題 Modal Dialog 顯示。

## 元件

### HelpDialog(QDialog) — `src/hcp_cms/ui/help_dialog.py`

- 大小：800x600，可調整大小
- 標題：「說明 — {頁面名稱}」
- 內容區：`QTextBrowser`（支援 HTML、內部錨點跳轉）
- 底部：「關閉」按鈕
- 深色主題樣式，與現有 Dialog 一致

### 頁面 → 章節對應表

| 頁面索引 | 頁面名稱 | 手冊章節標記 |
|---------|---------|------------|
| 0 | 儀表板 | `## 3. 儀表板` |
| 1 | 案件管理 | `## 4. 案件管理` |
| 2 | KMS 知識庫 | `## 5. KMS 知識庫` |
| 3 | 信件處理 | `## 6. 信件處理` |
| 4 | Mantis 同步 | `## 7. Mantis 同步` |
| 5 | 報表中心 | `## 8. 報表中心` |
| 6 | 規則設定 | `## 9. 規則設定` |
| 7 | 系統設定 | `## 10. 系統設定`（含第 11 章備份還原） |

### Markdown → HTML 轉換

- 使用 Python `markdown` 套件（含 `tables` 擴展）
- 轉換後注入深色主題 CSS（背景 `#1e293b`、文字 `#e2e8f0`、表格樣式）
- 手冊檔案路徑：打包後從 `sys._MEIPASS` 或開發時從專案根目錄讀取

### 快捷鍵綁定

- 在 `MainWindow._setup_shortcuts()` 新增 F1 綁定
- 呼叫 `_on_help_requested()` → 取得當前頁面索引 → 開啟 `HelpDialog`

## 資料流

```
F1 按下
  → MainWindow._on_help_requested()
  → self._nav_list.currentRow() → 頁面索引
  → HelpDialog(section_index, parent=self)
    → 讀取 operation-manual.md
    → 依 "## N." 標記擷取對應章節
    → markdown.markdown(section, extensions=["tables"])
    → 注入深色主題 CSS
    → QTextBrowser.setHtml(styled_html)
```

## 範圍外

- 不建立獨立說明檔案（複用手冊）
- 不做全文搜尋（章節已足夠精準）
- 不加入 i18n 鍵（說明內容直接從手冊讀取）
