# 案件 Header 格式化工具函數 設計規格

**日期：** 2026-05-13
**狀態：** 待確認
**關聯：** [桌面 App 推 Mantis 批次按鈕](./2026-05-13-desktop-mantis-push-design.md) — 本 spec 補強推送時的 summary / bugnote header 格式

## 背景與目標

目前推送案件到 Mantis 時，summary 直接用 `case.subject`，bugnote 第一行用 `[HCP-CMS: {case_id}] 更新`。Jill 反映應該對齊客服專區的提問格式：

```
2026/5/4 (週一) 下午 04:46【欣興】加班取小值確認
```

讓 Mantis 端 RD / PM 一眼看到「**何時**、**哪家客戶**、**什麼問題**」，與既有客服文件格式一致。

**目標**：新增通用格式化函數，套用至 Mantis 推送 summary + bugnote header。未來桌面 App 詳情視窗、報表也可重用。

## 設計決策

- **獨立工具函數**：新檔 `src/hcp_cms/core/case_formatter.py`，單一函數 `format_case_header(case, company_name) -> str`
- **嚴格模式**：缺漏 `sent_time` / `company_name` / `subject` 任一 → 拋 `ValueError`（caller 負責處理顯示警告）
- **主旨清理**：呼叫既有 `ThreadTracker.clean_subject()` 去 `RE: / FW: / 回覆: / 轉寄: / 答覆: / FWD:` 前綴
- **公司名稱由 caller 傳入**：函數本身不查 DB，純函數方便測試。MantisPushManager 呼叫前透過 `CompanyRepository.get_by_id(case.company_id)` 取 name
- **整合三處**：
  1. `MantisPushManager.push_case_as_new_ticket` 的 `summary`
  2. `MantisPushManager._build_bugnote_text` 的第一行 header
  3. `CaseView._on_push_to_mantis` 批次失敗時的 `setDetailedText`，把「缺什麼欄位」明確告知

## 格式規格

### 完整格式

```
{date} ({weekday}) {ampm} {time}【{company_name}】{clean_subject}
```

### 各欄位細則

| 欄位 | 範例 | 規則 |
|------|------|------|
| `date` | `2026/5/4` | `f"{dt.year}/{dt.month}/{dt.day}"` — **無前導 0**（5/4 不是 05/04）|
| `weekday` | `(週一)` | `["週一","週二","週三","週四","週五","週六","週日"][dt.weekday()]` |
| `ampm` | `下午` | `"上午" if dt.hour < 12 else "下午"`（中午 12:00 算下午）|
| `time` | `04:46` | 12h 制，**前導 0**。`hour_12 = dt.hour % 12 if (dt.hour % 12) else 12`；`f"{hour_12:02d}:{dt.minute:02d}"` |
| `company_name` | `欣興` | caller 傳入；空 / None → 拋 ValueError |
| `clean_subject` | `加班取小值確認` | `ThreadTracker.clean_subject(case.subject)`；空 → 拋 ValueError |

### 邊界情況

- `sent_time` 為空 / None / 解析失敗 → 拋 `ValueError("sent_time is empty or invalid")`
- `sent_time` 格式不一致（既有資料可能是 `"YYYY/MM/DD HH:MM"` 或 `"YYYY/MM/DD HH:MM:SS"`）→ 兩種都要能解析
- `company_name` 為 None / 空字串 → 拋 `ValueError("company_name is required")`
- `case.subject` 為 None / 空字串 → 拋 `ValueError("subject is empty")`
- `case.subject` 全部是前綴（如 `"RE: "`）→ `clean_subject()` 後為空 → 拋 `ValueError("subject is empty after cleaning")`

⚠ 假設 `sent_time` 為「本地時間 naive datetime」，與既有專案習慣一致（`datetime.now().strftime("%Y/%m/%d %H:%M:%S")`）。不處理時區轉換。

## 函數簽名

```python
# src/hcp_cms/core/case_formatter.py
"""案件 header 格式化工具 — 對齊客服專區提問格式。"""
from __future__ import annotations

from datetime import datetime

from hcp_cms.core.thread_tracker import ThreadTracker
from hcp_cms.data.models import Case

_WEEKDAYS = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]


def format_case_header(case: Case, company_name: str | None) -> str:
    """格式化案件 header — 「日期 (星期) 上午|下午 HH:MM【公司】主旨」。

    Args:
        case: 含 sent_time + subject 的案件
        company_name: 公司名稱（caller 從 CompanyRepository 查好傳入）

    Returns:
        如 "2026/5/4 (週一) 下午 04:46【欣興】加班取小值確認"

    Raises:
        ValueError: sent_time / company_name / subject 任一缺漏或無法解析
    """
    ...
```

## MantisPushManager 整合

### push_case_as_new_ticket

`MantisPushManager.__init__` 多注入 `CompanyRepository`：

```python
self._company_repo = CompanyRepository(conn)
```

`push_case_as_new_ticket` 內：

```python
company = self._company_repo.get_by_id(case.company_id) if case.company_id else None
company_name = company.name if company else None
try:
    summary = format_case_header(case, company_name)
except ValueError as e:
    return False, f"案件格式不完整：{e}"

ticket_id = self._client.create_issue(
    project_id=self._project_id,
    summary=summary,
    description=self._build_description(case),
    ...
)
```

### push_case_as_bugnote

`_build_bugnote_text` 第一行：

