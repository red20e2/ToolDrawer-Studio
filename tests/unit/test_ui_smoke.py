import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFileDialog

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
