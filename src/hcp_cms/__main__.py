"""HCP CMS 進入點"""

import sys

from PySide6.QtWidgets import QApplication

from hcp_cms.app import create_app


def main() -> None:
    app = QApplication(sys.argv)
    window = create_app()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
