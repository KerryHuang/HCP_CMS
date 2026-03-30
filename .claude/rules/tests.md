---
globs: tests/**/*.py
description: 測試檔案的命名、fixture、斷言、目錄劃分等慣例
---

# 測試慣例

- 測試檔案命名：`test_<module>.py`
- 測試類別命名：`Test<ClassName>`，方法：`test_<functionality>`
- 跨子層共用 fixture 放 `tests/conftest.py`（根層），模組特定 fixture 放測試檔案內
- DB fixture 使用 `yield` 進行 setup/teardown，結束後 `db.close()`
- 斷言使用簡潔 `assert` 語句，NEVER 使用 `self.assertEqual`
- 測試資料使用繁體中文（與實際使用情境一致）
- 導入路徑：`from hcp_cms.<layer>.<module> import <Class>`

## 邊界條件規範

- 時間格式函數 MUST 測試所有路徑：有秒/無秒（`HH:MM` vs `HH:MM:SS`）、ISO 8601、`YYYY/MM/DD` slash 格式各一個測試案例
- 字串清理 static method（如前綴去除）MUST 同時測試「單層前綴」與「多層前綴」（如 `"RE: RE: 主旨"`）
- Data 層測試若涉及 FK 約束（如 `cs_cases.company_id`）MUST 先插入父資料（`Company`、`QAKnowledge` 等），NEVER 假設 FK 不存在
