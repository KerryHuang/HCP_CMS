---
globs: src/hcp_cms/services/**
description: Services 層（MailProvider、MantisClient、CredentialManager）的開發慣例
---

# Services 層慣例

- 外部服務 MUST 實作對應 ABC 介面（MailProvider / MantisClient）
- 憑證管理透過 `CredentialManager`（keyring），NEVER 硬編碼密碼
- 方法命名 `snake_case` 動詞優先
- 所有外部 I/O 操作 MUST 有 try/except 錯誤處理
- 返回型別標註，可空用 `Type | None`
