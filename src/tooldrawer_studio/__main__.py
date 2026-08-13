import sys

from PySide6.QtWidgets import QApplication

from tooldrawer_studio.ui.release_window import ReleaseMainWindow
from tooldrawer_studio.version import APP_TITLE


def build_main_window() -> ReleaseMainWindow:
    window = ReleaseMainWindow()
    window.setWindowTitle(APP_TITLE)
    return window


def main() -> int:
    app = QApplication(sys.argv)
    window = build_main_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
