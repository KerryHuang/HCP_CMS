# HCP CMS 新手教學 & 測試 Checklist

逐步操作，每完成一項打勾。同時驗證系統功能是否正常運作。

---

## Phase A：啟動與基本操作

### A1. 啟動系統
```bash
cd D:\CMS
python -m hcp_cms
```
- [x] 視窗出現，標題為「HCP CMS v2.1」
- [x] 左側有 8 個導覽項目
- [x] 預設顯示儀表板頁面
- [x] 深色主題正確顯示

### A2. 瀏覽各頁面
依序點擊左側導覽列每一項：
- [x] 📊 儀表板 — 看到 4 個 KPI 卡片（全部顯示 0）
- [x] 📋 案件管理 — 看到空的案件列表 + 篩選器 + 按鈕
- [x] 📚 KMS 知識庫 — 看到搜尋框 + 空的結果表
- [x] 📧 信件處理 — 看到來源選擇、日期篩選、進度條
- [x] 🔧 Mantis 同步 — 看到 API 選擇、URL 輸入框
- [x] 📊 報表中心 — 看到報表類型選擇、年月設定
- [x] 📏 規則設定 — 看到規則類型下拉選單
- [x] ⚙️ 系統設定 — 看到使用者、資料庫、備份設定區域

### A3. 測試快捷鍵
- [x] 按 `Ctrl+Shift+K` — 應自動跳到 KMS 知識庫頁面

---

## Phase B：規則設定（先設定規則，後續分類才能運作）

### B1. 新增產品分類規則
1. 點擊左側「📏 規則設定」
2. 規則類型選「product」
3. 在下方表單填入：
   - Pattern: `WebLogic|WLS`
   - Value: `WebLogic`
   - Priority: `1`
4. 點擊「➕ 新增規則」
- [x] 規則出現在上方表格中

5. 再新增一條：
   - Pattern: `ERP|企業資源`
   - Value: `ERP`
   - Priority: `2`
- [x] 表格顯示 2 條規則，WebLogic 排在前面（priority 小的優先）

### B2. 新增問題類型規則
1. 規則類型改選「issue」
2. 依序新增：

| Pattern | Value | Priority |
|---------|-------|----------|
| `客制\|客製\|customize` | 客制需求 | 0 |
| `bug\|錯誤\|異常\|Exception` | BUG | 1 |
| `新功能\|新增\|Add feature` | NEW | 2 |
| `建議\|改善\|優化` | 建議改善 | 3 |
| `請問\|如何\|怎麼\|說明` | 邏輯咨詢 | 4 |
| `無法\|失敗\|不顯示` | 操作異常 | 5 |
| `維護\|月結\|批次` | OP | 6 |

- [x] 7 條規則全部新增成功

### B3. 新增錯誤類型規則
1. 規則類型改選「error」
2. 新增幾條：

| Pattern | Value | Priority |
|---------|-------|----------|
| `薪資\|薪水\|工資` | 薪資獎金計算 | 1 |
| `請假\|休假\|假單` | 差勤請假管理 | 2 |
| `加班\|超時\|OT` | 加班費計算 | 3 |
| `人事\|員工資料` | 人事資料管理 | 4 |
| `報表\|列印` | 報表產生 | 5 |

- [ ] 5 條規則新增成功

### B4. 新增優先級規則
1. 規則類型改選「priority」
2. 新增：
   - Pattern: `緊急|urgent|asap|\(急\)|【急】`
   - Value: `高`
   - Priority: `1`
- [ ] 規則新增成功

### B5. 新增廣播信規則
1. 規則類型改選「broadcast」
2. 新增：
   - Pattern: `維護客戶|更新公告|大PATCH|法規因應`
   - Value: `broadcast`
   - Priority: `1`
- [ ] 規則新增成功

---

## Phase C：手動建案測試

> 目前手動建案 UI 尚未完整，我們用 Python 指令測試核心功能。

### C1. 開啟終端機測試
關閉 APP，在終端機執行：

