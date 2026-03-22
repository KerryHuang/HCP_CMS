---
globs: tests/**
description: 測試檔案的命名、fixture、斷言、目錄劃分等慣例
---

# 測試慣例

- 測試檔案命名：`test_<module>.py`
- 測試類別命名：`Test<ClassName>`，方法：`test_<functionality>`
- 全域 fixture 放 `conftest.py`，模組特定 fixture 放測試檔案內
- DB fixture 使用 `yield` 進行 setup/teardown，結束後 `db.close()`
- 斷言使用簡潔 `assert` 語句，NEVER 使用 `self.assertEqual`
- 測試資料使用繁體中文（與實際使用情境一致）
- 導入路徑：`from hcp_cms.<layer>.<module> import <Class>`
