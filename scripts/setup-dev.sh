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
