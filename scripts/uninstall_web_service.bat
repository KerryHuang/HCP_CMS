@echo off
REM 解除 HCP CMS Web Portal Windows 服務
set SERVICE_NAME=HCP_CMS_Web

nssm stop %SERVICE_NAME%
nssm remove %SERVICE_NAME% confirm
echo HCP CMS Web Portal 服務已移除。
pause
