import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tooldrawer_studio.ui.calibration_view import CalibrationImageView


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _image_bytes(width: int = 1000, height: int = 500) -> bytes:
    pixels = np.full((height, width, 3), 255, dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    return encoded.tobytes()


def test_center_click_maps_to_native_image_pixels():
    app = _app()
    view = CalibrationImageView()
    view.resize(500, 250)
    view.set_image_bytes(_image_bytes())
    view.set_required_points(2)
    view.show()
    app.processEvents()

    viewport_point = view.mapFromScene(QPointF(500.0, 250.0))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=viewport_point)
    app.processEvents()

    points = view.points_px()
    assert len(points) == 1
    assert points[0].x_px == pytest.approx(500.0, abs=3.0)
    assert points[0].y_px == pytest.approx(250.0, abs=3.0)
    view.close()


def test_click_after_required_count_starts_a_new_point_sequence():
    app = _app()
    view = CalibrationImageView()
    view.resize(500, 250)
    view.set_image_bytes(_image_bytes())
    view.set_required_points(2)
    view.show()
    app.processEvents()

    first = view.mapFromScene(QPointF(200.0, 200.0))
    second = view.mapFromScene(QPointF(800.0, 200.0))
    third = view.mapFromScene(QPointF(500.0, 400.0))
    for position in (first, second, third):
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=position)
        app.processEvents()

    points = view.points_px()
    assert len(points) == 1
    assert points[0].x_px == pytest.approx(500.0, abs=3.0)
    assert points[0].y_px == pytest.approx(400.0, abs=3.0)
    view.close()


def test_zero_required_points_disables_manual_collection():
    app = _app()
    view = CalibrationImageView()
    view.resize(500, 250)
    view.set_image_bytes(_image_bytes())
    view.set_required_points(0)
    view.show()
    app.processEvents()

    point = view.mapFromScene(QPointF(500.0, 250.0))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()

    assert view.points_px() == ()
    view.close()


def test_new_portrait_image_starts_in_fit_mode_and_reports_zoom():
    app = _app()
    view = CalibrationImageView()
    view.resize(900, 600)
    view.show()
    app.processEvents()
    view.set_image_bytes(_image_bytes(width=600, height=1200))
    app.processEvents()

    assert view.is_fit_mode() is True
    assert 0.0 < view.zoom_percent() <= 100.0
    view.close()


def test_new_landscape_image_starts_in_fit_mode_and_reports_zoom():
    app = _app()
    view = CalibrationImageView()
    view.resize(900, 600)
    view.show()
    app.processEvents()
    view.set_image_bytes(_image_bytes(width=1600, height=700))
    app.processEvents()

    assert view.is_fit_mode() is True
    assert 0.0 < view.zoom_percent() <= 100.0
    view.close()


def test_actual_size_is_100_percent_and_manual_view_survives_resize():
    app = _app()
    view = CalibrationImageView()
    view.resize(800, 600)
    view.show()
    app.processEvents()
    view.set_image_bytes(_image_bytes(width=1000, height=500))
    view.set_actual_size()

    assert view.zoom_percent() == pytest.approx(100.0, abs=0.5)
    assert view.is_fit_mode() is False

    before = view.transform().m11()
    view.resize(1000, 700)
    app.processEvents()
    assert view.transform().m11() == pytest.approx(before, rel=1e-6)
    view.close()


def test_zoom_scale_clamps_between_ten_and_sixteen_hundred_percent():
    app = _app()
    view = CalibrationImageView()
    view.resize(800, 600)
    view.show()
    app.processEvents()
    view.set_image_bytes(_image_bytes(width=1000, height=500))

    view._set_zoom_scale(0.001)
    assert view.zoom_percent() == pytest.approx(10.0, abs=0.5)
    assert view.is_fit_mode() is False

    view._set_zoom_scale(100.0)
    assert view.zoom_percent() == pytest.approx(1600.0, abs=0.5)
    view.close()


def test_middle_mouse_drag_pans_actual_size_image():
    app = _app()
    view = CalibrationImageView()
    view.resize(400, 300)
    view.show()
    app.processEvents()
    view.set_image_bytes(_image_bytes(width=2000, height=1600))
    view.set_actual_size()
    app.processEvents()

    before_x = view.horizontalScrollBar().value()
    before_y = view.verticalScrollBar().value()
    start = QPoint(200, 150)
    end = QPoint(140, 100)
    QTest.mousePress(view.viewport(), Qt.MouseButton.MiddleButton, pos=start)
    QTest.mouseMove(view.viewport(), end)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.MiddleButton, pos=end)
    app.processEvents()

    assert (view.horizontalScrollBar().value(), view.verticalScrollBar().value()) != (
        before_x,
        before_y,
    )
    assert view.is_fit_mode() is False
    view.close()
