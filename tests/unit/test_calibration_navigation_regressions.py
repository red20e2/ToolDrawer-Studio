from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QCursor, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tooldrawer_studio.ui.calibration_main_window import CalibrationMainWindow
from tooldrawer_studio.ui.calibration_view import CalibrationImageView


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _image_bytes(width: int = 1600, height: int = 1200) -> bytes:
    pixels = np.full((height, width, 3), 255, dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    return encoded.tobytes()


def _viewport_center_scene(view: CalibrationImageView) -> QPointF:
    return view.mapToScene(view.viewport().rect().center())


def test_space_plus_left_drag_pans_actual_size_image():
    app = _app()
    view = CalibrationImageView()
    view.resize(500, 350)
    view.show()
    app.processEvents()
    view.set_image_bytes(_image_bytes(2200, 1800))
    view.set_actual_size()
    app.processEvents()

    before = (view.horizontalScrollBar().value(), view.verticalScrollBar().value())
    start = QPoint(250, 175)
    end = QPoint(180, 120)
    QTest.keyPress(view, Qt.Key.Key_Space)
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(view.viewport(), end)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    QTest.keyRelease(view, Qt.Key.Key_Space)
    app.processEvents()

    after = (view.horizontalScrollBar().value(), view.verticalScrollBar().value())
    assert after != before
    assert view.is_fit_mode() is False
    view.close()


def test_double_click_returns_manual_view_to_fit_image():
    app = _app()
    view = CalibrationImageView()
    view.resize(700, 500)
    view.show()
    app.processEvents()
    view.set_image_bytes(_image_bytes())
    view.set_actual_size()
    assert view.is_fit_mode() is False

    QTest.mouseDClick(
        view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=view.viewport().rect().center(),
    )
    app.processEvents()

    assert view.is_fit_mode() is True
    assert view.zoom_percent() < 100.0
    view.close()


def test_wheel_zoom_preserves_scene_location_under_pointer():
    app = _app()
    view = CalibrationImageView()
    view.resize(700, 500)
    view.show()
    app.processEvents()
    view.set_image_bytes(_image_bytes(2400, 1600))
    view.set_actual_size()
    app.processEvents()

    anchor = QPoint(215, 160)
    global_anchor = view.viewport().mapToGlobal(anchor)
    QCursor.setPos(global_anchor)
    app.processEvents()
    before = view.mapToScene(anchor)

    event = QWheelEvent(
        QPointF(anchor),
        QPointF(global_anchor),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    QApplication.sendEvent(view.viewport(), event)
    app.processEvents()
    after = view.mapToScene(anchor)

    assert view.zoom_percent() == pytest.approx(120.0, abs=1.0)
    assert after.x() == pytest.approx(before.x(), abs=2.0)
    assert after.y() == pytest.approx(before.y(), abs=2.0)
    view.close()


def test_manual_transform_and_scene_center_survive_representative_resizes():
    app = _app()
    view = CalibrationImageView()
    view.resize(800, 600)
    view.show()
    app.processEvents()
    view.set_image_bytes(_image_bytes(2600, 1900))
    view.set_actual_size()
    view.centerOn(QPointF(1300.0, 950.0))
    app.processEvents()

    scale = view.transform().m11()
    center = _viewport_center_scene(view)
    for width, height in ((1100, 700), (1366, 768), (1920, 1080), (2560, 1440)):
        view.resize(width, height)
        app.processEvents()
        current = _viewport_center_scene(view)
        assert view.transform().m11() == pytest.approx(scale, rel=1e-6)
        assert current.x() == pytest.approx(center.x(), abs=2.0)
        assert current.y() == pytest.approx(center.y(), abs=2.0)
    view.close()


def test_fit_mode_keeps_entire_image_inside_viewport_after_resizes():
    app = _app()
    view = CalibrationImageView()
    view.show()
    app.processEvents()
    view.set_image_bytes(_image_bytes(700, 1500))

    for width, height in ((1100, 700), (1366, 768), (1920, 1080), (2560, 1440)):
        view.resize(width, height)
        app.processEvents()
        image_rect = view._pixmap_item.boundingRect()
        top_left = view.mapFromScene(image_rect.topLeft())
        bottom_right = view.mapFromScene(image_rect.bottomRight())
        viewport = view.viewport().rect().adjusted(-2, -2, 2, 2)
        assert viewport.contains(top_left)
        assert viewport.contains(bottom_right)
        assert view.is_fit_mode() is True
    view.close()


@pytest.mark.parametrize("view_size", [(800, 600), (1000, 750), (1280, 960)])
def test_same_scene_target_produces_same_image_coordinate_at_different_logical_sizes(view_size):
    app = _app()
    view = CalibrationImageView()
    view.resize(*view_size)
    view.show()
    app.processEvents()
    view.set_image_bytes(_image_bytes(1600, 1000))
    view.set_required_points(2)
    app.processEvents()

    target = view.mapFromScene(QPointF(640.0, 360.0))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=target)
    app.processEvents()

    point = view.points_px()[0]
    assert point.x_px == pytest.approx(640.0, abs=2.0)
    assert point.y_px == pytest.approx(360.0, abs=2.0)
    view.close()


def test_calibration_method_switch_does_not_reset_manual_view():
    app = _app()
    window = CalibrationMainWindow()
    window.show()
    app.processEvents()
    try:
        view = window.calibration_view
        view.set_image_bytes(_image_bytes(2200, 1500))
        view.set_actual_size()
        view.centerOn(QPointF(1200.0, 760.0))
        app.processEvents()
        scale = view.transform().m11()
        center = _viewport_center_scene(view)

        for index in (1, 3, 0):
            window.calibration_mode.setCurrentIndex(index)
            app.processEvents()

        current = _viewport_center_scene(view)
        assert view.transform().m11() == pytest.approx(scale, rel=1e-6)
        assert current.x() == pytest.approx(center.x(), abs=2.0)
        assert current.y() == pytest.approx(center.y(), abs=2.0)
        assert view.is_fit_mode() is False
    finally:
        window.close()
