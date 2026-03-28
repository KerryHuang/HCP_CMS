---
name: testing
description: "Use when the user asks to run tests, check test results, fix failing tests, or validate code changes. Use when user says \"測試\", \"test\", \"跑測試\", \"驗證\", \"TDD\", \"覆蓋率\". Use when code changes need validation."
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

## 修 Bug 時的 TDD 流程（Law 3）

遵循 Law 3「先寫測試再寫實作」，修 bug 時 MUST 依照以下順序：

1. **重現** — 寫一個失敗測試精確重現 bug（測試 MUST 在修復前失敗）
2. **修復** — 修改程式碼讓測試通過
3. **自測** — 跑測試確認通過，並用腳本驗證實際行為
4. **交付** — 確認通過後才請使用者手動測試

```bash
# 步驟 1：寫測試，確認失敗
.venv/Scripts/python.exe -m pytest tests/unit/test_<模組>.py::test_<bug名稱> -v
# 預期：FAILED

# 步驟 2：修復程式碼

# 步驟 3：跑測試，確認通過
.venv/Scripts/python.exe -m pytest tests/unit/test_<模組>.py::test_<bug名稱> -v
# 預期：PASSED
```

## 自測驗證（交付前必做）

修改 Services / UI 層功能後，NEVER 直接請使用者測試。MUST 先自行驗證：

**Services 層（如 IMAP、Exchange）：**
```bash
.venv/Scripts/python.exe -c "
from hcp_cms.services.mail.imap import IMAPProvider
# 用實際參數測試，確認功能正確
"
```

**UI 層（如 EmailView、CaseView）：**
```bash
.venv/Scripts/python.exe -c "
import sys
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
from hcp_cms.ui.main_window import MainWindow
w = MainWindow()
w.show()
# 模擬操作，確認不會 crash
import time
for i in range(50):
    app.processEvents()
    time.sleep(0.1)
print('OK')
"
```

**自測通過後才可請使用者測試。**

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
| 「只跑相關的測試就好」 | 開發中可只跑失敗測試，但交付前 MUST 跑完整測試套件 |
| 「測試失敗先跳過」 | 先修好再繼續，不要累積技術債 |
| 「改完直接請使用者測」 | MUST 先自測通過再交付，避免使用者遇到 crash |
| 「修 bug 不用加測試」 | 每個 bug 修復 MUST 附帶迴歸測試，防止復發 |
| 「先實作再補測試」 | Law 3 要求 TDD，先寫測試再寫實作 |