```bash
cd D:\CMS
py
```

進入 Python 互動模式後，逐行貼上：

### C2. 建立資料庫連線
```python
from hcp_cms.data.database import DatabaseManager
from pathlib import Path
import os

# 找到你的 DB 路徑
db_path = Path(os.environ.get("APPDATA", "")) / "HCP_CMS" / "cs_tracker.db"
print(f"DB 路徑: {db_path}")
print(f"DB 存在: {db_path.exists()}")

db = DatabaseManager(db_path)
db.initialize()
print("✅ 資料庫連線成功")
```
- [ ] 顯示 DB 路徑和「✅ 資料庫連線成功」

### C3. 新增客戶公司
```python
from hcp_cms.data.models import Company
from hcp_cms.data.repositories import CompanyRepository

comp_repo = CompanyRepository(db.connection)

comp_repo.insert(Company(company_id="C-ASE", name="日月光集團", domain="aseglobal.com"))
comp_repo.insert(Company(company_id="C-UNI", name="欣興電子", domain="unimicron.com"))
comp_repo.insert(Company(company_id="C-CHI", name="頎邦科技", domain="chipbond.com.tw"))

companies = comp_repo.list_all()
for c in companies:
    print(f"  {c.company_id} | {c.name} | {c.domain}")
print(f"✅ 共 {len(companies)} 家客戶")
```
- [ ] 顯示 3 家客戶資訊

### C4. 用 CaseManager 建立案件
```python
from hcp_cms.core.case_manager import CaseManager

mgr = CaseManager(db.connection)

# 案件 1：一般問題
c1 = mgr.create_case(
    subject="薪資計算異常，員工反映金額有誤",
    body="您好，我們公司員工反映本月薪資計算有 bug，加班費未列入。請協助確認。",
    sender_email="user@aseglobal.com",
    sent_time="2026/03/20 09:00",
    contact_person="王大明",
    handler="JILL",
)
print(f"✅ 案件 1: {c1.case_id} | 產品={c1.system_product} | 類型={c1.issue_type} | 錯誤={c1.error_type} | 優先={c1.priority} | 公司={c1.company_id}")
```
- [ ] 案件 ID 為 CS-2026-001
- [ ] 產品=HCP（預設）
- [ ] 類型=BUG（匹配「bug」）
- [ ] 錯誤=薪資獎金計算（匹配「薪資」）
- [ ] 優先=中
- [ ] 公司=C-ASE

### C5. 建立更多案件
```python
# 案件 2：緊急問題
c2 = mgr.create_case(
    subject="(急) 請假模組無法操作",
    body="緊急！員工請假功能完全失敗，urgent 需要 patch。",
    sender_email="hr@unimicron.com",
    sent_time="2026/03/20 14:00",
    contact_person="李小芳",
    handler="JILL",
)
print(f"✅ 案件 2: {c2.case_id} | 類型={c2.issue_type} | 錯誤={c2.error_type} | 優先={c2.priority}")

# 案件 3：客製化需求
c3 = mgr.create_case(
    subject="客製化需求：加班補休以分鐘計算",
    body="我們需要客制開發，請問如何 customize 加班補休計算方式？",
    sender_email="pm@chipbond.com.tw",
    sent_time="2026/03/21 10:00",
    contact_person="張經理",
    handler="JILL",
)
print(f"✅ 案件 3: {c3.case_id} | 類型={c3.issue_type} | SLA={c3.sla_hours}h")

# 案件 4：邏輯咨詢
c4 = mgr.create_case(
    subject="請問報表如何設定篩選條件",
    body="您好，請問月結報表的篩選條件如何設定？",
    sender_email="user2@aseglobal.com",
    sent_time="2026/03/22 08:30",
    contact_person="陳小華",
    handler="JILL",
)
print(f"✅ 案件 4: {c4.case_id} | 類型={c4.issue_type} | 錯誤={c4.error_type}")
```
- [ ] 案件 2：優先=高（匹配「急」「緊急」「urgent」）
- [ ] 案件 3：類型=客制需求（priority 0 優先於邏輯咨詢），SLA=48h
- [ ] 案件 4：類型=邏輯咨詢（匹配「請問」），錯誤=報表產生

