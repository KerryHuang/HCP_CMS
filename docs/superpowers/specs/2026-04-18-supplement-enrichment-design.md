# 補充說明強化與人工編輯介面 設計規格

## 目標

提升每月大 PATCH 補充說明五欄位（修改原因、原問題、範例說明、修正後、注意事項）的自動分析準確度，並新增人工維護介面，讓使用者能在 S2T 完成後逐筆審閱與修正 AI 分析結果。

## 背景與現況

現行 `fetch_supplements` 流程：
1. 對每筆 Issue 呼叫 `MantisSoapClient.get_issue()`
2. 取得 Mantis `description` + 最後 5 條活動筆記（`notes_list`）
3. 合併為純文字傳入 `ClaudeContentService.extract_supplement()`
4. Claude 以簡單 prompt 回傳五欄位 JSON

問題：
- ReleaseNote.doc 解析出的 `description`/`impact` **未傳入** Claude
- Mantis 筆記無作者/日期標籤，Claude 無法判斷最新狀態
- Prompt 未定義欄位含義，Claude 需自行猜測
- 資料稀少時回傳空字串，使用者無法區分「真空白」與「資料不足」
- 現有 Issue 表格（紅框）無法顯示與編輯補充欄位

---

## 架構設計

### 涉及檔案

| 檔案 | 變更類型 | 職責 |
|------|----------|------|
| `src/hcp_cms/services/claude_content.py` | 修改 | 強化 `extract_supplement()` 介面與 prompt |
| `src/hcp_cms/core/monthly_patch_engine.py` | 修改 | `_fetch_supplement()` 傳入三來源結構化資料 |
| `src/hcp_cms/data/repositories.py` | 修改 | 新增 `update_issue_supplement()` |
| `src/hcp_cms/ui/patch_monthly_tab.py` | 修改 | 新增步驟按鈕 + 展開補充說明編輯器 |
| `src/hcp_cms/ui/supplement_editor_widget.py` | 新增 | 左右分割補充說明編輯器元件 |
| `src/hcp_cms/services/mantis/soap.py` | 修改 | `_parse_notes()` 上限 5→10 |
| `tests/unit/test_supplement_enrichment.py` | 新增 | 單元測試 |

---

## 功能規格

### 1. Claude 分析增強（方案 A）

#### 1.1 `ClaudeContentService.extract_supplement()` 介面調整

```python
def extract_supplement(
    self,
    release_note_description: str = "",
    release_note_impact: str = "",
    mantis_description: str = "",
    mantis_notes: list[dict] = [],   # [{"reporter": str, "date": str, "text": str}]
) -> dict[str, str]:
```

舊介面（`mantis_text: str`）整併為四個具名參數，分別對應三個資料來源。

#### 1.2 Prompt 結構

```
你是 HCP ERP 系統的技術文件分析助理。
請根據以下來自三個來源的資料，以繁體中文填寫五個補充說明欄位。

【欄位定義】
- 修改原因：此次修改的業務或技術背景，解釋「為什麼要改」
- 原問題：修改前系統存在的問題現象，解釋「原本出了什麼問題」
- 範例說明：具體操作情境或資料範例（如有）
- 修正後：修改後的行為或效果說明
- 注意事項：上線後測試重點、注意事項或相依模組

【資料：ReleaseNote 說明】
功能說明：{release_note_description}
影響說明：{release_note_impact}

【資料：Mantis 問題描述】
{mantis_description}

【資料：Mantis 活動筆記（依時間排列）】
{formatted_notes}

請以 JSON 格式回傳，key 為繁體中文欄位名稱。
若某欄位無對應內容且無法合理推斷，值填入「⚠ 資料不足，請人工補充」。
只回傳 JSON，不要其他說明。
```

#### 1.3 Mantis 筆記格式化

筆記上限由 5 增加至 10 條。格式化為：
```
[2026-03-15] 工程師 A：已修正 HRWF304.fmb 第 220 行邏輯
[2026-03-16] 測試人員 B：測試通過，確認無異常
```

空筆記時填入「（無活動記錄）」。

#### 1.4 資料不足標記（方案 C）

若三個來源合計有效文字少於 30 字（去除空白、標點後），Claude prompt 內額外加入說明：
「⚠ 注意：以上資料非常有限，若無法合理填寫請直接填入資料不足標記。」

⚠ 30 字閾值為初始估算值，實際效果需使用後調整。

---

### 2. `_fetch_supplement()` 資料整合

```python
def _fetch_supplement(
    self, iss: PatchIssue, client: MantisSoapClient, svc: ClaudeContentService
) -> dict[str, str]:
```

參數由 `issue_no: str` 改為 `iss: PatchIssue`，以取得 ReleaseNote 解析欄位：

```python
issue = client.get_issue(iss.issue_no.lstrip("0") or "0")
notes = [
    {"reporter": n.reporter, "date": n.date_submitted[:10], "text": n.text}
    for n in (issue.notes_list or [])
]
return svc.extract_supplement(
    release_note_description=iss.description or "",
    release_note_impact=iss.impact or "",
    mantis_description=issue.description if issue else "",
    mantis_notes=notes,
)
```

---

### 3. Repository 新增方法

