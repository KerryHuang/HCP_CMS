# HCP 客服 Web Portal 使用說明

## 一、開始使用

### 公司辦公室內

開瀏覽器，輸入：`http://<Jill PC IP>:8080`

### 在家或出差（遠端）

1. 裝 Tailscale（https://tailscale.com）— 免費版 3 人團隊夠用
2. 連 Jill PC 同一 Tailscale 網段
3. 開瀏覽器：`http://<Jill PC Tailscale IP>:8080`

## 二、登入

第一次開頁面會看到 3 個按鈕：jill / YOGA / Rebecca

→ 點自己名字 → cookie 自動記住，下次自動登入
→ 想切換身分：右上「登出」

## 三、看到哪些案件？

「我的案件」清單顯示：

- 您被指派 (`handler` = 您) 的案件
- 您管轄公司 (`companies.cs_staff_id` = 您) 的案件

⚠ **未指派的案件不會出現**，請 Jill 在桌面 App 指派後才會進來。

## 四、編輯案件

點任一案件 → 詳情頁可改：

| 欄位 | 說明 |
|------|------|
| 狀態 | 處理中 / 已回覆 / 已完成 / **已結案** |
| 處理進度 | 多行文字 |
| 處理人員 | 從客服列表選 |
| 優先度 | 高 / 中 / 低 |
| 技術負責人 | 自由輸入 |

按「儲存」即可。每次變更會自動寫入稽核 log（誰、何時、改了哪個欄位）。

### 何時用「已結案」？

| 狀態 | 客戶後續回信會發生什麼 |
|------|------|
| 已完成 | **建一筆新子案件**連結到原案件（從 thread 視角看像是重開）|
| 已結案 | **不會復活**，只在原案件加一筆「客戶來信」紀錄 |

選「已結案」會彈確認視窗，確認後即鎖定。

## 五、新增補充紀錄

詳情頁下方有「新增補充記錄」區，可選類型：

- 內部討論
- HCP 線上回覆
- HCP 信件回覆

## 六、回信給客戶

**請繼續使用 Outlook 回信，並 CC `hcpservice@`**——
HCP CMS 會自動把您的回信抓進系統，所有客服都看得到。

## 七、Mantis 整合

### 推到 Mantis（單筆）

詳情頁底部有「**建立 Mantis ticket**」按鈕：
1. 按下 → 確認視窗 → 確認推送
2. 成功 → 顯示新 ticket id + 案件自動連結到該 ticket

### 推送更新（bugnote）

若案件已連結 Mantis ticket，按鈕變「**推送更新為 bugnote**」：
1. 將當前狀態 + 進度 + 最新記錄推為 Mantis ticket 留言
2. 客戶看不到（內部 bugnote）

### 批次推送

清單頁勾選多筆案件 → 按「**推到 Mantis（N 筆）**」：
1. 確認視窗列出將推送的明細
2. 已連結 ticket 的會自動略過
3. 成功 / 失敗 / 略過 統計顯示

⚠ Mantis 推送是**手動觸發**，無自動同步。每筆都需您按按鈕確認。

## 八、報表匯出

報表功能在 Jill 的桌面 App，請洽 Jill。

## 九、稽核紀錄（僅 admin）

Jill 可開 `http://<host>:8080/audit` 看誰何時改了哪個案件的哪個欄位。

## 十、常見問題

**Q1: 為什麼我看不到某些案件？**
A: 該案件可能還沒指派 handler，或所屬公司不在您管轄範圍。請 Jill 確認。

**Q2: 我關案件後客戶又回信，案件會復活嗎？**
A:
- 選「已完成」→ 系統會建一筆新子案件連結到原案件
- 選「已結案」→ 不會復活，只在原案件加一筆「客戶來信」紀錄

**Q3: Mantis 推送失敗怎麼辦？**
A: 看錯誤訊息：
- 「Issue not found」→ Mantis 那個 ticket 被刪了，請重新連結
- 「Access denied」→ 通知 Jill 檢查 Mantis 帳號權限
- 「Category field must be supplied」→ 通知 Jill 檢查 project 設定
- 連線失敗 → 公司網路或 Mantis 主機問題

**Q4: 我可以在手機上用嗎？**
A: 可以，但目前 UI 沒做 RWD 最佳化，建議桌機 / 筆電。

**Q5: Jill 關機時我可以用嗎？**
A: ❌ Web Portal 跑在 Jill PC 上，她關機則服務停止。

## 十一、給管理員（Jill）的設定指引

### 部署

1. 確認 NSSM 已安裝於系統 PATH（https://nssm.cc/download）
2. 編輯 `scripts/install_web_service.bat` 內變數：
   - `DB_PATH`：cs_tracker.db 位置
   - `MANTIS_*`：Mantis credentials 與 project 218
3. 右鍵「以管理員身分執行」→ 服務自動安裝 + 啟動
4. Windows 防火牆：放行 inbound TCP port 8080
5. 告知 YOGA / Rebecca：`http://<your-PC-IP>:8080`

### 解除安裝

執行 `scripts/uninstall_web_service.bat`（管理員身分）

### Mantis project 218 設定提醒

POC（2026-05-13）發現該 project 強制要 category（唯一可用：`General`），
已設為預設值。若未來新增 category，請更新 `HCP_CMS_MANTIS_CATEGORY` 環境變數。
