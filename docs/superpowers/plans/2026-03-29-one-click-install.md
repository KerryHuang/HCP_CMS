# 一鍵安裝方案 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立開發者一鍵安裝腳本（Windows + macOS）、Inno Setup 安裝精靈、修復 3 個 macOS 相容性問題，並更新 README。

**Architecture:** 平台原生腳本（PowerShell / Bash）處理開發環境安裝；Inno Setup `.iss` 腳本把 PyInstaller 產出包成安裝程式；macOS 修復集中在 3 個既有檔案 + 1 個新建的 `ui/utils.py` 共用函式。

**Tech Stack:** PowerShell, Bash, Inno Setup 6, PyInstaller, PySide6

**Spec:** `docs/superpowers/specs/2026-03-29-one-click-install-design.md`

---

## 檔案結構

```
新建：
  scripts/setup-dev.ps1        # Windows 開發者一鍵安裝
  scripts/setup-dev.sh         # macOS 開發者一鍵安裝
  scripts/installer.iss        # Inno Setup 安裝精靈腳本
  src/hcp_cms/ui/utils.py      # 跨平台共用函式

修改：
  src/hcp_cms/ui/report_view.py:219    # os.startfile → open_file
  src/hcp_cms/ui/theme.py:140-153      # winreg → 跨平台主題偵測
  src/hcp_cms/data/seed_rules.py:318   # 硬編碼路徑 → get_default_db_path
  README.md                            # 更新安裝說明

測試：
  tests/unit/test_ui_utils.py          # open_file 測試
  tests/unit/test_theme_detect.py      # 跨平台主題偵測測試
  tests/unit/test_seed_rules_path.py   # seed_rules 路徑測試
```

---

### Task 1: 跨平台開檔共用函式 `open_file`

**Files:**
- Create: `src/hcp_cms/ui/utils.py`
- Create: `tests/unit/test_ui_utils.py`
- Modify: `src/hcp_cms/ui/report_view.py:3-5,219`

- [ ] **Step 1: 建立 test_ui_utils.py 寫失敗測試**

```python
"""跨平台開檔函式測試。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


class TestOpenFile:
    """測試 open_file 跨平台開檔。"""

    @patch("platform.system", return_value="Windows")
    @patch("os.startfile", create=True)
    def test_windows_使用_startfile(self, mock_startfile, _mock_sys):
        from hcp_cms.ui.utils import open_file

        open_file(Path("report.xlsx"))
        mock_startfile.assert_called_once_with(Path("report.xlsx"))

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen")
    def test_macos_使用_open(self, mock_popen, _mock_sys):
        from hcp_cms.ui.utils import open_file

        open_file(Path("report.xlsx"))
        mock_popen.assert_called_once_with(["open", "report.xlsx"])

    @patch("platform.system", return_value="Linux")
    @patch("subprocess.Popen")
    def test_linux_使用_xdg_open(self, mock_popen, _mock_sys):
        from hcp_cms.ui.utils import open_file

        open_file(Path("report.xlsx"))
        mock_popen.assert_called_once_with(["xdg-open", "report.xlsx"])
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_ui_utils.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hcp_cms.ui.utils'`

- [ ] **Step 3: 建立 `src/hcp_cms/ui/utils.py`**

```python
"""UI 層跨平台共用函式。"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path


def open_file(path: Path) -> None:
    """跨平台開啟檔案（Windows: startfile, macOS: open, Linux: xdg-open）。"""
    system = platform.system()
    if system == "Windows":
        os.startfile(path)  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
```

- [ ] **Step 4: 執行測試確認通過**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_ui_utils.py -v`
Expected: 3 passed

- [ ] **Step 5: 修改 `report_view.py` 使用 `open_file`**

將 `report_view.py` 第 5 行的 `import os` 移除（若其他地方不再使用 `os`），新增 import：

```python
from hcp_cms.ui.utils import open_file
```

將第 219 行：
```python
                os.startfile(path)  # type: ignore[attr-defined]