### C6. 測試回覆與重開
```python
# 回覆案件 1
mgr.mark_replied(c1.case_id, "2026/03/20 12:00")
print(f"✅ 案件 1 已回覆")

# 模擬客戶再次來信（對話串追蹤）
c5 = mgr.create_case(
    subject="RE: 薪資計算異常，員工反映金額有誤",
    body="感謝回覆，但問題仍然存在。",
    sender_email="user@aseglobal.com",
    sent_time="2026/03/21 09:00",
)
print(f"✅ 案件 5: {c5.case_id} | linked_to={c5.linked_case_id}")

# 檢查案件 1 是否被重開
from hcp_cms.data.repositories import CaseRepository
c1_updated = CaseRepository(db.connection).get_by_id(c1.case_id)
print(f"✅ 案件 1 狀態={c1_updated.status} | reply_count={c1_updated.reply_count}")
```
- [ ] 案件 5 的 linked_case_id = CS-2026-001（指向根案件）
- [ ] 案件 1 被重開：狀態=處理中，reply_count=1

### C7. 測試儀表板統計
```python
stats = mgr.get_dashboard_stats(2026, 3)
for k, v in stats.items():
    print(f"  {k}: {v}")
```
- [ ] total = 5
- [ ] replied >= 1
- [ ] avg_frt = 3.0（案件 1 從 09:00 到 12:00 = 3 小時）

---

## Phase D：KMS 知識庫測試

### D1. 建立 QA 並搜尋
```python
from hcp_cms.core.kms_engine import KMSEngine

kms = KMSEngine(db.connection)

# 手動建立 QA
qa1 = kms.create_qa(
    question="員工薪資計算出現異常怎麼辦？",
    answer="請檢查薪資參數設定，確認加班費計算公式。",
    solution="進入 HCP > 系統設定 > 薪資參數 > 檢查計算公式是否正確。",
    keywords="薪資 計算 異常 加班費",
    system_product="HCP",
    issue_type="BUG",
    created_by="JILL",
)
print(f"✅ QA 建立: {qa1.qa_id}")

qa2 = kms.create_qa(
    question="如何設定請假規則？",
    answer="進入差勤管理模組設定假別。",
    solution="HCP > 差勤管理 > 假別設定 > 新增假別並設定天數上限。",
    keywords="請假 假別 差勤",
    system_product="HCP",
    issue_type="邏輯咨詢",
    created_by="JILL",
)
print(f"✅ QA 建立: {qa2.qa_id}")
```
- [ ] 兩個 QA 建立成功

### D2. 搜尋測試
```python
# 直接搜尋
results = kms.search("薪資異常")
print(f"搜尋「薪資異常」: {len(results)} 筆")
for r in results:
    print(f"  {r.qa_id}: {r.question[:30]}...")

# 搜尋相關詞
results2 = kms.search("請假")
print(f"搜尋「請假」: {len(results2)} 筆")
```
- [ ] 「薪資異常」找到 qa1
- [ ] 「請假」找到 qa2

### D3. 同義詞測試
```python
from hcp_cms.data.models import Synonym
from hcp_cms.data.repositories import SynonymRepository

syn_repo = SynonymRepository(db.connection)
syn_repo.insert(Synonym(word="薪水", synonym="薪資", group_name="薪資相關"))
syn_repo.insert(Synonym(word="薪水", synonym="工資", group_name="薪資相關"))
syn_repo.insert(Synonym(word="薪水", synonym="月薪", group_name="薪資相關"))
print("✅ 同義詞已設定")

# 用「薪水」搜尋，應該找到含「薪資」的 QA
results3 = kms.search("薪水")
print(f"搜尋「薪水」（同義詞擴展）: {len(results3)} 筆")
```
- [ ] 搜尋「薪水」能找到含「薪資」的 QA（同義詞擴展生效）

