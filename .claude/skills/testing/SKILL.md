---
name: test
description: "[Project] Use when the user asks to run tests, check test results, or verify code works. Use when user says "測試", "test", "跑測試", "驗證". Use when code changes need validation.
---

# Running Tests

## Overview

執行測試驗證程式碼正確性。支援全部測試、單一檔案、單一測試、覆蓋率報告等模式。

## 前置條件

確認虛擬環境存在：

```bash
ls .venv/Scripts/python.exe 2>/dev/null || echo "需要先建立虛擬環境"
```

若不存在，引導使用者建立：
```bash
python -m venv .venv
.venv/Scripts/pip.exe install -e ".[dev]"
```

## 測試指令

### 執行全部測試

```bash
.venv/Scripts/python.exe -m pytest tests/ -v
```

### 只跑單元測試

```bash
.venv/Scripts/python.exe -m pytest tests/unit/ -v
```

### 只跑整合測試

```bash
.venv/Scripts/python.exe -m pytest tests/integration/ -v
```

### 跑特定檔案

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_<模組>.py -v
```

### 跑特定測試

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_<模組>.py::Test<類別>::test_<方法> -v
```

### 覆蓋率報告

```bash
.venv/Scripts/python.exe -m pytest tests/ --cov=hcp_cms --cov-report=term-missing
```

### 搭配關鍵字篩選

```bash
.venv/Scripts/python.exe -m pytest tests/ -v -k "keyword"
```

## 測試失敗處理

1. 仔細閱讀錯誤訊息和 traceback
2. 定位失敗的測試和斷言
3. 檢查相關的 source code
4. 修正問題後重跑**失敗的測試**（不需重跑全部）

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_<失敗檔案>.py::<失敗測試> -v
```

## 輔助檢查

### Lint 檢查

```bash
.venv/Scripts/ruff.exe check src/ tests/
```

### 型別檢查

```bash
.venv/Scripts/python.exe -m mypy src/hcp_cms/
```

## Red Flags

| 想法 | 現實 |
|------|------|
| 「改了一點不用跑測試」 | 任何變更都應驗證，尤其跨層修改 |
| 「只跑相關的測試就好」 | 修改 data 層需跑 unit + integration |
| 「測試失敗先跳過」 | 先修好再繼續，不要累積技術債 |
