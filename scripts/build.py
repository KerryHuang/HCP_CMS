"""PyInstaller 打包腳本"""

import subprocess
import sys


def build() -> None:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "HCP_CMS",
        "--windowed",
        "--onedir",
        "--add-data", "src/hcp_cms/i18n:hcp_cms/i18n",
        "--add-data", "resources:resources",
        "src/hcp_cms/__main__.py",
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    build()
