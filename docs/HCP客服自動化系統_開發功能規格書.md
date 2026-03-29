**HCP 客服自動化系統**

開發功能規格書

Development Function Specification

文件版本：v1.0

撰寫日期：2026/03/22

用途：重構前現行系統開發規格整理

**一、文件資訊**

  -------------- ------------------------------------------------
  **項目**       **內容**
  文件名稱       HCP 客服自動化系統 --- 開發功能規格書
  版本           v1.0
  日期           2026/03/22
  用途           重構前現行系統完整功能規格，供新版系統設計參考
  對應需求文件   HCP客服自動化系統\_需求文件.docx v1.0
  -------------- ------------------------------------------------

**二、系統架構**

**2.1 整體架構**

系統採用「本機 Python 後端 + 靜態 HTML 前端」架構，資料儲存於 SQLite，無需 Web Server。

  -------------- ---------------------------------- ------------------------------------ ----------------------------------------------
  **層次**       **元件**                           **技術**                             **職責**
  前端 UI        客服工作流程助理.html              React 18 + ExcelJS + Babel（CDN）    報表下載、QA 管理、規則瀏覽、Mantis 同步介面
  規則編輯器     rules\_editor.py                   Python BaseHTTPServer + HTML         提供本地 8765 port 的規則 GUI 編輯器
  信件處理引擎   email\_processor.py                Python 3.10+、extract-msg、sqlite3   讀取 .msg、分類、建案、匿名化、匯出 JS
  Mantis 同步    mantis\_sync.py                    Python + SOAP requests + openpyxl    SOAP 同步 Mantis 票務、產生 Excel 報表
  分類規則       rules\_config.py                   Python（list of tuple）              集中維護所有分類規則、客戶別名、SLA 設定
  資料儲存       cs\_tracker.db                     SQLite 3                             案件、QA、Mantis、已處理檔案紀錄
  資料橋接       cs\_cases\_data.js / qa\_data.js   JSON + JS 全域變數                   Python 產生，HTML 啟動時靜態載入
  -------------- ---------------------------------- ------------------------------------ ----------------------------------------------

**2.2 資料流**

-   .msg 信件 → email\_processor.py → SQLite cs\_cases → \_export\_cases\_json() → cs\_cases\_data.js → 客服工作流程助理.html（重新整理後讀取）

-   客服工作流程助理.html（TrackingTab/ReportTab）→ ExcelJS → .xlsx 下載（瀏覽器端產生，不需 Python）

-   mantis\_sync.py → Mantis SOAP API → SQLite mantis\_tickets → Excel 月報

-   QATab → 編輯 QA → 產生 qa\_data.js → HTML 重新載入後可見

**2.3 目錄結構（現行）**

  ---------------------------- -------------------------------------------
  **檔案/目錄**                **說明**
  email\_processor.py          核心信件處理引擎（\~3000 行）
  rules\_config.py             分類規則設定（\~480 行）
  rules\_editor.py             本地規則 GUI 編輯器（\~640 行）
  mantis\_sync.py              Mantis 同步 + Excel 報表產生（\~1100 行）
  客服工作流程助理.html        瀏覽器 UI（\~4200 行，React 單頁應用）
  客服系統安裝精靈.html        安裝引導頁面
  cs\_tracker.db               SQLite 資料庫
  cs\_cases\_data.js / .json   案件資料匯出（每次信件處理後更新）
  qa\_data.js / .json          QA 知識庫資料匯出
  user\_config.json            使用者設定（路徑、帳密）
  執行信件處理.bat             信件處理一鍵執行腳本
  執行Mantis同步.bat           Mantis 同步一鍵執行腳本
  打包為exe.bat                PyInstaller 打包腳本
  新電腦初始設定.bat           一鍵安裝 Python 環境腳本
  QA手冊\_匯入範本.xlsx        QA 知識庫 Excel 匯入範本
  ---------------------------- -------------------------------------------

**三、資料庫設計**

