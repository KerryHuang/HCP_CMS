#Requires -Version 5.1
<#
.SYNOPSIS
    HCP CMS 開發環境一鍵安裝（Windows）
.DESCRIPTION
    自動檢查並安裝 Git、Python，建立虛擬環境，安裝所有依賴。
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/setup-dev.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$MIN_PYTHON_MAJOR = 3
$MIN_PYTHON_MINOR = 10
$INSTALL_PYTHON_VERSION = "3.14"

function Write-Step { param([string]$Message) Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Message) Write-Host "    OK: $Message" -ForegroundColor Green }
function Write-Fail { param([string]$Message) Write-Host "    FAIL: $Message" -ForegroundColor Red }

# ── 0. 確認在專案根目錄 ──
if (-not (Test-Path "pyproject.toml")) {
    Write-Fail "請在專案根目錄執行此腳本（找不到 pyproject.toml）"
    exit 1
}

# ── 1. 檢查 Git ──
Write-Step "檢查 Git..."
$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) {
    $gitVersion = & git --version
    Write-Ok $gitVersion
} else {
    Write-Host "    未偵測到 Git，嘗試透過 winget 安裝..." -ForegroundColor Yellow
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Fail "未偵測到 winget。請手動安裝 Git：https://git-scm.com/download/win"
        exit 1
    }
    winget install --id Git.Git --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Git 安裝失敗，請手動安裝：https://git-scm.com/download/win"
        exit 1
    }
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    Write-Ok "Git 安裝完成"
}

# ── 2. 檢查 Python ──
Write-Step "檢查 Python >= $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR..."

function Get-PythonCmd {
    foreach ($cmd in @("py", "python", "python3")) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found) {
            try {
                $ver = & $cmd --version 2>&1
                if ($ver -match "(\d+)\.(\d+)\.(\d+)") {
                    $major = [int]$Matches[1]
                    $minor = [int]$Matches[2]
                    if ($major -gt $MIN_PYTHON_MAJOR -or ($major -eq $MIN_PYTHON_MAJOR -and $minor -ge $MIN_PYTHON_MINOR)) {
                        return @{ Cmd = $cmd; Version = $ver }
                    }
                }
            } catch {}
        }
    }
    return $null
}

$python = Get-PythonCmd
if ($python) {
    Write-Ok $python.Version
} else {
    Write-Host "    未偵測到 Python >= $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR，嘗試透過 winget 安裝..." -ForegroundColor Yellow
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Fail "未偵測到 winget。請手動安裝 Python：https://www.python.org/downloads/"
        exit 1
    }
    winget install --id "Python.Python.$INSTALL_PYTHON_VERSION" --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Python 安裝失敗，請手動安裝：https://www.python.org/downloads/"
        exit 1
    }
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    $python = Get-PythonCmd
    if (-not $python) {
        Write-Fail "Python 已安裝但無法偵測，請重新開啟終端後再執行此腳本"
        exit 1
    }
    Write-Ok $python.Version
}

$PY = $python.Cmd

# ── 3. 建立虛擬環境 ──
Write-Step "建立虛擬環境 .venv..."
if (Test-Path ".venv") {
    Write-Ok "已存在，跳過建立"
} else {
    & $PY -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "建立虛擬環境失敗"
        exit 1
    }
    Write-Ok "建立完成"
}

# ── 4. 安裝依賴 ──
Write-Step "安裝依賴套件（含開發工具）..."
& .venv\Scripts\pip.exe install --upgrade pip
& .venv\Scripts\pip.exe install -e ".[dev]"
if ($LASTEXITCODE -ne 0) {
    Write-Fail "依賴安裝失敗，請查看上方錯誤訊息"
    exit 1
}
Write-Ok "依賴安裝完成"

# ── 5. 驗證 ──
Write-Step "驗證安裝..."
$checks = @(
    @{ Name = "PySide6";  Cmd = '.venv\Scripts\python.exe -c "import PySide6; print(PySide6.__version__)"' },
    @{ Name = "pytest";   Cmd = '.venv\Scripts\python.exe -m pytest --version' },
    @{ Name = "ruff";     Cmd = '.venv\Scripts\ruff.exe --version' }
)
$allOk = $true
foreach ($check in $checks) {
    try {
        $output = Invoke-Expression $check.Cmd 2>&1
        Write-Ok "$($check.Name): $output"
    } catch {
        Write-Fail "$($check.Name) 驗證失敗"
        $allOk = $false
    }
}

if (-not $allOk) {
    Write-Host "`n部分驗證失敗，請檢查上方訊息。" -ForegroundColor Yellow
    exit 1
}

# ── 完成 ──
Write-Host "`n========================================" -ForegroundColor Green
Write-Host " HCP CMS 開發環境安裝完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "常用指令："
Write-Host "  啟動應用程式:  .venv\Scripts\python.exe -m hcp_cms"
Write-Host "  執行測試:      .venv\Scripts\python.exe -m pytest tests/ -v"
Write-Host "  程式碼檢查:    .venv\Scripts\ruff.exe check src/ tests/"
Write-Host ""
