---
description: 暫存檔案管理規則 — 非專案必要檔案放 _temp/，commit 前檢查散落檔案
alwaysApply: true
---

# 暫存檔案管理規則

- 非專案系統必要的檔案（xlsx、csv、備份、使用者資料等）MUST 放在 `_temp/` 資料夾下
- `_temp/` 已在 `.gitignore` 中排除，不會進入版本控制
- Commit 前 MUST 檢查根目錄及各層是否有散落的非系統檔案，若有則先搬至 `_temp/` 再 commit
- 非系統檔案判斷標準：非 `.py`、`.md`、`.toml`、`.json`、`.txt`（i18n）、`LICENSE`、`.gitignore` 的檔案，或與專案程式碼無關的資料夾