**3.1 cs\_cases（客服案件）**

  ------------------ -------------- ------------ --------------------------------------------------------------
  **欄位名稱**       **資料型態**   **預設值**   **說明**
  case\_id           TEXT PK        ---          CS-YYYY-NNN，每年流水號重置
  contact\_method    TEXT           ---          聯絡方式：Email / Phone / 其他
  status             TEXT           處理中       處理中 / 已回覆 / 已完成 / Closed
  priority           TEXT           中           高 / 中 / 低
  replied            TEXT           否           是 / 否
  sent\_time         TEXT           ---          信件寄出時間（YYYY/MM/DD HH:MM）
  company            TEXT           ---          客戶公司（COMPANY\_ALIAS 轉換後的中文名或 domain）
  contact\_person    TEXT           ---          客戶聯絡人姓名
  subject            TEXT           ---          信件主旨（已去除 RE:/FW:）
  system\_product    TEXT           ---          HCP / WebLogic / ERP
  issue\_type        TEXT           ---          問題類型（7 大類 + OTH）
  error\_type        TEXT           ---          錯誤類型（33 個功能模組）
  impact\_period     TEXT           當前         影響期間說明
  progress           TEXT           ---          處理進度/解決方式（自由文字，可多次追加）
  actual\_reply      TEXT           ---          實際首次回覆時間
  notes              TEXT           ---          備注（含自動追加的後續來信紀錄）
  rd\_assignee       TEXT           ---          指派的技術人員（RD）
  handler            TEXT           ---          負責客服人員
  reply\_count       INTEGER        0            來回次數（後續來信時累計；亦可動態從 linked\_case\_id 計算）
  linked\_case\_id   TEXT           NULL         指向同對話串的根案件 ID（後續來信才有值）
  ------------------ -------------- ------------ --------------------------------------------------------------

**3.2 qa\_knowledge（QA 知識庫）**

  ----------------- -------------- -----------------------------------------
  **欄位名稱**      **資料型態**   **說明**
  qa\_id            TEXT PK        QA-YYYYMM-NNN，每月流水號重置
  system\_product   TEXT           系統產品
  issue\_type       TEXT           問題類型
  error\_type       TEXT           錯誤類型/功能模組
  question          TEXT           問題描述（已匿名化）
  answer            TEXT           標準回覆內容（已匿名化）
  has\_image        TEXT           是否有附圖：是/否，預設否
  doc\_name         TEXT           Word 文件名稱（若已建立客服QA說明文件）
  created\_date     TEXT           建立日期
  created\_by       TEXT           建立者（user\_config.user\_name）
  notes             TEXT           備注（含關聯案件 ID）
  company           TEXT           來源客戶公司（選填）
  ----------------- -------------- -----------------------------------------

**3.3 mantis\_tickets（Mantis 票務）**

  ------------------- -------------- ---------------------------------------
  **欄位名稱**        **資料型態**   **說明**
  ticket\_id          TEXT PK        Mantis 票號
  created\_time       TEXT           建立時間
  company             TEXT           客戶公司
  summary             TEXT           票務摘要
  related\_cs\_case   TEXT           關聯的客服案件 ID（可多個，分號分隔）
  priority            TEXT           優先等級
  status              TEXT           狀態
  issue\_type         TEXT           問題類型
  module              TEXT           功能模組
  handler             TEXT           負責工程師
  planned\_fix        TEXT           預計修復版本/時間
  actual\_fix         TEXT           實際修復版本/時間
  progress            TEXT           處理進度
  notes               TEXT           備注
  ------------------- -------------- ---------------------------------------

**3.4 processed\_files（已處理信件）**

  --------------- -------------- ------------------------------
  **欄位名稱**    **資料型態**   **說明**
  filename        TEXT PK        信件檔名（.msg），防重複建案
  processed\_at   TEXT           處理時間戳
  --------------- -------------- ------------------------------

**四、各模組功能規格**

**4.1 email\_processor.py --- 核心信件處理引擎**

主要功能分為五大區塊：

**4.1.1 信件讀取（\_read\_msg）**

  ---------- ---------------------------------------------------------------------------------------------------------
  **項目**   **說明**
  輸入       .msg 檔案路徑
  函式庫     extract-msg（pip install extract-msg）
  解析欄位   sender（寄件人 email）、subject（主旨）、body（本文，TEXT 格式）、date（日期）、attachments（附件清單）
  特殊處理   去除 BOM、正規化換行符、提取純文字（避免 HTML 殘留標籤）
  輸出       dict: sender, subject, body, date, attachments
  ---------- ---------------------------------------------------------------------------------------------------------

