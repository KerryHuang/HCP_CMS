# MSG QA 自動抽取設計文件

**日期：** 2026-03-24
**功能：** 從 .MSG 信件對話串自動抽取問與答，儲存至 KMS 待審核佇列

---

## 背景

HCP CMS 匯入 .MSG 信件時，信件 body 通常包含完整對話串：
- 上半部：HCPSERVICE@ARES.COM.TW 的回覆（答）
- 下半部：嵌入的客戶原始問題（問）

目前系統讀取整個 body 為單一字串，未拆分對話串，KMS 也無法自動建立 QA 條目。
本功能讓系統自動識別問與答，儲存為「待審核」狀態，由人工確認後才進入搜尋索引。

---

## 需求摘要

| 項目 | 規格 |
|------|------|
| 切割策略 | Regex 掃描 `From:` / `寄件者:` 行，取第一個非 `@ares.com.tw` 地址為分割點 |
| 我方識別 | 地址含 `@ares.com.tw`（不限定特定帳號） |
| QA 初始狀態 | `待審核`（不進入 FTS 搜尋索引） |
| 人工審核 | 可編輯問題、回覆、解決方案、關鍵字，按「確認完成」後才建立 FTS 索引 |
| 中間儲存 | 「儲存草稿」維持待審核狀態，保存已編輯內容 |

---

## 資料流

```
.MSG 匯入（EmailView._do_import_rows）
        │
        ▼
MSGReader._read_msg_file()
  └─ _split_thread(body, own_domain="@ares.com.tw")
       ├─ thread_answer: str | None   ← body 上半（HCPSERVICE 回覆）
       └─ thread_question: str | None ← body 下半（客戶問題，清除 header 行）

RawEmail 新增欄位：thread_answer, thread_question

        │
        ▼
EmailView._do_import_rows()
  ├─ CaseManager.import_email(...)          ← 建案，介面不變
  └─ if raw_email.thread_question:
       KMSEngine.extract_qa_from_email(raw_email, case_id)
         └─ create_qa(..., status="待審核")  ← 不寫入 FTS

        │
        ▼
KMSView「待審核」分頁
  ├─ list_pending() 顯示列表
  ├─ 點選 → QAReviewDialog（可編輯所有欄位）
  │    ├─ [儲存草稿] → update_qa()，status 維持待審核
  │    └─ [確認完成] → update_qa() + approve_qa()
  │                      ├─ status = "已完成"
  │                      └─ FTS index 建立
  └─ [刪除] → delete_qa()
```

---

## 元件異動清單

### 1. `services/mail/base.py` — RawEmail

新增欄位：
```python
thread_question: str | None = None  # 客戶問題段（清除 header 後）
thread_answer: str | None = None    # HCPSERVICE 回覆段
```

### 2. `services/mail/msg_reader.py` — MSGReader

新增正則表達式：
```python
# 偵測嵌入 From 行（中英文）
_THREAD_FROM_RE = re.compile(
    r"^(?:From|寄件者)\s*:\s*.*?([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})",
    re.MULTILINE | re.IGNORECASE,
)
# 清除引用 header 行
_HEADER_LINE_RE = re.compile(
    r"^(?:From|To|Sent|Subject|寄件者|收件者|傳送時間|主旨)\s*:.*$",
    re.MULTILINE | re.IGNORECASE,
)
```

新增靜態方法 `_split_thread(body, own_domain="@ares.com.tw") -> tuple[str | None, str | None]`：
- 掃描所有符合 `_THREAD_FROM_RE` 的行
- 取第一個地址不含 `own_domain` 的行為分割點
- 上半段 → `thread_answer`（strip 空白）
- 下半段 → 移除 header 行後 → `thread_question`
- 找不到則回傳 `(None, None)`

`_read_msg_file()` 呼叫 `_split_thread()` 後將結果寫入 `RawEmail`。

### 3. `data/models.py` — QAKnowledge

```python
status: str = "已完成"  # 新增：'待審核' | '已完成'
```

### 4. `data/database.py` — DDL

```sql
CREATE TABLE IF NOT EXISTS qa_knowledge (
    ...
    status TEXT DEFAULT '已完成',   -- 新增欄位（位於 source 之後）
    ...
);
```

### 5. `data/migration.py` — 既有資料庫

```sql
ALTER TABLE qa_knowledge ADD COLUMN status TEXT DEFAULT '已完成';
```

### 6. `data/repositories.py` — QARepository

| 方法 | 變更 |
|------|------|
| `insert()` | SQL 加入 `status` 欄位與參數 |
| `update()` | SQL 加入 `status` 欄位與參數 |
| `list_by_status(status: str)` | 新增：`WHERE status = ?` |

### 7. `core/kms_engine.py` — KMSEngine

**`create_qa()` 異動：**
- 新增 `status: str = "已完成"` 參數
- 僅當 `status == "已完成"` 時呼叫 `_fts.index_qa()`

**新增方法：**

```python
def extract_qa_from_email(self, raw_email: RawEmail, case_id: str | None = None) -> QAKnowledge | None:
    """從 RawEmail thread 欄位抽取 QA，儲存為待審核。無問題段則回傳 None。"""

def approve_qa(self, qa_id: str) -> QAKnowledge | None:
    """審核通過：status → 已完成，建立 FTS 索引。"""

def list_pending(self) -> list[QAKnowledge]:
    """列出所有待審核 QA。"""
```

**`search()` 異動：**
- 加入 `WHERE status = '已完成'` 過濾（或在 FTS 層過濾）

### 8. `ui/email_view.py` — EmailView

`_do_import_rows()` 匯入成功後：
```python
if raw_email.thread_question and self._kms:
    self._kms.extract_qa_from_email(raw_email, case.case_id)
```

### 9. `ui/kms_view.py` — KMSView

- 頂部加入 Tab 切換：「全部」／「待審核 🔴N」
- 待審核 tab：三欄表格（QA編號、問題預覽、來源案件）
- 按鈕：「✏️ 編輯審核」、「🗑️ 刪除」
- 新增 `QAReviewDialog`：可編輯問題、回覆、解決方案、關鍵字、產品
  - [取消] / [儲存草稿] / [✅ 確認完成]

---

## 測試範圍

| 測試類別 | 項目 |
|----------|------|
| unit | `MSGReader._split_thread()` — 英文 From、中文寄件者、多層巢狀、無客戶 From、@ares 自回 |
| unit | `KMSEngine.extract_qa_from_email()` — 有/無 thread_question |
| unit | `KMSEngine.approve_qa()` — status 更新 + FTS 索引 |
| unit | `KMSEngine.create_qa(status="待審核")` — 不呼叫 FTS |
| unit | `KMSEngine.search()` — 待審核 QA 不出現在搜尋結果 |
| unit | `QARepository.list_by_status()` |
| integration | .MSG 匯入 → KMS 待審核出現 → 審核通過 → 搜尋可找到 |

---

## 不在本次範圍

- 匿名化（Anonymizer）整合：待審核 QA 保留原始內容，由審核者手動修改敏感資訊
- 多層巢狀對話串全部抽取（只取最外層一組問答）
- 批次審核（一次確認多筆）
