#!/usr/bin/env python3
"""Hook: 在 Write/Edit 後執行 ruff format（自動修正）+ ruff check（阻擋錯誤）"""
import json
import subprocess
import sys
import os

data = json.load(sys.stdin)
file_path = data.get("tool_input", {}).get("file_path", "")

if not file_path.endswith(".py"):
    sys.exit(0)

if not os.path.isfile(file_path):
    sys.exit(0)

project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
ruff = os.path.join(project_dir, ".venv", "Scripts", "ruff.exe")

if not os.path.isfile(ruff):
    ruff = "ruff"

# 自動格式化（不阻擋）
subprocess.run([ruff, "format", file_path], capture_output=True, text=True)

# Lint 檢查（有錯誤則阻擋）
result = subprocess.run(
    [ruff, "check", file_path, "--no-fix"],
    capture_output=True,
    text=True,
)

if result.returncode != 0:
    errors = result.stdout.strip().split("\n")[:10]
    print("\n".join(errors), file=sys.stderr)
    sys.exit(2)

sys.exit(0)
