"""HCP CMS application entry point."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from hcp_cms import __version__
from hcp_cms.data.database import DatabaseManager
from hcp_cms.i18n.translator import load_language
from hcp_cms.ui.main_window import MainWindow


def get_default_db_path() -> Path:
    """Get default database path based on platform."""
    import platform

    if platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "HCP_CMS"
    else:
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / "HCP_CMS"
    base.mkdir(parents=True, exist_ok=True)
    return base / "cs_tracker.db"


def main() -> int:
    """Main entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("HCP CMS")
    app.setApplicationVersion(__version__)

    # Initialize i18n
    load_language("zh_TW")

    # Initialize database
    db_path = get_default_db_path()
    db = DatabaseManager(db_path)
    db.initialize()

    # Initialize theme
    from hcp_cms.ui.theme import ThemeManager

    theme_mgr = ThemeManager(db_path.parent)

    # Create and show main window
    window = MainWindow(db.connection, db_dir=db_path.parent, theme_mgr=theme_mgr)
    window.show()

    # Run application
    result = app.exec()

    # Cleanup
    db.close()

    return result


if __name__ == "__main__":
    sys.exit(main())