**4.1.2 自動分類（\_auto\_extract）**

  -------------- ---------------------------------------- ------------------------------------------------------------------------------------------------
  **分類項目**   **函式**                                 **邏輯**
  系統產品       規則比對 SYSTEM\_PRODUCT\_RULES          依 (keyword\_regex, product) tuple 列表，第一個比對到的 regex 取其 product；無匹配則用 DEFAULT
  問題類型       規則比對 ISSUE\_TYPE\_RULES              同上，7 大類 + OTH
  錯誤類型       規則比對 ERROR\_TYPE\_RULES              33 個模組關鍵字
  優先等級       \_parse\_rd + PRIORITY\_HIGH\_KEYWORDS   主旨/本文含高優先關鍵字 → 高；否則中
  聯絡人         \_extract\_contact\_person               從本文 Dear/您好/聯絡人欄位提取，fallback 從 quoted header
  負責人         \_extract\_hcp\_handler                  從 CS 簽名行提取客服人員姓名
  進度備注       \_extract\_body\_progress                提取本文第一段作為初始進度說明
  客戶公司       \_apply\_company\_alias                  從 sender email domain 查詢 COMPANY\_ALIAS
  -------------- ---------------------------------------- ------------------------------------------------------------------------------------------------

**4.1.3 案件管理（\_insert\_case / \_link\_and\_update\_case）**

-   \_next\_case\_id(conn)：查詢本年最大流水號 + 1，格式 CS-YYYY-NNN

-   \_find\_related\_incoming\_case(conn)：從 DB 查詢同公司 + 主旨相似的未結案，用於判斷是否為後續來信

-   \_find\_thread\_parent(conn)：識別對話串根案件（Mantis 票號相同 or 同公司+相似主旨）

-   \_link\_and\_update\_case()：後續來信時更新根案件的 reply\_count、notes，並設定 linked\_case\_id

-   \_reopen\_existing\_case()：已回覆案件收到後續來信時，重新開啟為「處理中」

-   \_find\_already\_replied\_case()：找出我方已回覆的同案件，避免重複建立回覆紀錄

**4.1.4 匿名化（\_anonymize\_qa）**

-   輸入：question/answer 文字、company（域名）、person\_names（待替換人名清單）、company\_aliases（中文別名）

-   16 條正則規則依序套用（詳見需求文件 F04）

-   規則 ⑦⑮：公司域名與中文別名分別替換為「貴客戶」

-   規則 ⑫：職稱+中文姓名（員工/工程師/承辦人 etc.）→「相關人員」，不使用 lookahead 避免過度匹配

**4.1.5 資料匯出（\_export\_cases\_json / \_export\_qa\_json）**

-   \_export\_cases\_json(conn, out\_path)：SELECT 全部 cs\_cases，計算動態 reply\_count（max(db值, linked關係計算值)），輸出 cs\_cases\_data.json 與 .js

-   \_export\_qa\_json(conn, out\_path)：SELECT 全部 qa\_knowledge，輸出 qa\_data.json 與 .js

-   JS 格式：window.CS\_CASES\_DATA = {\...}; 和 window.QA\_DATA = {\...};，供 HTML \<script src\> 靜態載入

**4.2 rules\_config.py --- 分類規則設定**

  -------------------------- -------------------------- ------------------------------------------------------------
  **常數名稱**               **型態**                   **說明**
  COMPANY\_ALIAS             dict\[str,str\]            email domain → 中文公司名（10 組，支援子域名 fallback）
  SYSTEM\_PRODUCT\_RULES     list\[tuple\[str,str\]\]   (keyword\_regex, product) 列表，依序比對，第一個符合者取值
  SYSTEM\_PRODUCT\_DEFAULT   str                        無匹配時的預設值（\"HCP\"）
  ISSUE\_TYPE\_RULES         list\[tuple\[str,str\]\]   (keyword\_regex, issue\_type) 共 7 大類
  ISSUE\_TYPE\_DEFAULT       str                        無匹配時的預設值（\"OTH\"）
  ERROR\_TYPE\_RULES         list\[tuple\[str,str\]\]   (keyword\_regex, module\_name) 共 33 個功能模組
  ERROR\_TYPE\_DEFAULT       str                        無匹配時的預設值（\"人事資料管理\"）
  PRIORITY\_HIGH\_KEYWORDS   str（regex）               高優先判斷正則
  SLA\_HOURS                 int                        一般案件 SLA：24 小時
  SLA\_HOURS\_HIGH           int                        高優先 SLA：4 小時
  SLA\_HOURS\_CUSTOM         int                        客制需求 SLA：48 小時
  -------------------------- -------------------------- ------------------------------------------------------------

