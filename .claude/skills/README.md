# HCP CMS — Claude Code 技能總覽

本專案提供以下 Claude Code 技能（Skills），在對話中輸入 `/指令` 即可觸發。

## Git 操作

| 指令 | 用途 | 說明 |
|------|------|------|
| `/commit` | 提交變更 | 繁體中文 commit 訊息、逐一 stage 檔案、自動附加 Co-Authored-By |
| `/push` | 推送到遠端 | 推送前安全檢查、禁止 force push main/master、推送後提醒回顧 |
| `/pull` | 拉取遠端變更 | 檢查本地狀態、衝突處理引導 |
| `/reflect` | Session 回顧 | 分析技能/規則/CLAUDE.md 缺口，委託 RCC 技能執行補強 |

## 開發工具

| 指令 | 用途 | 說明 |
|------|------|------|
| `/test` | 執行測試 | pytest 全部/單一/覆蓋率/關鍵字篩選 |
| `/run` | 啟動應用程式 | 啟動 PySide6 GUI 桌面應用 |
| `/build` | 建置執行檔 | PyInstaller 打包成 Windows .exe |
| `/poc` | POC 驗證 | 技術可行性原型 + 需求情境列舉，正式實作前快速驗證假設 |

## 發行流程

| 指令 | 用途 | 說明 |
|------|------|------|
| `/release` | 發行新版本 | 更新版號 → 建置 → Git 標籤 |
| `/publish` | 本地發行驗證 | 8 項檢查 + 驗證報告，確認品質後交付 |

## 文件維護

| 指令 | 用途 | 說明 |
|------|------|------|
| `/update-docs` | 更新專案文件 | 比對程式碼現況，同步所有文件 |

## 使用方式

1. 在 Claude Code 對話中直接輸入 `/指令`（如 `/test`）
2. Claude 會載入對應技能並引導完整流程
3. 也可用中文觸發，例如：「幫我跑測試」、「提交這些變更」、「打包程式」

## 技能檔案結構

```
.claude/skills/
├── README.md               ← 本檔案
├── committing/SKILL.md     ← /commit
├── pushing/SKILL.md        ← /push
├── pulling/SKILL.md        ← /pull
├── reflecting/SKILL.md     ← /reflect
├── testing/SKILL.md        ← /test
├── running/SKILL.md        ← /run
├── building/SKILL.md       ← /build
├── releasing/SKILL.md      ← /release
├── publishing/SKILL.md     ← /publish
├── poc/SKILL.md            ← /poc
└── updating-docs/SKILL.md  ← /update-docs
```
