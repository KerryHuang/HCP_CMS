# 一鍵安裝方案設計

## 概述

為 HCP CMS 建立完整的安裝體驗：開發者一鍵安裝開發環境（Windows + macOS），一般使用者透過 Inno Setup 安裝精靈安裝應用程式。同時修復 3 個 macOS 相容性問題。

## 產出檔案

```
scripts/
├── setup-dev.ps1       # Windows 開發者一鍵安裝
├── setup-dev.sh        # macOS 開發者一鍵安裝
├── build.py            # PyInstaller 打包（已有）
└── installer.iss       # Inno Setup 安裝精靈腳本

src/hcp_cms/
├── ui/report_view.py   # 修復 os.startfile()
├── ui/theme.py         # 修復 macOS 主題偵測
└── data/seed_rules.py  # 修復路徑硬編碼

README.md               # 更新安裝說明
```

---

## 一、開發者一鍵安裝腳本

### 共用流程

```
開始
 ├─ 1. 檢查 Git → 沒有 → 自動安裝（winget / brew）
 ├─ 2. 檢查 Python >= 3.10 → 沒有 → 自動安裝（winget / brew）
 ├─ 3. 建立 .venv 虛擬環境
 ├─ 4. pip install -e ".[dev]"
 ├─ 5. 驗證安裝（import PySide6, pytest --version）
 └─ 完成 → 印出成功訊息 + 使用說明
```

### Windows `setup-dev.ps1`

| 步驟 | 動作 | 失敗處理 |
|------|------|----------|
| 檢查 Git | `git --version` | 執行 `winget install Git.Git`，裝完要求重開終端 |
| 檢查 Python | `py --version` 或 `python --version`，比對版號 >= 3.10 | 執行 `winget install Python.Python.3.14` |
| 建 venv | `python -m venv .venv` | 提示錯誤並中止 |
| 安裝依賴 | `.venv\Scripts\pip install -e ".[dev]"` | 顯示錯誤日誌路徑 |
| 驗證 | `.venv\Scripts\python -c "import PySide6"` | 提示可能的修復方式 |

### macOS `setup-dev.sh`

| 步驟 | 動作 | 失敗處理 |
|------|------|----------|
| 檢查 Homebrew | `brew --version` | 提示安裝指令（不自動裝 brew，需要使用者密碼） |
| 檢查 Git | `git --version` | `brew install git`（或提示 `xcode-select --install`） |
| 檢查 Python | `python3 --version`，比對版號 >= 3.10 | `brew install python@3.14` |
| 建 venv | `python3 -m venv .venv` | 提示錯誤並中止 |
| 安裝依賴 | `.venv/bin/pip install -e ".[dev]"` | 顯示錯誤日誌路徑 |
| 驗證 | `.venv/bin/python -c "import PySide6"` | 提示可能的修復方式 |

### 設計決策

- **Homebrew 不自動安裝** — 安裝 brew 需要 sudo 密碼，不適合靜默執行，偵測到缺少時印出安裝指令讓使用者自行執行
- **winget 優先** — Windows 10 1709+ 內建，覆蓋率最高；若偵測不到 winget 則提示手動下載連結
- **Python 版本** — 腳本指定安裝 3.14（專案當前使用版本），但允許 >= 3.10 的既有安裝通過檢查

---

## 二、Inno Setup 安裝精靈（一般使用者）

### 打包流程

```
PyInstaller 打包 (build.py)
 └─ dist/HCP_CMS/              # onedir 產出
      ├─ HCP_CMS.exe
      ├─ *.dll, *.pyd
      └─ hcp_cms/i18n/

Inno Setup 編譯 (installer.iss)
 └─ dist/HCP_CMS_Setup_2.1.0.exe   # 最終安裝檔
```

### 安裝精靈設定

