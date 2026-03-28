# POC 驗證流程 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `/poc` 技能與 writing-plans 風險標記規則，讓開發新功能前能快速驗證技術假設與需求理解。

**Architecture:** 新增 1 個技能（`/poc`）、1 個規則（`poc-risk-assessment.md`），並修改 `.gitignore` 加入 `_poc/` 排除。技能遵循現有 SKILL.md 格式，規則遵循現有 `.claude/rules/` 格式。

**Tech Stack:** Claude Code Skills / Rules 框架

---

## 檔案結構

| 操作 | 檔案 | 職責 |
|------|------|------|
| 新增 | `.claude/skills/poc/SKILL.md` | `/poc` 技能定義：6 步驗證流程 |
| 新增 | `.claude/rules/poc-risk-assessment.md` | writing-plans 產出計畫時的風險標記規則 |
| 修改 | `.gitignore` | 加入 `_poc/` 排除 |
| 修改 | `.claude/skills/README.md` | 加入 `/poc` 技能說明 |

---

### Task 1: 新增 `/poc` 技能

**Files:**
- Create: `.claude/skills/poc/SKILL.md`

- [ ] **Step 1: 建立 `/poc` 技能檔案**

建立 `.claude/skills/poc/SKILL.md`，內容如下：

```markdown
---
name: poc
description: "Use when the user needs to verify technical feasibility or requirement assumptions before implementation. Use when user says \"POC\", \"poc\", \"驗證\", \"原型\", \"spike\", \"試做\". Use when a plan step is marked [POC]. Use before TDD implementation of uncertain features."
---

# POC 驗證

## Overview

在正式 TDD 實作前，快速驗證技術可行性或需求假設。避免實作完才發現根本性問題，減少來回修改次數。

## 觸發時機

- 手動：使用者輸入 `/poc`
- 自動：執行 writing-plans 產出的 `[POC]` 標記步驟時

## 流程

### 步驟 1：定義假設

明確列出要驗證的假設，格式：

```
假設：<要驗證的具體事項>
風險類型：技術可行性 / 需求確定性
驗證標準：<怎樣算驗證通過>
```

範例：
```
假設：PySide6 QTreeWidget 支援 drag & drop 重新排序
風險類型：技術可行性
驗證標準：能拖曳 item 到新位置，drop 後 item 順序更新
```

若使用者未提供明確假設，引導他們釐清：
- 「你想驗證什麼？」
- 「怎樣算成功？怎樣算失敗？」

### 步驟 2：判斷驗證方式

根據風險類型選擇驗證方式：

| 風險類型 | 驗證方式 | 說明 |
|----------|----------|------|
| **技術可行性** | 拋棄式原型 | 在 `_poc/` 寫最小程式碼驗證 API 行為、效能、相容性 |
| **需求確定性** | 情境列舉 | 列出邊界情境 + 預期行為，逐項與使用者確認 |
| **兩者皆有** | 先情境列舉，再原型驗證 | 先釐清需求再驗證技術 |

### 步驟 3：執行驗證

**拋棄式原型（技術可行性）：**

1. 建立 `_poc/` 目錄（若不存在）
2. 在 `_poc/` 內寫最小原型碼

```bash
mkdir -p _poc
```

原型碼規則：
- 可直接 `import` 專案模組（`from hcp_cms.xxx import Yyy`）
- 不需要遵守 TDD、lint、型別標註等品質要求
- 目標是最快速度驗證假設，不是寫產品碼
- 盡量控制在一個檔案內

執行原型：
```bash
.venv/Scripts/python.exe _poc/<原型檔名>.py
```

**情境列舉（需求確定性）：**

列出所有邊界情境，格式：

```
| # | 情境 | 預期行為 | 確認 |
|---|------|----------|------|
| 1 | <情境描述> | <預期行為> | ⬜ |
| 2 | <情境描述> | <預期行為> | ⬜ |
```

逐項與使用者確認，標記 ✅ 或修正預期行為。

### 步驟 4：記錄結論

在 `_poc/` 內建立 `FINDINGS.md`：

```markdown
# POC 結論：<假設簡述>

## 假設
<原始假設>

## 結果
- 狀態：✅ 通過 / ❌ 失敗 / ⚠️ 部分通過
- 發現：<具體發現>

