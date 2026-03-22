# Phase 3-6 Implementation Plans

## Phase 3: Services 外部整合
- Task 1: MailProvider 抽象介面 + MSGReader 實作
- Task 2: IMAPProvider 實作
- Task 3: ExchangeProvider 實作
- Task 4: MantisClient 抽象介面 + REST/SOAP 實作
- Task 5: CredentialManager (keyring)

## Phase 4: Scheduler 排程
- Task 1: Scheduler 基礎架構 (QTimer + QThread worker)
- Task 2: EmailJob, SyncJob, BackupJob, ReportJob

## Phase 5: UI 層
- Task 1: MainWindow + 導覽框架
- Task 2: DashboardView
- Task 3: CaseView (案件管理)
- Task 4: KMSView (知識庫)
- Task 5: EmailView (信件處理)
- Task 6: MantisView + ReportView + RulesView + SettingsView

## Phase 6: i18n + 打包
- Task 1: i18n 框架 + 語系檔
- Task 2: app.py 進入點
- Task 3: PyInstaller 打包設定
