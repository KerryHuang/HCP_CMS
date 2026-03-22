---
globs: "**"
description: Git 推送與發行的安全規則，禁止自動 push 和 release
alwaysApply: true
---

# Git 安全規則

- 實作完程式碼後 NEVER 自動執行 `git push`，MUST 先詢問使用者確認
- NEVER 自動執行 release 流程（版號更新、打標籤、建置發行），MUST 先詢問使用者
- NEVER 使用 `git push --force`，除非使用者明確要求
- NEVER force push 到 `main` 或 `master`，即使使用者要求也要先警告風險
- Commit 完成後，告知使用者結果並等待指示，不主動進入 push 或 release