## 對正式實作的影響
- <需要調整的事項>
- <新增的邊界測試案例>
- <需要修改的計畫步驟>
```

### 步驟 5：回饋到計畫

根據 POC 結論：

- 若假設通過 → 確認計畫步驟可照原訂執行
- 若假設失敗 → 調整實作方案，必要時回到 brainstorming 重新設計
- 若部分通過 → 修改計畫步驟，新增針對發現的邊界測試案例

將調整內容更新到對應的 plan 文件中。

### 步驟 6：清理

詢問使用者是否刪除 `_poc/` 內容：

```
POC 驗證完成。要清理 _poc/ 目錄嗎？
(A) 是，刪除全部
(B) 保留 FINDINGS.md，刪除原型碼
(C) 全部保留
```

執行清理：
```bash
# 選項 A
rm -rf _poc/*

# 選項 B
find _poc -type f ! -name "FINDINGS.md" -delete
```

## 關鍵原則

- 原型碼是拋棄式的，NEVER 將 `_poc/` 內的程式碼複製到正式實作
- 正式實作仍然走完整 TDD 流程（Law 3）
- `_poc/` 已被 `.gitignore` 排除，不會進版控
- 每次 POC 聚焦驗證一個假設，不要同時驗證多個

## Red Flags

| 想法 | 現實 |
|------|------|
| 「這功能很簡單不用 POC」 | 簡單功能也可能有 API 行為意外，有疑慮就驗證 |
| 「POC 碼寫得不錯，直接搬過去用」 | 原型碼缺少測試和品質保證，MUST 重新 TDD 實作 |
| 「同時驗證三個假設比較快」 | 混在一起難以判斷哪個通過哪個失敗，一次一個 |
| 「POC 不用記錄，記在腦裡就好」 | FINDINGS.md 讓未來的自己和團隊成員也能理解決策脈絡 |
```

- [ ] **Step 2: 確認技能檔案結構正確**

```bash
cat .claude/skills/poc/SKILL.md | head -5
```

預期：看到 frontmatter 的 `---`、`name: poc`、`description:`。

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/poc/SKILL.md
git commit -m "feat(skills): 新增 /poc 驗證技能

定義 6 步驗證流程：定義假設 → 判斷驗證方式 → 執行驗證 → 記錄結論 → 回饋計畫 → 清理。
支援技術可行性（拋棄式原型）與需求確定性（情境列舉）兩種驗證方式。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: 新增風險標記規則

**Files:**
- Create: `.claude/rules/poc-risk-assessment.md`

- [ ] **Step 1: 建立規則檔案**

建立 `.claude/rules/poc-risk-assessment.md`，內容如下：

```markdown
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
```

- [ ] **Step 2: 確認規則檔案結構正確**

```bash
cat .claude/rules/poc-risk-assessment.md | head -5
```

預期：看到 frontmatter 的 `---`、`globs:`、`description:`。

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/poc-risk-assessment.md
git commit -m "feat(rules): 新增 POC 風險標記規則

writing-plans 產出計畫時，對每個 Task 評估技術可行性與需求確定性，
高風險步驟標記 [POC]，正式實作前 MUST 先用 /poc 驗證。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: 修改 .gitignore 與更新 README

**Files:**
- Modify: `.gitignore`
- Modify: `.claude/skills/README.md`

- [ ] **Step 1: 在 `.gitignore` 加入 `_poc/`**

在 `.gitignore` 末尾加入：

```
_poc/
```

- [ ] **Step 2: 確認 `.gitignore` 內容正確**

```bash
grep "_poc/" .gitignore
```

預期：`_poc/`

- [ ] **Step 3: 更新 `.claude/skills/README.md`**

在 `## 開發工具` 表格中新增一行：

```markdown
| `/poc` | POC 驗證 | 技術可行性原型 + 需求情境列舉，正式實作前快速驗證假設 |
```

在底部 `技能檔案結構` 區塊中新增：

```
├── poc/SKILL.md            ← /poc
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore .claude/skills/README.md
git commit -m "chore: 加入 _poc/ 到 gitignore 並更新技能 README

- .gitignore 排除 _poc/ 目錄（POC 原型碼不進版控）
- README.md 新增 /poc 技能說明

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```
