---
name: reflect
description: "[Project] Use when the user asks to review the session for skill/rule improvements. Use when user says \"回顧\", \"reflect\", \"檢討\", \"反思\". Use after /push to analyze whether skills, rules, or CLAUDE.md need strengthening."
---

# Session 回顧

## Overview

回顧本次 session 的工作內容，分析是否需要補強技能、規則或 CLAUDE.md，讓下一次任務更清楚完整。

## 流程

### 步驟 1：前置檢查

確認本次 session 有實際工作：

```bash
git log --oneline --since="4 hours ago"
```

- 若無任何 commit，告知使用者「本次 session 無程式碼變更，跳過回顧」並結束
- 若有 commit，記錄 commit 數量（`<n>`），繼續下一步

### 步驟 2：收集資料

同時執行以下命令（平行）：

```bash
# commit 歷史
git log --oneline --since="4 hours ago"

# 變更檔案清單
git diff --stat HEAD~<n>..HEAD

# 程式碼差異
git diff HEAD~<n>..HEAD
```

同時讀取以下檔案（平行）：

- 所有 `.claude/rules/*.md`
- 所有 `.claude/skills/*/SKILL.md`
- `CLAUDE.md`（完整內容）

同時從當前對話記憶中提取：

- 本次做了什麼任務
- 遇到什麼問題或反覆修正
- 使用者給過什麼修正指示
- 有沒有重複出現的操作模式

### 步驟 3：四維度分析

逐一分析以下維度，每條建議 MUST 有具體依據（引用 commit、對話片段、或程式碼變更）：

**1. 技能（Skills）缺口：**
- 有沒有重複執行的多步驟操作，但目前沒有對應技能？
- 現有技能的流程有沒有遺漏步驟，導致本次需要額外補救？

**2. 規則（Rules）缺口：**
- 有沒有發現新的編碼慣例但 `.claude/rules/` 裡沒寫？
- 有沒有違反某種隱性慣例被使用者糾正？

**3. CLAUDE.md Law 缺口：**
- 有沒有跨層級的原則性問題反覆出現？
- 現有 law 是否需要補充細節或新增條目？

**4. CLAUDE.md 快速參考：**
- 常用指令有沒有變更（新增依賴、新的測試指令等）？
- 專案結構有沒有新增模組需要更新？

**分析原則：**
- NEVER 提泛泛的「可以考慮改善」，每條建議必須有明確的觸發事實
- 若某維度無建議則標示「無需調整」，不硬湊

### 步驟 4：呈現報告

以以下格式呈現：

```
═══════════════════════════════════
  Session 回顧報告
═══════════════════════════════════

  技能（Skills）
  [1] <動作> <目標> — <依據>

  規則（Rules）
  [2] <動作> <目標> — <依據>

  CLAUDE.md
  [3] <動作> <目標> — <依據>

  無需調整：<維度名稱>

═══════════════════════════════════
請輸入要執行的編號（如 1,3），或輸入「全部」/「跳過」：
```

### 步驟 5：委託 RCC 技能執行

使用者選擇後，依序執行選中項目。MUST 呼叫對應的 RCC 技能，NEVER 自己直接建立或修改配置檔：

| 操作 | 呼叫技能 |
|------|----------|
| 新增技能 | `rcc:writing-skills` |
| 改善既有技能 | `rcc:improving-skills` |
| 新增規則 | `rcc:writing-rules` |
| 修改 CLAUDE.md（Law / 快速參考 / 專案結構） | `rcc:writing-claude-md` |

**執行方式：**
- 將分析結果作為上下文傳給對應 RCC 技能
- 每個項目完成後簡短報告修改結果
- 若單次有多個同類型項目（如 2 條新規則），可在同一次 RCC 技能呼叫中一起處理

每個項目完成後簡短報告：
```
✓ [1] 已建立 .claude/skills/linting/SKILL.md（via rcc:writing-skills）
✓ [3] 已更新 CLAUDE.md 快速參考區塊（via rcc:writing-claude-md）
```

### 步驟 6：收尾

全部完成後：

1. 若有新增/修改技能，同步更新 `.claude/skills/README.md`
2. 顯示執行摘要
3. 提醒使用者：「變更尚未提交，可用 `/commit` 提交這些改善。」
4. NEVER 自動 commit 或 push

## Red Flags

| 想法 | 現實 |
|------|------|
| 「這次 session 太簡單不用回顧」 | 簡單 session 也可能暴露規則缺口 |
| 「硬湊幾條建議比較好看」 | 無需調整就標示無需調整，不硬湊 |
| 「直接改 CLAUDE.md 全部重寫比較快」 | 只改對應區塊，避免破壞其他內容 |
| 「建議不用附依據」 | 每條建議 MUST 有觸發事實，否則不列入 |
| 「改完直接 commit 省一步」 | 遵循 git-safety，讓使用者決定何時提交 |
