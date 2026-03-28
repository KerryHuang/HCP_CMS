---
name: push
description: "[Project] Use when the user asks to push commits to remote. Use when user says "推送", "push", "上傳". Use when commits are ready to be shared.
---

# Pushing to Remote

## Overview

推送前必須確認分支狀態、遠端同步情況，避免意外覆蓋他人工作。

## 流程

### 步驟 1：檢查狀態

同時執行：

```bash
git status
git log --oneline -5
git branch -vv
```

### 步驟 2：安全檢查

確認以下項目：

- [ ] 工作區無未提交的變更（若有，先提醒使用者）
- [ ] 確認當前分支名稱正確
- [ ] 檢查是否有 upstream 設定

### 步驟 3：同步遠端

```bash
git fetch origin
git log --oneline HEAD..origin/<branch> 2>/dev/null
```

- 若遠端有新 commit，**告知使用者**建議先 pull
- NEVER 自動執行 `git push --force`

### 步驟 4：推送

**一般推送：**
```bash
git push origin <branch>
```

**首次推送（無 upstream）：**
```bash
git push -u origin <branch>
```

**注意：** Git 安全規則（見 `.claude/rules/git-safety.md`）適用於所有 push 操作。若 push 被拒絕，說明原因並建議 pull 後重試。

### 步驟 5：驗證

```bash
git log --oneline -3
git branch -vv
```

確認遠端追蹤分支已更新。

### 步驟 6：回顧提醒

推送完成後，提示使用者：

> 「推送完成。建議執行 `/reflect` 回顧本次 session，檢討是否需要補強技能或規則。」

## Red Flags

| 想法 | 現實 |
|------|------|
| 「直接 push 不用檢查」 | 可能覆蓋遠端變更，先 fetch 確認 |
