# 寄件備份清單 設計文件

**日期：** 2026-03-28
**狀態：** 已確認

---

## 需求摘要

在「信件處理」頁面（`EmailView`）新增「寄件備份」分頁，讓客服人員可清楚掌握特定日期範圍內發出的回覆信件，並自動識別對應公司及統計各公司回覆次數。

---

## 架構方案

選用 **方案 B**：新增 `SentMailManager`（Core 層）+ `SentMailTab`（UI 層）。

- Core 層負責：呼叫 `MailProvider`、公司比對、統計計算
- UI 層負責：渲染彙總表與清單表，不含業務邏輯
- 符合 6 層架構規範（Law 2）

---

## 新增元件

| 元件 | 層 | 路徑 |
|------|----|----|
| `EnrichedSentMail` dataclass | Core | `src/hcp_cms/core/sent_mail_manager.py` |
| `SentMailManager` | Core | `src/hcp_cms/core/sent_mail_manager.py` |
| `SentMailTab` | UI | 嵌入 `src/hcp_cms/ui/email_view.py` |
| `test_sent_mail_manager.py` | 測試 | `tests/unit/test_sent_mail_manager.py` |

---

## 資料模型

```python
@dataclass
class EnrichedSentMail:
    date: str
    recipients: list[str]
    subject: str
    company_id: str | None
    company_name: str | None
    linked_case_id: str | None
    company_reply_count: int  # 本次查詢範圍內該公司出現次數
```

---

## Core 層：`SentMailManager`

### 介面

```python
class SentMailManager:
    def __init__(self, conn: sqlite3.Connection, provider: MailProvider) -> None: ...

    def fetch_and_enrich(
        self, since: datetime, until: datetime
    ) -> list[EnrichedSentMail]: ...

    def _resolve_company(
        self, subject: str, recipients: list[str]
    ) -> tuple[str | None, str | None]:
        # 回傳 (company_id, company_name)
        ...
```

### 公司比對邏輯（優先順序）

1. **cs_cases 比對**：`cs_cases.subject` 完全比對 → 取 `company_id`，JOIN `companies.name`
2. **Email domain 比對**：取 `recipients[0]` 的 domain → 查 `companies.domain` 完全比對
3. **未知**：兩者皆查不到 → `company_id = None`，顯示「未知」

### `until` 過濾

`MailProvider.fetch_sent_messages(since)` 僅接受 `since` 參數，`until` 在 `SentMailManager.fetch_and_enrich()` 內以 Python 過濾排除範圍外信件。

### 統計計算

`fetch_and_enrich` 回傳前，統計結果清單中各 `company_id` 的出現次數，填入每筆 `EnrichedSentMail.company_reply_count`。

---

## UI 層：`SentMailTab`

### 版面結構

```
┌─────────────────────────────────────────────────────┐
│  [←]  [日期]  [→]   [7天]   [今天]   [重新整理]    │  ← 工具列（同收件分頁）
├─────────────────────────────────────────────────────┤
│  公司彙總                                            │
│  ┌──────────────┬──────┐                            │
│  │ 公司名稱     │ 次數 │                            │
│  │ ABC 公司     │  5   │                            │
│  └──────────────┴──────┘                            │
├─────────────────────────────────────────────────────┤
│  寄件清單                                            │
│  ┌──────────┬────────────┬──────────────┬──────┬────────┬──────┐
│  │ 日期     │ 收件人     │ 主旨         │ 公司 │ 案件   │ 次數 │
│  └──────────┴────────────┴──────────────┴──────┴────────┴──────┘
└─────────────────────────────────────────────────────┘
```

### 行為規格

- **日期篩選**：與收件分頁相同模式——`QDateEdit` + 前後箭頭 + 「7天」(往前) + 「今天」按鈕
- **重新整理**：在背景執行緒呼叫 `SentMailManager.fetch_and_enrich(since, until)`，完成後 emit signal 更新 UI
- **彙總表**：依次數降冪排列，固定顯示於清單上方
- **清單表**：「案件」欄若有值，點擊可複製 `case_id`；無值顯示「—」
- **「次數」欄**：同一查詢範圍內，該公司所有寄件的累計總數

### Signal / Slot

```python
_worker_done = Signal(object)   # list[EnrichedSentMail]，背景完成後更新表格
_worker_error = Signal(str)     # 錯誤訊息
```

---

## 測試策略

測試檔案：`tests/unit/test_sent_mail_manager.py`
使用 in-memory SQLite + mock `MailProvider`

| 測試方法 | 驗證項目 |
|---------|---------|
| `test_resolve_company_by_case` | subject 完全比對 cs_cases → 正確回傳公司 |
| `test_resolve_company_by_domain` | subject 無案件但 domain 可比對 → 回傳公司 |
| `test_resolve_company_unknown` | 兩者都查不到 → 回傳 `(None, None)` |
| `test_fetch_and_enrich_counts` | 同公司多封信 → `company_reply_count` 正確累計 |
| `test_fetch_and_enrich_date_filter` | `until` 過濾正確排除範圍外信件 |

---

## 未納入範圍

- 寄件備份持久化至 SQLite（方案 C，評估後不划算）
- 點擊清單列跳轉至對應案件頁面（可列入後續需求）
- 寄件內容預覽（可列入後續需求）
