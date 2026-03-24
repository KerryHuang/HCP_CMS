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
| 我方識別 | 地址含 `@ares.com.tw`（大小寫不敏感，不限定特定帳號） |
| QA 初始狀態 | `待審核`（不進入 FTS 搜尋索引） |
| 人工審核 | 可編輯問題、回覆、解決方案、關鍵字，按「確認完成」後才建立 FTS 索引 |
| 中間儲存 | 「儲存草稿」維持待審核狀態，保存已編輯內容，**不寫入 FTS** |
| status 降級 | **禁止**將已完成 QA 改回待審核（防止 FTS 殭屍索引） |

---

## 資料流

```
.MSG 匯入（EmailView._do_import_rows）
        │
        ▼
MSGReader._read_msg_file()
  └─ _split_thread(body, own_domain="@ares.com.tw")
       ├─ thread_answer: str | None   ← body 上半（HCPSERVICE 回覆）
       └─ thread_question: str | None ← body 下半（客戶問題，清除 header 行後 strip；
                                         strip 後為空字串則回傳 None）

RawEmail 建構式明確傳入：
  RawEmail(..., thread_question=tq, thread_answer=ta)

        │
        ▼
EmailView._do_import_rows()
  ├─ CaseManager.import_email(...)           ← 建案，介面不變
  └─ if raw_email.thread_question:           ← "" 與 None 均為 falsy，安全
       self._kms.extract_qa_from_email(raw_email, case.case_id)
         └─ create_qa(..., status="待審核")   ← 不寫入 FTS

        │
        ▼
KMSView「待審核」分頁
  ├─ list_pending() 顯示列表
  ├─ 點選 → QAReviewDialog（可編輯所有欄位）
  │    ├─ [儲存草稿] → update_qa(qa_id, question=..., answer=...) ← status 不變，不寫 FTS
  │    └─ [確認完成] → approve_qa(qa_id, question=..., answer=...) ← 單一入口
  │                       ├─ 內部設定 fields["status"] = "已完成"
  │                       ├─ 呼叫 update_qa()（setattr 後 qa.status == "已完成"，守衛放行 FTS）
  │                       └─ FTS index 建立
  └─ [刪除] → delete_qa()
               └─ 待審核 QA 未進 FTS，remove_qa_index 執行空刪除，無害
```

---

## 元件異動清單

### 1. `services/mail/base.py` — RawEmail

新增欄位：
```python
thread_question: str | None = None  # 客戶問題段（清除 header 後，空字串統一轉 None）
thread_answer: str | None = None    # HCPSERVICE 回覆段
```

### 2. `services/mail/msg_reader.py` — MSGReader

新增模組層正則表達式：
```python
# 偵測嵌入 From 行（中英文），擷取 email 地址
_THREAD_FROM_RE = re.compile(
    r"^(?:From|寄件者)\s*:\s*.*?([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})",
    re.MULTILINE | re.IGNORECASE,
)
# 清除引用 header 行（中英文版）
_HEADER_LINE_RE = re.compile(
    r"^(?:From|To|Sent|Subject|寄件者|收件者|傳送時間|主旨)\s*:.*$",
    re.MULTILINE | re.IGNORECASE,
)
```

新增靜態方法：
```python
@staticmethod
def _split_thread(body: str, own_domain: str = "@ares.com.tw") -> tuple[str | None, str | None]:
    """回傳 (thread_answer, thread_question)。
    - own_domain 比對大小寫不敏感（addr.lower() 與 own_domain.lower() 比對）
    - thread_question strip 後若為空字串，回傳 None（非空字串 ""）
    - 找不到非我方 From 行則兩者皆回傳 None
    """
```

`_read_msg_file()` 最後建構 `RawEmail` 時，**明確傳入**兩個新欄位：
```python
thread_answer, thread_question = MSGReader._split_thread(body_text)
email = RawEmail(
    ...,
    thread_question=thread_question,   # ← 明確具名參數，不可省略
    thread_answer=thread_answer,       # ← 明確具名參數，不可省略
)
```

### 3. `data/models.py` — QAKnowledge

```python
status: str = "已完成"  # 新增：'待審核' | '已完成'（禁止其他值）
```

### 4. `data/database.py` — DDL

```sql
CREATE TABLE IF NOT EXISTS qa_knowledge (
    qa_id          TEXT PRIMARY KEY,
    system_product TEXT,
    issue_type     TEXT,
    error_type     TEXT,
    question       TEXT,
    answer         TEXT,
    solution       TEXT,
    keywords       TEXT,
    has_image      TEXT DEFAULT '否',
    doc_name       TEXT,
    company_id     TEXT REFERENCES companies(company_id),
    source_case_id TEXT REFERENCES cs_cases(case_id),
    source         TEXT DEFAULT 'manual',
    status         TEXT DEFAULT '已完成',   -- 新增（位於 source 之後）
    created_by     TEXT,
    created_at     TEXT,
    updated_at     TEXT,
    notes          TEXT
);
```