| 項目 | 設定 |
|------|------|
| 安裝路徑 | `C:\Program Files\HCP_CMS`（可自訂） |
| 桌面捷徑 | 預設勾選建立 |
| 開始選單 | `HCP 客服管理系統` 資料夾 |
| 解除安裝 | 控制面板可解除，自動清理安裝檔案 |
| 資料庫位置 | 不包含在安裝目錄，維持 `%APPDATA%\HCP_CMS\`（解除安裝不刪除使用者資料） |
| 版號 | 從 `pyproject.toml` 讀取，顯示在安裝畫面 |

### 安裝頁面流程

```
歡迎頁 → 授權協議（可選）→ 選擇安裝路徑 → 選擇元件 → 安裝進度 → 完成（勾選立即啟動）
```

### 設計決策

- **不包含 Python runtime** — PyInstaller onedir 已自帶，安裝包獨立可執行
- **資料庫不隨安裝包** — 首次啟動時 `DatabaseManager` 自動建立，升級安裝不覆蓋使用者資料
- **版號自動化** — `installer.iss` 的版號由 build 流程從 `pyproject.toml` 注入，避免手動維護

---

## 三、macOS 相容性修復

### 修復 1：`os.startfile()` → 跨平台開檔（高優先）

**檔案**：`src/hcp_cms/ui/report_view.py:219`

抽成共用函式 `open_file(path)` 放在 `src/hcp_cms/ui/utils.py`：

```python
import os
import platform
import subprocess
from pathlib import Path

def open_file(path: Path) -> None:
    """跨平台開啟檔案。"""
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", str(path)])
    elif system == "Windows":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", str(path)])
```

`report_view.py` 改為呼叫 `open_file(path)`。

### 修復 2：系統主題偵測（中優先）

**檔案**：`src/hcp_cms/ui/theme.py:143-150`

```python
import platform
import subprocess

def _is_light_theme() -> bool:
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
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True,
            )
            # 回傳非 0 表示無 Dark 設定 → 淺色模式
            return result.returncode != 0
    except Exception:
        pass
    return False  # 預設深色模式
```

### 修復 3：`seed_rules.py` 路徑統一（低優先）

**檔案**：`src/hcp_cms/data/seed_rules.py:318`

```python
# 修復前
db_path = Path(os.environ.get("APPDATA", str(Path.home()))) / "HCP_CMS" / "cs_tracker.db"

# 修復後
from hcp_cms.app import get_default_db_path
db_path = get_default_db_path()
```

### 設計決策

- **修復 1** 抽共用函式，避免未來散落多處
- **修復 2** 保留 try-except 容錯，偵測失敗回傳深色模式（現有預設行為不變）
- **修復 3** 不新增邏輯，直接重用已有的 `get_default_db_path()`

---

## 四、README 更新

### 一般使用者區塊

```markdown
## 安裝（一般使用者）

1. 從 Releases 頁面下載 `HCP_CMS_Setup_x.x.x.exe`
2. 執行安裝精靈，依提示完成安裝
3. 從桌面捷徑或開始選單啟動「HCP 客服管理系統」
```

### 開發者區塊

```markdown
## 安裝（開發者）

### Windows
在專案根目錄，右鍵以 PowerShell 執行：
powershell -ExecutionPolicy Bypass -File scripts/setup-dev.ps1

### macOS
前置條件：先安裝 Homebrew（https://brew.sh）
chmod +x scripts/setup-dev.sh && ./scripts/setup-dev.sh

### 腳本會自動完成：
- 檢查並安裝 Git（winget / brew）
- 檢查並安裝 Python >= 3.10（winget / brew）
- 建立 .venv 虛擬環境
- 安裝所有依賴（含開發工具）
- 驗證安裝結果
```

### 系統需求表更新

| 項目 | Windows | macOS |
|------|---------|-------|
| 作業系統 | Windows 10 1709+ | macOS 12+ |
| 磁碟空間 | ~200MB | ~200MB |
| 套件管理器 | winget（內建） | Homebrew |
| 一鍵安裝 | `setup-dev.ps1` | `setup-dev.sh` |

### 設計決策

- 一般使用者放最前面，步驟最少（3 步完成）
- 開發者區塊清楚標示平台差異
- 移除原本假設使用者已會 `git clone` + `pip install` 的說明

---

## 實作順序

1. macOS 相容性修復（3 個檔案）— 基礎相容性先到位
2. 開發者一鍵安裝腳本（`.ps1` + `.sh`）
3. Inno Setup 安裝精靈腳本（`installer.iss`）
4. README 更新
