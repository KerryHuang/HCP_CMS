---
name: publish
description: "[Project] Use when the user asks to verify a release locally before distribution. Use when user says \"發行驗證\", \"publish\", \"驗證版本\", \"本地驗證\". Use when a build is complete and needs pre-distribution validation."
---

# Local Publish Verification

## Overview

在將建置產出交付給使用者前，執行完整的本地驗證流程，確保發行品質。

## 流程

### 步驟 1：版本一致性檢查

確認版本號在所有位置一致：

```bash
# pyproject.toml 的版本
grep 'version' pyproject.toml | head -1

# __init__.py 的版本
grep '__version__' src/hcp_cms/__init__.py
```

兩處版本號 MUST 一致。若不一致，**停止發行**並修正。

### 步驟 2：完整品質檢查

MUST 全部通過才能繼續：

```bash
# 1. 測試
.venv/Scripts/python.exe -m pytest tests/ -v

# 2. Lint
.venv/Scripts/ruff.exe check src/ tests/

# 3. 格式化
.venv/Scripts/ruff.exe format --check src/ tests/

# 4. 型別檢查
.venv/Scripts/python.exe -m mypy src/hcp_cms/
```

若任何檢查失敗，**停止發行**，告知使用者具體問題。

### 步驟 3：建置

```bash
.venv/Scripts/python.exe scripts/build.py
```

確認建置成功：
```bash
ls dist/HCP_CMS/HCP_CMS.exe && echo "建置成功" || echo "建置失敗，停止發行"
```

### 步驟 4：驗證打包內容

檢查關鍵檔案是否存在：

```bash
# 主程式
ls dist/HCP_CMS/HCP_CMS.exe

# 語系檔
ls dist/HCP_CMS/hcp_cms/i18n/zh_TW.json
ls dist/HCP_CMS/hcp_cms/i18n/en.json
```

缺少任何關鍵檔案 → **停止發行**並回報。

### 步驟 5：啟動測試

```bash
# 嘗試啟動（會開啟 GUI 視窗）
dist/HCP_CMS/HCP_CMS.exe
```

**告知使用者**：
- 程式即將啟動，請確認以下項目：
  1. 視窗是否正常顯示
  2. 側邊導覽列是否完整
  3. 儀表板是否正常載入
  4. 切換各頁面是否正常
- 確認完畢後關閉視窗

**等待使用者回報結果**，NEVER 自行判定通過。

### 步驟 6：產出驗證報告

所有檢查通過後，產出驗證報告：

```
═══════════════════════════════════════
  HCP CMS v<版號> 發行驗證報告
═══════════════════════════════════════
  日期：<今天日期>
  分支：<當前分支>
  Commit：<最新 commit hash>
───────────────────────────────────────
  [✓] 版本一致性（pyproject.toml / __init__.py）
  [✓] 測試通過（N 個測試）
  [✓] Lint 通過（ruff check）
  [✓] 格式檢查通過（ruff format）
  [✓] 型別檢查通過（mypy）
  [✓] 建置成功（PyInstaller）
  [✓] 打包內容完整（exe + i18n）
  [✓] 啟動測試通過（使用者確認）
───────────────────────────────────────
  結論：✓ 可以發行
═══════════════════════════════════════
```

若有任何項目未通過，將 `[✓]` 改為 `[✗]` 並標註原因，結論改為 `✗ 不可發行`。

### 步驟 7：交付準備

驗證通過後，告知使用者：

- 發行包位置：`dist/HCP_CMS/`
- 可將整個 `HCP_CMS/` 目錄壓縮後交付
- 建議壓縮指令：

```bash
cd dist && tar -czf HCP_CMS_v<版號>.tar.gz HCP_CMS/
```

**詢問使用者**是否需要：
1. 打 Git 標籤（`/release` 流程）
2. 推送到遠端（`/push` 流程）

## Red Flags

| 想法 | 現實 |
|------|------|
| 「測試過了直接發」 | 版本一致性、打包內容、啟動測試都要驗 |
| 「啟動畫面正常就好」 | 使用者必須確認各頁面都正常 |
| 「驗證報告太囉嗦」 | 報告是發行品質的證據，不可省略 |
| 「不用等使用者確認」 | GUI 測試只有人類能判定，MUST 等回報 |
