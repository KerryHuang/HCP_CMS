# Session 回顧技能設計

## 概述

建立 `/reflect` 技能，在每次 session 結束（通常是 `/push` 之後）回顧本次工作，分析是否需要補強專案的技能、規則或 CLAUDE.md，讓下一次任務能更清楚完整。

## 觸發方式

### `/reflect` 獨立技能

- 技能檔：`.claude/skills/reflecting/SKILL.md`
- 觸發詞：`/reflect`、「回顧」、「檢討」、「反思」
- 可在任何時候手動呼叫

### `/push` 嵌入提示

在 `/push` 步驟 5（驗證）之後新增提示：

> 「推送完成。建議執行 `/reflect` 回顧本次 session，檢討是否需要補強技能或規則。」

### 前置條件

- 必須在有實際工作的 session 中（不是只聊天）
- 若 git log 顯示本次無新 commit，提示「本次 session 無程式碼變更，跳過回顧」

## 資料收集

技能觸發後，第一步同時收集以下資料：

### Git 資料（平行執行）

```bash
# 本次 session 的 commit（取最近 push 範圍）
git log --oneline origin/<branch>..HEAD
# 若已 push，改用最近一段時間的 commit
git log --oneline --since="4 hours ago"

# 變更的檔案清單
git diff --stat HEAD~<n>..HEAD

# 實際程式碼差異
git diff HEAD~<n>..HEAD
```

### 現有配置（平行讀取）

- 所有 `.claude/rules/*.md`
- 所有 `.claude/skills/*/SKILL.md`
- `CLAUDE.md`（law 區塊 + 快速參考）

### 對話上下文

直接從當前對話記憶中提取：

- 本次做了什麼任務
- 遇到什麼問題或反覆修正
- 使用者給過什麼修正指示（feedback）
- 有沒有重複出現的操作模式

## 分析邏輯

針對四個維度逐一分析：

### 1. 技能（Skills）缺口

- 本次 session 有沒有重複執行的多步驟操作，但目前沒有對應技能？
- 現有技能的流程有沒有遺漏步驟，導致本次需要額外補救？
- 例：反覆手動做「跑 lint → 修 lint 錯誤 → 重跑」→ 建議新增 `/lint` 技能

### 2. 規則（Rules）缺口

- 本次 session 有沒有發現新的編碼慣例但 `.claude/rules/` 裡沒寫？
- 有沒有違反某種隱性慣例被使用者糾正？
- 例：使用者糾正「scheduler 層不該直接呼叫 UI」→ 建議新增 `scheduler-layer.md` 規則

### 3. CLAUDE.md Law 缺口

- 本次 session 有沒有跨層級的原則性問題反覆出現？
- 現有 law 是否需要補充細節或新增條目？
- 例：多次處理 i18n 翻譯但沒有統一規範 → 建議新增 Law

### 4. CLAUDE.md 快速參考

- 常用指令有沒有變更（新增依賴、新的測試指令等）？
- 專案結構有沒有新增模組需要更新？

### 分析原則

- 只提有具體依據的建議（引用 commit、對話片段、或程式碼變更）
- 不提泛泛的「可以考慮改善」，每條建議必須有明確的觸發事實
- 若某維度無建議則標示「無需調整」，不硬湊

## 建議呈現

分析完後，以分類報告呈現：

```
═══════════════════════════════════
  Session 回顧報告
═══════════════════════════════════

  技能（Skills）
  [1] 新增 /lint 技能 — 本次反覆手動執行 ruff check + 修正流程
  [2] 更新 /test 技能 — 缺少「只跑單一檔案」的快捷步驟

  規則（Rules）
  [3] 新增 scheduler-layer.md — 本次踩到 scheduler 直接呼叫 UI 的問題

  CLAUDE.md
  [4] 快速參考新增 ruff 指令 — 本次多次手動查找 lint 指令

  無需調整：Law 區塊

═══════════════════════════════════
請輸入要執行的編號（如 1,3,4），或輸入「全部」/「跳過」：
```

## 使用者選擇後執行

委託對應的 RCC 技能執行，不自行直接建立或修改配置檔：

| 操作 | 呼叫技能 |
|------|----------|
| 新增技能 | `rcc:writing-skills` |
| 改善既有技能 | `rcc:improving-skills` |
| 新增規則 | `rcc:writing-rules` |
| 修改 CLAUDE.md（Law / 快速參考 / 專案結構） | `rcc:writing-claude-md` |

- 將分析結果作為上下文傳給對應 RCC 技能
- 每個項目完成後簡短報告修改結果
- 若單次有多個同類型項目，可在同一次 RCC 技能呼叫中一起處理
- 全部完成後顯示執行摘要
- 不自動 commit，提醒使用者可用 `/commit` 提交變更
