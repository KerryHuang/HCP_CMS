# Phase 2：Core 業務邏輯 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 實作 HCP CMS 的核心業務邏輯層，包含分類引擎、匿名化、案件管理、KMS 搜尋引擎、對話串追蹤。這些模組依賴 Phase 1 的 Data 層，並為 Phase 3+ 的 Services/UI 層提供業務 API。

**Architecture:** Core 層不依賴 UI 或外部服務，僅依賴 Data 層的 Repository 和 FTS。每個模組職責單一，透過明確介面互相協作。

**Tech Stack:** Python 3.10+, sqlite3, jieba, re, openpyxl, pytest

**Spec:** `docs/superpowers/specs/2026-03-22-hcp-cms-refactor-design.md` Sections 5-7

**Phase 1 已完成：** DatabaseManager, Models, Repositories, FTSManager, BackupManager, MergeManager, MigrationManager (96 tests pass)

---

## 檔案結構

```
src/hcp_cms/core/
├── __init__.py
├── classifier.py        # 多維分類引擎（product/issue/error/priority）
├── anonymizer.py        # PII 匿名化（16 條規則）
├── case_manager.py      # 案件 CRUD 高階操作 + 狀態流轉
├── kms_engine.py        # KMS 搜尋 + QA 管理 + Excel 匯入匯出
├── thread_tracker.py    # 對話串追蹤（根案件辨識、linked_case_id）
└── report_engine.py     # Excel 報表產生（追蹤表 + 月報）

tests/unit/
├── test_classifier.py
├── test_anonymizer.py
├── test_case_manager.py
├── test_kms_engine.py
├── test_thread_tracker.py
└── test_report_engine.py
```

---

### Task 1: Core 套件初始化 + Classifier 分類引擎

**Files:**
- Create: `src/hcp_cms/core/__init__.py`
- Create: `src/hcp_cms/core/classifier.py`
- Create: `tests/unit/test_classifier.py`

**Classifier 功能：**
- `classify(subject, body, sender_email)` → dict with system_product, issue_type, error_type, priority, company_id, is_broadcast
- 從 DB 讀取 classification_rules 表，依 priority 排序，第一個 regex match 取值
- 支援 product / issue / error / priority / broadcast 五種 rule_type
- 公司識別：從 sender email domain 查 companies 表
- subject + body 前 300 字作為比對文本

**Tests:**
- test_classify_product（regex match → HCP/WebLogic/ERP）
- test_classify_issue_type（match → BUG/NEW/客制需求/OTH）
- test_classify_error_type（match → 功能模組）
- test_classify_priority（高優先關鍵字 → 高，否則 → 中）
- test_classify_broadcast（廣播關鍵字 → is_broadcast=True）
- test_classify_company（sender domain → company_id lookup）
- test_classify_no_match_uses_defaults
- test_classify_uses_first_match（priority ordering）

---

### Task 2: Anonymizer 匿名化引擎

**Files:**
- Create: `src/hcp_cms/core/anonymizer.py`
- Create: `tests/unit/test_anonymizer.py`

**Anonymizer 功能：**
- `anonymize(text, company_domain, company_aliases, person_names)` → str
- 16 條正則規則依序套用（spec F04）：
  1. email → [email]
  2. URL → [URL]
  3. IP → [IP]
  4. 稱謂+姓名（您好 XXX）→ 您好
  5. 寄件人簽名行（From: / 寄件人：）→ 略
  6. 完整姓名+公司 → 相關人員
  7. 客戶公司英文域名 → 貴客戶
  8. CS 人員識別詞 → 略
  9. Hi/Hello [英文名] → Hi
  10. 敬啟者/致 → 略
  11. Best regards/Thanks + 姓名 → 略
  12. 職稱+中文姓名 → 相關人員
  13. 姓名|職稱格式 → （簽名已略）
  14. 獨立英文人名 → 相關人員
  15. 公司中文別名 → 貴客戶
  16. 獨立 2-4 中文字（姓名）→ 相關人員

**Tests:**
- test_anonymize_email（email 地址替換）
- test_anonymize_url
- test_anonymize_ip
- test_anonymize_greeting_name（您好 王大明 → 您好）
- test_anonymize_company_domain（aseglobal.com → 貴客戶）
- test_anonymize_company_alias（日月光集團 → 貴客戶）
- test_anonymize_job_title_name（工程師 陳小華 → 相關人員）
- test_anonymize_english_name（Hi John → Hi）
- test_anonymize_signature_block（Best regards, John → 略）
- test_anonymize_preserves_content（正常文字不被修改）

---

### Task 3: CaseManager 案件管理

**Files:**
- Create: `src/hcp_cms/core/case_manager.py`
- Create: `tests/unit/test_case_manager.py`

**CaseManager 功能：**
- `create_case(email_data, classifier, anonymizer)` → Case
  - 呼叫 classifier.classify() 取得分類結果
  - 呼叫 thread_tracker 辨識對話串
  - 建立案件，存入 DB，建立 FTS 索引
