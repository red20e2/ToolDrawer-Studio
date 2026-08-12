import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFileDialog

from tooldrawer_studio.calibration.service import PixelPoint
from tooldrawer_studio.ui.calibration_view import CalibrationImageView
from tooldrawer_studio.ui.main_window import MainWindow
from tooldrawer_studio.ui.workflow_controller import WorkflowController


def test_main_window_constructs_with_four_workflow_stages():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.windowTitle() == "ToolDrawer Studio"
    assert window.tabs.count() == 4
    assert isinstance(window.calibration_view, CalibrationImageView)
    assert window.calibration_mode.count() == 5
    assert window.calibration_mode.itemText(0) == "Known distance"
    assert window.calibration_mode.itemText(4) == "Printable target"
    assert window.low_confidence_override.isHidden()
    window.close()
    assert app is not None


def test_low_confidence_calibration_stays_on_warning_screen(
    monkeypatch, simple_tools_image_path: Path
):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.controller.import_image(simple_tools_image_path)
    monkeypatch.setattr(
        window.calibration_view,
        "points_px",
        lambda: (PixelPoint(0.0, 0.0), PixelPoint(20.0, 0.0)),
    )
    window.known_distance.setValue(10.0)
    window.tabs.setCurrentIndex(0)

    window._calibrate()

    assert window.controller.active_calibration is not None
    assert window.controller.active_calibration.confidence < 0.75
    assert not window.low_confidence_override.isHidden()
    assert window.tabs.currentIndex() == 0
    window.close()
    assert app is not None


def test_opening_uncalibrated_project_disables_detect_stage(
    monkeypatch, tmp_path: Path, simple_tools_image_path: Path
):
    app = QApplication.instance() or QApplication([])
    controller = WorkflowController()
    controller.import_image(simple_tools_image_path)
    project_path = tmp_path / "uncalibrated.tds"
    controller.save(project_path)

    window = MainWindow()
    window.tabs.setTabEnabled(1, True)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(project_path), "ToolDrawer Studio (*.tds)"),
    )

    window._open_project()

    assert not window.tabs.isTabEnabled(1)
    window.close()
    assert app is not None
