---
name: pull
description: "[Project] Use when the user asks to pull changes from remote. Use when user says "拉取", "pull", "同步", "更新分支". Use when needing to sync with remote repository.
---

# Pulling from Remote

## Overview

拉取遠端變更前必須確認本地狀態，避免未提交的變更遺失或產生意外衝突。

## 流程

### 步驟 1：檢查本地狀態

```bash
git status
git stash list
```

### 步驟 2：處理未提交變更

**若有未提交的變更：**
- 告知使用者有未提交的變更
- 提供選項：
  1. 先 commit 再 pull
  2. 先 stash 再 pull
  3. 取消 pull
- **等待使用者選擇**，NEVER 自動決定

**若工作區乾淨：** 直接進入步驟 3

### 步驟 3：檢查遠端變更

```bash
git fetch origin
git log --oneline HEAD..origin/<branch>
```

- 顯示遠端有哪些新 commit
- 若無新 commit，告知使用者已是最新

### 步驟 4：拉取變更

```bash
git pull origin <branch>
```

### 步驟 5：處理衝突（若有）

若 pull 產生衝突：

1. 列出衝突檔案：`git diff --name-only --diff-filter=U`
2. 逐一顯示衝突內容
3. **詢問使用者**如何解決每個衝突
4. NEVER 自動選擇 ours 或 theirs
5. 解決後：`git add <檔案>` → `git commit`

### 步驟 6：驗證

```bash
git log --oneline -5
git status
```

確認 pull 成功且工作區乾淨。若之前有 stash：

```bash
git stash pop
```

並確認 stash 還原成功。

## Red Flags

| 想法 | 現實 |
|------|------|
| 「直接 pull 不用管本地變更」 | 可能遺失未提交的工作 |
| 「衝突直接用 theirs 覆蓋」 | 可能丟失本地重要修改，問使用者 |
| 「自動 stash 比較方便」 | 使用者可能不想 stash，先詢問 |
