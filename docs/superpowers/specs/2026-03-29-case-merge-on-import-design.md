# 同主旨信件自動整合為一個案件 — 設計文件

**日期：** 2026-03-29
**狀態：** 已核准

---

## 需求摘要

匯入同公司、同主旨（去除 RE:/FW: 前綴後相同）的多封信件時，不再各自建立獨立案件，而是整合為一個案件，後續信件以 CaseLog 方式記錄處理進度。同時提供一鍵整合已存在的重複案件。

**合併條件：** 相同 `company_id` + 相同 `clean_subject`（遞迴去除 RE:/FW:/回覆:/轉寄:/答覆: 前綴）

---

## 架構方案

**方案 B — 新增 `CaseMerger` + 修改 `CaseManager.import_email()`**

兩個職責：
1. **Find-or-Create**：匯入時先查有無匹配案件，有則加 CaseLog，沒有才建新案件
2. **MergeDuplicates**：掃描資料庫，將現有重複案件整合為最早那一筆，其餘刪除

---

## 元件設計

### 新增：`src/hcp_cms/core/case_merger.py`

```python
class CaseMerger:
    def __init__(self, conn: sqlite3.Connection) -> None: ...

    def find_duplicate_groups(self) -> list[list[Case]]:
        """找出所有 (company_id, clean_subject) 相同的案件群組（每群組 ≥ 2 筆）。"""

    def merge_group(self, cases: list[Case]) -> Case:
        """保留 sent_time 最早的案件，其餘 CaseLog 移轉後刪除。回傳 primary 案件。"""

    def merge_all_duplicates(self) -> int:
        """執行全部群組合併，回傳刪除的案件筆數。"""
```

### 修改：`src/hcp_cms/core/case_manager.py`

`import_email()` 加入 Find-or-Create：
1. `clean = ThreadTracker.clean_subject(subject)`
2. `existing = CaseRepository.find_by_company_and_subject(company_id, clean)`
3. **有 existing** → `direction = _detect_direction(sender, subject)` → `CaseDetailManager.add_log(...)` → `reply_count += 1` → `CaseRepository.update(existing)`
4. **沒有 existing** → 原有建案流程不變

### 新增：`CaseRepository.find_by_company_and_subject()`

```python
def find_by_company_and_subject(
    self, company_id: str, clean_subject: str
) -> Case | None:
    """查詢 company_id 相同且主旨（去前綴後）相符的最早案件。
    實作：先抓該公司所有案件，Python 側逐一 clean_subject() 比對。
    """
```

### 新增：`CaseLogRepository.transfer_logs()`

```python
def transfer_logs(self, from_case_id: str, to_case_id: str) -> None:
    """將 from_case_id 的所有 CaseLog 的 case_id 改為 to_case_id。"""
```

### 修改：`src/hcp_cms/ui/settings_view.py`

「系統設定」頁加入「🔧 整合重複案件」按鈕：
- 點擊 → 呼叫 `CaseMerger(conn).merge_all_duplicates()`
- 成功 → 顯示「已整合 N 個重複案件」
- 失敗 → 顯示錯誤訊息

### 修改：方向標籤 `"CS 回覆"` → `"HCP 回覆"`

- `src/hcp_cms/data/models.py` 第 159 行（註解）
- `src/hcp_cms/ui/case_detail_dialog.py` 第 689 行（下拉選單）
- `_detect_direction()` 回傳值

---

## 方向判斷邏輯（C 方案）

```python
def _detect_direction(sender: str, subject: str) -> str:
    """判斷信件方向：優先看寄件者，其次看主旨前綴。"""
    sender_lower = sender.lower()
    if "@ares.com.tw" in sender_lower or "hcpservice" in sender_lower:
        return "HCP 回覆"
    if re.match(r'^(RE|FW|FWD|回覆|轉寄|答覆)\s*:', subject, re.IGNORECASE):
        return "HCP 回覆"
    return "客戶來信"
```

---

## 資料流

### 匯入時（Find-or-Create）

```
import_email(subject, sender, company_id, ...)
  → clean = ThreadTracker.clean_subject(subject)
  → existing = CaseRepository.find_by_company_and_subject(company_id, clean)
  → 有 existing？
      是 → direction = _detect_direction(sender, subject)
           CaseDetailManager.add_log(existing.case_id, direction, body, logged_at=sent_time)
           existing.reply_count += 1
           CaseRepository.update(existing)
      否 → 原有建案流程（不變）
```

### 整合重複案件（MergeDuplicates）

```
CaseMerger.merge_all_duplicates()
  → 找出所有 (company_id, clean_subject) 相同且數量 ≥ 2 的群組
  → 每群組：
      primary = sent_time 最早的案件（若相同則取 case_id 字典序最小）
      secondary[] = 其餘案件
      ① 將 secondary 的 case_logs 的 case_id 改為 primary.case_id
      ② primary.reply_count += sum(secondary.reply_count)
      ③ CaseRepository.update(primary)
      ④ CaseRepository.delete(secondary.case_id)（每筆）
  → 回傳刪除的案件總筆數
```

---

## 邊界條件與錯誤處理

| 情況 | 處理 |
|------|------|
| `company_id` 為 None | 略過 find-or-create，走原有建案流程 |
| 群組只有 1 筆案件 | 不合併（跳過） |
| 兩筆 `sent_time` 相同 | 保留 `case_id` 字典序較小者為 primary |
| `merge_all_duplicates` 中途失敗 | 已完成的群組保留，未完成的保留原狀，log 錯誤 |
| UI 整合時無重複案件 | 顯示「目前無重複案件」，不報錯 |

---

## 標籤變更（不做 DB Migration）

`"HCP 回覆"` 僅套用在新建的 CaseLog 記錄。現有資料庫中的 `"CS 回覆"` 歷史記錄維持不變，UI 下拉選單同時支援兩種顯示。

---

## 測試計畫

### 新增：`tests/unit/test_case_merger.py`

- `test_find_duplicate_groups_returns_groups` — 相同 company+clean_subject 的案件歸為一組
- `test_find_duplicate_groups_different_company` — 不同公司+相同主旨不算重複
- `test_find_duplicate_groups_single_case_excluded` — 單筆不被列入
- `test_merge_group_keeps_earliest` — 保留 sent_time 最早的案件
- `test_merge_group_transfers_logs` — secondary 的 CaseLog 移轉至 primary
- `test_merge_group_sums_reply_count` — reply_count 累加
- `test_merge_group_deletes_secondary` — secondary 從資料庫刪除
- `test_merge_all_duplicates_returns_count` — 回傳正確刪除筆數

### 修改：`tests/unit/test_case_manager.py`

- `test_import_email_find_existing_adds_log` — 相同 company+主旨已有案件 → 加入 CaseLog
- `test_import_email_no_match_creates_case` — 無匹配 → 建新案件
- `test_import_email_direction_hcp_reply` — `@ares.com.tw` → direction = "HCP 回覆"
- `test_import_email_direction_client` — 外部寄件者 + 無 RE: → direction = "客戶來信"

### 修改：`tests/unit/test_repositories.py`

- `test_find_by_company_and_subject_found`
- `test_find_by_company_and_subject_not_found`
- `test_find_by_company_and_subject_clean_subject_match` — RE: 前綴去除後相符