### D4. 從信件對話串抽取待審核 QA
```python
from hcp_cms.services.mail.base import RawEmail
from hcp_cms.services.mail.msg_reader import MSGReader

# 模擬含對話串的信件 body（我方回覆在上，客戶問題在下）
body = (
    "您好，薪資計算問題已確認，請依以下步驟操作。\n\n"
    "From: user@aseglobal.com\n"
    "Sent: 2026-03-20\n"
    "To: hcpservice@ares.com.tw\n"
    "Subject: 請問薪資如何計算\n\n"
    "請問系統薪資計算邏輯為何？"
)
ta, tq = MSGReader._split_thread(body)
raw = RawEmail(thread_question=tq, thread_answer=ta)

# 抽取為待審核 QA
pending_qa = kms.extract_qa_from_email(raw)
if pending_qa:
    print(f"✅ 抽取成功: {pending_qa.qa_id} | status={pending_qa.status}")
    print(f"   問題: {pending_qa.question}")
else:
    print("❌ 未找到對話串")

# 審核通過
approved = kms.approve_qa(pending_qa.qa_id, answer="請至 HCP > 薪資參數確認計算公式。")
print(f"✅ 審核通過: status={approved.status}")

# 搜尋應可找到
results = kms.search("薪資計算")
print(f"搜尋「薪資計算」: {len(results)} 筆")
```
- [ ] 抽取成功，status=待審核
- [ ] 審核通過後 status=已完成
- [ ] 搜尋「薪資計算」找到剛審核的 QA

---

## Phase E：報表產生測試

### E1. 產生追蹤表
```python
from hcp_cms.core.report_engine import ReportEngine
from pathlib import Path

engine = ReportEngine(db.connection)

output_dir = Path("D:/CMS/test_reports")
output_dir.mkdir(exist_ok=True)

tracking_path = engine.generate_tracking_table(
    start_date="2026/03/01",
    end_date="2026/03/31",
    output_path=output_dir / "追蹤表_202603.xlsx",
)
print(f"✅ 追蹤表: {tracking_path}")
```
- [ ] 檔案產生在 D:\CMS\test_reports\追蹤表_202603.xlsx
- [ ] 用 Excel 開啟，檢查：
  - [ ] 「客戶索引」頁籤有 3 家客戶
  - [ ] 「問題追蹤總表」有 5 筆案件
  - [ ] 「QA知識庫」有 QA 記錄
  - [ ] 有客戶獨立頁籤（如「日月光_問題」）
  - [ ] 有「Mantis提單追蹤」頁籤
  - [ ] 標題列為深藍色白字

### E2. 產生月報
```python
report_path = engine.generate_monthly_report(
    start_date="2026/03/01",
    end_date="2026/03/31",
    output_path=output_dir / "月報_202603.xlsx",
)
print(f"✅ 月報: {report_path}")
```
- [ ] 檔案產生成功
- [ ] 用 Excel 開啟，檢查：
  - [ ] 「月報摘要」有 KPI 數據（案件總數=5）
  - [ ] 「案件明細」有 5 筆
  - [ ] 「客戶分析」有各客戶統計數據

---

## Phase F：備份與還原測試

### F1. 備份
```python
from hcp_cms.data.backup import BackupManager

backup_dir = Path("D:/CMS/test_backups")
backup_mgr = BackupManager(db.connection, backup_dir)

backup_path = backup_mgr.create_backup()
print(f"✅ 備份: {backup_path}")
print(f"   大小: {backup_path.stat().st_size} bytes")
```
- [ ] 備份檔案建立成功

### F2. 匯出 ZIP
```python
zip_path = backup_mgr.export_zip(backup_dir / "hcp_cms_export.zip")
print(f"✅ ZIP 匯出: {zip_path}")
```
- [ ] ZIP 檔案建立成功

### F3. 列出備份
```python
backups = backup_mgr.list_backups()
print(f"✅ 備份數量: {len(backups)}")
for b in backups:
    print(f"   {b.name}")
```
- [ ] 列出至少 1 個備份檔