### 5. `data/migration.py` — 既有資料庫

```python
try:
    conn.execute("ALTER TABLE qa_knowledge ADD COLUMN status TEXT DEFAULT '已完成'")
    conn.commit()
except sqlite3.OperationalError:
    pass  # 欄位已存在（重跑 migration 冪等）
```

`MigrationManager._migrate()` 本體中加入上述程式碼片段。
歷史資料由 SQLite 的 `DEFAULT '已完成'` 自動填入，符合「舊資料視為已完成」的語意，
不需要對現有 INSERT 語句做任何修改。

### 6. `data/repositories.py` — QARepository

| 方法 | 變更 |
|------|------|
| `insert()` | SQL 與 dict **加入 `status` 欄位**（`updated_at` 照舊由 `_now()` 設定） |
| `update()` | SQL 與 dict **加入 `status` 欄位**（⚠️ 高優先：缺此欄位將導致 `approve_qa()` 靜默失敗） |
| `list_by_status(status: str) -> list[QAKnowledge]` | 新增：`SELECT * FROM qa_knowledge WHERE status = ?` |
| `list_approved() -> list[QAKnowledge]` | 新增（語意清晰）：`list_by_status("已完成")` 的別名 |

**`insert()` SQL 差異（摘要）：**
```sql
-- 欄位清單加入 status（位於 source 之後）
INSERT INTO qa_knowledge (
    qa_id, system_product, issue_type, error_type, question, answer,
    solution, keywords, has_image, doc_name, company_id, source_case_id,
    source, status, created_by, created_at, updated_at, notes
) VALUES (
    :qa_id, :system_product, ..., :source, :status, :created_by, ...
)
-- dict 加入 "status": qa.status
```

**`update()` SQL 差異（摘要）：**
```sql
UPDATE qa_knowledge SET
    ...
    source = :source,
    status = :status,   -- 新增
    updated_at = :updated_at,
    ...
-- dict 加入 "status": qa.status
```

**`update()` status 持久化**是 `approve_qa()` 正確運作的前提。測試必須涵蓋「`update()` 執行後，`get_by_id()` 取回的 status 確實更新至資料庫」。

### 7. `core/kms_engine.py` — KMSEngine

**`create_qa()` 異動：**
- 新增 `status: str = "已完成"` 參數
- **僅當 `status == "已完成"` 時**呼叫 `_fts.index_qa()`

**`update_qa()` 異動（FTS 守衛）：**
- setattr 迴圈執行完畢後，讀取 **`qa.status`**（記憶體中已更新的值）
- `qa.status == "已完成"` → 呼叫 `_fts.update_qa_index()`
- `qa.status == "待審核"` → 跳過 FTS
- 守衛對象是 setattr 後的 `qa.status`，**非** `fields.get("status")`；
  若呼叫端未傳入 `status`，守衛依資料庫既有值判斷（即 `get_by_id()` 取回的原始 status）

**`search()` 異動：**
- FTS 取回 `qa_id` 後，`get_by_id()` 取得完整物件，在 **Python 層**過濾 `qa.status == "已完成"`
- 不在 `qa_fts` 虛擬表加 WHERE（虛擬表無 status 欄位，會拋 `OperationalError`）

**`list_all()` / KMSView「全部」tab：**
- KMSView「全部」tab 改為呼叫 `list_approved()`（僅顯示已完成 QA）
- `export_to_excel()` 預設也以 `list_approved()` 為資料來源，排除待審核 QA

**status 降級禁止：**
- `update_qa()` 加入守衛：若目前 `qa.status == "已完成"` 且新 `status == "待審核"`，記錄警告並拒絕更新（回傳 `None`，不拋例外）

**`auto_extract_qa()` 廢棄：**
- 現有 `auto_extract_qa(case)` 從 Case 物件的 subject/progress 抽取 QA，直接以 `status="已完成"` 寫入 FTS，與本功能的「待審核」流程不一致
- 搜尋結果顯示 `auto_extract_qa` 目前**未被任何呼叫端使用**
- 本次實作中標記為 deprecated（保留方法但 docstring 加上 `.. deprecated::` 說明），由 `extract_qa_from_email()` 取代
- 舊方法產生的已完成 QA 維持現狀，不受影響

**新增方法：**

