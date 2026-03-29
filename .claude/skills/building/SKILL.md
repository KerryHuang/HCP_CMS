---
name: build
description: "[Project] Use when the user asks to build, package, or create an executable. Use when user says "打包", "build", "編譯", "建置", "產生執行檔". Use when preparing the application for distribution.
---

# Building the Application

## Overview

使用 PyInstaller 將 HCP CMS 打包成 Windows 可執行檔 (.exe)，可在沒有 Python 環境的電腦上執行。

## 前置條件

```bash
# 確認虛擬環境和 PyInstaller
.venv/Scripts/pip.exe show pyinstaller || echo "需要安裝: pip install -e '.[dev]'"
```

## 建置流程

### 步驟 1：確認測試通過

建置前 MUST 先跑完所有測試：

```bash
.venv/Scripts/python.exe -m pytest tests/ -v
```

若有失敗，先修正再建置。NEVER 在測試失敗時建置。

### 步驟 2：確認 Lint 通過

```bash
.venv/Scripts/ruff.exe check src/ tests/
```

### 步驟 3：清除舊建置產出

MUST 在建置前清除，否則 PyInstaller 遇到舊 dist 目錄會報錯中止：

```bash
rm -rf build/ dist/ *.spec
```

### 步驟 4：執行建置

```bash
.venv/Scripts/python.exe scripts/build.py
```

**建置參數（由 `scripts/build.py` 控制）：**

| 參數 | 值 | 說明 |
|------|-----|------|
| `--name` | `HCP_CMS` | 執行檔名稱 |
| `--windowed` | — | 不顯示終端機視窗 |
| `--onedir` | — | 輸出為目錄（非單一檔案） |
| `--add-data` | `i18n`, `resources` | 打包語系檔和資源 |
| 入口 | `src/hcp_cms/__main__.py` | 程式進入點 |

### 步驟 5：驗證產出

```bash
ls dist/HCP_CMS/ 2>/dev/null && echo "建置成功" || echo "建置失敗"
```

建置成功後，執行檔位於 `dist/HCP_CMS/HCP_CMS.exe`。

## 產出目錄結構

```
dist/
└── HCP_CMS/
    ├── HCP_CMS.exe      # 主程式
    ├── hcp_cms/i18n/     # 語系檔
    ├── resources/        # 資源檔
    └── ...               # 相依套件 DLL
```

## 清除建置產出

```bash
rm -rf build/ dist/ *.spec
```

## Red Flags

| 想法 | 現實 |
|------|------|
| 「測試沒過但先打包看看」 | 測試失敗的程式不應打包，先修正 |
| 「用 --onefile 比較方便」 | 專案用 --onedir，啟動較快且易於除錯 |
| 「不用打包語系檔」 | 缺少 i18n 檔案會導致介面文字遺失 |
| 「直接建置不用清除」 | 舊 dist 目錄存在時 PyInstaller 會報錯中止 |
