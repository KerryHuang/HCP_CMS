---
globs: src/hcp_cms/data/**
description: Data 層（Repository、Model、FTS5）的命名與實作慣例
---

# Data 層慣例

- Repository 類別命名 `XxxRepository`，接收 `conn: sqlite3.Connection`
- CRUD 方法命名：`insert()` / `get_by_id()` / `list_all()` / `update()` / `delete()`
- 查詢方法：`list_by_xxx()` / `get_by_xxx()` / `count_by_xxx()`
- SQL 必須使用參數化查詢（`:name` 或 `?`），NEVER 字串拼接
- Model 使用 `@dataclass`，欄位 snake_case，可空型別用 `str | None`
- 時間戳記使用 `_now()` 輔助函數，格式 `"%Y/%m/%d %H:%M:%S"`
- 每次修改操作後呼叫 `self._conn.commit()`