```python
def _build_bugnote_text(self, case: Case) -> str:
    company = self._company_repo.get_by_id(case.company_id) if case.company_id else None
    company_name = company.name if company else None
    try:
        header = format_case_header(case, company_name)
    except ValueError:
        # bugnote 比 ticket 容忍度高：缺資料時 fallback 為舊格式
        header = f"[HCP-CMS: {case.case_id}] 更新"

    parts = [header]
    if case.status:
        parts.append(f"【當前狀態】{case.status}")
    ...
```

⚠ bugnote header 用 fallback 而非拋例外：bugnote 是「補充推送」，不應因格式不完整而拒絕推（已有 ticket，是輔助動作）。

### push_case_as_new_ticket vs bugnote 行為差異說明

| 模式 | 格式不完整時 |
|------|------|
| 建新 ticket | **拒絕推送**，返回 (False, "案件格式不完整：...") — 因為 summary 是 ticket 的主要識別 |
| 推 bugnote | **改用 fallback 格式繼續**（`[HCP-CMS: {case_id}] 更新`）— 因為已有 ticket，bugnote 是更新 |

## CaseView UI 改動

`_on_push_to_mantis` 結果顯示，失敗訊息已用 `setDetailedText` 列出每筆案件的 error。本次無需改動 UI 程式碼——錯誤訊息「案件格式不完整：...」會自然帶出。

僅補一條 module docstring 註記，提醒使用者：
> 失敗筆數明細可展開查看「Show Details」，常見原因：案件缺寄件時間 / 客戶 / 主旨欄位。

## 測試策略

### 新檔 `tests/unit/test_case_formatter.py`

| 測試 | 覆蓋 |
|------|------|
| `test_full_format_with_all_fields` | 完整輸入產生預期字串 |
| `test_strips_re_prefix` | "RE: 印表機" → "印表機" |
| `test_strips_multiple_prefixes` | "RE: FW: 印表機" → "印表機" |
| `test_weekday_each_day` | 7 天 weekday 對映正確 |
| `test_morning` | 09:00 → "上午 09:00" |
| `test_noon` | 12:00 → "下午 12:00" |
| `test_afternoon` | 16:46 → "下午 04:46" |
| `test_midnight` | 00:30 → "上午 12:30" |
| `test_no_leading_zero_on_month_day` | "2026/5/4" 不是 "2026/05/04" |
| `test_leading_zero_on_hour` | 4:46 → "04:46" |
| `test_accepts_sent_time_with_seconds` | "YYYY/MM/DD HH:MM:SS" 格式 |
| `test_accepts_sent_time_without_seconds` | "YYYY/MM/DD HH:MM" 格式 |
| `test_raises_when_sent_time_missing` | ValueError |
| `test_raises_when_company_name_missing` | ValueError |
| `test_raises_when_subject_missing` | ValueError |
| `test_raises_when_subject_only_prefixes` | 主旨全部是 "RE: " → clean 後空 → ValueError |

### 既有 `tests/unit/test_mantis_push_manager.py` 補充

| 新增測試 | 覆蓋 |
|---|---|
| `test_push_uses_formatted_summary` | 推送時 SOAP 收到的 summary 是 format_case_header 的輸出 |
| `test_push_fails_when_case_has_no_company_link` | 案件 company_id=None → returns (False, "案件格式不完整：...") |
| `test_push_fails_when_company_id_does_not_exist` | company_id 指向不存在公司 → returns False |

### 既有測試需調整

- 既有 `setup` fixture 內所有案件沒設 `company_id`，需補上對應 Company：原本 `Case(case_id="C-1", subject="...", priority="高", handler="YOGA")` 改為加上 `company_id="CO-1"` 並先 insert `Company(company_id="CO-1", name="測試公司", ...)`。

## 工程量

**~1-1.5 小時**，3 個 Tasks：

1. **新 `format_case_header` + 16 個單元測試**（~30 分鐘）
2. **`MantisPushManager` 整合**（含 CompanyRepository 注入 + push_case_as_new_ticket / _build_bugnote_text 改動 + 既有測試 setup 補 Company）（~40 分鐘）
3. **手動 smoke test + commit + lint**（~20 分鐘）

## 風險與緩解

| 風險 | 緩解 |
|------|------|
| 既有 mantis push manager 測試大量 `Case(case_id="C-1", subject="x", handler="YOGA")` 無 company_id 會集體失敗 | Task 2 順手把所有 fixture 補上 company_id + Company insert |
| `sent_time` 格式跨年代不一致（早期可能 `"YYYY-MM-DD"` 或其他）| 加 `_parse_sent_time(s) -> datetime` 嘗試多種 strptime 格式，全失敗才拋 ValueError |
| 主旨內含 `]` 但沒 `[` 等異常字符會被 ThreadTracker.clean_subject 影響 | clean_subject 是既有函數，行為已穩定 |
| 推 bugnote 用 fallback 格式可能讓 Jill 困惑「為何 ticket summary 用新格式但 bugnote 不一定」| spec 已說明，UI 不額外提示 — 反正 bugnote 內容詳細，使用者一看就懂 |

## 後續事項（不在本次範圍）

- 桌面 App 詳情視窗 / 報表也套用同一格式：直接 `from hcp_cms.core.case_formatter import format_case_header`，呼叫即可
- 提供 `format_case_short_header(case, company_name) -> str` 變體（無時間，只「【公司】主旨」）給清單頁使用
- 客服 Web Portal 案件詳情頁也用此格式
