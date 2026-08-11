import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from tooldrawer_studio.ui.main_window import MainWindow


def test_main_window_constructs_with_four_workflow_stages():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.windowTitle() == "ToolDrawer Studio"
    assert window.tabs.count() == 4
    window.close()
    assert app is not None