- `update_case(case_id, **fields)` → Case
- `mark_replied(case_id, reply_time)` — 設定 replied=是, actual_reply, status=已回覆
- `reopen_case(case_id, reason)` — 已回覆 → 處理中, reply_count+1, notes 追加
- `close_case(case_id)` — status=已完成
- `get_dashboard_stats(year, month)` → dict (total, replied, pending, reply_rate, avg_frt)
- FRT 計算：actual_reply - sent_time（小時），排除 >720h

**Tests:**
- test_create_case_from_email_data
- test_mark_replied
- test_reopen_case（已回覆 → 處理中, reply_count+1）
- test_close_case
- test_dashboard_stats（total, replied, pending, reply_rate）
- test_frt_calculation
- test_frt_excludes_outliers（>720h 排除）

---

### Task 4: ThreadTracker 對話串追蹤

**Files:**
- Create: `src/hcp_cms/core/thread_tracker.py`
- Create: `tests/unit/test_thread_tracker.py`

**ThreadTracker 功能：**
- `find_thread_parent(company_id, subject, mantis_id)` → Case | None
  - 比對依據：① Mantis 票號相同 ② 同公司 + 主旨相似（去除 RE:/FW:）
- `clean_subject(subject)` → str — 去除 RE:/FW:/回覆:/轉寄: 前綴
- `subjects_match(s1, s2)` → bool — 清理後比對
- `link_to_parent(child_case, parent_case)` — 設定 linked_case_id, 更新 reply_count

**Tests:**
- test_clean_subject（RE: FW: 移除）
- test_subjects_match（清理後相同 → True）
- test_subjects_not_match
- test_find_parent_by_mantis_id
- test_find_parent_by_subject_similarity
- test_find_parent_no_match → None
- test_link_to_parent（linked_case_id 設定, reply_count 遞增）

---

### Task 5: KMSEngine 知識管理引擎

**Files:**
- Create: `src/hcp_cms/core/kms_engine.py`
- Create: `tests/unit/test_kms_engine.py`

**KMSEngine 功能：**
- `search(query, filters)` → list[QAKnowledge] — FTS5 搜尋 + 從 DB 取完整記錄
- `create_qa(question, answer, solution, ...)` → QAKnowledge — 建立 + FTS 索引
- `update_qa(qa_id, **fields)` → QAKnowledge — 更新 + 重建 FTS 索引
- `delete_qa(qa_id)` — 刪除 + 移除 FTS 索引
- `auto_extract_qa(case, anonymizer)` → QAKnowledge | None — 偵測詢問句型，自動建立待審核 QA
- `import_from_excel(file_path)` → int — 批次匯入，回傳匯入筆數
- `export_to_excel(file_path, qa_list)` — 匯出為 Excel

**Tests:**
- test_search_returns_full_qa_objects
- test_create_qa_with_fts_index
- test_update_qa_rebuilds_index
- test_delete_qa_removes_index
- test_auto_extract_qa_detects_question（含「請問」→ 自動建立）
- test_auto_extract_qa_no_question → None
- test_import_export_excel_roundtrip

---

### Task 6: ReportEngine 報表引擎

**Files:**
- Create: `src/hcp_cms/core/report_engine.py`
- Create: `tests/unit/test_report_engine.py`

**ReportEngine 功能：**
- `generate_tracking_table(year, month, output_path)` → Path
  - 頁籤：客戶索引、問題追蹤總表、QA 知識庫、各客戶分頁、客制需求
- `generate_monthly_report(year, month, output_path)` → Path
  - 頁籤：月報摘要（KPI）、案件明細、各客戶、未結案、Mantis 進度
- 使用 openpyxl 產生 .xlsx
- 延續原系統樣式：微軟正黑體、深藍標題(1E3A5F)、交替行色(F9FAFB)

**Tests:**
- test_generate_tracking_table_creates_xlsx
- test_tracking_table_has_expected_sheets（客戶索引、總表、QA）
- test_generate_monthly_report_creates_xlsx
- test_monthly_report_kpi_calculation（案件總數、回覆率）
- test_report_with_no_data（0 筆 → 仍產生空報表）
- test_report_style_applied（字型、顏色驗證）

---

### Task 7: 整合測試 + Core 層驗證

**Files:**
- Create: `tests/integration/test_core_layer.py`

**整合測試：**
- test_email_to_case_to_qa_workflow（模擬信件 → 分類 → 建案 → 自動抽取 QA → 搜尋）
- test_thread_tracking_workflow（根案件 → 後續來信 → link → reopen）
- test_report_generation_with_real_data（建立案件 → 產生追蹤表 → 驗證內容）

驗證：
- `py -m pytest -v` 全部通過
- `py -m ruff check src/hcp_cms/core/`
- `py -m mypy src/hcp_cms/core/ --ignore-missing-imports`

---

## Phase 2 完成標準

- [ ] 所有 7 個 Task 完成
- [ ] `py -m pytest -v` 全部通過
- [ ] `py -m ruff check` 無錯誤
- [ ] Classifier 能依 DB 規則分類信件
- [ ] Anonymizer 能處理 16 條匿名化規則
- [ ] CaseManager 能建案、回覆、重開、關閉
- [ ] ThreadTracker 能辨識對話串
- [ ] KMSEngine 能搜尋、CRUD、Excel 匯入匯出
- [ ] ReportEngine 能產生追蹤表和月報 Excel
