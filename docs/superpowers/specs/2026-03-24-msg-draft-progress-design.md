# .msg 草稿寄件人與進度標記解析 Design Spec

**日期：** 2026-03-24
**狀態：** 已核准

---

## 目標

1. 從 .msg 本文中擷取 `==進度:…==` 標記，自動寫入 `Case.progress`（處理進度欄位）
2. 草稿 .msg（`msg.sender` 為空白）時，從 body 任意位置搜尋 `From: name <email>` 行，補回正確的寄件人與公司

---

## 架構方向

**方向 A（已選定）**：擴充 `RawEmail` 新增 `progress_note` 欄位。解析邏輯集中在 `MSGReader`，業務邏輯（寫入 case）在 `CaseManager`。

---

## 資料流

```
.msg 檔案
  └─ MSGReader._read_msg_file()
       ├─ msg.sender 為空 → 從 body 搜尋 From: 行補回 sender
       ├─ body 含 ==進度:…== → 擷取為 progress_note
       └─ 回傳 RawEmail（含 sender, to_recipients, html_body, progress_note）
           └─ CaseManager.create_case()
                ├─ sender → Classifier 識別公司
                └─ progress_note → Case.progress
```

---

## 元件設計

### 1. `RawEmail`（`services/mail/base.py`）

新增欄位：
```python
progress_note: str | None = None
```

### 2. `MSGReader._read_msg_file()`（`services/mail/msg_reader.py`）

**進度擷取**
- Regex：`==進度[:：]\s*(.*?)==`（`re.DOTALL | re.IGNORECASE`）
- 擷取第一個符合的群組，strip 空白後存入 `progress_note`
- 全形冒號（：）與半形冒號（:）皆接受

**草稿寄件人補修**
- 條件：`msg.sender` 為空字串或 None
- Regex：`From:\s*[^<\n]*<([^>]+)>` — 取角括號內 email
- Fallback：`From:\s*(\S+@\S+)` — 取純 email（無顯示名稱格式）
- 搜尋範圍：整個 `msg.body`（`re.MULTILINE`）
- 找到後更新 `email.sender`

### 3. `CaseManager.create_case()`（`core/case_manager.py`）

新增參數：`progress_note: str | None = None`

邏輯（**body 標記優先於主旨/檔名標記**）：
```python
# classification["progress"] 來自主旨/檔名標記解析（Classifier）
# progress_note 來自 body ==進度==，優先使用
final_progress = progress_note.strip() if progress_note else classification.get("progress")
case.progress = final_progress
```

**優先順序說明：** 使用者在 body 明確標記 `==進度==` 代表最新進度，應覆蓋主旨標記的解析結果。

### 4. `CaseManager.import_email()`

新增 `progress_note: str | None = None` 參數，傳給 `create_case()`：
```python
def import_email(self, ..., progress_note: str | None = None, ...) -> tuple[...]:
    ...
    case = self.create_case(
        ...
        progress_note=progress_note,
    )
```

### 5. `EmailView._do_import_rows()`（`ui/email_view.py`）

補傳 `progress_note`：
```python
case, action = manager.import_email(
    ...
    progress_note=email.progress_note,
)
```

---

## 測試計畫

| 測試 | 位置 |
|------|------|
| `RawEmail` 有 `progress_note` 欄位 | `test_services.py::TestRawEmail` |
| body 含 `==進度:…==` → `progress_note` 正確 | `test_services.py::TestMSGReader` mock |
| body 跨行 `==進度:…==` → 完整擷取 | `test_services.py::TestMSGReader` mock |
| body 全形冒號 `==進度：…==` → 正確擷取 | `test_services.py::TestMSGReader` mock |
| 無標記 → `progress_note` 為 None | `test_services.py::TestMSGReader` mock |
| `msg.sender` 空白，body 含 `From: Name <email>` → sender 補回 | `test_services.py::TestMSGReader` mock |
| `msg.sender` 空白，body 含純 email 格式 `From: user@domain.com` → fallback regex 補回 | `test_services.py::TestMSGReader` mock |
| `msg.sender` 有值 → 不被覆蓋 | `test_services.py::TestMSGReader` mock |
| `create_case(progress_note=…)` → `case.progress` 寫入 | `test_case_manager.py` |
| `create_case()` 有主旨標記又有 `progress_note` → body 標記優先 | `test_case_manager.py` |
| `import_email(progress_note=…)` → 傳遞至 `create_case()` → `case.progress` 正確 | `test_case_manager.py` |

---

## 不在範圍內（YAGNI）

- 多個 `==進度==` 標記：只取第一個
- 從主旨擷取進度：不實作（主旨進度已由 Classifier 處理）
- 草稿的顯示名稱解析 → `contact_person`：本次不實作

---

## 異動檔案

| 動作 | 檔案 |
|------|------|
| 修改 | `src/hcp_cms/services/mail/base.py` |
| 修改 | `src/hcp_cms/services/mail/msg_reader.py` |
| 修改 | `src/hcp_cms/core/case_manager.py`（`create_case()` + `import_email()`）|
| 修改 | `src/hcp_cms/ui/email_view.py`（`_do_import_rows()` 補傳 `progress_note`）|
| 修改 | `tests/unit/test_services.py` |
| 修改 | `tests/unit/test_case_manager.py` |
