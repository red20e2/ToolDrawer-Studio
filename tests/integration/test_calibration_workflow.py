from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tooldrawer_studio.calibration.presets import A4
from tooldrawer_studio.calibration.service import PixelPoint
from tooldrawer_studio.ui.calibration_main_window import CalibrationMainWindow
from tooldrawer_studio.ui.workflow_controller import WorkflowController


def test_paper_calibration_survives_save_reopen_and_traces(
    tmp_path: Path, simple_tools_image_path: Path
):
    controller = WorkflowController()
    controller.import_image(simple_tools_image_path)
    record = controller.calibrate_paper(
        (
            PixelPoint(0, 0),
            PixelPoint(299, 0),
            PixelPoint(299, 199),
            PixelPoint(0, 199),
        ),
        A4,
    )

    assert record.method == "paper:a4"
    assert record.confidence >= 0.75
    assert len(controller.trace_tools()) == 2

    project_path = tmp_path / "paper-calibrated.tds"
    controller.save(project_path)
    reopened = WorkflowController.open(project_path)

    assert reopened.active_calibration is not None
    assert reopened.active_calibration.method == "paper:a4"
    assert len(reopened.trace_tools()) == 2


def test_known_distance_calibration_runs_through_canvas_sidebar(
    simple_tools_image_path: Path,
):
    app = QApplication.instance() or QApplication([])
    window = CalibrationMainWindow()
    window.show()
    app.processEvents()
    try:
        window.controller.import_image(simple_tools_image_path)
        window._reset_for_uncalibrated_active_image()
        window.calibration_sidebar.known_distance.setValue(100.0)
        window.calibration_sidebar.calibration_mode.setCurrentIndex(0)
        window._calibration_mode_changed()

        for scene_point in (QPointF(50.0, 100.0), QPointF(150.0, 100.0)):
            QTest.mouseClick(
                window.calibration_view.viewport(),
                Qt.MouseButton.LeftButton,
                pos=window.calibration_view.mapFromScene(scene_point),
            )
        app.processEvents()

        window._calibrate()

        assert window.controller.active_calibration is not None
        assert window.controller.active_calibration.method == "known_distance"
        assert window.tabs.isTabEnabled(1) is True
    finally:
        window.close()


def test_failed_calibration_keeps_selected_points_for_correction(
    simple_tools_image_path: Path,
):
    app = QApplication.instance() or QApplication([])
    window = CalibrationMainWindow()
    errors: list[str] = []
    window._show_error = lambda exc: errors.append(str(exc))  # type: ignore[method-assign]
    window.show()
    app.processEvents()
    try:
        window.controller.import_image(simple_tools_image_path)
        window._reset_for_uncalibrated_active_image()
        window.calibration_sidebar.calibration_mode.setCurrentIndex(0)
        window._calibration_mode_changed()

        QTest.mouseClick(
            window.calibration_view.viewport(),
            Qt.MouseButton.LeftButton,
            pos=window.calibration_view.mapFromScene(QPointF(50.0, 100.0)),
        )
        app.processEvents()
        before = window.calibration_view.points_px()

        window._calibrate()

        assert errors
        assert window.calibration_view.points_px() == before
    finally:
        window.close()