```
改為：
```python
                open_file(path)
```

- [ ] **Step 6: 執行全部測試確認無迴歸**

Run: `.venv/Scripts/python.exe -m pytest tests/ -v --tb=short`
Expected: all passed

- [ ] **Step 7: Commit**

```bash
git add src/hcp_cms/ui/utils.py tests/unit/test_ui_utils.py src/hcp_cms/ui/report_view.py
git commit -m "feat: 跨平台開檔函式 open_file — 取代 os.startfile"
```

---

### Task 2: macOS 系統主題偵測

**Files:**
- Modify: `src/hcp_cms/ui/theme.py:140-153`
- Create: `tests/unit/test_theme_detect.py`

- [ ] **Step 1: 建立 test_theme_detect.py 寫失敗測試**

```python
"""系統主題偵測跨平台測試。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestDetectSystemLight:
    """測試 _detect_system_light 跨平台偵測。"""

    @patch("platform.system", return_value="Windows")
    def test_windows_淺色模式(self, _mock_sys):
        mock_winreg = MagicMock()
        mock_winreg.QueryValueEx.return_value = (1, 1)
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            from hcp_cms.ui.theme import ThemeManager

            tm = ThemeManager.__new__(ThemeManager)
            assert tm._detect_system_light() is True

    @patch("platform.system", return_value="Windows")
    def test_windows_深色模式(self, _mock_sys):
        mock_winreg = MagicMock()
        mock_winreg.QueryValueEx.return_value = (0, 1)
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            from hcp_cms.ui.theme import ThemeManager

            tm = ThemeManager.__new__(ThemeManager)
            assert tm._detect_system_light() is False

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.run")
    def test_macos_淺色模式(self, mock_run, _mock_sys):
        mock_run.return_value = MagicMock(returncode=1)  # 無 Dark 設定 = 淺色
        from hcp_cms.ui.theme import ThemeManager

        tm = ThemeManager.__new__(ThemeManager)
        assert tm._detect_system_light() is True

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.run")
    def test_macos_深色模式(self, mock_run, _mock_sys):
        mock_run.return_value = MagicMock(returncode=0)  # 有 Dark 設定 = 深色
        from hcp_cms.ui.theme import ThemeManager

        tm = ThemeManager.__new__(ThemeManager)
        assert tm._detect_system_light() is False

    @patch("platform.system", return_value="Linux")
    def test_未知平台_預設深色(self, _mock_sys):
        from hcp_cms.ui.theme import ThemeManager

        tm = ThemeManager.__new__(ThemeManager)
        assert tm._detect_system_light() is False
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_theme_detect.py -v`
Expected: FAIL — macOS 和 Linux 測試應失敗（目前只有 winreg 邏輯）

- [ ] **Step 3: 修改 `theme.py` 的 `_detect_system_light` 方法**

將 `theme.py` 第 140-153 行替換為：

```python
    def _detect_system_light(self) -> bool:
        """偵測系統是否為淺色模式（Windows / macOS）。"""
        import platform

        system = platform.system()
        try:
            if system == "Windows":
                import winreg

                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                )
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                winreg.CloseKey(key)
                return value == 1
            elif system == "Darwin":
                import subprocess

                result = subprocess.run(
                    ["defaults", "read", "-g", "AppleInterfaceStyle"],
                    capture_output=True,
                    text=True,
                )
                return result.returncode != 0
        except Exception:
            pass
        return False
```

- [ ] **Step 4: 執行測試確認通過**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_theme_detect.py -v`
Expected: 5 passed

- [ ] **Step 5: 執行全部測試確認無迴歸**

Run: `.venv/Scripts/python.exe -m pytest tests/ -v --tb=short`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add src/hcp_cms/ui/theme.py tests/unit/test_theme_detect.py
git commit -m "feat: macOS 系統主題偵測 — defaults read AppleInterfaceStyle"
```

---

### Task 3: seed_rules.py 路徑修復

**Files:**
- Modify: `src/hcp_cms/data/seed_rules.py:318`
- Create: `tests/unit/test_seed_rules_path.py`

- [ ] **Step 1: 建立 test_seed_rules_path.py 寫失敗測試**

```python
"""seed_rules 路徑修復測試。"""

from __future__ import annotations

from unittest.mock import patch


class TestSeedRulesPath:
    """確認 seed_rules.main() 使用跨平台路徑。"""

    @patch("platform.system", return_value="Darwin")
    @patch("pathlib.Path.home")
    def test_macos_使用_library_application_support(self, mock_home, _mock_sys):
        from pathlib import Path

        mock_home.return_value = Path("/Users/testuser")

        from hcp_cms.app import get_default_db_path

        result = get_default_db_path()
        assert "Library/Application Support/HCP_CMS" in str(result)

    @patch("platform.system", return_value="Windows")
    def test_windows_使用_appdata(self, _mock_sys):
        from hcp_cms.app import get_default_db_path

        result = get_default_db_path()
        assert "HCP_CMS" in str(result)
```

- [ ] **Step 2: 執行測試確認通過**（這是驗證 `get_default_db_path` 已正確的基線測試）

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_seed_rules_path.py -v`
Expected: 2 passed

- [ ] **Step 3: 修改 `seed_rules.py` 第 318 行**

將：
```python
    db_path = Path(os.environ.get("APPDATA", str(Path.home()))) / "HCP_CMS" / "cs_tracker.db"
```
改為：
```python
    from hcp_cms.app import get_default_db_path

    db_path = get_default_db_path()
```

- [ ] **Step 4: 執行全部測試確認無迴歸**

Run: `.venv/Scripts/python.exe -m pytest tests/ -v --tb=short`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/data/seed_rules.py tests/unit/test_seed_rules_path.py
git commit -m "fix: seed_rules 使用 get_default_db_path 統一跨平台路徑"
```

---

### Task 4: Windows 開發者一鍵安裝腳本

**Files:**
- Create: `scripts/setup-dev.ps1`

- [ ] **Step 1: 建立 `scripts/setup-dev.ps1`**

```powershell
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
    # 刷新 PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    Write-Ok "Git 安裝完成"
}

# ── 2. 檢查 Python ──
Write-Step "檢查 Python >= $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR..."

function Get-PythonCmd {
    # 嘗試 py launcher → python → python3
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
```

- [ ] **Step 2: 在 Windows 上手動測試腳本**

Run: `powershell -ExecutionPolicy Bypass -File scripts/setup-dev.ps1`
Expected: 每個步驟顯示 OK，最後顯示完成訊息

- [ ] **Step 3: Commit**

```bash
git add scripts/setup-dev.ps1
git commit -m "feat: Windows 開發者一鍵安裝腳本 setup-dev.ps1"
```

---

### Task 5: macOS 開發者一鍵安裝腳本

**Files:**
- Create: `scripts/setup-dev.sh`

- [ ] **Step 1: 建立 `scripts/setup-dev.sh`**

```bash
#!/usr/bin/env bash
# HCP CMS 開發環境一鍵安裝（macOS）
# 用法：chmod +x scripts/setup-dev.sh && ./scripts/setup-dev.sh

set -euo pipefail

MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10
INSTALL_PYTHON_VERSION="3.14"

step()  { printf "\n\033[36m==> %s\033[0m\n" "$1"; }
ok()    { printf "    \033[32mOK: %s\033[0m\n" "$1"; }
fail()  { printf "    \033[31mFAIL: %s\033[0m\n" "$1"; }

# ── 0. 確認在專案根目錄 ──
if [ ! -f "pyproject.toml" ]; then
    fail "請在專案根目錄執行此腳本（找不到 pyproject.toml）"
    exit 1
fi

# ── 1. 檢查 Homebrew ──
step "檢查 Homebrew..."
if command -v brew &>/dev/null; then
    ok "$(brew --version | head -1)"
else
    fail "未偵測到 Homebrew，請先安裝："
    echo '    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    echo "    安裝完成後重新執行此腳本。"
    exit 1
fi

# ── 2. 檢查 Git ──
step "檢查 Git..."
if command -v git &>/dev/null; then
    ok "$(git --version)"
else
    echo "    未偵測到 Git，透過 brew 安裝..."
    brew install git
    ok "Git 安裝完成"
fi

# ── 3. 檢查 Python ──
step "檢查 Python >= ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}..."

find_python() {
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            ver=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [ "$major" -gt "$MIN_PYTHON_MAJOR" ] || { [ "$major" -eq "$MIN_PYTHON_MAJOR" ] && [ "$minor" -ge "$MIN_PYTHON_MINOR" ]; }; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

PY=$(find_python) || true
if [ -n "$PY" ]; then
    ok "$($PY --version)"
else
    echo "    未偵測到 Python >= ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}，透過 brew 安裝..."
    brew install "python@${INSTALL_PYTHON_VERSION}"
    PY=$(find_python) || {
        fail "Python 已安裝但無法偵測，請重新開啟終端後再執行此腳本"
        exit 1
    }
    ok "$($PY --version)"
fi

# ── 4. 建立虛擬環境 ──
step "建立虛擬環境 .venv..."
if [ -d ".venv" ]; then
    ok "已存在，跳過建立"
else
    $PY -m venv .venv
    ok "建立完成"
fi

# ── 5. 安裝依賴 ──
step "安裝依賴套件（含開發工具）..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
ok "依賴安裝完成"

# ── 6. 驗證 ──
step "驗證安裝..."
ALL_OK=true

verify() {
    local name=$1 cmd=$2
    if output=$(eval "$cmd" 2>&1); then
        ok "$name: $output"
    else
        fail "$name 驗證失敗"
        ALL_OK=false
    fi
}

verify "PySide6" '.venv/bin/python -c "import PySide6; print(PySide6.__version__)"'
verify "pytest"  '.venv/bin/python -m pytest --version'
verify "ruff"    '.venv/bin/ruff --version'

if [ "$ALL_OK" = false ]; then
    echo ""
    fail "部分驗證失敗，請檢查上方訊息。"
    exit 1
fi

# ── 完成 ──
printf "\n\033[32m========================================\033[0m\n"
printf "\033[32m HCP CMS 開發環境安裝完成！\033[0m\n"
printf "\033[32m========================================\033[0m\n"
echo ""
echo "常用指令："
echo "  啟動應用程式:  .venv/bin/python -m hcp_cms"
echo "  執行測試:      .venv/bin/python -m pytest tests/ -v"
echo "  程式碼檢查:    .venv/bin/ruff check src/ tests/"
echo ""
```

- [ ] **Step 2: 確認腳本有執行權限**

Run: `chmod +x scripts/setup-dev.sh`

- [ ] **Step 3: Commit**

```bash
git add scripts/setup-dev.sh
git commit -m "feat: macOS 開發者一鍵安裝腳本 setup-dev.sh"
```

---

### Task 6: Inno Setup 安裝精靈腳本

**Files:**
- Create: `scripts/installer.iss`

- [ ] **Step 1: 建立 `scripts/installer.iss`**

```iss
; HCP CMS Inno Setup 安裝精靈
; 編譯方式：iscc scripts/installer.iss
; 前置條件：先執行 python scripts/build.py 產生 dist/HCP_CMS/

#define MyAppName "HCP 客服管理系統"
#define MyAppNameEn "HCP CMS"
#define MyAppVersion "2.1.0"
#define MyAppPublisher "HCP"
#define MyAppExeName "HCP_CMS.exe"
#define MyAppURL "https://github.com/KerryHuang/HCP_CMS"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppNameEn}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=HCP_CMS_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "建立桌面捷徑"; GroupDescription: "其他選項:"; Flags: checked

[Files]
Source: "..\dist\HCP_CMS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\解除安裝 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即啟動 {#MyAppName}"; Flags: nowait postinstall skipifsilent
```

- [ ] **Step 2: 驗證 `.iss` 語法**（需要本機安裝 Inno Setup）

Run: `"C:\Program Files (x86)\Inno Setup 6\iscc.exe" scripts/installer.iss` （若已安裝）
或跳過此步驟，待 CI/CD 或手動驗證。

- [ ] **Step 3: Commit**

```bash
git add scripts/installer.iss
git commit -m "feat: Inno Setup 安裝精靈腳本 — 桌面捷徑、開始選單、解除安裝"
```

---

### Task 7: 更新 README.md 安裝說明

**Files:**
- Modify: `README.md:17-61`

- [ ] **Step 1: 替換 README.md 的「系統需求」和「快速開始」區塊**

將第 17-68 行（系統需求 + 快速開始的 4 個小節）替換為：

```markdown
## 系統需求

| 項目 | Windows | macOS |
|------|---------|-------|
| 作業系統 | Windows 10 1709+ | macOS 12+ |
| 磁碟空間 | ~200MB（含依賴） | ~200MB（含依賴） |
| 套件管理器 | winget（內建） | [Homebrew](https://brew.sh) |

## 安裝（一般使用者）

1. 從 [Releases](https://github.com/KerryHuang/HCP_CMS/releases) 頁面下載 `HCP_CMS_Setup_x.x.x.exe`
2. 執行安裝精靈，依提示完成安裝
3. 從桌面捷徑或開始選單啟動「HCP 客服管理系統」

> 安裝包已包含所有執行時依賴，不需要額外安裝 Python。

## 安裝（開發者）

一鍵安裝腳本會自動檢查並安裝 Git、Python，建立虛擬環境，安裝所有依賴。

### Windows

在專案根目錄開啟 PowerShell，執行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-dev.ps1
```

### macOS

前置條件：先安裝 [Homebrew](https://brew.sh)。

```bash
chmod +x scripts/setup-dev.sh && ./scripts/setup-dev.sh
```

### 腳本會自動完成

- 檢查並安裝 Git（winget / brew）
- 檢查並安裝 Python >= 3.10（winget / brew）
- 建立 `.venv` 虛擬環境
- 安裝所有依賴套件（含開發工具）
- 驗證安裝結果（PySide6 / pytest / ruff）

### 手動安裝

如果你偏好手動安裝，或一鍵腳本不適用於你的環境：

```bash
git clone https://github.com/KerryHuang/HCP_CMS.git
cd HCP_CMS
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS:   source .venv/bin/activate
pip install -e ".[dev]"
```

## 啟動與開發

```bash
# 啟動應用程式
.venv/Scripts/python -m hcp_cms          # Windows
.venv/bin/python -m hcp_cms              # macOS

# 執行測試
.venv/Scripts/python -m pytest tests/ -v           # Windows
.venv/bin/python -m pytest tests/ -v               # macOS

# 程式碼品質
.venv/Scripts/ruff check src/ tests/               # Windows
.venv/bin/ruff check src/ tests/                    # macOS
```
```

- [ ] **Step 2: 檢查 README 格式正確**

Run: 用文字編輯器或 preview 工具確認 markdown 渲染正常。

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: 更新 README 安裝說明 — 一般使用者 + 開發者雙軌"
```

---

## 實作順序摘要

| Task | 內容 | 依賴 |
|------|------|------|
| 1 | 跨平台開檔函式 `open_file` | 無 |
| 2 | macOS 系統主題偵測 | 無 |
| 3 | seed_rules.py 路徑修復 | 無 |
| 4 | Windows 一鍵安裝腳本 | 無 |
| 5 | macOS 一鍵安裝腳本 | 無 |
| 6 | Inno Setup 安裝精靈 | 無 |
| 7 | 更新 README | Task 4, 5, 6 完成後 |

Task 1-6 彼此無依賴，可平行開發。Task 7 最後執行。