```python
# PatchRepository
def update_issue_supplement(self, issue_id: int, supplement: dict, manual: bool = False) -> None:
    """更新 issue 的 mantis_detail 中的 supplement 欄位。
    manual=True 時一併設定 supplement_edited=True 旗標。
    """
```

`mantis_detail` JSON 結構新增 `supplement_edited: bool` 旗標，預設 False，人工儲存時設為 True。

---

### 4. 流程步驟新增

`patch_monthly_tab.py` 步驟列由：

```
① 選月份 → ② 選來源 → ③ 匯入 → ④ 編輯 → ⑤ S2T → ⑥ Excel → ⑦ 驗證 → ⑧ 通知信 → ⑨ 完成
```

改為：

```
① 選月份 → ② 選來源 → ③ 匯入 → ④ 編輯 → ⑤ S2T → ⑥ 補充說明 → ⑦ Excel → ⑧ 驗證 → ⑨ 通知信 → ⑩ 完成
```

新增「⑥ 補充說明」步驟按鈕，點擊後在主頁面下半區展開 `SupplementEditorWidget`（取代原 Issue 表格顯示區）。

---

### 5. SupplementEditorWidget（新檔案）

#### 5.1 佈局

```
┌──────────────────────────────────────────────────────────────┐
│ [🔄 重新從 Mantis 分析全部]                                  │
├──────────────────┬───────────────────────────────────────────┤
│ QListWidget      │ QScrollArea（右側編輯面板）               │
│                  │                                           │
│ ● 0017023 ✅    │  Issue 0017023 — HRWF304 薪資異常        │
│ ● 0016552 ⚠    │                                           │
│ ● 0015843 ○    │  修改原因  ┌──────────────────────────┐   │
│ ● 0018201 ✏   │            │ QTextEdit（可編輯）       │   │
│                  │            └──────────────────────────┘   │
│                  │  原問題    ┌──────────────────────────┐   │
│                  │            │                          │   │
│                  │            └──────────────────────────┘   │
│                  │  範例說明  ┌──────────────────────────┐   │
│                  │            │                          │   │
│                  │            └──────────────────────────┘   │
│                  │  修正後    ┌──────────────────────────┐   │
│                  │            │                          │   │
│                  │            └──────────────────────────┘   │
│                  │  注意事項  ┌──────────────────────────┐   │
│                  │            │                          │   │
│                  │            └──────────────────────────┘   │
│                  │                                           │
│                  │  [🔄 重新分析此 Issue]  [💾 儲存]        │
└──────────────────┴───────────────────────────────────────────┘
```

#### 5.2 左側清單狀態圖示

| 圖示 | 顏色 | 條件 |
|------|------|------|
| ✅ | 綠色 | 五欄位皆有內容且無「⚠ 資料不足」 |
| ⚠ | 橘色 | 至少一欄包含「⚠ 資料不足」標記 |
| ○ | 灰色 | `supplement` 為空（尚未分析） |
| ✏ | 藍色 | `supplement_edited = True`（已人工修改） |

優先級：✏ > ✅ > ⚠ > ○

#### 5.3 Signals

```python
class SupplementEditorWidget(QWidget):
    supplement_saved = Signal(int, dict)   # (issue_id, supplement)
    reanalyze_requested = Signal(int)      # issue_id
    reanalyze_all_requested = Signal()
```

#### 5.4 互動行為

- 點選左側列 → 右側載入該 Issue 補充欄位（未儲存變更時提示確認）
- 「💾 儲存」→ 寫回 DB（`manual=True`），左側圖示更新為 ✏
- 「🔄 重新分析此 Issue」→ 在背景執行 `_fetch_supplement()`，完成後更新右側（不覆蓋已人工標記 ✏ 的欄位，除非使用者確認）
- 「🔄 重新從 Mantis 分析全部」→ 對所有 ○/⚠ 狀態 Issue 執行批次分析，跳過 ✏ 狀態

---

## 資料流

```
scan_monthly_dir()
  └─ PatchIssue（description, impact 來自 ReleaseNote）→ DB

fetch_supplements(patch_id)
  └─ 逐筆 PatchIssue
       ├─ MantisSoapClient.get_issue() → description + notes(最多10條)
       └─ ClaudeContentService.extract_supplement(
              release_note_description,
              release_note_impact,
              mantis_description,
              mantis_notes,
          ) → 五欄位 dict
       └─ PatchRepository.update_issue_supplement(issue_id, supplement)

SupplementEditorWidget（人工編輯）
  └─ PatchRepository.update_issue_supplement(issue_id, supplement, manual=True)
```

---

## 測試範圍

| 測試 | 描述 |
|------|------|
| `test_extract_supplement_all_sources` | 三來源皆有資料時，五欄位均有輸出 |
| `test_extract_supplement_sparse_data` | 合計文字 < 30 字時，至少一欄含「⚠ 資料不足」 |
| `test_extract_supplement_no_client` | Claude client 為 None 時回傳空 dict |
| `test_update_issue_supplement_manual` | `manual=True` 時 `supplement_edited` 旗標為 True |
| `test_supplement_editor_status_icon` | 五欄位有「⚠」→ 橘色；全填 → 綠色；空 → 灰色；edited → 藍色 |
| `test_fetch_supplement_passes_release_note` | `_fetch_supplement` 正確傳入 `iss.description`/`iss.impact` |
