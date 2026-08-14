from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tooldrawer_studio.ui.calibration_main_window import CalibrationMainWindow


def test_f11_toggle_enters_and_leaves_fullscreen_without_hiding_workspace():
    app = QApplication.instance() or QApplication([])
    window = CalibrationMainWindow()
    window.show()
    app.processEvents()
    try:
        assert window.isFullScreen() is False
        window.toggle_fullscreen()
        app.processEvents()
        assert window.isFullScreen() is True
        assert window.tabs.isVisible() is True
        assert window.calibration_workspace.isVisible() is True

        window.toggle_fullscreen()
        app.processEvents()
        assert window.isFullScreen() is False
    finally:
        window.close()


def test_fullscreen_toggle_remembers_preexisting_maximized_state():
    app = QApplication.instance() or QApplication([])
    window = CalibrationMainWindow()
    window.showMaximized()
    app.processEvents()
    try:
        assert window.isMaximized() is True
        window.toggle_fullscreen()
        app.processEvents()
        assert window.isFullScreen() is True
        window.toggle_fullscreen()
        app.processEvents()
        assert window.isMaximized() is True
    finally:
        window.close()