---

## Phase G：在 GUI 中驗證

### G1. 重新啟動 APP
```python
db.close()
exit()
```

```bash
python -m hcp_cms
```

### G2. 儀表板
- [ ] KPI 卡片顯示正確數據（本月案件=5，回覆率>0%）
- [ ] 最近案件表格有資料

### G3. 案件管理
1. 點擊「📋 案件管理」
2. 點擊「🔄 重新整理」
- [ ] 案件列表顯示 5 筆案件
- [ ] 點擊案件，下方顯示詳情
3. 點擊篩選選「處理中」→「🔄 重新整理」
- [ ] 只顯示處理中的案件

### G4. KMS 搜尋與待審核
1. 點擊「📚 KMS 知識庫」
2. 搜尋框輸入「薪資」按搜尋
- [ ] 顯示搜尋結果（只含已完成 QA）
3. 點擊結果，下方顯示問題/回覆/解決方案
- [ ] 詳情正確顯示
4. 切換至「待審核」分頁
- [ ] 顯示待審核 QA 列表（若有，tab 標題顯示 🔴N）
5. 點擊一筆 QA → 點「✏️ 編輯審核」
- [ ] 開啟對話框，欄位已預填問題與回覆

### G5. 規則瀏覽
1. 點擊「📏 規則設定」
2. 切換不同規則類型
- [ ] 每種類型都顯示之前新增的規則

### G6. 報表產生
1. 點擊「📊 報表中心」
2. 選「追蹤表」，年=2026，月=3
3. 點擊「📥 產生並下載」，選擇儲存位置
- [ ] Excel 檔案產生成功

---

## Phase H：進階功能測試

### H1. 案件詳情對話框
1. 在案件管理頁面，雙擊任一案件
- [ ] 開啟 3 分頁詳情對話框（基本資訊 / Mantis 關聯 / 操作日誌）
- [ ] 基本資訊分頁顯示案件所有欄位
- [ ] 修改欄位後按儲存，確認資料已更新

### H2. CSV 匯入案件
1. 準備一個包含案件資料的 CSV 檔案
2. 在案件管理頁面，點擊 CSV 匯入按鈕
- [ ] 開啟 3 步驟匯入精靈
- [ ] 步驟 1：選擇 CSV 檔案，系統正確偵測編碼
- [ ] 步驟 2：欄位對應正確顯示
- [ ] 步驟 3：預覽數量正確，匯入成功

### H3. 批次刪除案件
1. 在案件管理頁面，點擊刪除案件按鈕
2. 設定日期範圍
- [ ] 顯示符合條件的案件數量
- [ ] 確認刪除後，案件列表已更新

### H4. 自定義欄位
1. 建立一個新的自定義欄位
- [ ] 自定義欄位出現在案件詳情中
- [ ] CSV 匯入時可對應至自定義欄位

---

## Phase I：結案 Checklist

完成以上所有步驟後，確認：

- [ ] 規則設定正常運作（新增、顯示）
- [ ] 信件分類正確（產品、問題類型、錯誤類型、優先級、公司）
- [ ] 案件生命週期正常（建立→回覆→重開→結案）
- [ ] 對話串追蹤正確（RE: 信件自動關聯）
- [ ] KMS 搜尋正常（直接搜尋 + 同義詞擴展）
- [ ] 信件 QA 抽取正常（待審核流程：抽取→草稿→審核通過→搜尋可找到）
- [ ] 報表產生正確（追蹤表 + 月報）
- [ ] 備份/匯出功能正常
- [ ] CSV 匯入案件正常（3 步驟精靈）
- [ ] 批次刪除案件正常（日期範圍刪除）
- [ ] 案件詳情對話框正常（3 分頁編輯）
- [ ] 自定義欄位正常（建立、顯示、CSV 對應）
- [ ] GUI 顯示正確
- [ ] 儀表板 KPI 正確

**全部通過 = 系統驗收完成！**
