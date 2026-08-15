import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tooldrawer_studio.calibration.service import PixelPoint
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


def test_set_points_fills_draggable_markers():
    app = _app()
    view = CalibrationImageView()
    view.resize(500, 250)
    view.set_image_bytes(_image_bytes())
    view.set_required_points(4)
    view.set_points(
        (
            PixelPoint(100.0, 80.0),
            PixelPoint(800.0, 80.0),
            PixelPoint(800.0, 400.0),
            PixelPoint(100.0, 400.0),
        )
    )
    view.show()
    app.processEvents()

    points = view.points_px()
    assert len(points) == 4
    assert points[0].x_px == pytest.approx(100.0, abs=1.0)
    view.close()
