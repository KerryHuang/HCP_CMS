---
name: update-docs
description: "[Project] Use when the user asks to update documentation, sync docs with code, or refresh project files. Use when user says \"更新文件\", \"update docs\", \"同步文件\", \"文件更新\". Use after significant code changes that may have made documentation outdated."
---

# Updating Project Documentation

## Overview

確保所有專案文件與目前程式碼同步。文件過時比沒有文件更危險。

## 文件清單

以下是需要檢查和更新的所有文件：

| 文件 | 路徑 | 內容 |
|------|------|------|
| README.md | `README.md` | 專案概述、快速開始、架構、技術棧 |
| CLAUDE.md | `CLAUDE.md` | 開發法則、專案結構、快速參考 |
| 藍圖 | `docs/blueprint.md` | 技術棧、依賴版本 |
| 操作手冊 | `docs/operation-manual.md` | 使用者操作指引 |
| 新手教學 | `docs/getting-started-checklist.md` | 啟動測試 checklist |
| Skills README | `.claude/skills/README.md` | 技能總覽 |

## 流程

### 步驟 1：收集程式碼現況

同時執行以下命令收集最新狀態：

```bash
# 版本號
grep 'version' pyproject.toml | head -1
grep '__version__' src/hcp_cms/__init__.py

# 依賴
grep -A 20 'dependencies' pyproject.toml

# 目錄結構
ls src/hcp_cms/
ls src/hcp_cms/ui/
ls src/hcp_cms/core/
ls src/hcp_cms/data/
ls src/hcp_cms/services/
ls src/hcp_cms/scheduler/

# 測試結構
ls tests/unit/
ls tests/integration/
```

### 步驟 2：逐一比對文件

對每份文件：

1. **讀取**文件內容
2. **比對**程式碼現況
3. **列出**過時或不正確的部分
4. 向使用者**報告**差異

格式：
```
📄 <文件名>
  ✓ 版本號正確
  ✗ 專案架構缺少新增的 xxx 模組
  ✗ 快速開始指令與 CLAUDE.md 不一致
```

### 步驟 3：確認更新範圍

將所有發現的差異彙總，**詢問使用者**：
- 哪些文件要更新
- 是否有其他需要修改的內容

NEVER 自動更新所有文件，等待使用者確認範圍。

### 步驟 4：逐一更新

按照使用者確認的範圍，逐一更新文件。

**更新原則：**
- 保持現有文件風格和語調
- 只修改過時的部分，NEVER 重寫整份文件
- 版本號、指令、路徑必須與程式碼一致
- 所有內容使用繁體中文

### 步驟 5：交叉驗證

更新完成後，確認文件之間的一致性：

| 檢查項目 | 涉及文件 |
|----------|----------|
| 版本號一致 | `pyproject.toml` ↔ `__init__.py` ↔ `README.md` ↔ `blueprint.md` |
| 啟動指令一致 | `CLAUDE.md` ↔ `README.md` ↔ `getting-started-checklist.md` |
| 依賴版本一致 | `pyproject.toml` ↔ `blueprint.md` ↔ `README.md` |
| 目錄結構一致 | 實際檔案 ↔ `CLAUDE.md` ↔ `README.md` |
| 技能清單一致 | `.claude/skills/` ↔ `.claude/skills/README.md` |

### 步驟 6：報告結果

產出更新摘要：

```
═══════════════════════════════════
  文件更新報告
═══════════════════════════════════
  已更新：
    ✓ README.md — 更新版本號、新增 xxx 模組
    ✓ blueprint.md — 更新依賴版本
  未變更：
    — operation-manual.md（已是最新）
  需人工確認：
    ⚠ getting-started-checklist.md — 新功能的測試步驟需補充
═══════════════════════════════════
```

## Red Flags

| 想法 | 現實 |
|------|------|
| 「只更新 README 就好」 | 所有文件都要檢查，版本號可能散落多處 |
| 「自動全部更新省時間」 | 必須讓使用者確認範圍，避免改壞文件 |
| 「文件不重要，程式碼才重要」 | 過時文件誤導新人，比沒文件更危險 |
| 「重寫整份比較快」 | 只改過時的部分，保留原有風格 |
