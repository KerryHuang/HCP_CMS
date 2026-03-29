# 寄件備份匯出 Excel — 設計文件

**日期：** 2026-03-29
**狀態：** 已核准

---

## 需求摘要

在「寄件備份」分頁加入「匯出 Excel」按鈕，讓使用者將當前查詢結果匯出為 `.xlsx` 檔案。
匯出內容包含兩個工作表：公司彙總、寄件清單。

---

## 架構方案

採用 **Core 層 ExcelExporter**，符合 6 層架構分離原則：
- UI 層只負責：儲存最新資料、彈出對話框、呼叫 exporter、顯示結果
- Core 層負責：格式化並寫出 xlsx

---

## 元件設計

### 新增：`src/hcp_cms/core/excel_exporter.py`

```python
class ExcelExporter:
    def export_sent_mail(self, mails: list[EnrichedSentMail], path: str) -> None
```

**工作表 1「公司彙總」**
- 欄位：公司名稱、次數
- 排序：依次數降冪（與畫面一致）
- 第一列為粗體標題列

**工作表 2「寄件清單」**
- 欄位：日期、收件人、主旨、公司、案件、次數
- 順序：原始順序（fetch 回傳順序）
- 收件人多筆：以 `", "` 合併為一個儲存格
- 案件為空時：填 `—`
- 第一列為粗體標題列

---

### 修改：`src/hcp_cms/ui/sent_mail_tab.py`

1. 新增實例變數 `_current_mails: list[EnrichedSentMail] = []`
2. `_on_worker_done` 中同步更新 `_current_mails` 並啟用匯出按鈕
3. 日期導航列右側加「📥 匯出 Excel」按鈕，初始 `setEnabled(False)`
4. 點擊處理：
   - 取得日期字串作為預設檔名 `寄件備份_YYYY-MM-DD.xlsx`
   - 呼叫 `QFileDialog.getSaveFileName()`
   - 使用者取消 → 靜默忽略
   - 呼叫 `ExcelExporter().export_sent_mail(self._current_mails, path)`
   - 成功 → `_log` 顯示 `✅ 已匯出至 <path>`
   - 失敗 → `_log` 顯示 `❌ 匯出失敗：<錯誤訊息>`

---

## 資料流

```
使用者點「📥 匯出 Excel」
  → QFileDialog.getSaveFileName()（預設：寄件備份_YYYY-MM-DD.xlsx）
  → 使用者取消 → 中止（無 log）
  → ExcelExporter.export_sent_mail(_current_mails, path)
  → openpyxl 寫出 .xlsx（兩個工作表）
  → _log 顯示結果
```

---

## 邊界條件與錯誤處理

| 情況 | 處理 |
|------|------|
| `_current_mails` 為空 | 按鈕 disabled，不可點擊 |
| 使用者取消對話框 | 靜默忽略，不寫 log |
| 寫檔失敗（權限/磁碟滿） | `_log` 顯示 `❌ 匯出失敗：<錯誤訊息>` |
| 收件人多筆 | 以 `", "` 合併為一個儲存格 |
| 案件欄位為空 | 填入 `—` |

---

## 測試計畫

**新增：`tests/unit/test_excel_exporter.py`**

- 用 `tmp_path` fixture 產生暫存路徑
- 驗證檔案存在
- 驗證工作表名稱為「公司彙總」、「寄件清單」
- 驗證「公司彙總」列數 = 公司數 + 1（標題）
- 驗證「寄件清單」列數 = 信件數 + 1（標題）
- 驗證排序：公司彙總依次數降冪
- 驗證收件人多筆合併

---

## 依賴

- `openpyxl>=3.1`（已在 `pyproject.toml` 中）
- 無需新增依賴
