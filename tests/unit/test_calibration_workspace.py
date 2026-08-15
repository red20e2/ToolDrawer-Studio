from __future__ import annotations

import importlib
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from tooldrawer_studio.capture.pending import CaptureSessionService


def _workspace_type():
    module = importlib.import_module("tooldrawer_studio.ui.calibration_workspace")
    return module.CalibrationWorkspace


@pytest.mark.parametrize(
    "width,height",
    [
        (1100, 700),
        (1366, 768),
        (1920, 1080),
        (2560, 1440),
    ],
)
def test_canvas_gets_all_space_except_narrow_sidebar(width: int, height: int):
    app = QApplication.instance() or QApplication([])
    CalibrationWorkspace = _workspace_type()
    workspace = CalibrationWorkspace(CaptureSessionService())
    workspace.resize(width, height)
    workspace.show()
    app.processEvents()

    assert 300 <= workspace.sidebar.width() <= 340
    assert workspace.view.width() >= width - 390
    assert workspace.view.height() >= height - 40
    workspace.close()


def test_sidebar_collapse_preserves_view_and_sidebar_state():
    app = QApplication.instance() or QApplication([])
    CalibrationWorkspace = _workspace_type()
    workspace = CalibrationWorkspace(CaptureSessionService())
    workspace.resize(1200, 800)
    workspace.show()
    app.processEvents()

    workspace.sidebar.known_distance.setValue(150.0)
    original_view = workspace.view
    workspace.set_sidebar_collapsed(True)
    app.processEvents()
    assert workspace.sidebar_is_collapsed() is True
    assert workspace.sidebar.isVisible() is False

    workspace.set_sidebar_collapsed(False)
    app.processEvents()
    assert workspace.sidebar_is_collapsed() is False
    assert workspace.sidebar.known_distance.value() == pytest.approx(150.0)
    assert workspace.view is original_view
    workspace.close()