*📌 規則比對邏輯：對 subject + body（前 300 字）進行 re.search（case-insensitive），第一個命中的規則取值。*

**4.3 mantis\_sync.py --- Mantis 同步與報表**

**4.3.1 SOAP 介面**

-   協定：SOAP 1.1，HTTP POST，Content-Type: text/xml

-   方法：mc\_issue\_get（依票號取得單一 Issue 完整資料）

-   認證：user/password 含於 SOAP envelope Header（Basic Auth 嵌入式）

-   URL：由 user\_config 中 mantis\_url 設定

**4.3.2 同步邏輯（sync\_ticket）**

-   依票號查詢 Mantis，取得 summary、status、priority、handler、notes 等欄位

-   若 DB 無此票號則 INSERT；已存在則 UPDATE

-   自動關聯：從 summary 或 notes 中偵測 CS-XXXX 格式，更新 related\_cs\_case

**4.3.3 報表產生（generate\_report / generate\_tracking\_table）**

-   generate\_report()：產生月報 Excel（四頁籤：摘要/案件明細/未結案/Mantis 進度），使用 openpyxl

-   generate\_tracking\_table()：產生追蹤表 Excel（客戶索引/總表/各客戶分頁/客制需求），使用 openpyxl

-   樣式：openpyxl 直接設定 font、fill、alignment、border，無額外框架

**4.4 客服工作流程助理.html --- 瀏覽器 UI**

單一 HTML 檔案，使用 CDN 載入 React 18、Babel、ExcelJS。主要功能分為以下 Tab：

  -------------- ---------------------- ------------------------------------------------------------------------------
  **Tab 名稱**   **對應 Function**      **主要功能**
  DashboardTab   DashboardTab()         系統狀態總覽：資料載入狀態、案件統計、快速跳轉
  追蹤表下載     TrackingTab()          設定查詢月份，下載問題追蹤表 Excel（ExcelJS 瀏覽器端產生）
  月報下載       ReportTab()            選擇月份區間與頁籤，下載月報 Excel
  QA 知識庫      QATab()                瀏覽、新增、編輯、搜尋 QA；下載 Excel；產生 qa\_data.js
  規則瀏覽       RulesTab()             顯示目前 rules\_config.py 中的分類規則（唯讀，由 RulesEditorTab 載入後顯示）
  規則設定       RulesEditorTab()       載入 rules\_config.py，以 GUI 方式新增/刪除規則，產生新版設定文字
  Mantis 同步    SyncTab()              顯示 Mantis 連線狀態、同步結果
  信件說明       EmailTab()             說明信件處理流程、路徑設定提示
  合併報表       CombinedReportsTab()   （實驗性）同時下載追蹤表 + 月報
  系統設定       SettingsTab()          顯示設定說明與各子頁籤（Mantis/規則/路徑設定指引）
  -------------- ---------------------- ------------------------------------------------------------------------------

**4.4.1 ExcelJS 報表產生（TrackingTab / ReportTab）**

-   函式庫：ExcelJS（CDN unpkg），於瀏覽器端記憶體中產生 .xlsx，Blob 下載

-   XL 物件：封裝 ExcelJS 操作的全域輔助物件，包含 XL.title()、XL.hdr()、XL.data()、XL.s()、XL.sRow()、XL.statusColor()、XL.addSheetNav() 等方法

-   addSheetNav(wb)：在每個 worksheet 底部加入導覽列（各頁籤互相超連結），使用 \#\"SheetName\"!A1 格式的 hyperlink

