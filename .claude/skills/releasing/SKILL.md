---
name: release
description: "[Project] Use when the user asks to release, publish, or create a new version. Use when user says "發行", "release", "發佈新版", "版本更新". Use when preparing a release package for deployment.
---

# Releasing a New Version

## Overview

建立新版本發行：更新版號、建置執行檔、打 Git 標籤。此為桌面應用，不發佈到 PyPI。

## 流程

### 步驟 1：確認所有檢查通過

MUST 依序執行：

```bash
# 測試
.venv/Scripts/python.exe -m pytest tests/ -v

# Lint
.venv/Scripts/ruff.exe check src/ tests/

# 型別檢查
.venv/Scripts/python.exe -m mypy src/hcp_cms/
```

所有檢查 MUST 通過才能繼續。

### 步驟 2：更新版本號

版本號在 `pyproject.toml` 的 `version` 欄位：

```toml
[project]
version = "2.0.0"
```

**版號規則（語意化版本）：**

| 變更類型 | 版號位置 | 範例 |
|----------|----------|------|
| 重大變更（不相容） | 主版號 | 2.0.0 → 3.0.0 |
| 新功能（向下相容） | 次版號 | 2.0.0 → 2.1.0 |
| 修正錯誤 | 修訂號 | 2.0.0 → 2.0.1 |

**詢問使用者**要更新哪個版號位置，NEVER 自行決定。

### 步驟 3：提交版本更新

```bash
git add pyproject.toml
git commit -m "$(cat <<'EOF'
chore: 更新版本號至 <新版號>

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

### 步驟 4：建置執行檔

```bash
.venv/Scripts/python.exe scripts/build.py
```

驗證建置成功：
```bash
ls dist/HCP_CMS/HCP_CMS.exe && echo "建置成功"
```

### 步驟 5：打 Git 標籤

```bash
git tag -a v<版號> -m "Release v<版號>"
```

### 步驟 6：推送（詢問使用者）

**詢問使用者**是否要推送到遠端：

```bash
git push origin <branch>
git push origin v<版號>
```

NEVER 自動推送，等待使用者確認。

## Red Flags

| 想法 | 現實 |
|------|------|
| 「測試沒全過但急著發行」 | 不通過測試的版本不能發行 |
| 「版號我自己決定就好」 | 版號影響使用者，必須問使用者 |
| 「標籤之後再打」 | 標籤是發行的一部分，建置完就打 |
| 「直接 push 省時間」 | 推送前必須讓使用者確認 |
