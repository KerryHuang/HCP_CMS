---
globs: "docs/superpowers/plans/**"
description: writing-plans 產出計畫時的風險評估與 [POC] 標記規則
---

# POC 風險標記規則

撰寫實作計畫（writing-plans）時，MUST 對每個 Task 評估以下兩個風險維度：

## 風險評估維度

### 技術可行性 — 高風險信號

- 首次使用的 PySide6 API 或 Widget
- 複雜的 SQL 查詢（多表 JOIN、遞迴 CTE、FTS5 進階用法）
- 跨層互動（如 Scheduler 觸發 UI 更新）
- 第三方服務整合（IMAP、Exchange、Mantis API）
- 效能敏感操作（大量資料處理、即時搜尋）

### 需求確定性 — 高風險信號

- 模糊的邊界條件（「適當處理」、「合理的預設值」）
- 多種可能的 UI 行為（使用者操作順序不確定）
- 未確認的業務規則（由使用者或 PM 決定的邏輯）
- 複雜的狀態轉換（多狀態流程、並發操作）

## 標記方式

- 任一維度為高風險 → 該 Task 標題加上 `[POC]` 標記
- 標記時 MUST 附註風險原因，格式：`[POC: <原因>]`
- 範例：`### Task 3: 信件排程引擎 [POC: 首次使用 QThread + Signal 跨線程通訊]`

## 執行規則

- `[POC]` 標記的 Task 在正式實作前，MUST 先用 `/poc` 技能驗證
- 若所有 Task 都低風險，不需要標記任何 `[POC]`
- NEVER 為了「安全起見」過度標記，只標記真正有風險的步驟