-   來回次數：由 getReplyCount(c) 動態計算，取 DB 值與 linked\_case\_id 關係計算值的最大值

**4.4.2 資料載入機制**

-   cs\_cases\_data.js 與 qa\_data.js 透過 HTML 末端的 \<script src\> 靜態載入

-   載入後設定 window.CS\_CASES\_DATA 和 window.QA\_DATA 全域變數

-   onerror 處理：若檔案不存在或路徑錯誤，設定為 null 並顯示警告

-   更新後需手動重新整理頁面（F5）才能讀取新版資料；介面提供「🔄 重新整理頁面」按鈕

*📌 重構建議：改用 Fetch API 定期或按鈕觸發重載，不依賴靜態 \<script\>*

**4.4.3 規則設定（RulesEditorTab）**

-   讀取 rules\_config.py 文字，以正則解析 COMPANY\_ALIAS / ISSUE\_TYPE\_RULES / ERROR\_TYPE\_RULES 等

-   解析後儲存至 React state 和 window.\_COMPANY\_ALIAS\_MAP（供匿名化使用）

-   編輯後可產生新版 rules\_config.py 文字，供使用者貼回 Python 檔案

**五、分類規則設計**

**5.1 問題類型（ISSUE\_TYPE\_RULES）**

  -------------- ------------------------------- --------------------------
  **問題類型**   **代表關鍵字（舉例）**          **說明**
  客制需求       客制、客製、customize           客戶要求的客製化開發需求
  NEW            新功能、新增、Add feature       新增功能請求
  BUG            BUG、錯誤、異常、Exception      程式錯誤或系統異常
  建議改善       建議、改善、優化、enhancement   系統改善建議
  邏輯咨詢       邏輯、請問、如何計算、說明      業務邏輯詢問
  操作異常       操作、無法、失敗、不顯示        操作上遭遇困難
  OP             維護、定期、月結、執行批次      系統操作/維運類
  OTH（預設）    （無匹配）                      其他未分類
  -------------- ------------------------------- --------------------------

**5.2 錯誤類型（ERROR\_TYPE\_RULES）--- 33 個功能模組**

以下為 33 個功能模組關鍵字分類（用於 error\_type 欄位）：

  -------------- -------------- ----------------------
  **模組群 A**   **模組群 B**   **模組群 C**
  薪資計算       加班費計算     出缺勤管理
  請假管理       人事資料管理   組織管理
  員工自助服務   績效考核       教育訓練
  招募管理       離職管理       薪資結構
  報表產生       系統安全       系統設定
  資料匯入匯出   介面整合       法院扣薪
  留停復職       工作排程       資料查詢
  授權管理       系統升級       錯誤通知
  資料備份       連線設定       語系設定
  列印設定       操作確認       其他（預設）
  ---            ---            人事資料管理（預設）
  -------------- -------------- ----------------------

**5.3 COMPANY\_ALIAS（客戶域名對應）**

將信件寄件人的 email domain 對應到中文公司顯示名稱。比對邏輯：

-   完整比對：domain 完全符合 key（如 \"abc.com.tw\"）

-   子域名 fallback：若不符合，嘗試去除最前層 label，再次比對（如 \"mail.abc.com.tw\" → 試 \"abc.com.tw\"）

-   若仍不符合，直接使用 domain 原文作為公司名

**六、報表設計規格**

**6.1 追蹤表 Excel 頁籤結構**

  ---------------- -------------- ------------ ---------------------------------------------------------------
  **頁籤名稱**     **顏色主題**   **欄位數**   **主要內容**
  📋 客戶索引       藍色系         6            \#, 公司名稱, Email域名, 聯絡方式, 案件數, 快速連結（超連結）
  問題追蹤總表     藍色系         26           完整 26 欄：案件編號\~備注，含來回次數、FRT、RD指派
  QA知識庫         紫色系         11           QA編號\~備注 11 欄
  {公司名}\_問題   藍色系         各異         各客戶獨立頁籤，依案件數排序，含公司統計與案件列表
  ---------------- -------------- ------------ ---------------------------------------------------------------

