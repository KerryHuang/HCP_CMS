# 信件連線設定 UI 設計文件

**日期：** 2026-03-28
**範圍：** `src/hcp_cms/ui/settings_view.py`

---

## 目標

在 `SettingsView` 新增「📧 信件連線設定」GroupBox，讓使用者可在 UI 中設定 IMAP 或 Exchange EWS 的連線參數，並將憑證安全儲存於 OS keyring。

---

## 架構

### 層次關係

```
SettingsView (UI 層)
  └── CredentialManager (Services 層)
        └── OS keyring (keyring 套件)

測試連線時：
  └── IMAPProvider / ExchangeProvider (Services 層)
```

UI 層只直接呼叫 `CredentialManager` 與 `IMAPProvider` / `ExchangeProvider`，不接觸 SQLite。

---

## UI 設計

### 佈局：單一 GroupBox + 協定切換按鈕（A 方案）

位置：插入於現有 `mantis_group` **之後**（信件與 Mantis 同屬連線設定，放在一起）。

```
┌─ 📧 信件連線設定 ──────────────────────────────────┐
│  [ IMAP ]  [ Exchange ]                            │
│                                                    │
│  （IMAP 模式）                                      │
│  主機：  [________________________]                │
│  Port：  [ 993 ]  ☑ 使用 SSL                      │
│  帳號：  [________________________]                │
│  密碼：  [________________________]                │
│                                                    │
│  （Exchange 模式）                                  │
│  Server：[____________] （選填，留空用 autodiscover）│
│  Email： [________________________]                │
│  帳號：  [________________________]                │
│  密碼：  [________________________]                │
│                                                    │
│  [ 🔌 測試連線 ]  [ 💾 儲存設定 ]                  │
└────────────────────────────────────────────────────┘
```

### 互動行為

- 預設顯示 IMAP 模式
- 點擊協定按鈕時：
  - 切換按鈕樣式（選中 = 藍底白字，未選中 = 灰底）
  - 隱藏目前協定的欄位，顯示另一組
  - 從 keyring 載入對應憑證（若已儲存）
- 「儲存設定」：將當前顯示協定的欄位儲存至 keyring
- 「測試連線」：以當前欄位內容實際建立連線，顯示成功 / 失敗訊息

---

## Keyring 鍵值規格

| 協定     | 欄位    | Key                     | 說明             |
|----------|---------|-------------------------|------------------|
| IMAP     | 主機    | `mail_imap_host`        |                  |
| IMAP     | Port    | `mail_imap_port`        | 字串，預設 `993` |
| IMAP     | SSL     | `mail_imap_ssl`         | `"1"` 或 `"0"`  |
| IMAP     | 帳號    | `mail_imap_user`        |                  |
| IMAP     | 密碼    | `mail_imap_password`    |                  |
| Exchange | Server  | `mail_exchange_server`  | 可為空字串       |
| Exchange | Email   | `mail_exchange_email`   |                  |
| Exchange | 帳號    | `mail_exchange_user`    |                  |
| Exchange | 密碼    | `mail_exchange_password`|                  |
| 共用     | 現用協定 | `mail_active_protocol`  | `"imap"` 或 `"exchange"`，用於重啟後還原切換狀態 |

---

## 元件設計

### 新增方法（SettingsView）

| 方法 | 說明 |
|------|------|
| `_build_mail_group() -> QGroupBox` | 建立信件設定區塊，供 `_setup_ui()` 呼叫 |
| `_on_mail_protocol_switch(protocol: str)` | 切換 IMAP / Exchange 欄位顯示 |
| `_load_mail_creds(protocol: str)` | 從 keyring 載入指定協定的憑證 |
| `_on_save_mail()` | 儲存當前協定憑證至 keyring |
| `_on_test_mail()` | 測試連線，顯示結果 MessageBox |

### 欄位 Widget 命名

- `_mail_imap_host`, `_mail_imap_port`, `_mail_imap_ssl`, `_mail_imap_user`, `_mail_imap_pwd`
- `_mail_exchange_server`, `_mail_exchange_email`, `_mail_exchange_user`, `_mail_exchange_pwd`
- `_mail_imap_btn`, `_mail_exchange_btn`（協定切換按鈕）
- `_mail_imap_widget`, `_mail_exchange_widget`（各協定欄位容器，用於 show/hide）

---

## 錯誤處理

- 測試連線失敗：顯示 `QMessageBox.warning`，說明可能原因
- 主機欄位為空時「儲存設定」：顯示 `QMessageBox.warning`
- keyring 操作失敗：靜默忽略（`CredentialManager` 已處理）

---

## 不在範圍內

- 排程器自動收信的觸發（Scheduler 層）
- 多帳號管理
- OAuth / App Password 流程
