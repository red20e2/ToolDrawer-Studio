import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tooldrawer_studio.measurement.models import ImagePoint
from tooldrawer_studio.ui.measurement_view import MeasurementImageView


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _png_bytes(width: int = 200, height: int = 100) -> bytes:
    pixels = np.full((height, width, 3), 245, dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    return encoded.tobytes()


def test_overlay_preserves_source_pixel_endpoints():
    app = _app()
    view = MeasurementImageView()
    view.resize(500, 250)
    view.set_image_bytes(_png_bytes())
    view.set_overlay(
        [
            ImagePoint(20, 20),
            ImagePoint(180, 20),
            ImagePoint(180, 80),
            ImagePoint(20, 80),
        ],
        ImagePoint(50, 30),
        ImagePoint(50, 70),
    )
    view.show()
    app.processEvents()

    endpoints = view.endpoints_px()
    assert endpoints == (ImagePoint(50, 30), ImagePoint(50, 70))
    view.close()


def test_manual_two_point_mode_works_without_automatic_overlay():
    app = _app()
    view = MeasurementImageView()
    view.resize(500, 250)
    view.set_image_bytes(_png_bytes())
    view.set_manual_point_mode(True)
    emitted: list[tuple[ImagePoint, ImagePoint]] = []
    view.endpointsChanged.connect(emitted.append)
    view.show()
    app.processEvents()

    first = view.mapFromScene(QPointF(40.0, 25.0))
    second = view.mapFromScene(QPointF(40.0, 75.0))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=first)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=second)
    app.processEvents()

    endpoints = view.endpoints_px()
    assert len(endpoints) == 2
    assert endpoints[0].x_px == pytest.approx(40.0, abs=2.0)
    assert endpoints[0].y_px == pytest.approx(25.0, abs=2.0)
    assert endpoints[1].x_px == pytest.approx(40.0, abs=2.0)
    assert endpoints[1].y_px == pytest.approx(75.0, abs=2.0)
    assert emitted[-1] == endpoints

    third = view.mapFromScene(QPointF(100.0, 50.0))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=third)
    app.processEvents()
    restarted = view.endpoints_px()
    assert len(restarted) == 1
    assert restarted[0].x_px == pytest.approx(100.0, abs=2.0)
    view.close()


def test_moving_handle_clamps_to_image_and_emits_updated_pair():
    app = _app()
    view = MeasurementImageView()
    view.resize(500, 250)
    view.set_image_bytes(_png_bytes())
    view.set_overlay([], ImagePoint(20, 20), ImagePoint(100, 80))
    emitted: list[tuple[ImagePoint, ImagePoint]] = []
    view.endpointsChanged.connect(emitted.append)
    view.show()
    app.processEvents()

    view._endpoint_handles[0].setPos(QPointF(-50.0, -25.0))
    app.processEvents()

    endpoints = view.endpoints_px()
    assert endpoints[0] == ImagePoint(0.0, 0.0)
    assert emitted[-1] == endpoints
    view.close()


def test_clear_measurement_removes_endpoints_and_silhouette():
    view = MeasurementImageView()
    view.set_image_bytes(_png_bytes())
    view.set_overlay(
        [ImagePoint(10, 10), ImagePoint(190, 10), ImagePoint(190, 90)],
        ImagePoint(20, 20),
        ImagePoint(20, 80),
    )

    view.clear_measurement()

    assert view.endpoints_px() == ()
    assert view._silhouette_item is None
    view.close()
