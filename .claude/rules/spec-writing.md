---
globs:
  - "docs/superpowers/specs/**/*.md"
description: "設計規格文件（docs/superpowers/specs/）的撰寫慣例"
alwaysApply: false
---

# 設計規格撰寫慣例

- 業務決策啟發式規則（heuristic）若有已知限制，MUST 以 ⚠ 標記並說明限制原因
  - 範例：`⚠ RE: 前綴視為 HCP 回覆——客戶若直接回信不加前綴則誤判為客戶來信，屬可接受誤差`
  - 目的：防止 code reviewer 將設計決策誤判為技術 bug 提出修改
- 涉及閾值、容忍範圍或「目前假設」的規則 MUST 附註假設前提
- 架構決策若有多種可行方案，MUST 記錄選擇理由與排除方案
  - 範例：**選擇方案 B**（新增 CaseMerger）；排除方案 A（修改 CaseRepository）：職責過重，違反單一職責原則
