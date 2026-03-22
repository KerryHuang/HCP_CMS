---
globs: src/hcp_cms/ui/**
description: PySide6 UI 層的命名慣例、主題色系與架構約束
---

# UI 層慣例

- Widget 類別命名：以 `View` / `Widget` / `Card` 結尾
- UI 初始化統一使用 `_setup_ui()` 方法
- Slot 方法命名：`_on_<action>` 或 `_on_<widget>_<action>`
- Signal/Slot 連線寫在 `_setup_ui()` 內
- objectName 使用 camelCase（供 CSS 選擇器使用）
- 深色主題色系：背景 `#111827` / `#1e293b`，文字 `#f1f5f9` / `#e2e8f0`
- NEVER 在 UI 層放置業務邏輯，委託給 Core 層
