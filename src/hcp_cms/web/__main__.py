"""HCP CMS Web Portal entry point.

啟動：python -m hcp_cms.web

環境變數：
    HCP_CMS_DB                資料庫檔案路徑（預設：~/.hcp_cms/cs_tracker.db）
    HCP_CMS_MANTIS_URL        Mantis 主機 URL（選用，未設定則 Mantis 推送停用）
    HCP_CMS_MANTIS_USER       Mantis 帳號
    HCP_CMS_MANTIS_PASS       Mantis 密碼
    HCP_CMS_MANTIS_PROJECT    Mantis 目標 project id
    HCP_CMS_MANTIS_CATEGORY   Mantis category（預設 General）
"""
import os
from pathlib import Path

from hcp_cms.data.database import DatabaseManager
from hcp_cms.services.credential import CredentialManager
from hcp_cms.web.app import create_app


def _resolve_mantis_config() -> dict:
    """從環境變數或 keyring 取 Mantis 設定。"""
    creds = CredentialManager()
    return {
        "base_url": os.environ.get("HCP_CMS_MANTIS_URL") or (creds.retrieve("mantis_url") or ""),
        "user": os.environ.get("HCP_CMS_MANTIS_USER") or (creds.retrieve("mantis_user") or ""),
        "password": os.environ.get("HCP_CMS_MANTIS_PASS") or (creds.retrieve("mantis_password") or ""),
        "project_id": os.environ.get("HCP_CMS_MANTIS_PROJECT", ""),
        "category": os.environ.get("HCP_CMS_MANTIS_CATEGORY", "General"),
    }


def main() -> None:
    db_path = Path(
        os.environ.get("HCP_CMS_DB") or (Path.home() / ".hcp_cms" / "cs_tracker.db")
    )
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = DatabaseManager(db_path)
    db.initialize()

    mantis_cfg = _resolve_mantis_config()
    create_app(
        conn=db.connection,
        db_dir=db_path.parent,
        mantis_base_url=mantis_cfg["base_url"],
        mantis_user=mantis_cfg["user"],
        mantis_password=mantis_cfg["password"],
        mantis_project_id=mantis_cfg["project_id"],
        mantis_category=mantis_cfg["category"],
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
