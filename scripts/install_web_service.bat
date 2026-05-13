@echo off
REM 安裝 HCP CMS Web Portal 為 Windows 服務（需要 NSSM）
REM 用法：以管理員身分執行此腳本
REM 編輯下方 SET 變數後再執行

setlocal

set SERVICE_NAME=HCP_CMS_Web
set PROJECT_ROOT=%~dp0..
set PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe

REM === 請依您的環境編輯以下變數 ===
set DB_PATH=C:\Users\Jill\.hcp_cms\cs_tracker.db
set MANTIS_URL=https://hcpservice.ares.com.tw/mantis
set MANTIS_USER=JILL
set MANTIS_PASS=YOUR_PASSWORD_HERE
set MANTIS_PROJECT=218
set MANTIS_CATEGORY=General
REM === 編輯結束 ===

REM 檢查 NSSM
where nssm >nul 2>nul
if errorlevel 1 (
    echo NSSM 未安裝。請從 https://nssm.cc 下載並加入 PATH。
    pause
    exit /b 1
)

REM 檢查 Python venv
if not exist "%PYTHON_EXE%" (
    echo Python venv 不存在於 %PYTHON_EXE%
    pause
    exit /b 1
)

REM 移除既有服務（若存在）
nssm stop %SERVICE_NAME% 2>nul
nssm remove %SERVICE_NAME% confirm 2>nul

REM 安裝
nssm install %SERVICE_NAME% "%PYTHON_EXE%" "-m" "hcp_cms.web"
nssm set %SERVICE_NAME% AppDirectory "%PROJECT_ROOT%"
nssm set %SERVICE_NAME% DisplayName "HCP CMS Web Portal"
nssm set %SERVICE_NAME% Description "客服 3 人共用 Web Portal（NiceGUI / port 8080）"
nssm set %SERVICE_NAME% Start SERVICE_AUTO_START
nssm set %SERVICE_NAME% AppStdout "%PROJECT_ROOT%\logs\web_service.log"
nssm set %SERVICE_NAME% AppStderr "%PROJECT_ROOT%\logs\web_service_error.log"

REM 環境變數
nssm set %SERVICE_NAME% AppEnvironmentExtra ^
    HCP_CMS_DB=%DB_PATH% ^
    HCP_CMS_MANTIS_URL=%MANTIS_URL% ^
    HCP_CMS_MANTIS_USER=%MANTIS_USER% ^
    HCP_CMS_MANTIS_PASS=%MANTIS_PASS% ^
    HCP_CMS_MANTIS_PROJECT=%MANTIS_PROJECT% ^
    HCP_CMS_MANTIS_CATEGORY=%MANTIS_CATEGORY%

mkdir "%PROJECT_ROOT%\logs" 2>nul

REM 啟動
nssm start %SERVICE_NAME%

echo.
echo === HCP CMS Web Portal 服務已安裝並啟動 ===
echo 開瀏覽器：http://localhost:8080
echo 設防火牆放行 port 8080 inbound 讓 LAN 其他客服可連
echo 日誌位置：%PROJECT_ROOT%\logs\
pause
