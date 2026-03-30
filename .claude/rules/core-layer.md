---
globs: src/hcp_cms/core/**/*.py
description: Core 層業務邏輯類別的命名、建構子、回傳值等慣例
---

# Core 層慣例

- 類別命名：`XxxManager` 或 `XxxEngine`，職責單一
- 建構子只接收 `conn: sqlite3.Connection`，內部建立 Repository 實例
- NEVER 直接執行 SQL，所有資料庫操作委託給 Repository
- 公開方法 `snake_case` 動詞優先，私有方法 `_snake_case`
- 返回型別必須標註，可空用 `Type | None`
- 查詢失敗返回 `None`，不拋異常
- 可組合依賴同層其他 Core 類別
- NEVER 從 Core 層 import Data 層 Repository 以外的模組（如 `_clean_subject` 輔助函數）
  - 若 Core 與 Data 層均需同一邏輯，各層獨立實作，不跨層共用函數（避免 Core 層意外依賴 Data 層內部細節）
