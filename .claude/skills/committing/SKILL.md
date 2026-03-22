---
name: commit
description: "[Project] Use when the user asks to commit, stage, or save changes to git. Use when user says "提交", "commit", "存檔". Use when implementation is complete and changes need to be committed.
---

# Committing Changes

## Overview

提交變更時必須遵循專案慣例：繁體中文訊息、具名檔案 staging、新 commit 而非 amend。

## 流程

### 步驟 1：檢查狀態

同時執行以下命令（平行）：

```bash
git status
git diff --stat
git diff --cached --stat
git log --oneline -5
```

### 步驟 2：分析變更

- 確認哪些檔案需要 stage
- 檢查是否有不該提交的檔案（`.env`、`__pycache__`、`*.pyc`、大型二進位檔）
- 若有可疑檔案，**詢問使用者**再決定

### 步驟 3：Stage 檔案

- MUST 使用 `git add <具體檔案>` 逐一加入
- NEVER 使用 `git add .` 或 `git add -A`
- 若檔案很多，可分批但必須列出每個檔案

### 步驟 4：撰寫 Commit 訊息

**格式要求：**

```
<類型>: <簡述>（繁體中文）

<詳細說明>（選填，繁體中文）

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
```

**類型對照：**

| 類型 | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修復錯誤 |
| `refactor` | 重構（不改行為） |
| `test` | 測試相關 |
| `docs` | 文件更新 |
| `chore` | 雜項（依賴、設定） |
| `style` | 格式調整 |

**規則：**
- 簡述和詳細說明 MUST 使用繁體中文
- 類型前綴使用英文（`feat`、`fix` 等）
- 簡述控制在 50 字元內
- MUST 包含 `Co-Authored-By` 行

### 步驟 5：建立 Commit

```bash
git commit -m "$(cat <<'EOF'
<類型>: <繁體中文簡述>

<繁體中文詳細說明>

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

- MUST 使用 HEREDOC 格式確保換行正確
- NEVER 使用 `--amend`（除非使用者明確要求）
- NEVER 使用 `--no-verify`（hook 失敗應修正問題）
- Hook 失敗後，修正問題、重新 stage、建立**新** commit

### 步驟 6：驗證

```bash
git log --oneline -1
git status
```

確認 commit 成功且工作區乾淨。

## Red Flags

| 想法 | 現實 |
|------|------|
| 「用英文寫 commit 訊息比較快」 | Law 1 要求繁體中文，無例外 |
| 「git add . 比較方便」 | 可能誤加敏感檔案，逐一加入 |
| 「hook 失敗用 --amend 修」 | amend 會改到前一個 commit，必須新建 |
| 「Co-Authored-By 不重要」 | 專案慣例，必須包含 |