**6.2 月報 Excel 頁籤結構**

  --------------- ---------- ----------------------------------------------------------------------------
  **頁籤名稱**    **可選**   **主要內容**
  📊 月報摘要      是         KPI 3行（標籤/數值/說明）+ 問題類型統計 + 狀態統計 + 客戶統計 + 備注說明欄
  📋 案件明細      是         查詢區間所有案件完整欄位，含篩選器
  🏢 各客戶頁籤    是         每家客戶一個頁籤，含問題類型/狀態統計 + 案件列表
  ⚠️ 未結案清單   是         所有未完成案件，含老化天數長條圖
  🔧 Mantis 進度   是         同步後的 Mantis 票務一覽
  --------------- ---------- ----------------------------------------------------------------------------

**6.3 月報摘要 KPI 定義**

  -------------- ------------------------------------------------------------------ -------------------
  **KPI 名稱**   **計算方式**                                                       **顯示格式**
  案件總數       查詢期間所有案件數                                                 整數
  已回覆         replied = \"是\" 的案件數                                          整數
  待處理         狀態非「已完成/Closed」的案件數                                    整數
  回覆率         已回覆數 ÷ 案件總數 × 100%                                         XX.X%（綠色粗體）
  平均 FRT       avg(actual\_reply - sent\_time)，排除 \> 720h，無資料顯示「---」   X.Xh
  -------------- ------------------------------------------------------------------ -------------------

**6.4 Excel 樣式規範**

  --------------- ------------------------------------------------------------
  **元素**        **規範**
  字型            微軟正黑體，11pt（資料列）；10pt（說明列）；8pt（備注）
  標題列          深藍色（1E3A5F）背景，白色粗體
  副標題列        淡藍色（2563EB）背景，白色
  數字欄          靠右對齊，藍色（1E3A8A）
  百分比欄        綠色粗體（065F46），靠右對齊
  待處理/高優先   橘紅色（E65100 / DC2626）醒目
  交替行          奇數行白色，偶數行淡灰色（F9FAFB）
  超連結          藍色底線（0563C1），跨頁 hyperlink 格式 \#\'SheetName\'!A1
  邊框            細線（CCCCCC），所有資料格
  --------------- ------------------------------------------------------------

**七、錯誤處理規格**

  ----------------------------------- ----------------------------------------------- -------------------------------------------
  **情境**                            **處理方式**                                    **使用者呈現**
  .msg 解析失敗                       try-except 捕捉，記錄 stderr，繼續處理下一封    終端機輸出警告，不中斷批次
  信件已處理（重複）                  processed\_files 查詢，略過                     終端機輸出「已處理，跳過」
  廣播信偵測                          \_is\_broadcast\_email() 判斷，直接封存不建案   終端機輸出「廣播信，封存」
  DB 寫入失敗                         sqlite3.OperationalError catch，rollback        終端機輸出錯誤詳情
  Excel 鎖定（被 Office 開啟）        捕捉 PermissionError，提示使用者關閉檔案        終端機 / HTML 顯示「請關閉 Excel 後重試」
  Mantis SOAP 連線失敗                requests.exceptions 捕捉，timeout 設定          終端機輸出連線失敗，跳過同步
  HTML 載入 cs\_cases\_data.js 失敗   onerror handler → window.CS\_CASES\_DATA=null   UI 顯示「🔄 重新整理頁面」按鈕
  ExcelJS 載入失敗（CDN）             無 ExcelJS 時設 trackStatus=\"nosheetjs\"       UI 顯示「請確認網路連線」
  查詢月份格式錯誤                    正則驗證 YYYY/MM 格式                           UI 顯示「格式有誤」
  查詢無資料（0 筆）                  判斷 allCases.length === 0                      UI 顯示「0 筆」+ 重新整理按鈕
  ----------------------------------- ----------------------------------------------- -------------------------------------------

**八、部署規格**

**8.1 環境需求**

  ------------------ ----------------------------------------------------------------------
  **項目**           **需求**
  作業系統           Windows 10/11（64-bit）
  Python 版本        3.10 以上（型態提示 str \| None 語法）
  必要 Python 套件   extract-msg（.msg 解析）、openpyxl（Excel）、requests（Mantis SOAP）
  瀏覽器             Chrome 90+ 或 Edge 90+（支援 ES2020+、ExcelJS）
  網路連線           CDN 載入時需連外（React/ExcelJS）；純下載報表時可離線（需預先快取）
  磁碟空間           主程式 \< 1MB；cs\_tracker.db 視資料量，一般 \< 10MB
  ------------------ ----------------------------------------------------------------------

