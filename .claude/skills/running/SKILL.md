---
name: run
description: "[Project] Use when the user asks to run, start, or launch the application. Use when user says "執行", "run", "啟動", "開啟程式". Use when needing to test the application manually.
---

# Running the Application

## Overview

啟動 HCP CMS 桌面應用程式。此為 PySide6 GUI 應用，會開啟視窗介面。

## 前置條件

確認虛擬環境和依賴：

```bash
ls .venv/Scripts/python.exe 2>/dev/null || echo "需要先建立虛擬環境"
```

若不存在：
```bash
python -m venv .venv
.venv/Scripts/pip.exe install -e ".[dev]"
```

## 啟動指令

```bash
.venv/Scripts/python.exe -m hcp_cms
```

**注意：** 此指令會啟動 GUI 視窗，在 CLI 中會阻塞直到視窗關閉。

## 常見問題

### ImportError

```bash
# 確認套件已安裝
.venv/Scripts/pip.exe install -e ".[dev]"
```

### PySide6 無法載入

```bash
# 確認 PySide6 版本
.venv/Scripts/pip.exe show PySide6
```

### 資料庫相關錯誤

應用首次啟動會自動建立 SQLite 資料庫。若遇到 schema 錯誤，可能需要刪除舊資料庫重建。

## Red Flags

| 想法 | 現實 |
|------|------|
| 「直接用系統 Python 跑」 | MUST 使用 .venv 的 Python，避免依賴衝突 |
| 「背景執行不管它」 | GUI 應用需要前台執行，觀察是否正常啟動 |