```python
def extract_qa_from_email(self, raw_email: RawEmail, case_id: str | None = None) -> QAKnowledge | None:
    """從 RawEmail thread 欄位抽取 QA，儲存為待審核。無問題段則回傳 None。"""
    if not raw_email.thread_question:
        return None
    return self.create_qa(
        question=raw_email.thread_question,
        answer=raw_email.thread_answer or "",
        source="email",
        source_case_id=case_id,
        status="待審核",   # create_qa 因 status != "已完成" 不寫 FTS
    )

def approve_qa(self, qa_id: str, **updated_fields) -> QAKnowledge | None:
    """單一入口：更新欄位內容 → status = '已完成' → 建立 FTS 索引。

    確認完成時直接呼叫此方法，不要先呼叫 update_qa() 再呼叫 approve_qa()。
    內部設定 fields["status"] = "已完成" 後呼叫 update_qa()；
    update_qa() 的守衛因 qa.status == "已完成" 而放行 FTS 寫入。
    """
    updated_fields["status"] = "已完成"
    return self.update_qa(qa_id, **updated_fields)

def list_pending(self) -> list[QAKnowledge]:
    """列出所有待審核 QA。"""
    return self._qa_repo.list_by_status("待審核")
```

### 8. `ui/email_view.py` — EmailView

**`KMSEngine` 注入：**
- `EmailView.__init__(self, conn, kms: KMSEngine | None = None)` 新增 `kms` 參數
- `self._kms = kms`
- `MainWindow` 建構單一 `KMSEngine(conn)` 實例，同時注入 `EmailView` 與 `KMSView`，確保兩者共用同一 `conn` 與記憶體狀態

`_do_import_rows()` 匯入成功後：
```python
if raw_email.thread_question and self._kms:
    self._kms.extract_qa_from_email(raw_email, case.case_id)
```

### 9. `ui/kms_view.py` — KMSView

- 頂部加入 Tab 切換：「全部」／「待審核 🔴N」（N 為 `list_pending()` 筆數）
- **「全部」tab**：資料來源改為 `kms.list_approved()`，不顯示待審核 QA
- **「待審核」tab**：三欄表格（QA編號、問題預覽、來源案件）
- 按鈕：「✏️ 編輯審核」、「🗑️ 刪除」
- 新增 `QAReviewDialog`（`QDialog` 子類別）：
  - 可編輯欄位：問題、回覆、解決方案、關鍵字、產品
  - [取消] → 關閉，不儲存
  - [儲存草稿] → `kms.update_qa(qa_id, question=..., answer=..., ...)` → status 仍為待審核，不寫 FTS
  - [✅ 確認完成] → `kms.approve_qa(qa_id, question=..., answer=..., ...)` → 移入全部列表

---

## 測試範圍

| 測試類別 | 項目 |
|----------|------|
| unit | `_split_thread()` — 英文 From |
| unit | `_split_thread()` — 中文寄件者 |
| unit | `_split_thread()` — 多層巢狀（只取最外層客戶 From） |
| unit | `_split_thread()` — 無客戶 From 行 → `(None, None)` |
| unit | `_split_thread()` — 全部 From 均為 @ares.com.tw → `(None, None)` |
| unit | `_split_thread()` — own_domain 大小寫混用（`User@ARES.COM.TW`）仍識別為我方 |
| unit | `_split_thread()` — 客戶段清除 header 後為空 → `thread_question = None` |
| unit | `KMSEngine.create_qa(status="待審核")` — 不呼叫 FTS |
| unit | `KMSEngine.update_qa(status="待審核")` — 不呼叫 FTS |
| unit | `KMSEngine.update_qa()` 未傳 status，原 status 為待審核 → 不呼叫 FTS |
| unit | `KMSEngine.update_qa()` 未傳 status，原 status 為已完成 → 呼叫 FTS |
| unit | `KMSEngine.update_qa()` 嘗試從已完成降級 → 拒絕，回傳 None |
| unit | `KMSEngine.extract_qa_from_email()` — 有 thread_question → 建立待審核 QA |
| unit | `KMSEngine.extract_qa_from_email()` — 無 thread_question → 回傳 None |
| unit | `KMSEngine.approve_qa()` — status 更新為已完成 + FTS 索引建立 |
| unit | `KMSEngine.search()` — 待審核 QA 不出現在搜尋結果 |
| unit | `KMSEngine.delete_qa()` — 刪除待審核 QA 不影響 FTS（空刪除無害） |
| unit | `QARepository.list_by_status("待審核")` |
| unit | `QARepository.update()` 寫入 status 後，`get_by_id()` 取回值一致（持久化驗證） |
| integration | .MSG 匯入 → KMS 待審核出現 → 審核通過 → 搜尋可找到 |

---

## 不在本次範圍

- 匿名化（Anonymizer）整合：待審核 QA 保留原始內容，由審核者手動修改敏感資訊
- 多層巢狀對話串全部抽取（只取最外層一組問答）
- 批次審核（一次確認多筆）
- 匯出 Excel 的待審核 QA 篩選 UI（本次直接排除待審核，不提供篩選切換）