**8.2 安裝步驟（一般使用者）**

-   下載並解壓 HCP客服工具包\_遷移包.zip 至目標資料夾（如 D:\\01HCP\\Claude）

-   雙擊執行「新電腦初始設定.bat」→ 自動安裝 Python 3 與必要套件

-   雙擊執行「執行信件處理.bat」→ 首次執行觸發設定精靈，輸入信件路徑

-   設定完成後，將待處理 .msg 信件放入收件夾，再次執行「執行信件處理.bat」

-   開啟「客服工作流程助理.html」，按 F5 重新整理後即可看到案件並下載報表

**8.3 打包為 .exe**

-   執行「打包為exe.bat」→ 使用 PyInstaller \--onefile 打包 email\_processor.py 和 mantis\_sync.py

-   產生於 dist\_exe/ 資料夾：「信件處理器.exe」和「Mantis同步.exe」

-   優點：目標電腦無需安裝 Python；缺點：打包檔較大（約 30-60MB），啟動較慢

**8.4 ZIP 遷移包結構（HCP客服工具包\_遷移包.zip）**

  ---------------------------------- -------------- ------------------------------------
  **檔案**                           **是否必要**   **說明**
  email\_processor.py                必要           核心引擎
  rules\_config.py                   必要           分類規則
  mantis\_sync.py                    必要           Mantis 同步
  rules\_editor.py                   建議           規則 GUI 編輯器
  客服工作流程助理.html              必要           瀏覽器 UI
  客服系統安裝精靈.html              建議           安裝引導
  user\_config.json                  可選           複製時可帶走路徑設定（勿納入版控）
  cs\_tracker.db                     可選           若需遷移歷史資料則帶走
  cs\_cases\_data.js / qa\_data.js   可選           對應 DB 的快取，可重新產生
  \*.bat                             建議           一鍵執行腳本
  QA手冊\_匯入範本.xlsx              建議           QA 匯入格式範本
  MSG讀取與寫入邏輯文件.docx         建議           開發技術文件
  ---------------------------------- -------------- ------------------------------------

**九、重構建議**

**9.1 架構重構優先建議**

-   **【高優先】拆分 email\_processor.py：依責任切為 msg\_reader.py、case\_manager.py、classifier.py、anonymizer.py、exporter.py**

-   **【高優先】拆分 客服工作流程助理.html：React 組件獨立化，使用 Vite 或 Create React App 打包，不再依賴 CDN**

-   **【中優先】規則引擎資料化：將 rules\_config.py 的規則存入 SQLite（rule\_engine 表），透過 CRUD 介面管理，取代 Python 文字編輯**

-   **【中優先】資料更新機制：改用 Fetch API 定期輪詢或 WebSocket 推送更新，取代靜態 \<script src\> 載入**

-   **【低優先】多人協作：若有多人同時使用需求，改用 PostgreSQL + FastAPI backend**

**9.2 建議新增功能**

-   自動化測試：pytest + 模擬 .msg 信件，覆蓋 F01-F05

-   Email 直連：IMAP 或 Exchange EWS API，取代手動匯出 .msg

-   全文搜尋：SQLite FTS5 或 Whoosh，讓 QA 知識庫可按內容搜尋

-   Dashboard 視覺化：ECharts 或 Chart.js 圖表，取代純文字統計

-   帳密安全：Mantis 帳密改用 Windows Credential Manager 或加密存儲

**9.3 現行版本已知限制**

-   cs\_cases\_data.js 靜態載入：每次信件處理後必須手動重新整理頁面才能看到新資料

-   HTML 需要 CDN：離線環境下 React 和 ExcelJS 無法載入

-   規則設定有三個入口（.py 直接編輯 / rules\_editor.py / HTML RulesEditorTab），可能造成不一致

-   email\_processor.py 超過 3000 行，維護困難

-   沒有自動化測試覆蓋，重構風險較高
